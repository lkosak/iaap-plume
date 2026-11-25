"""Detect NOAA HYSPLIT and write CONTROL files.

The public unregistered Linux build runs trajectories on forecast
meteorology. Dispersion on forecast meteorology is disabled. Dispersion
on archived meteorology is allowed. The screening footprint stays
NOT HYSPLIT either way.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def check_hysplit(env: dict | None = None) -> dict:
    source = env if env is not None else os.environ
    exe = (source.get("HYSPLIT_EXEC") or "").strip()
    result = {
        "executable": exe or None,
        "ran": False,
        "forecast_dispersion": False,
        "reason": "",
    }
    if not exe:
        result["reason"] = (
            "HYSPLIT_EXEC is not set. The public unregistered Linux build "
            "also disables dispersion when the meteorology is a forecast. "
            "See docs/HYSPLIT.md."
        )
        return result
    path = Path(exe)
    if not path.is_file():
        result["reason"] = f"HYSPLIT_EXEC is not a file: {exe}"
        return result
    if not os.access(path, os.X_OK):
        result["reason"] = f"HYSPLIT_EXEC is not executable: {exe}"
        return result
    try:
        with tempfile.TemporaryDirectory(prefix="hysplit-probe-") as temporary:
            proc = subprocess.run(
                [str(path)],
                cwd=temporary,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
    except (OSError, subprocess.TimeoutExpired) as exc:
        result["reason"] = f"Could not run HYSPLIT_EXEC: {exc}"
        return result
    blob = f"{proc.stdout or ''}\n{proc.stderr or ''}"
    result["ran"] = True
    result["returncode"] = proc.returncode
    result["output_excerpt"] = blob[:500]
    lowered = blob.lower()
    if "forecast" in lowered and any(token in lowered for token in ("not", "disable", "unregistered", "will not")):
        result["reason"] = "The executable reported that forecast dispersion is unavailable."
        return result
    result["reason"] = (
        "An executable is present, but this pipeline still publishes the "
        "screening ensemble. A registered build and ARL forecast files are "
        "required before any map can be labeled HYSPLIT. See docs/HYSPLIT.md."
    )
    return result


def write_trajectory_control(
    path: Path,
    *,
    year: int,
    month: int,
    day: int,
    hour: int,
    lat: float,
    lon: float,
    height_m: float,
    hours: int,
    met_dir: str,
    met_files: list[str],
    output_name: str = "tdump",
) -> None:
    """Write a HYSPLIT trajectory CONTROL file.

    Line order matches ``pysplit`` ``_populate_control``: start time, one
    location, runtime hours, vertical motion 0 (use the data), model top
    10000 m, meteorology directory/file pairs, output directory, output name.
    """
    if not met_files:
        raise ValueError("at least one meteorology file is required")
    directory = met_dir.rstrip("/")
    lines = [
        f"{year % 100:02d} {month:02d} {day:02d} {hour:02d}",
        "1",
        f"{lat} {lon} {height_m}",
        str(hours),
        "0",
        "10000.0",
        str(len(met_files)),
    ]
    for name in met_files:
        lines.append(f"{directory}/")
        lines.append(name)
    lines.append("./")
    lines.append(output_name)
    path.write_text("\n".join(lines) + "\n")


def locate_executables(env: dict | None = None) -> dict[str, Path | None]:
    """Resolve hyts_std, hycs_std, and con2asc from HYSPLIT_EXEC or HYSPLIT_HOME."""
    source = env if env is not None else os.environ
    raw = (source.get("HYSPLIT_EXEC") or source.get("HYSPLIT_HOME") or "").strip()
    found = {"hyts_std": None, "hycs_std": None, "con2asc": None}
    if not raw:
        return found
    path = Path(raw)
    directories = []
    if path.is_dir():
        directories.append(path)
        directories.append(path / "exec")
    else:
        directories.append(path.parent)
    for directory in directories:
        for name in found:
            candidate = directory / name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                found[name] = candidate
    if path.is_file() and os.access(path, os.X_OK) and path.name in found:
        found[path.name] = path
    return found


def write_multi_trajectory_control(
    path: Path,
    *,
    when: datetime,
    points: list[tuple[float, float, float]],
    hours: int,
    met_dir: str,
    met_files: list[str],
    output_name: str = "tdump",
) -> None:
    """One start time, several heights. Vertical motion 0 uses the met field (3D)."""
    if not points:
        raise ValueError("at least one starting point is required")
    if not met_files:
        raise ValueError("at least one meteorology file is required")
    moment = when.astimezone(timezone.utc)
    directory = met_dir.rstrip("/")
    lines = [
        f"{moment.year % 100:02d} {moment.month:02d} {moment.day:02d} {moment.hour:02d}",
        str(len(points)),
    ]
    for lat, lon, height in points:
        lines.append(f"{lat} {lon} {height}")
    lines.extend([str(hours), "0", "10000.0", str(len(met_files))])
    for name in met_files:
        lines.append(f"{directory}/")
        lines.append(name)
    lines.append("./")
    lines.append(output_name)
    path.write_text("\n".join(lines) + "\n")


def write_concentration_control(
    path: Path,
    *,
    when: datetime,
    lat: float,
    lon: float,
    height_m: float,
    hours: int,
    emit_hours: float,
    met_dir: str,
    met_files: list[str],
    center_lat: float,
    center_lon: float,
    spacing: float,
    span_lat: float,
    span_lon: float,
    level_m: float = 100.0,
    output_name: str = "cdump",
) -> None:
    """Unit-rate concentration CONTROL. The rate is 1 per hour, not a lead inventory.

    Line order follows the NOAA concentration tutorial. Deposition uses a
    10 µm sphere at 2.5 g/cm³ so a relative deposit field can be normalized.
    Those particle numbers are an assumption, not a measurement.
    """
    if not met_files:
        raise ValueError("at least one meteorology file is required")
    moment = when.astimezone(timezone.utc)
    directory = met_dir.rstrip("/")
    lines = [
        f"{moment.year % 100:02d} {moment.month:02d} {moment.day:02d} {moment.hour:02d}",
        "1",
        f"{lat} {lon} {height_m}",
        str(hours),
        "0",
        "10000.0",
        str(len(met_files)),
    ]
    for name in met_files:
        lines.append(f"{directory}/")
        lines.append(name)
    lines.extend(
        [
            "1",
            "REL",
            "1.0",
            f"{emit_hours}",
            f"{moment.year % 100:02d} {moment.month:02d} {moment.day:02d} {moment.hour:02d} 00",
            "1",
            f"{center_lat} {center_lon}",
            f"{spacing} {spacing}",
            f"{span_lat} {span_lon}",
            "./",
            output_name,
            "2",
            f"0 {level_m}",
            f"{moment.year % 100:02d} {moment.month:02d} {moment.day:02d} {moment.hour:02d} 00",
            "99 99 99 99 99",
            "00 01 00",
            "1",
            "10.0 2.5 1.0",
            "0.0 0.0 0.0 0.0 0.0",
            "0.0 0.0 0.0",
            "0.0",
            "0.0",
        ]
    )
    path.write_text("\n".join(lines) + "\n")


def parse_tdump(text: str) -> list[dict]:
    """Group HYSPLIT tdump data lines by trajectory number.

    A data line has at least 12 fields: trajectory, grid, year, month, day,
    hour, minute, forecast hour, age, latitude, longitude, height.
    """
    grouped: dict[int, list[dict]] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 12:
            continue
        try:
            traj = int(parts[0])
            year = int(parts[2])
            month = int(parts[3])
            day = int(parts[4])
            hour = int(parts[5])
            minute = int(parts[6])
            age = float(parts[8])
            lat = float(parts[9])
            lon = float(parts[10])
            height = float(parts[11])
        except ValueError:
            continue
        if not (1 <= month <= 12 and 1 <= day <= 31 and 0 <= hour <= 23 and 0 <= minute <= 59):
            continue
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            continue
        if year < 100:
            year += 2000 if year < 70 else 1900
        when = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
        grouped.setdefault(traj, []).append(
            {
                "time": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "age_h": age,
                "lat": lat,
                "lon": lon,
                "height_m": height,
            }
        )
    return [{"number": number, "points": points} for number, points in sorted(grouped.items())]


def parse_concentration_ascii(text: str) -> list[tuple[float, float, float]]:
    """Lat/lon/value points from triplets or from con2asc columns.

    con2asc writes ``DAY HR LAT LON <species><level>`` and one row per grid
    point. A level ending in 00000 is deposition; other levels are airborne.
    This helper returns the airborne column (the last column when both exist).
    """
    columns = parse_hysplit_columns(text)
    air = [name for name in columns if not name.endswith("00000")]
    if air:
        return columns[air[-1]]
    if columns:
        return next(iter(columns.values()))
    return _parse_grid_block(text)


def parse_hysplit_columns(text: str) -> dict[str, list[tuple[float, float, float]]]:
    """Split a con2asc file into named columns of (lat, lon, value)."""
    header: list[str] | None = None
    columns: dict[str, list[tuple[float, float, float]]] = {}
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0].upper() == "DAY" and "LAT" in {item.upper() for item in parts}:
            # DAY HR LAT LON then one name per value column
            lat_at = next(i for i, item in enumerate(parts) if item.upper() == "LAT")
            header = parts[lat_at + 2 :]
            for name in header:
                columns.setdefault(name, [])
            continue
        if header and len(parts) >= 4 + len(header):
            try:
                lat = float(parts[2])
                lon = float(parts[3])
                values = [float(item) for item in parts[4 : 4 + len(header)]]
            except ValueError:
                continue
            if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
                continue
            for name, value in zip(header, values):
                columns[name].append((lat, lon, value))
            continue
        if len(parts) == 3:
            try:
                lat, lon, value = float(parts[0]), float(parts[1]), float(parts[2])
            except ValueError:
                continue
            if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
                columns.setdefault("value", []).append((lat, lon, value))
    return columns


def _parse_triplets(text: str) -> list[tuple[float, float, float]]:
    found = []
    for line in text.splitlines():
        if line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 3:
            continue
        try:
            lat, lon, value = float(parts[0]), float(parts[1]), float(parts[2])
        except ValueError:
            continue
        if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
            found.append((lat, lon, value))
    return found


def _parse_grid_block(text: str) -> list[tuple[float, float, float]]:
    """A block that states center, spacing, and grid size, then the values."""
    numbers = [float(item) for item in re.findall(r"[-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?", text)]
    # Look for center_lat, center_lon, dlat, dlon, nlat, nlon as six consecutive values
    # with nlat and nlon small integers and deltas between 0.001 and 5 degrees.
    for index in range(0, max(0, len(numbers) - 6)):
        lat, lon, dlat, dlon, nlat_f, nlon_f = numbers[index : index + 6]
        nlat, nlon = int(nlat_f), int(nlon_f)
        if nlat < 2 or nlon < 2 or nlat > 400 or nlon > 400:
            continue
        if abs(nlat - nlat_f) > 1e-6 or abs(nlon - nlon_f) > 1e-6:
            continue
        if not (0.001 <= abs(dlat) <= 5 and 0.001 <= abs(dlon) <= 5):
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        count = nlat * nlon
        values = numbers[index + 6 : index + 6 + count]
        if len(values) < count:
            continue
        lat0 = lat - (nlat - 1) * dlat / 2.0
        lon0 = lon - (nlon - 1) * dlon / 2.0
        points = []
        for row in range(nlat):
            for col in range(nlon):
                points.append((lat0 + row * dlat, lon0 + col * dlon, values[row * nlon + col]))
        return points
    return []


def run_executable(executable: Path, workdir: Path, timeout: int) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PATH"] = str(executable.parent) + os.pathsep + env.get("PATH", "")
    return subprocess.run(
        [str(executable)],
        cwd=workdir,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
