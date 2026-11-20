"""ARL-format meteorology from NOAA's forecast and archive servers.

The HTTPS tree at ``https://www.ready.noaa.gov/data/forecast/`` is the same
collection NOAA documents at ``ftp://ftp.arl.noaa.gov/forecast/``. Archive
files are under ``/data/archives/``. This module does not invent files that
the listing does not contain.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

# A 2-hour schedule cannot spend itself on multi-gigabyte ARL files.
# The 1-degree GFS forecast file is about 1.4 GB; HRRR pieces are larger.
MAX_MET_BYTES = 400 * 1024 * 1024
DOWNLOAD_DEADLINE_SECONDS = 90
READ_TIMEOUT_SECONDS = 20

FORECAST_INDEX = "https://www.ready.noaa.gov/data/forecast"
ARCHIVE_HRRR = "https://www.ready.noaa.gov/data/archives/hrrr"
ARCHIVE_NAM12 = "https://www.ready.noaa.gov/data/archives/nam12"
USER_AGENT = "IAAAPIndependentScreening/1.0 (relative footprint dashboard)"

# (regex on the filename, first forecast hour, last forecast hour), inclusive.
_SPLIT = (
    (re.compile(r"^hysplit\.t(\d{2})z\.hrrrf00$"), "HRRR", 0, 5),
    (re.compile(r"^hysplit\.t(\d{2})z\.hrrrf06$"), "HRRR", 6, 11),
    (re.compile(r"^hysplit\.t(\d{2})z\.hrrrf12$"), "HRRR", 12, 17),
    (re.compile(r"^hysplit\.t(\d{2})z\.hrrrf18$"), "HRRR", 18, 18),
    (re.compile(r"^hysplit\.t(\d{2})z\.namf$"), "NAM", 0, 84),
    (re.compile(r"^hysplit\.t(\d{2})z\.namsf$"), "NAM", 0, 48),
    (re.compile(r"^hysplit\.t(\d{2})z\.gfsf$"), "GFS", 0, 240),
)
_HRRR_CHUNK = re.compile(r"^(\d{8})_(\d{2})-(\d{2})_hrrr$")
_NAM12_DAY = re.compile(r"^(\d{8})_nam12$")
_PRIORITY = ("HRRR", "NAM", "GFS")


@dataclass(frozen=True)
class RemoteFile:
    name: str
    day: date
    url: str


@dataclass
class MetChoice:
    model: str
    cycle: str
    valid_start: str
    valid_end: str
    files: list[RemoteFile]
    skipped: list[dict] = field(default_factory=list)


def enforce_met_cap(content_length: int | None, name: str) -> None:
    """Refuse a meteorology file that is larger than the schedule can carry."""
    if content_length is None:
        return
    if content_length > MAX_MET_BYTES:
        raise RuntimeError(
            f"{name} is {content_length} bytes, over the {MAX_MET_BYTES} byte cap. "
            "HYSPLIT met was skipped so the screening ensemble can still publish."
        )


def _get(url: str, timeout: int = 25) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def _links(html: str) -> list[str]:
    return re.findall(r'href="([^"?][^"]*)"', html)


def list_forecast_day(day: date) -> list[RemoteFile]:
    stamp = day.strftime("%Y%m%d")
    url = f"{FORECAST_INDEX}/{stamp}/"
    try:
        html = _get(url).decode("latin1", "replace")
    except Exception as exc:  # noqa: BLE001 — one missing day must not stop the search
        print(f"arl forecast {stamp}: {exc}")
        return []
    found = []
    for name in _links(html):
        name = name.rstrip("/")
        if any(pattern.match(name) for pattern, *_rest in _SPLIT):
            found.append(RemoteFile(name=name, day=day, url=f"{url}{name}"))
    return found


def list_forecast(days: list[date]) -> list[RemoteFile]:
    found: list[RemoteFile] = []
    for day in days:
        found.extend(list_forecast_day(day))
    return found


def _cycle_of(day: date, hour: int) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def select_forecast(files: list[RemoteFile], need_start: datetime, need_end: datetime) -> MetChoice:
    """Pick the newest HRRR cycle that covers the window, else NAM, else GFS."""
    if need_end < need_start:
        raise ValueError("need_end is before need_start")
    grouped: dict[tuple[str, datetime], list[tuple[RemoteFile, int, int]]] = {}
    for item in files:
        for pattern, model, start_h, end_h in _SPLIT:
            match = pattern.match(item.name)
            if not match:
                continue
            cycle = _cycle_of(item.day, int(match.group(1)))
            grouped.setdefault((model, cycle), []).append((item, start_h, end_h))
            break

    skipped: list[dict] = []
    for model in _PRIORITY:
        cycles = sorted((cycle for (name, cycle) in grouped if name == model), reverse=True)
        if not cycles:
            skipped.append({"model": model, "cycle": "", "reason": f"no {model} forecast file was listed"})
            continue
        for cycle in cycles:
            pieces = grouped[(model, cycle)]
            chosen = _covering_pieces(pieces, cycle, need_start, need_end)
            if not chosen:
                continue
            start_hour = min(start_h for _item, start_h, _end in chosen)
            return MetChoice(
                model=model,
                cycle=_iso(cycle),
                valid_start=_iso(cycle + timedelta(hours=start_hour)),
                valid_end=_iso(cycle + timedelta(hours=max(end_h for _item, _s, end_h in chosen))),
                files=[item for item, _s, _e in chosen],
                skipped=skipped,
            )
        newest = cycles[0]
        end_hour = max(end_h for _item, _start, end_h in grouped[(model, newest)])
        skipped.append(
            {
                "model": model,
                "cycle": _iso(newest),
                "reason": (
                    f"newest {model} cycle ends {_iso(newest + timedelta(hours=end_hour))}, "
                    "before the trajectory window ends"
                ),
            }
        )
    raise RuntimeError("no ARL forecast file covers the trajectory window. " + "; ".join(
        f"{item['model']} {item['cycle']}: {item['reason']}" for item in skipped
    ))


def _covering_pieces(pieces, cycle: datetime, need_start: datetime, need_end: datetime):
    start_h = (need_start - cycle).total_seconds() / 3600.0
    end_h = (need_end - cycle).total_seconds() / 3600.0
    if start_h < 0:
        return None
    overlapping = [item for item in pieces if item[2] >= start_h and item[1] <= end_h]
    if not overlapping:
        return None
    ordered = sorted(overlapping, key=lambda item: item[1])
    if ordered[0][1] > start_h or ordered[-1][2] < end_h:
        return None
    for previous, current in zip(ordered, ordered[1:]):
        if current[1] > previous[2] + 1:
            return None
    return ordered


def select_archive(names: list[str], need_start: datetime, need_end: datetime) -> MetChoice:
    """Prefer a NAM12 day file pair. Otherwise the HRRR six-hour chunks that cover the window."""
    nam_days = {}
    hrrr_chunks = []
    for name in names:
        nam = _NAM12_DAY.match(name)
        if nam:
            nam_days[nam.group(1)] = name
        hrrr = _HRRR_CHUNK.match(name)
        if hrrr:
            hrrr_chunks.append((name, hrrr.group(1), int(hrrr.group(2)), int(hrrr.group(3))))

    needed_days = []
    cursor = need_start.astimezone(timezone.utc).date()
    last = need_end.astimezone(timezone.utc).date()
    while cursor <= last:
        needed_days.append(cursor.strftime("%Y%m%d"))
        cursor += timedelta(days=1)
    if needed_days and all(day in nam_days for day in needed_days):
        files = [
            RemoteFile(name=nam_days[day], day=_parse_day(day), url=_nam12_url(day, nam_days[day]))
            for day in needed_days
        ]
        return MetChoice(
            model="NAM12",
            cycle=f"archive {needed_days[0]}–{needed_days[-1]}",
            valid_start=_iso(datetime.strptime(needed_days[0], "%Y%m%d").replace(tzinfo=timezone.utc)),
            valid_end=_iso(datetime.strptime(needed_days[-1], "%Y%m%d").replace(tzinfo=timezone.utc) + timedelta(days=1)),
            files=files,
        )

    want_start = need_start.astimezone(timezone.utc)
    want_end = need_end.astimezone(timezone.utc)
    chosen = []
    for name, day, start_hour, end_hour in hrrr_chunks:
        start = datetime.strptime(day, "%Y%m%d").replace(tzinfo=timezone.utc) + timedelta(hours=start_hour)
        end = datetime.strptime(day, "%Y%m%d").replace(tzinfo=timezone.utc) + timedelta(hours=end_hour, minutes=59)
        if end >= want_start and start <= want_end:
            chosen.append((start, end, RemoteFile(name=name, day=_parse_day(day), url=f"{ARCHIVE_HRRR}/{name}")))
    chosen.sort()
    if chosen and chosen[0][0] <= want_start and chosen[-1][1] >= want_end:
        return MetChoice(
            model="HRRR",
            cycle="archive",
            valid_start=_iso(chosen[0][0]),
            valid_end=_iso(chosen[-1][1]),
            files=[item[2] for item in chosen],
            skipped=[{"model": "NAM12", "cycle": "", "reason": "NAM12 archive did not cover every UTC day in the window"}],
        )
    missing = [day for day in needed_days if day not in nam_days]
    raise RuntimeError(
        "Archived ARL meteorology for the release window is not on the server yet. "
        f"NAM12 missing {', '.join(missing) or 'none'}. "
        f"HRRR chunks listed: {len(hrrr_chunks)}."
    )


def _parse_day(stamp: str) -> date:
    return datetime.strptime(stamp, "%Y%m%d").date()


def _nam12_url(day: str, name: str) -> str:
    year, month = day[:4], day[4:6]
    return f"{ARCHIVE_NAM12}/{year}/{month}/{name}"


def list_archive_names() -> list[str]:
    """Names of recent HRRR chunks and the current year's NAM12 files."""
    names: list[str] = []
    try:
        html = _get(ARCHIVE_HRRR + "/").decode("latin1", "replace")
        names.extend(name for name in _links(html) if _HRRR_CHUNK.match(name.rstrip("/")))
    except Exception as exc:  # noqa: BLE001
        print(f"arl hrrr archive: {exc}")
    year = datetime.now(timezone.utc).year
    for month in range(1, 13):
        url = f"{ARCHIVE_NAM12}/{year}/{month:02d}/"
        try:
            html = _get(url, timeout=40).decode("latin1", "replace")
        except Exception:
            continue
        for name in _links(html):
            name = name.rstrip("/")
            if _NAM12_DAY.match(name):
                names.append(name)
    return names


