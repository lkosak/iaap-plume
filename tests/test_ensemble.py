import re
from datetime import datetime, timezone

from pipeline.config import FAIRFIELD_LAT, FAIRFIELD_LON, SOURCE_LAT, SOURCE_LON
from pipeline.encoding import unpack_u8
from pipeline.ensemble import SCENARIOS, build_run, render_narrative
from pipeline.geo import bearing_deg, haversine_km
from pipeline.grid import Grid
from pipeline.met import uniform_met

OFFICIAL = {
    "retrieved_at": "2026-11-20T16:00:00Z",
    "retrieved_at_chicago": "Nov 20, 2026, 10:00 AM CT (America/Chicago)",
    "preface": "Official material is separate from the model.",
    "sources": [],
    "monitoring": {"status": "not_provided", "note": "none", "rows": []},
}
HYSPLIT = {"executable": None, "ran": False, "forecast_dispersion": False, "reason": "not installed in this test"}


def _run(datasets, **kwargs):
    defaults = dict(
        official=OFFICIAL,
        skipped=[],
        hysplit_check=HYSPLIT,
        generated_at=datetime(2026, 11, 20, 16, tzinfo=timezone.utc),
        n_particles=16,
        scenarios=SCENARIOS[:1],
        hours=2,
        seed=11,
    )
    defaults.update(kwargs)
    return build_run(datasets, **defaults)


def test_wednesday_uses_planned_release_and_fallbacks_span_midday():
    hours = [item.hour for item in SCENARIOS]
    assert min(hours) >= 10
    assert max(hours) <= 14
    assert hours.count(12) >= 2
    assert sum(hours) / len(hours) == 12
    t0 = int(datetime(2026, 11, 25, 12, tzinfo=timezone.utc).timestamp())
    run = _run(
        [uniform_met(1.0, 0.0, hours=48, t0=t0)],
        scenarios=SCENARIOS,
        n_particles=4,
        hours=1,
    )
    assert "9:00 AM" in run["schedule"]["ensemble_center_chicago"]
    sensitivity = run["receptor"]["size_height_sensitivity"]
    sizes = {0.5, 2, 8, 10, 25}
    heights = {20, 30, 60, 150, 200, 300, 500}
    assert len(sensitivity) == len(sizes) * len(heights)
    assert {(row["diameter_um"], row["height_m"]) for row in sensitivity} == {
        (size, height) for size in sizes for height in heights
    }
    assert all(row["n_members"] == 1 for row in sensitivity)

    assert all("9:00 AM" in member["release_local"] for member in run["release_days"]["2026-11-25"]["members"])
    for day in ("2026-11-26", "2026-11-27"):
        window = run["release_days"][day]["release_window_chicago"]
        assert "10:00 AM" in window and "2:00 PM" in window
    assert "Nov 20" in run["schedule"]["change"]
    assert "Nov 25" in run["schedule"]["change"]


def test_fairfields_distance_and_bearing():
    distance = float(haversine_km(SOURCE_LAT, SOURCE_LON, FAIRFIELD_LAT, FAIRFIELD_LON))
    bearing = bearing_deg(SOURCE_LAT, SOURCE_LON, FAIRFIELD_LAT, FAIRFIELD_LON)
    assert 55 < distance < 85
    assert 260 < bearing < 330


def test_places_fall_inside_the_grid():
    grid = Grid()
    grid.index_scalar(SOURCE_LAT, SOURCE_LON)
    grid.index_scalar(FAIRFIELD_LAT, FAIRFIELD_LON)


def test_default_grid_covers_a_day_of_transport():
    """At least 300 km, and enough for about a day at 11 m/s, on every side."""
    grid = Grid()
    edges = (
        (grid.lat_min, SOURCE_LON),
        (grid.lat_max, SOURCE_LON),
        (SOURCE_LAT, grid.lon_min),
        (SOURCE_LAT, grid.lon_max),
    )
    distances = [float(haversine_km(SOURCE_LAT, SOURCE_LON, lat, lon)) for lat, lon in edges]
    assert min(distances) >= 900
    assert grid.dlat == 0.08 and grid.dlon == 0.08
    assert grid.nlat * grid.nlon < 80_000


def test_opposite_winds_move_the_centroid_opposite_ways():
    t0 = int(datetime(2026, 11, 25, 12, tzinfo=timezone.utc).timestamp())
    east = _run([uniform_met(12.0, 0.0, hours=48, t0=t0)])
    west = _run([uniform_met(-12.0, 0.0, hours=48, t0=t0)])
    assert east["footprint"]["centroid_lon"] > west["footprint"]["centroid_lon"]
    for run in (east, west):
        hits = run["receptor"]["air_hits"]
        assert 0 <= hits <= run["receptor"]["n_members"]
        assert run["engine"]["is_hysplit"] is False
        assert run["engine"]["label"] == "NOT HYSPLIT"


