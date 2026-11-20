#!/usr/bin/env python3
"""One-time Nov 9–Dec 7 wind climatology. Not part of the forecast schedule.

Writes web/public/climatology.json from ERA5 (Open-Meteo archive) and a
Burlington ASOS cross-check. Run it by hand when the file should be refreshed.
"""

from __future__ import annotations

import csv
import json
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

LAT = 40.7858
LON = -91.2444
FAIRFIELD_BEARING_DEG = 292.4
TOWARD_FAIRFIELD_FROM_DEG = 112.4
DISTANCE_KM = 65.3
CALM_MS = 1.0
# 1 m/s is about 1.94 knots. METAR speeds are whole knots, so under 2 knots
# is the same calm cut as under 1 m/s.
CALM_KT = 2.0
DAY_HOURS = ("16", "17", "18", "19", "20")
SECTORS = (
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
)
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "public" / "climatology.json"
USER_AGENT = "IAAAPIndependentScreening/1.0 (climatology, not a forecast)"


def angle_difference(left: float, right: float) -> float:
    span = abs(left - right) % 360.0
    return min(span, 360.0 - span)


def sector_index(direction_deg: float) -> int:
    return int((direction_deg + 11.25) % 360.0 / 22.5)


def sector_name(direction_deg: float) -> str:
    return SECTORS[sector_index(direction_deg)]


def _round(value: float) -> float:
    return round(value, 1)


def summarize(samples: list[tuple[str, float, float]], *, calm_below: float) -> dict:
    """samples are (day, speed, direction_from_deg) already limited to the daytime window."""
    usable = [(day, speed, direction) for day, speed, direction in samples if speed is not None and direction is not None]
    count = len(usable)
    calm = [item for item in usable if item[1] < calm_below]
    moving = [item for item in usable if item[1] >= calm_below]
    counts = [0] * 16
    for _day, _speed, direction in moving:
        counts[sector_index(direction)] += 1
    rose = []
    for index, name in enumerate(SECTORS):
        center = index * 22.5
        rose.append(
            {
                "sector": name,
                "from_deg": center,
                "hours": counts[index],
                "pct": _round(100.0 * counts[index] / count) if count else 0.0,
                "toward_fairfield": angle_difference(center, TOWARD_FAIRFIELD_FROM_DEG) < 11.25,
            }
        )
    prevailing = sorted(rose, key=lambda item: (-item["hours"], item["sector"]))
    toward_22 = sum(1 for _d, speed, direction in moving if angle_difference(direction, TOWARD_FAIRFIELD_FROM_DEG) <= 22.5)
    toward_45 = sum(1 for _d, speed, direction in moving if angle_difference(direction, TOWARD_FAIRFIELD_FROM_DEG) <= 45.0)
    by_day: dict[str, list[tuple[float, float]]] = {}
    for day, speed, direction in usable:
        by_day.setdefault(day, []).append((speed, direction))
    complete_days = [items for items in by_day.values() if len(items) >= len(DAY_HOURS)]
    persist_22 = 0
    persist_45 = 0
    for items in complete_days:
        if all(speed >= calm_below and angle_difference(direction, TOWARD_FAIRFIELD_FROM_DEG) <= 22.5 for speed, direction in items):
            persist_22 += 1
        if all(speed >= calm_below and angle_difference(direction, TOWARD_FAIRFIELD_FROM_DEG) <= 45.0 for speed, direction in items):
            persist_45 += 1
    day_count = len(complete_days)
    return {
        "n_hours": count,
        "n_days": day_count,
        "calm_pct": _round(100.0 * len(calm) / count) if count else 0.0,
        "toward_fairfield_22_5_pct": _round(100.0 * toward_22 / count) if count else 0.0,
        "toward_fairfield_45_pct": _round(100.0 * toward_45 / count) if count else 0.0,
        "full_window_22_5_pct_of_days": _round(100.0 * persist_22 / day_count) if day_count else 0.0,
        "full_window_45_pct_of_days": _round(100.0 * persist_45 / day_count) if day_count else 0.0,
        "prevailing": [
            {"sector": item["sector"], "from_deg": item["from_deg"], "pct": item["pct"]}
            for item in prevailing[:3]
        ],
        "rose": rose,
    }


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read()


