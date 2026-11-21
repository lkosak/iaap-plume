"""The footprint cell that contains IAAAP has to be drawn on IAAAP.

A single image stretched from the grid's southwest corner to its northeast
corner is linear in Web Mercator, not in latitude. That was invisible on the
old 4° box and about 63 km on the enlarged box.
"""

import json
import math
from pathlib import Path

from pipeline.encoding import unpack_u8

SOURCE_LAT = 40.7858281
SOURCE_LON = -91.2444371
RUNS = Path(__file__).resolve().parents[1] / "web" / "public" / "runs"

OLD_GRID = dict(lat_min=39.20, lon_min=-94.20, dlat=0.06, dlon=0.06, nlat=70, nlon=90)
NEW_GRID = dict(lat_min=32.16, lon_min=-102.64, dlat=0.08, dlon=0.08, nlat=216, nlon=285)


def cell_index(grid, lat, lon):
    i = math.floor((lat - grid["lat_min"]) / grid["dlat"])
    j = math.floor((lon - grid["lon_min"]) / grid["dlon"])
    return i, j


def cell_edges(grid, i, j):
    """Same edges the map uses: row 0 is the south edge, from stored metadata."""
    return {
        "south": grid["lat_min"] + i * grid["dlat"],
        "north": grid["lat_min"] + (i + 1) * grid["dlat"],
        "west": grid["lon_min"] + j * grid["dlon"],
        "east": grid["lon_min"] + (j + 1) * grid["dlon"],
    }


def _mercator(lat):
    phi = math.radians(lat)
    return math.log(math.tan(math.pi / 4 + phi / 2))


def _unmercator(y):
    return math.degrees(2 * math.atan(math.exp(y)) - math.pi / 2)


def image_overlay_latitude(grid, i):
    """Latitude Leaflet gives the center of row i inside one imageOverlay."""
    lat_max = grid["lat_min"] + grid["nlat"] * grid["dlat"]
    fraction = ((grid["nlat"] - 1 - i) + 0.5) / grid["nlat"]
    north, south = _mercator(lat_max), _mercator(grid["lat_min"])
    return _unmercator(north + fraction * (south - north))


def test_source_cell_edges_contain_iaaap_for_both_grid_sizes():
    for grid in (OLD_GRID, NEW_GRID):
        i, j = cell_index(grid, SOURCE_LAT, SOURCE_LON)
        edges = cell_edges(grid, i, j)
        assert edges["south"] <= SOURCE_LAT < edges["north"]
        assert edges["west"] <= SOURCE_LON < edges["east"]
        assert abs((edges["north"] - edges["south"]) - grid["dlat"]) < 1e-12
        assert abs((edges["east"] - edges["west"]) - grid["dlon"]) < 1e-12
        center_lat = (edges["south"] + edges["north"]) / 2
        center_lon = (edges["west"] + edges["east"]) / 2
        assert abs(center_lat - SOURCE_LAT) < grid["dlat"]
        assert abs(center_lon - SOURCE_LON) < grid["dlon"]


def test_one_image_overlay_shifts_only_the_enlarged_grid():
    old_i, _ = cell_index(OLD_GRID, SOURCE_LAT, SOURCE_LON)
    new_i, _ = cell_index(NEW_GRID, SOURCE_LAT, SOURCE_LON)
    old_true = OLD_GRID["lat_min"] + (old_i + 0.5) * OLD_GRID["dlat"]
    new_true = NEW_GRID["lat_min"] + (new_i + 0.5) * NEW_GRID["dlat"]
    old_shift_km = abs(image_overlay_latitude(OLD_GRID, old_i) - old_true) * 111.32
    new_shift_km = abs(image_overlay_latitude(NEW_GRID, new_i) - new_true) * 111.32
    assert old_shift_km < OLD_GRID["dlat"] * 111.32
    assert new_shift_km > 50


def test_archived_runs_keep_the_source_cell_for_both_grid_sizes():
    seen = set()
    for path in sorted(RUNS.glob("*/run.json")):
        run = json.loads(path.read_text())
        grid = run["grid"]
        seen.add(grid["dlat"])
        assert abs(grid["lat_max"] - (grid["lat_min"] + grid["nlat"] * grid["dlat"])) < 1e-6
        assert abs(grid["lon_max"] - (grid["lon_min"] + grid["nlon"] * grid["dlon"])) < 1e-6
        i, j = cell_index(grid, SOURCE_LAT, SOURCE_LON)
        air = unpack_u8(grid["air_member_hits"], grid["nlat"] * grid["nlon"]).reshape(grid["nlat"], grid["nlon"])
        assert air[i, j] > 0, path.name
        edges = cell_edges(grid, i, j)
        assert edges["south"] <= SOURCE_LAT < edges["north"]
        assert edges["west"] <= SOURCE_LON < edges["east"]
    assert 0.06 in seen and 0.08 in seen
