"""HYSPLIT trajectory ensemble on ARL forecast meteorology.

The screening footprint is not modified. A missing executable or a forecast
that does not cover the base day is recorded, and the snapshot still archives.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from pipeline.arl import download, list_forecast, select_forecast
from pipeline.config import (
    EVENT_DATE,
    HYSPLIT_HEIGHTS_M,
    HYSPLIT_RELEASE_HOURS_CT,
    HYSPLIT_TRAJECTORY_LABEL,
    RELEASE_DATES,
    SIM_HOURS,
    SOURCE_LAT,
    SOURCE_LON,
)
from pipeline.hysplit import locate_executables, parse_tdump, run_executable, write_multi_trajectory_control
from pipeline.timeutil import iso, stamp

CHI = ZoneInfo("America/Chicago")
# Five release times. Each hyts_std call has to finish inside this, and the
# whole set has to finish inside the budget, or the layer is marked unavailable.
TRAJECTORY_TIMEOUT_SECONDS = 90
TRAJECTORY_BUDGET_SECONDS = 900
EXTRA_DAYS = RELEASE_DATES[1:]


def release_times(day=None) -> list[datetime]:
    when = day or EVENT_DATE
    times = []
    for hour in HYSPLIT_RELEASE_HOURS_CT:
        local = datetime(when.year, when.month, when.day, hour, tzinfo=CHI)
        times.append(local.astimezone(timezone.utc))
    return times


def trajectory_window() -> tuple[datetime, datetime]:
    times = release_times()
    return times[0], times[-1] + timedelta(hours=SIM_HOURS)


def empty_product(reason: str, skipped: list[dict] | None = None) -> dict:
    return {
        "label": HYSPLIT_TRAJECTORY_LABEL,
        "real_hysplit": False,
        "forecast_dispersion": False,
        "note": (
            "NOAA HYSPLIT trajectories were not produced for this archive entry. "
            "The colored footprint is still the screening ensemble, labeled NOT HYSPLIT. "
            + reason
        ),
        "status": "unavailable",
        "reason": reason,
        "met": None,
        "skipped": skipped or [],
        "trajectories": [],
    }


def build_trajectories(
    met_dir: Path | None = None,
    *,
    now: datetime | None = None,
    priority: tuple[str, ...] | None = None,
    max_bytes: int | None = None,
    deadline_seconds: int | None = None,
    need_start: datetime | None = None,
    need_end: datetime | None = None,
) -> dict:
    if os.environ.get("SKIP_HYSPLIT") == "1":
        return empty_product(
            "unavailable: this ensemble run does not download HYSPLIT meteorology. "
            "A separate workflow attaches trajectories when they are ready."
        )
    tools = locate_executables()
    executable = tools.get("hyts_std")
    if executable is None:
        return empty_product("unavailable: HYSPLIT_EXEC is not set, so hyts_std was not run.")
    moment = now or datetime.now(timezone.utc)
    days = [moment.date() - timedelta(days=offset) for offset in range(0, 4)]
    if need_start is None or need_end is None:
        need_start, need_end = trajectory_window()
    try:
        choice = select_forecast(
            list_forecast(days),
            need_start,
            need_end,
            **({"priority": priority} if priority is not None else {}),
        )
    except Exception as exc:  # noqa: BLE001 — the screening run must still archive
        return empty_product(f"unavailable: {exc}")
    directory = Path(met_dir or "data/arl")
    local_files = []
    try:
        for item in choice.files:
            kwargs = {}
            if max_bytes is not None:
                kwargs["max_bytes"] = max_bytes
            if deadline_seconds is not None:
                kwargs["deadline_seconds"] = deadline_seconds
            local_files.append(download(item, directory, **kwargs))
    except Exception as exc:  # noqa: BLE001
        return empty_product(
            f"unavailable: Could not download {choice.model} meteorology: {exc}",
            choice.skipped,
        )
    trajectories = []
    errors = []
    started = time.monotonic()
    for when in release_times():
        if time.monotonic() - started > TRAJECTORY_BUDGET_SECONDS:
            return empty_product(
                "unavailable: HYSPLIT exceeded its runtime budget. "
                "The screening ensemble was still published.",
                choice.skipped,
            )
        points = [(SOURCE_LAT, SOURCE_LON, float(height)) for height in HYSPLIT_HEIGHTS_M]
        try:
            parsed = _run_one(executable, when, points, local_files)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{stamp(when)}: {exc}")
            continue
        for height, track in zip(HYSPLIT_HEIGHTS_M, parsed):
            trajectories.append(
                {
                    "height_m_agl": height,
                    "release_utc": iso(when),
                    "release_chicago": stamp(when),
                    "release_day": EVENT_DATE.isoformat(),
                    "points": track["points"],
                }
            )
    valid_end = datetime.fromisoformat(choice.valid_end)
    extra_tracks: dict[str, list[dict]] = {}
    extra_reasons: dict[str, str] = {}
    covered: list[str] = ["Wednesday"]
    for day in EXTRA_DAYS:
        name = day.strftime("%A")
        tracks_for_day: list[dict] = []
        reason = ""
        need = release_times(day)[-1] + timedelta(hours=SIM_HOURS)
        if valid_end < need:
            reason = (
                f"Forecast meteorology ends {choice.valid_end}, before {name}'s trajectories "
                f"would finish ({iso(need)}). This HYSPLIT layer covers {' and '.join(covered)} only."
            )
        elif time.monotonic() - started > TRAJECTORY_BUDGET_SECONDS:
            reason = (
                f"{name} trajectories were not run because the runtime budget was spent "
                f"on {' and '.join(covered)}. This HYSPLIT layer covers {' and '.join(covered)} only."
            )
        else:
            for when in release_times(day):
                if time.monotonic() - started > TRAJECTORY_BUDGET_SECONDS:
                    reason = f"{name} trajectories were cut off by the runtime budget. Part of {name} may be missing."
                    break
                points = [(SOURCE_LAT, SOURCE_LON, float(height)) for height in HYSPLIT_HEIGHTS_M]
                try:
                    parsed = _run_one(executable, when, points, local_files)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{stamp(when)}: {exc}")
                    continue
                for height, track in zip(HYSPLIT_HEIGHTS_M, parsed):
                    tracks_for_day.append(
                        {
                            "height_m_agl": height,
                            "release_utc": iso(when),
                            "release_chicago": stamp(when),
                            "release_day": day.isoformat(),
                            "points": track["points"],
                        }
                    )
            if not tracks_for_day and not reason:
                reason = f"hyts_std did not return {name} trajectories. This HYSPLIT layer covers {' and '.join(covered)} only."
        extra_tracks[day.isoformat()] = tracks_for_day
        extra_reasons[day.isoformat()] = reason
        if tracks_for_day:
            covered.append(name)
    if not trajectories:
        return empty_product(
            "hyts_std did not return trajectories. " + "; ".join(errors),
            choice.skipped,
        )
    return {
        "label": HYSPLIT_TRAJECTORY_LABEL,
        "real_hysplit": True,
        "forecast_dispersion": False,
        "note": (
            "These paths are NOAA HYSPLIT 3D trajectories on ARL forecast meteorology. "
            "They are not concentrations and not measurements of lead. "
            "The colored footprint on the other layers is a separate screening ensemble labeled NOT HYSPLIT. "
            "The public unregistered build does not run dispersion on forecast meteorology."
        ),
        "status": "ok",
        "reason": "",
        "met": {
            "model": choice.model,
            "cycle": choice.cycle,
            "files": [item.name for item in choice.files],
            "urls": [item.url for item in choice.files],
            "valid_start": choice.valid_start,
            "valid_end": choice.valid_end,
            "retrieved_at": iso(moment),
            "source": "NOAA ARL forecast files (ftp://ftp.arl.noaa.gov/forecast/ via https://www.ready.noaa.gov/data/forecast/).",
        },
        "skipped": choice.skipped,
        "trajectories": trajectories
        + [track for day in EXTRA_DAYS for track in extra_tracks[day.isoformat()]],
        "by_day": {
            EVENT_DATE.isoformat(): {"real_hysplit": True, "trajectories": trajectories},
            **{
                day.isoformat(): {
                    "real_hysplit": bool(extra_tracks[day.isoformat()]),
                    "reason": extra_reasons[day.isoformat()],
                    "trajectories": extra_tracks[day.isoformat()],
                }
                for day in EXTRA_DAYS
            },
        },
        "errors": errors,
    }


def _job_directory(executable: Path) -> Path:
    """HYSPLIT reads ``../bdyfiles`` from the working directory."""
    root = executable.resolve().parent.parent
    if not (root / "bdyfiles").is_dir():
        raise RuntimeError(f"HYSPLIT bdyfiles directory is missing next to {executable}")
    return Path(tempfile.mkdtemp(prefix="job-", dir=root))


def _run_one(executable: Path, when: datetime, points, local_files: list[Path]) -> list[dict]:
    work = _job_directory(executable)
    try:
        return _run_in(executable, work, when, points, local_files)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _run_in(executable: Path, work: Path, when: datetime, points, local_files: list[Path]) -> list[dict]:
        met_dir = work / "met"
        met_dir.mkdir()
        names = []
        for item in local_files:
            destination = met_dir / item.name
            destination.symlink_to(item.resolve())
            names.append(item.name)
        write_multi_trajectory_control(
            work / "CONTROL",
            when=when,
            points=points,
            hours=SIM_HOURS,
            met_dir=str(met_dir),
            met_files=names,
        )
        (work / "SETUP.CFG").write_text("&SETUP\ntratio = 0.75,\n/\n")
        completed = run_executable(executable, work, timeout=TRAJECTORY_TIMEOUT_SECONDS)
        tdump = work / "tdump"
        if not tdump.exists():
            excerpt = f"{completed.stdout}\n{completed.stderr}"[-500:]
            raise RuntimeError(f"hyts_std exit {completed.returncode}: {excerpt}")
        parsed = parse_tdump(tdump.read_text(errors="replace"))
        if len(parsed) < len(points):
            raise RuntimeError(f"expected {len(points)} trajectories, parsed {len(parsed)}")
        return parsed
