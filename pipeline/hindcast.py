"""Post-event HYSPLIT concentration and deposition on archived ARL meteorology.

The public build can run dispersion on archived files. Output kept for the
dashboard is a percent of the peak in that field. Raw model values are not
written into the archive.
"""

from __future__ import annotations

import argparse
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from pipeline.arl import download, list_archive_names, select_archive
from pipeline.config import (
    GRID_DLAT,
    GRID_DLON,
    GRID_LAT_MIN,
    GRID_LON_MIN,
    GRID_NLAT,
    GRID_NLON,
    HYSPLIT_HINDCAST_LABEL,
    SIM_HOURS,
    SOURCE_LAT,
    SOURCE_LON,
)
from pipeline.encoding import pack_u8
from pipeline.grid import Grid
from pipeline.hysplit import (
    locate_executables,
    parse_hysplit_columns,
    run_executable,
    write_concentration_control,
)
from pipeline.hysplit_traj import release_times
from pipeline.timeutil import iso, stamp


def normalize(values: np.ndarray) -> np.ndarray:
    """Map a field onto 0–100 by its own peak. A zero peak stays zero."""
    finite = np.where(np.isfinite(values), values, 0.0)
    finite = np.maximum(finite, 0.0)
    peak = float(finite.max()) if finite.size else 0.0
    if peak <= 0.0:
        return np.zeros(finite.shape, dtype=np.uint8)
    scaled = np.clip(np.rint(100.0 * finite / peak), 0, 100)
    return scaled.astype(np.uint8)


def accumulate(points: list[tuple[float, float, float]], grid: Grid) -> np.ndarray:
    field = np.zeros(grid.shape, dtype=np.float64)
    for lat, lon, value in points:
        if value <= 0:
            continue
        i, j = grid.index(lat, lon)
        i = int(i)
        j = int(j)
        if 0 <= i < grid.nlat and 0 <= j < grid.nlon:
            field[i, j] = max(field[i, j], float(value))
    return field


def _product(reason: str, *, real: bool, met: dict | None = None, grid: dict | None = None) -> dict:
    return {
        "label": HYSPLIT_HINDCAST_LABEL,
        "real_hysplit": real,
        "generated_at": iso(datetime.now(timezone.utc)),
        "generated_at_chicago": stamp(datetime.now(timezone.utc)),
        "note": (
            "post-event hindcast from NOAA HYSPLIT on archived ARL meteorology. "
            "The release mass is unknown, so the map is a percent of the peak in this run. "
            "It is not a concentration, not a deposition amount, and not a measurement of lead. "
            "It is separate from the screening footprint and from official advisories."
        ),
        "reason": reason,
        "met": met,
        "grid": grid,
    }


def build_hindcast(met_dir: Path | None = None) -> dict:
    tools = locate_executables()
    executable = tools.get("hycs_std")
    converter = tools.get("con2asc")
    if executable is None or converter is None:
        return _product("hycs_std or con2asc is not available.", real=False)
    start = release_times()[0]
    end = release_times()[-1] + timedelta(hours=SIM_HOURS)
    try:
        choice = select_archive(list_archive_names(), start, end)
    except Exception as exc:  # noqa: BLE001
        return _product(str(exc), real=False)
    directory = Path(met_dir or "data/arl")
    local_files = [download(item, directory) for item in choice.files]
    text, _same = _run_concentration(executable, converter, start, end, local_files)
    columns = parse_hysplit_columns(text)
    air_points: list[tuple[float, float, float]] = []
    dep_points: list[tuple[float, float, float]] = []
    for name, points in columns.items():
        if name.endswith("00000"):
            dep_points.extend(points)
        else:
            air_points.extend(points)
    grid = Grid()
    air = normalize(accumulate(air_points, grid))
    deposition = normalize(accumulate(dep_points, grid))
    return _product(
        "",
        real=True,
        met={
            "model": choice.model,
            "cycle": choice.cycle,
            "files": [item.name for item in choice.files],
            "urls": [item.url for item in choice.files],
            "valid_start": choice.valid_start,
            "valid_end": choice.valid_end,
            "source": "NOAA ARL archive (HRRR or NAM12).",
        },
        grid={
            **grid.as_dict(),
            "relative_air": pack_u8(air),
            "relative_deposition": pack_u8(deposition),
            "scale": "percent of the peak in this run",
        },
    )