def test_grid_encoding_matches_the_fairfield_cell():
    t0 = int(datetime(2026, 11, 25, 12, tzinfo=timezone.utc).timestamp())
    run = _run([uniform_met(3.0, 1.0, hours=48, t0=t0), uniform_met(-3.0, 4.0, hours=48, t0=t0)])
    grid = run["grid"]
    count = grid["nlat"] * grid["nlon"]
    hits = unpack_u8(grid["air_member_hits"], count).reshape(grid["nlat"], grid["nlon"])
    cell = run["receptor"]["cell"]
    assert int(hits[cell["i"], cell["j"]]) == run["receptor"]["air_hits"]
    assert hits.max() <= run["ensemble"]["n_members"]


def test_all_release_days_are_stored_and_a_short_model_drops_later_days():
    from datetime import date

    from pipeline.config import UPDATE_UNTIL_UTC

    long_start = int(datetime(2026, 11, 25, 12, tzinfo=timezone.utc).timestamp())
    long_run = _run([uniform_met(2.0, 1.0, hours=120, t0=long_start)], n_particles=8, hours=8)
    days = long_run["release_days"]
    assert set(days) == {"2026-11-25", "2026-11-26", "2026-11-27"}
    wednesday = days["2026-11-25"]
    thursday = days["2026-11-26"]
    friday = days["2026-11-27"]
    assert wednesday["n_members"] == thursday["n_members"] == friday["n_members"] > 0
    assert wednesday["members"][0]["release_iso"].startswith("2026-11-25")
    assert thursday["members"][0]["release_iso"].startswith("2026-11-26")
    assert friday["members"][0]["release_iso"].startswith("2026-11-27")
    assert wednesday["receptor"]["air_hits"] == long_run["receptor"]["air_hits"]
    for day in (wednesday, thursday, friday):
        assert "centroid_bearing_deg" in day["footprint"]
        assert "nearest_overlap_km" in day["receptor"]
        assert day["grid"]["encoding"] == "sparse"
        assert day["grid"]["cells"]
    # Wednesday 9 AM CT plus 8 h is 23:00 UTC on Nov 25, before the ticker stops.
    assert UPDATE_UNTIL_UTC >= "2026-11-25T23:00:00"
    # Friday 2 PM CT plus 8 h is 04:00 UTC on Nov 28, before the ticker stops.
    assert UPDATE_UNTIL_UTC >= "2026-11-28T04:00:00"
    short_start = int(datetime(2026, 11, 25, 12, tzinfo=timezone.utc).timestamp())
    short_run = _run([uniform_met(2.0, 1.0, hours=20, t0=short_start)], n_particles=4, hours=8)
    assert short_run["release_days"]["2026-11-25"]["n_members"] > 0
    assert short_run["release_days"]["2026-11-26"]["n_members"] == 0
    assert short_run["release_days"]["2026-11-26"]["skipped"]
    assert short_run["release_days"]["2026-11-27"]["n_members"] == 0
    assert short_run["release_days"]["2026-11-27"]["skipped"]
    assert date.fromisoformat("2026-11-24")


def test_same_seed_is_reproducible():
    t0 = int(datetime(2026, 11, 25, 12, tzinfo=timezone.utc).timestamp())
    datasets = [uniform_met(4.0, 2.0, hours=48, t0=t0)]
    first = _run(datasets)
    second = _run(datasets)
    assert first["grid"]["air_member_hits"] == second["grid"]["air_member_hits"]
    assert first["receptor"]["air_hits"] == second["receptor"]["air_hits"]


def test_user_facing_model_text_does_not_make_a_safety_claim():
    t0 = int(datetime(2026, 11, 25, 12, tzinfo=timezone.utc).timestamp())
    run = _run([uniform_met(1.0, 0.0, hours=48, t0=t0)])
    blob = " ".join([run["narrative"], run["disclaimer"], run["engine"]["summary"], run["engine"]["label"]])
    assert re.search(r"\b(safe|unsafe)\b", blob, re.I) is None
    assert "contamin" not in blob.lower()
    assert "µg" not in blob
    assert "not a measurement" in blob
    assert "not concentrations" in run["disclaimer"] or "not a concentration" in run["narrative"]


def test_narrative_zero_overlap_does_not_say_the_air_is_clear():
    text = render_narrative(
        {
            "n_members": 4,
            "air_hits": 0,
            "air_neighbor_hits": 0,
            "deposition_hits": 0,
            "distance_km": 66,
            "bearing_deg": 292,
            "bearing_word": "west-northwest",
            "cells_with_air": 3,
            "footprint_word": "northeast",
            "nearest_overlap_km": 40,
            "fraction_left_map": 0.0,
            "hours": 8,
            "arrival_earliest_chicago": None,
            "arrival_latest_chicago": None,
        }
    )
    assert "Surface-deposition overlap in the Fairfield cell: 0 of 4 members" in text
    assert "No ensemble member" in text
    assert "northeast" in text
    assert "clear" not in text.lower()