def download(item: RemoteFile, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    dest = directory / item.name
    if dest.exists() and dest.stat().st_size > MAX_MET_BYTES:
        dest.unlink()
    if dest.exists() and dest.stat().st_size > 0:
        print(f"arl reuse {dest} ({dest.stat().st_size} bytes)", flush=True)
        return dest
    print(f"arl download {item.url}", flush=True)
    request = Request(item.url, headers={"User-Agent": USER_AGENT})
    temporary = dest.with_suffix(dest.suffix + ".partial")
    started = time.monotonic()
    try:
        with urlopen(request, timeout=READ_TIMEOUT_SECONDS) as response, temporary.open("wb") as handle:
            enforce_met_cap(_content_length(response.headers.get("Content-Length")), item.name)
            written = 0
            while True:
                if time.monotonic() - started > DOWNLOAD_DEADLINE_SECONDS:
                    raise RuntimeError(
                        f"{item.name} download exceeded {DOWNLOAD_DEADLINE_SECONDS}s "
                        f"after {written} bytes. HYSPLIT met was skipped."
                    )
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                enforce_met_cap(written, item.name)
                handle.write(chunk)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    temporary.replace(dest)
    print(f"arl saved {dest} ({dest.stat().st_size} bytes)", flush=True)
    return dest


def _content_length(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(value)