def _run_concentration(executable: Path, converter: Path, start: datetime, end: datetime, local_files: list[Path]):
    hours = max(1, int(round((end - start).total_seconds() / 3600.0)))
    grid = Grid()
    center_lat = (grid.lat_min + grid.lat_max) / 2.0
    center_lon = (grid.lon_min + grid.lon_max) / 2.0
    root = executable.resolve().parent.parent
    if not (root / "bdyfiles").is_dir():
        raise RuntimeError(f"HYSPLIT bdyfiles directory is missing next to {executable}")
    work = Path(tempfile.mkdtemp(prefix="job-", dir=root))
    try:
        return _concentration_in(executable, converter, work, start, end, local_files, hours, center_lat, center_lon)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _concentration_in(executable, converter, work: Path, start: datetime, end: datetime, local_files, hours: int, center_lat: float, center_lon: float):
        met_dir = work / "met"
        met_dir.mkdir()
        names = []
        for item in local_files:
            destination = met_dir / item.name
            destination.symlink_to(item.resolve())
            names.append(item.name)
        write_concentration_control(
            work / "CONTROL",
            when=start,
            lat=SOURCE_LAT,
            lon=SOURCE_LON,
            height_m=50.0,
            hours=hours,
            emit_hours=1.0,
            met_dir=str(met_dir),
            met_files=names,
            center_lat=center_lat,
            center_lon=center_lon,
            spacing=GRID_DLAT,
            span_lat=GRID_NLAT * GRID_DLAT,
            span_lon=GRID_NLON * GRID_DLON,
        )
        (work / "SETUP.CFG").write_text("&SETUP\ninitd = 4,\nnumpar = 2000,\nmaxpar = 10000,\nkhmax = 9999,\n/\n")
        completed = run_executable(executable, work, timeout=3600)
        if not (work / "cdump").exists():
            excerpt = f"{completed.stdout}\n{completed.stderr}"[-500:]
            raise RuntimeError(f"hycs_std exit {completed.returncode}: {excerpt}")
        air = _con2asc(converter, work, "-icdump", "-oconc", "-z")
        text = _ascii_from(work, "conc")
        if not text:
            raise RuntimeError(f"con2asc produced no concentration text: {air.stdout[-300:]} {air.stderr[-300:]}")
        return text, text


def _con2asc(converter: Path, work: Path, *args: str):
    import os
    import subprocess

    env = os.environ.copy()
    env["PATH"] = str(converter.parent) + os.pathsep + env.get("PATH", "")
    return subprocess.run(
        [str(converter), *args],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def _ascii_from(work: Path, stem: str) -> str:
    chunks = []
    for path in sorted(work.iterdir()):
        if not path.is_file() or path.name == "cdump":
            continue
        if not path.name.lower().startswith(stem.lower()):
            continue
        try:
            chunks.append(path.read_text(errors="replace"))
        except OSError:
            continue
    return "\n".join(chunks)


def publish_hindcast(out_dir: Path, product: dict) -> Path | None:
    if not product.get("real_hysplit"):
        print(product.get("reason") or "Hindcast not written.")
        return None
    out_dir = Path(out_dir)
    run_id = datetime.now(timezone.utc).strftime("hindcast-%Y%m%dT%H%M%SZ")
    product = {**product, "id": run_id}
    dest = out_dir / run_id
    dest.mkdir(parents=True, exist_ok=True)
    import json

    text = json.dumps(product, indent=2) + "\n"
    (dest / "hindcast.json").write_text(text)
    (out_dir / "latest.json").write_text(text)
    index_path = out_dir / "index.json"
    if index_path.exists():
        index = json.loads(index_path.read_text())
    else:
        index = {"runs": []}
    index["runs"] = [item for item in index.get("runs", []) if item.get("id") != run_id]
    index["runs"].append(
        {
            "id": run_id,
            "generated_at_chicago": product.get("generated_at_chicago"),
            "label": product.get("label"),
            "met": (product.get("met") or {}).get("model"),
        }
    )
    index_path.write_text(json.dumps(index, indent=2) + "\n")
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Archive one post-event HYSPLIT hindcast.")
    parser.add_argument("--out", default="web/public/hindcast")
    args = parser.parse_args(argv)
    today = datetime.now(timezone.utc).date()
    if not (datetime(2026, 11, 24, tzinfo=timezone.utc).date() <= today <= datetime(2026, 11, 27, tzinfo=timezone.utc).date()):
        print("Hindcast runs 24–27 Nov 2026, after archived meteorology for Nov 23 can exist.")
        return 0
    product = build_hindcast()
    dest = publish_hindcast(Path(args.out), product)
    if dest is None:
        print(product["reason"])
        return 0
    print(f"Archived hindcast → {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
