"""Detect NOAA HYSPLIT and write a trajectory CONTROL file.

The trajectory CONTROL layout matches the public pysplit writer, which
follows NOAA's trajectory CONTROL. This module does not claim to run a
concentration forecast: the unregistered Linux build disables dispersion
on forecast meteorology, and no HYSPLIT executable is available here.
"""

from __future__ import annotations

import os
import subprocess
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
        proc = subprocess.run(
            [str(path)],
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