def fetch_era5() -> list[dict]:
    rows = []
    for year in range(2000, 2026):
        query = urllib.parse.urlencode(
            {
                "latitude": f"{LAT}",
                "longitude": f"{LON}",
                "start_date": f"{year}-11-09",
                "end_date": f"{year}-12-07",
                "hourly": "wind_speed_10m,wind_direction_10m,wind_speed_100m,wind_direction_100m",
                "models": "era5",
                "timezone": "UTC",
                "wind_speed_unit": "ms",
            }
        )
        payload = json.loads(_get("https://archive-api.open-meteo.com/v1/archive?" + query))
        hourly = payload["hourly"]
        for index, stamp in enumerate(hourly["time"]):
            rows.append(
                {
                    "time": stamp,
                    "speed_10m": hourly["wind_speed_10m"][index],
                    "direction_10m": hourly["wind_direction_10m"][index],
                    "speed_100m": hourly["wind_speed_100m"][index],
                    "direction_100m": hourly["wind_direction_100m"][index],
                }
            )
        print(f"era5 {year}: {len(hourly['time'])} hours")
    return rows


def fetch_kbrl() -> list[tuple[str, float, float]]:
    samples = []
    for year in range(2000, 2026):
        url = (
            "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?"
            f"station=KBRL&data=drct&data=sknt&year1={year}&month1=11&day1=9"
            f"&year2={year}&month2=12&day2=7&tz=Etc/UTC&format=onlycomma"
            "&latlon=no&missing=M&trace=T&direct=no&report_type=3"
        )
        text = _get(url).decode("utf-8", "replace")
        for record in csv.DictReader(text.splitlines()):
            if record.get("sknt") in (None, "", "M") or record.get("drct") in (None, "", "M"):
                continue
            stamp = datetime.strptime(record["valid"], "%Y-%m-%d %H:%M")
            if f"{stamp.hour:02d}" not in DAY_HOURS:
                continue
            samples.append((stamp.strftime("%Y-%m-%d"), float(record["sknt"]), float(record["drct"])))
        print(f"kbrl {year}")
    return samples


def daytime(rows: list[dict], speed_key: str, direction_key: str) -> list[tuple[str, float, float]]:
    samples = []
    for row in rows:
        if row["time"][11:13] not in DAY_HOURS:
            continue
        speed = row[speed_key]
        direction = row[direction_key]
        if speed is None or direction is None:
            continue
        samples.append((row["time"][:10], float(speed), float(direction)))
    return samples


def build_document(era5_rows: list[dict], kbrl_samples: list[tuple[str, float, float]]) -> dict:
    ten = summarize(daytime(era5_rows, "speed_10m", "direction_10m"), calm_below=CALM_MS)
    hundred = summarize(daytime(era5_rows, "speed_100m", "direction_100m"), calm_below=CALM_MS)
    kbrl = summarize(kbrl_samples, calm_below=CALM_KT)
    return {
        "title": "Historical wind context (climatology, not a forecast)",
        "kind": "climatology",
        "not_a_forecast": True,
        "source": "Open-Meteo Historical Weather API, ERA5 (archive-api.open-meteo.com, models=era5)",
        "asos_source": "Iowa Environmental Mesonet, Burlington ASOS KBRL routine reports",
        "place": {"name": "Iowa Army Ammunition Plant", "lat": LAT, "lon": LON},
        "fairfield": {
            "bearing_deg": FAIRFIELD_BEARING_DEG,
            "distance_km": DISTANCE_KM,
            "wind_from_deg": TOWARD_FAIRFIELD_FROM_DEG,
        },
        "period": "9 November through 7 December, 2000–2025",
        "window": "10:00 AM–2:00 PM CT, taken as 16:00–20:00 UTC",
        "calm_below_m_s": CALM_MS,
        "note": (
            "Historical reanalysis climatology for this calendar window. "
            "It is not a forecast, not a plume, and not an exposure estimate. "
            "The Monday forecast layers take precedence."
        ),
        "era5_10m": ten,
        "era5_100m": hundred,
        "kbrl": {
            "station": "KBRL",
            "n_hours": kbrl["n_hours"],
            "toward_fairfield_22_5_pct": kbrl["toward_fairfield_22_5_pct"],
            "toward_fairfield_45_pct": kbrl["toward_fairfield_45_pct"],
            "calm_pct": kbrl["calm_pct"],
        },
    }


def main() -> None:
    document = build_document(fetch_era5(), fetch_kbrl())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(document, indent=2) + "\n")
    ten = document["era5_10m"]
    print(
        f"Wrote {OUT}: 10 m toward Fairfield "
        f"{ten['toward_fairfield_22_5_pct']}% / {ten['toward_fairfield_45_pct']}%, "
        f"calm {ten['calm_pct']}%, prevailing {ten['prevailing'][0]['sector']} {ten['prevailing'][0]['pct']}%"
    )


if __name__ == "__main__":
    main()
