"""Cross meteorology with release assumptions and count member overlap.

The number that goes on the map is how many members put a particle in a
cell, divided by how many members ran. It is not a concentration.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import NamedTuple

import numpy as np

from pipeline.config import (
    DISCLAIMER,
    ENGINE_LABEL,
    ENGINE_NAME,
    ENGINE_SUMMARY,
    ENSEMBLE_SEED,
    EVENT_DATE,
    FAIRFIELD_LAT,
    FAIRFIELD_LON,
    FAIRFIELD_NAME,
    N_PARTICLES,
    PLANNED_RELEASE_HOUR_CT,
    RELEASE_DATES,
    SIM_HOURS,
    SOURCE_BBOX,
    SOURCE_LAT,
    SOURCE_LON,
    SOURCE_NAME,
    TIMEZONE,
    DT_SECONDS,
)
from pipeline.encoding import pack_u16, pack_u8
from pipeline.geo import bearing_deg, cardinal, cardinal_word, haversine_km
from pipeline.grid import Grid
from pipeline.hysplit import check_hysplit
from pipeline.met import MetDataset
from pipeline.model import MemberSpec, Physics, run_member
from pipeline.timeutil import CHI, iso, stamp, utc_now


class Scenario(NamedTuple):
    hour: int
    height_m: float
    diameter_um: float
    density: float
    dep_scale: float
    wet_scale: float
    turb_scale: float
    rotation_deg: float
    speed_factor: float


# Timing for the Thursday and Friday fallback scenarios. Wednesday uses the
# planned release hour for each of these physical parameter combinations.
SCENARIOS = (
    Scenario(10, 20, 2, 2500, 0.5, 0.5, 0.7, 0, 1.00),
    Scenario(11, 200, 10, 8000, 1.2, 1.0, 1.2, 20, 0.85),
    Scenario(12, 60, 25, 8000, 1.5, 1.3, 1.0, -20, 1.15),
    Scenario(12, 300, 2, 3000, 0.6, 0.8, 1.4, 15, 1.05),
    Scenario(13, 30, 8, 6000, 1.0, 1.6, 0.8, -15, 0.90),
    Scenario(14, 150, 2, 2500, 0.4, 1.2, 1.3, 25, 1.20),
)


SENSITIVITY_DIAMETERS_UM = (0.5, 2, 8, 10, 25)
SENSITIVITY_HEIGHTS_M = (20, 30, 60, 150, 200, 300, 500)
SENSITIVITY_DENSITY_KG_M3 = 2500


def fairfield_sensitivity(datasets, *, release_time, hours, seed, n_particles, physics):
    """Compare size and height with fixed source, density and random seed."""
    end = release_time + timedelta(hours=hours)
    usable = [dataset for dataset in datasets if dataset.covers(release_time, end)[0]]
    if not usable:
        return []
    grid = Grid()
    i, j = grid.index_scalar(FAIRFIELD_LAT, FAIRFIELD_LON)
    rows = []
    for height in SENSITIVITY_HEIGHTS_M:
        for diameter in SENSITIVITY_DIAMETERS_UM:
            spec = MemberSpec(
                seed=seed, release_time=release_time, minute_origin=release_time,
                release_lat=SOURCE_LAT, release_lon=SOURCE_LON, height_m=height,
                diameter_m=diameter * 1e-6, density=SENSITIVITY_DENSITY_KG_M3,
                wind_rotation_deg=0, wind_speed_factor=1, dep_scale=1, wet_scale=1,
                turb_scale=1, n_particles=n_particles, hours=hours, dt=DT_SECONDS,
            )
            air = deposition = 0
            for dataset in usable:
                result = run_member(dataset, spec, grid, physics)
                air += int(result["air_dwell"][i, j] > 0)
                deposition += int(result["deposited"][i, j] > 0)
            rows.append({
                "height_m": height, "diameter_um": diameter,
                "air_hits": air, "deposition_hits": deposition, "n_members": len(usable),
            })
    return rows


def schedule_block(official: dict, start: datetime, end: datetime) -> dict:
    """Schedule the ensemble was built around, plus any dates the latest fetch mentioned."""
    mentions = []
    for source in official.get("sources") or []:
        blob = " ".join(
            part for part in (source.get("title"), source.get("excerpt"), source.get("note")) if part
        ).lower()
        flags = []
        if any(token in blob for token in ("november 23", "nov. 23", "nov 23", "monday")):
            flags.append("mentions Monday or Nov 23")
        if any(token in blob for token in ("november 20", "nov. 20", "nov 20", "friday")):
            flags.append("mentions Friday or Nov 20")
        if any(token in blob for token in ("postpon", "delay", "reschedul")):
            flags.append("mentions a schedule change")
        if flags:
            mentions.append(
                {
                    "id": source.get("id"),
                    "publisher": source.get("publisher"),
                    "kind": source.get("kind"),
                    "url": source.get("url"),
                    "status": source.get("status"),
                    "title": source.get("title"),
                    "flags": flags,
                }
            )
    return {
        "change": (
            "Postponed from about noon CT on Friday, Nov 20, 2026. "
            "The planned detonation is Wednesday, Nov 25, 2026 at 9:00 AM CT. "
            "Thursday and Friday are fallback scenarios."
        ),
        "change_basis": (
            "CBS Chicago reported the postponement and attributed it to the Army. "
            "The lines below are whatever the latest page retrieval actually contained. "
            "If they disagree with this sentence, believe the agency page."
        ),
        "ensemble_center_chicago": stamp(release_local(PLANNED_RELEASE_HOUR_CT)),
        "ensemble_window_chicago": f"{stamp(start)} through {stamp(end)}",
        "fetched_mentions": mentions,
    }


def release_local(hour: int, day=None) -> datetime:
    when = day or EVENT_DATE
    return datetime(when.year, when.month, when.day, hour, 0, tzinfo=CHI)


def _day_label(day) -> tuple[str, str]:
    names = {23: ("Monday", "Mon Nov 23"), 24: ("Tuesday", "Tue Nov 24"), 25: ("Wednesday", "Wed Nov 25"), 26: ("Thursday", "Thu Nov 26"), 27: ("Friday", "Fri Nov 27")}
    return names.get(day.day, (day.strftime("%A"), day.isoformat()))


def render_narrative(stats: dict) -> str:
    n = stats["n_members"]
    hits = stats["air_hits"]
    neigh = stats["air_neighbor_hits"]
    distance = stats["distance_km"]
    toward = stats["bearing_word"]
    bearing = stats["bearing_deg"]
    parts = [
        f"Fairfield is {distance:.0f} km {toward} of the installation centroid ({bearing:.0f}°).",
    ]
    if stats["cells_with_air"] <= 0:
        parts.append("No airborne footprint fell inside the map window on this run.")
    else:
        parts.append(
            "The relative airborne footprint on this run lies mostly "
            f"to the {stats['footprint_word']} of the installation centroid."
        )
    if hits <= 0 and neigh <= 0:
        edge = stats["nearest_overlap_km"]
        if edge is None:
            parts.append(
                "No ensemble member placed an airborne particle in the Fairfield cell or the eight cells around it."
            )
        else:
            parts.append(
                "No ensemble member placed an airborne particle in the Fairfield cell or the eight cells around it. "
                f"The nearest cell with any member is about {edge:.0f} km from Fairfield."
            )
    else:
        parts.append(
            f"Airborne overlap in the Fairfield cell: {hits} of {n} ensemble members. "
            f"The highest overlap in that cell or its eight neighbors is {neigh} of {n}."
        )
    parts.append(
        f"Surface-deposition overlap in the Fairfield cell: {stats['deposition_hits']} of {n} members, "
        "using the assumed removal parameters."
    )
    if hits > 0 and stats.get("arrival_earliest_chicago") and stats.get("arrival_latest_chicago"):
        if stats["arrival_earliest_chicago"] == stats["arrival_latest_chicago"]:
            parts.append(
                "Members that reach the Fairfield cell first do so around "
                f"{stats['arrival_earliest_chicago']}."
            )
        else:
            parts.append(
                "First arrival in the Fairfield cell, across members that reach it, runs from "
                f"{stats['arrival_earliest_chicago']} to {stats['arrival_latest_chicago']}."
            )
    if stats["fraction_left_map"] >= 0.15:
        parts.append(
            f"About {stats['fraction_left_map']:.0%} of particles left the map window during the "
            f"{stats['hours']:.0f}-hour simulation, so the drawn footprint is cut off at the border."
        )
    parts.append("Overlap counts model scenarios. It is not a measurement of lead and not a concentration.")
    return " ".join(parts)


def _sparse_cells(air_hits, dep_hits, air_pct, dep_pct, earliest, latest) -> list[dict]:
    occupied = np.nonzero((air_hits > 0) | (dep_hits > 0))
    cells = []
    for i, j in zip(occupied[0].tolist(), occupied[1].tolist()):
        cells.append(
            {
                "i": int(i),
                "j": int(j),
                "air": int(air_hits[i, j]),
                "dep": int(dep_hits[i, j]),
                "air_pct": int(air_pct[i, j]),
                "dep_pct": int(dep_pct[i, j]),
                "earliest": int(earliest[i, j]),
                "latest": int(latest[i, j]),
            }
        )
    return cells


def _simulate_day(
    datasets: list[MetDataset],
    day,
    *,
    scenarios: tuple[Scenario, ...],
    hours: float,
    physics: Physics,
    seed: int,
    n_particles: int,
    fetch_skipped: list[dict],
) -> dict:
    """One day of release scenarios. Models that end too soon are dropped for this day only."""
    weekday, label = _day_label(day)
    window_start = release_local(min(item.hour for item in scenarios), day)
    window_end = release_local(max(item.hour for item in scenarios), day) + timedelta(hours=hours)
    skipped = list(fetch_skipped)
    usable: list[MetDataset] = []
    for dataset in datasets:
        ok, reason = dataset.covers(window_start, window_end)
        if ok:
            usable.append(dataset)
        else:
            skipped.append(
                {
                    "model_id": dataset.model_id,
                    "label": dataset.model_label,
                    "cycle": dataset.cycle,
                    "reason": reason,
                }
            )
    grid = Grid()
    origin = window_start
    empty_grid = {
        **grid.as_dict(),
        "encoding": "sparse",
        "cells": [],
        "arrival_origin": iso(origin),
        "no_arrival": 65535,
        "n_members": 0,
    }
    if not usable:
        return {
            "id": day.isoformat(),
            "label": label,
            "weekday": weekday,
            "date": day.isoformat(),
            "n_members": 0,
            "particles_per_member": n_particles,
            "release_window_chicago": (
                f"{stamp(window_start)} through {stamp(release_local(max(item.hour for item in scenarios), day))}"
            ),
            "narrative": (
                f"No forecast in this run reaches the {label} release window "
                "through the 8 hours after the last release. "
                "Overlap counts are not a measurement of lead and not a concentration."
            ),
            "receptor": {
                "name": FAIRFIELD_NAME,
                "lat": FAIRFIELD_LAT,
                "lon": FAIRFIELD_LON,
                "distance_km": round(float(haversine_km(SOURCE_LAT, SOURCE_LON, FAIRFIELD_LAT, FAIRFIELD_LON)), 1),
                "bearing_deg_from_source": round(bearing_deg(SOURCE_LAT, SOURCE_LON, FAIRFIELD_LAT, FAIRFIELD_LON), 1),
                "bearing_cardinal": cardinal(bearing_deg(SOURCE_LAT, SOURCE_LON, FAIRFIELD_LAT, FAIRFIELD_LON)),
                "bearing_word": cardinal_word(bearing_deg(SOURCE_LAT, SOURCE_LON, FAIRFIELD_LAT, FAIRFIELD_LON)),
                "cell": {"i": 0, "j": 0},
                "air_hits": 0,
                "air_neighbor_hits": 0,
                "deposition_hits": 0,
                "n_members": 0,
                "arrival_earliest_chicago": None,
                "arrival_latest_chicago": None,
                "nearest_overlap_km": None,
            },
            "footprint": {
                "cells_with_air": 0,
                "centroid_lat": None,
                "centroid_lon": None,
                "centroid_bearing_deg": None,
                "direction_word": "nowhere on the map",
                "fraction_particles_left_map": 0.0,
            },
            "used": [],
            "skipped": skipped,
            "members": [],
            "grid": empty_grid,
            "dense": None,
            "covered": False,
        }

    member_rows = []
    results = []
    for dataset in usable:
        for scenario in scenarios:
            index = len(member_rows)
            member_seed = seed + index * 10007
            rng = np.random.default_rng(member_seed)
            south, west, north, east = SOURCE_BBOX
            release_lat = float(rng.uniform(south, north))
            release_lon = float(rng.uniform(west, east))
            release_time = release_local(scenario.hour, day)
            spec = MemberSpec(
                seed=member_seed + 17,
                release_time=release_time,
                minute_origin=origin,
                release_lat=release_lat,
                release_lon=release_lon,
                height_m=scenario.height_m,
                diameter_m=scenario.diameter_um * 1e-6,
                density=scenario.density,
                wind_rotation_deg=scenario.rotation_deg,
                wind_speed_factor=scenario.speed_factor,
                dep_scale=scenario.dep_scale,
                wet_scale=scenario.wet_scale,
                turb_scale=scenario.turb_scale,
                n_particles=n_particles,
                hours=hours,
                dt=DT_SECONDS,
            )
            result = run_member(dataset, spec, grid, physics)
            results.append(result)
            member_rows.append(
                {
                    "id": f"m{index:02d}",
                    "model_id": dataset.model_id,
                    "model_label": dataset.model_label,
                    "cycle": dataset.cycle,
                    "release_local": stamp(release_time),
                    "release_iso": iso(release_time),
                    "height_m": scenario.height_m,
                    "diameter_um": scenario.diameter_um,
                    "density_kg_m3": scenario.density,
                    "wind_rotation_deg": scenario.rotation_deg,
                    "wind_speed_factor": scenario.speed_factor,
                    "dep_scale": scenario.dep_scale,
                    "wet_scale": scenario.wet_scale,
                    "turb_scale": scenario.turb_scale,
                    "source_lat": round(release_lat, 5),
                    "source_lon": round(release_lon, 5),
                    "settling_m_s": result["settling_m_s"],
                    "n_deposited": result["n_deposited"],
                    "n_outside_end": result["n_outside_end"],
                }
            )

    n_members = len(results)
    air_hits = np.zeros(grid.shape, dtype=np.int16)
    dep_hits = np.zeros(grid.shape, dtype=np.int16)
    dwell = np.zeros(grid.shape, dtype=np.float64)
    dep_weight = np.zeros(grid.shape, dtype=np.float64)
    earliest = np.full(grid.shape, 65535, dtype=np.int32)
    latest = np.zeros(grid.shape, dtype=np.int32)
    reached = np.zeros(grid.shape, dtype=bool)
    left = 0
    particles = 0
    for result in results:
        air_hits += (result["air_dwell"] > 0).astype(np.int16)
        dep_hits += (result["deposited"] > 0).astype(np.int16)
        dwell += result["air_dwell"]
        dep_weight += result["deposited"]
        first = result["first_minute"]
        hit = first >= 0
        earliest = np.where(hit, np.minimum(earliest, first), earliest)
        latest = np.where(hit & (first >= latest), first, latest)
        reached |= hit
        left += result["n_outside_end"] + result["n_deposited_outside"]
        particles += result["n_particles"]
    earliest = np.where(reached, earliest, 65535)
    latest = np.where(reached, latest, 65535)

    def norm_pct(weights: np.ndarray) -> np.ndarray:
        peak = float(weights.max()) if weights.size else 0.0
        if peak <= 0:
            return np.zeros(grid.shape, dtype=np.uint8)
        return np.clip(np.rint(100.0 * weights / peak), 0, 100).astype(np.uint8)

    air_pct = norm_pct(dwell)
    dep_pct = norm_pct(dep_weight)
    i_f, j_f = grid.index_scalar(FAIRFIELD_LAT, FAIRFIELD_LON)
    i0, i1 = max(0, i_f - 1), min(grid.nlat, i_f + 2)
    j0, j1 = max(0, j_f - 1), min(grid.nlon, j_f + 2)
    bearing = bearing_deg(SOURCE_LAT, SOURCE_LON, FAIRFIELD_LAT, FAIRFIELD_LON)
    distance = float(haversine_km(SOURCE_LAT, SOURCE_LON, FAIRFIELD_LAT, FAIRFIELD_LON))
    cells = int((air_hits > 0).sum())
    if cells:
        ii, jj = np.nonzero(air_hits > 0)
        lats = grid.lat_min + (ii + 0.5) * grid.dlat
        lons = grid.lon_min + (jj + 0.5) * grid.dlon
        weights = air_hits[ii, jj].astype(float)
        lat_bar = float((weights * lats).sum() / weights.sum())
        lon_bar = float((weights * lons).sum() / weights.sum())
        footprint_bearing = bearing_deg(SOURCE_LAT, SOURCE_LON, lat_bar, lon_bar)
        footprint_word = cardinal_word(footprint_bearing)
        nearest = float(haversine_km(FAIRFIELD_LAT, FAIRFIELD_LON, lats, lons).min())
    else:
        lat_bar = lon_bar = footprint_bearing = None
        footprint_word = "nowhere on the map"
        nearest = None
    air_cell = int(air_hits[i_f, j_f])
    dep_cell = int(dep_hits[i_f, j_f])
    neighbor = int(air_hits[i0:i1, j0:j1].max()) if air_hits.size else 0
    arrival_e = int(earliest[i_f, j_f])
    arrival_l = int(latest[i_f, j_f])
    arrival_e_stamp = None
    arrival_l_stamp = None
    if air_cell > 0 and arrival_e != 65535:
        arrival_e_stamp = stamp(origin + timedelta(minutes=arrival_e))
        arrival_l_stamp = stamp(origin + timedelta(minutes=arrival_l))
    fraction_left = (left / particles) if particles else 0.0
    stats = {
        "n_members": n_members,
        "air_hits": air_cell,
        "air_neighbor_hits": neighbor,
        "deposition_hits": dep_cell,
        "distance_km": distance,
        "bearing_deg": bearing,
        "bearing_word": cardinal_word(bearing),
        "cells_with_air": cells,
        "footprint_word": footprint_word,
        "nearest_overlap_km": nearest,
        "fraction_left_map": fraction_left,
        "hours": hours,
        "arrival_earliest_chicago": arrival_e_stamp,
        "arrival_latest_chicago": arrival_l_stamp,
    }
    used = [
        {
            "model_id": dataset.model_id,
            "label": dataset.model_label,
            "cycle": dataset.cycle,
            "valid_start": dataset.valid_start,
            "valid_end": dataset.valid_end,
            "levels": dataset.level_names,
            "n_stations": int(dataset.lat.size),
            "notes": dataset.notes,
            "request_urls": dataset.request_urls,
        }
        for dataset in usable
    ]
    packed_grid = {
        **grid.as_dict(),
        "encoding": "sparse",
        "cells": _sparse_cells(air_hits, dep_hits, air_pct, dep_pct, earliest, latest),
        "arrival_origin": iso(origin),
        "no_arrival": 65535,
        "n_members": n_members,
    }
    return {
        "id": day.isoformat(),
        "label": label,
        "weekday": weekday,
        "date": day.isoformat(),
        "n_members": n_members,
        "particles_per_member": n_particles,
        "release_window_chicago": (
            f"{stamp(window_start)} through {stamp(release_local(max(item.hour for item in scenarios), day))}"
        ),
        "narrative": render_narrative(stats),
        "receptor": {
            "name": FAIRFIELD_NAME,
            "lat": FAIRFIELD_LAT,
            "lon": FAIRFIELD_LON,
            "distance_km": round(distance, 1),
            "bearing_deg_from_source": round(bearing, 1),
            "bearing_cardinal": cardinal(bearing),
            "bearing_word": cardinal_word(bearing),
            "cell": {"i": i_f, "j": j_f},
            "air_hits": air_cell,
            "air_neighbor_hits": neighbor,
            "deposition_hits": dep_cell,
            "n_members": n_members,
            "arrival_earliest_chicago": arrival_e_stamp,
            "arrival_latest_chicago": arrival_l_stamp,
            "nearest_overlap_km": None if nearest is None else round(nearest, 1),
        },
        "footprint": {
            "cells_with_air": cells,
            "centroid_lat": lat_bar,
            "centroid_lon": lon_bar,
            "centroid_bearing_deg": None if footprint_bearing is None else round(footprint_bearing, 1),
            "direction_word": footprint_word,
            "fraction_particles_left_map": round(fraction_left, 3),
        },
        "used": used,
        "skipped": skipped,
        "members": member_rows,
        "grid": packed_grid,
        "dense": {
            "air_hits": air_hits,
            "dep_hits": dep_hits,
            "air_pct": air_pct,
            "dep_pct": dep_pct,
            "earliest": earliest,
            "latest": latest,
            "origin": origin,
        },
        "covered": True,
        "window_start": window_start,
        "window_end_release": release_local(max(item.hour for item in scenarios), day),
    }


def build_run(
    datasets: list[MetDataset],
    *,
    official: dict,
    skipped: list[dict] | None = None,
    retrieved_at: datetime | None = None,
    seed: int = ENSEMBLE_SEED,
    n_particles: int = N_PARTICLES,
    scenarios: tuple[Scenario, ...] | None = None,
    hours: float | None = None,
    physics: Physics | None = None,
    hysplit_check: dict | None = None,
    generated_at: datetime | None = None,
) -> dict:
    scenarios = scenarios or SCENARIOS
    hours = SIM_HOURS if hours is None else hours
    physics = physics or Physics()
    generated = generated_at or utc_now()
    if not scenarios:
        raise RuntimeError("at least one release scenario is required")
    fetch_skipped = list(skipped or [])
    days = [
        _simulate_day(
            datasets,
            day,
            scenarios=(
                tuple(item._replace(hour=PLANNED_RELEASE_HOUR_CT) for item in scenarios)
                if day == EVENT_DATE else scenarios
            ),
            hours=hours,
            physics=physics,
            seed=seed,
            n_particles=n_particles,
            fetch_skipped=fetch_skipped,
        )
        for day in RELEASE_DATES
    ]
    monday = next(item for item in days if item["date"] == EVENT_DATE.isoformat())
    if not monday["covered"]:
        detail = "; ".join(f"{item['label']} {item['cycle']}: {item['reason']}" for item in monday["skipped"])
        raise RuntimeError(f"No meteorological dataset covers the Wednesday release window. {detail}")
    hysplit = hysplit_check if hysplit_check is not None else check_hysplit()
    from datetime import timezone as utc_tz

    run_id = generated.astimezone(utc_tz.utc).strftime("%Y%m%dT%H%M%SZ")
    dense = monday["dense"]
    retrieved = retrieved_at or generated
    public_days = {}
    for item in days:
        public_days[item["id"]] = {
            key: value
            for key, value in item.items()
            if key not in {"dense", "covered", "window_start", "window_end_release"}
        }
    sensitivity = fairfield_sensitivity(
        datasets, release_time=release_local(PLANNED_RELEASE_HOUR_CT),
        hours=hours, seed=seed, n_particles=n_particles, physics=physics,
    )
    public_days[EVENT_DATE.isoformat()]["receptor"]["size_height_sensitivity"] = sensitivity
    window_start = monday["window_start"]
    return {
        "schema_version": 2,
        "run_id": run_id,
        "generated_at": iso(generated),
        "generated_at_chicago": stamp(generated),
        "timezone": TIMEZONE,
        "demo": False,
        "disclaimer": DISCLAIMER,
        "narrative": monday["narrative"],
        "engine": {
            "name": ENGINE_NAME,
            "is_hysplit": False,
            "label": ENGINE_LABEL,
            "summary": ENGINE_SUMMARY,
            "hysplit_check": hysplit,
        },
        "event": {
            "name": "Planned controlled detonations of degraded lead azide at IAAAP",
            "date": EVENT_DATE.isoformat(),
            "release_window_chicago": monday["release_window_chicago"],
            "release_window_note": (
                "The Friday, Nov 20, about-noon CT plan was postponed. "
                "The planned detonation is Wednesday, Nov 25 at 9:00 AM CT. "
                "Thursday and Friday are screened from 10:00 AM to 2:00 PM CT as fallback scenarios. "
                "The map defaults to Wednesday. Read the official section for the latest agency wording."
            ),
            "simulation_hours_after_release": hours,
            "step_seconds": DT_SECONDS,
        },
        "source": {
            "name": SOURCE_NAME,
            "lat": SOURCE_LAT,
            "lon": SOURCE_LON,
            "bbox": {
                "south": SOURCE_BBOX[0],
                "west": SOURCE_BBOX[1],
                "north": SOURCE_BBOX[2],
                "east": SOURCE_BBOX[3],
            },
            "note": (
                "Marker is the OpenStreetMap centroid of the installation. "
                "Each ensemble member picks a release point inside the installation outline "
                "because the in-place detonation coordinate was not published."
            ),
        },
        "receptor": monday["receptor"],
        "footprint": monday["footprint"],
        "forecast": {
            "retrieved_at": iso(retrieved) if isinstance(retrieved, datetime) else str(retrieved),
            "retrieved_at_chicago": stamp(retrieved) if isinstance(retrieved, datetime) else None,
            "attribution": "Forecast weather data from Open-Meteo.com, using NOAA/NWS HRRR, RRFS, and GFS fields.",
            "used": monday["used"],
            "skipped": monday["skipped"],
        },
        "ensemble": {
            "n_members": monday["n_members"],
            "particles_per_member": n_particles,
            "seed": seed,
            "varied": [
                "meteorology (model and, when available, an older GFS cycle)",
                "wind direction and speed perturbations",
                "release time on fallback days",
                "release height",
                "particle diameter and density",
                "release point inside the installation",
                "dry deposition, wet removal, and mixing scales",
                "release day (Wednesday Nov 25, Thursday Nov 26, or Friday Nov 27)",
            ],
            "members": monday["members"],
        },
        "grid": {
            **{key: value for key, value in monday["grid"].items() if key not in {"encoding", "cells"}},
            "air_member_hits": pack_u8(dense["air_hits"]),
            "deposition_member_hits": pack_u8(dense["dep_hits"]),
            "air_relative_pct": pack_u8(dense["air_pct"]),
            "deposition_relative_pct": pack_u8(dense["dep_pct"]),
            "arrival_earliest_min": pack_u16(dense["earliest"].astype(np.uint16)),
            "arrival_latest_min": pack_u16(dense["latest"].astype(np.uint16)),
            "arrival_origin": iso(dense["origin"]),
            "no_arrival": 65535,
            "n_members": monday["n_members"],
        },
        "release_days": public_days,
        "schedule": _both_days_schedule(official, window_start, monday["window_end_release"], days),
        "official": official,
    }


def _both_days_schedule(official, start, end, days) -> dict:
    schedule = schedule_block(official, start, end)
    windows = [item["release_window_chicago"] for item in days]
    if len(windows) > 1:
        schedule["ensemble_window_chicago"] = " and ".join(windows)
    return schedule
