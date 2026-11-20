from datetime import datetime, timedelta, timezone

import numpy as np

from pipeline.grid import Grid
from pipeline.met import uniform_met
from pipeline.model import MemberSpec, Physics, run_member, settling_velocity
from pipeline.timeutil import CHI


def _spec(**overrides):
    origin = datetime(2026, 11, 23, 14, tzinfo=timezone.utc)
    base = dict(
        seed=7,
        release_time=origin,
        minute_origin=origin,
        release_lat=39.20 + 30.5 * 0.06,
        release_lon=-94.20 + 45.5 * 0.06,
        height_m=100.0,
        diameter_m=1e-6,
        density=1000.0,
        wind_rotation_deg=0.0,
        wind_speed_factor=1.0,
        dep_scale=1.0,
        wet_scale=1.0,
        turb_scale=1.0,
        n_particles=8,
        hours=1.0,
        dt=600,
    )
    base.update(overrides)
    return MemberSpec(**base)


def test_water_droplet_settling_is_about_3_mm_per_second():
    speed = settling_velocity(10e-6, 1000.0)
    assert 0.0025 < speed < 0.004


def test_coarse_particle_settles_much_faster_than_fine():
    fine = settling_velocity(2e-6, 2500.0)
    coarse = settling_velocity(30e-6, 8000.0)
    assert coarse > fine * 100


def test_east_wind_moves_the_footprint_east():
    grid = Grid()
    spec = _spec()
    dataset = uniform_met(10.0, 0.0, hours=6, t0=int(datetime(2026, 11, 23, 12, tzinfo=timezone.utc).timestamp()))
    physics = Physics(enable_turb=False, enable_dry=False, enable_wet=False)
    result = run_member(dataset, spec, grid, physics)
    columns = result["air_dwell"].sum(axis=0)
    occupied = np.flatnonzero(columns > 0)
    start_j = grid.index_scalar(spec.release_lat, spec.release_lon)[1]
    east_lon = grid.lon_min + (occupied.max() + 0.5) * grid.dlon
    assert occupied.max() > start_j + 4
    assert spec.release_lon + 0.30 < east_lon < spec.release_lon + 0.55
    assert result["n_deposited"] == 0
    assert result["n_airborne_end"] == spec.n_particles


def test_large_particles_deposit_and_fine_ones_stay_aloft():
    grid = Grid()
    dataset = uniform_met(0.0, 0.0, hours=6, t0=int(datetime(2026, 11, 23, 12, tzinfo=timezone.utc).timestamp()))
    physics = Physics(enable_turb=False, enable_wet=False, vd_extra=0.0001)
    coarse = run_member(
        dataset,
        _spec(n_particles=40, diameter_m=30e-6, density=8000.0, height_m=80.0, hours=2, dt=300, seed=3),
        grid,
        physics,
    )
    fine = run_member(
        dataset,
        _spec(n_particles=20, diameter_m=2e-6, density=2500.0, height_m=200.0, hours=2, dt=600, seed=4),
        grid,
        physics,
    )
    assert coarse["n_deposited"] / coarse["n_particles"] > 0.8
    assert fine["n_deposited"] == 0
    assert coarse["n_deposited"] + coarse["n_airborne_end"] == coarse["n_particles"]


def test_release_cell_is_marked_at_the_release_minute():
    grid = Grid()
    origin = datetime(2026, 11, 23, 8, tzinfo=CHI)
    spec = _spec(release_time=origin + timedelta(hours=3), minute_origin=origin, hours=0.5, n_particles=2)
    dataset = uniform_met(0.0, 0.0, hours=30, t0=int(datetime(2026, 11, 23, 12, tzinfo=timezone.utc).timestamp()))
    result = run_member(dataset, spec, grid, Physics(enable_turb=False, enable_dry=False, enable_wet=False))
    i, j = grid.index_scalar(spec.release_lat, spec.release_lon)
    assert result["first_minute"][i, j] == 180
