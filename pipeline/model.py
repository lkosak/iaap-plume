"""Screening Lagrangian particles. Not NOAA HYSPLIT.

Each particle has weight 1. Nothing in this module converts weight to
micrograms, and there is no emission rate to convert. Callers turn the
counts into shares of ensemble members.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np

from pipeline.grid import Grid
from pipeline.met import MetDataset
from pipeline.timeutil import CHI


def cunningham(diameter_m: float, lam: float = 6.5e-8) -> float:
    knudsen = (2.0 * lam) / diameter_m
    return 1.0 + knudsen * (1.257 + 0.4 * math.exp(-1.1 / knudsen))


def settling_velocity(diameter_m: float, density_kg_m3: float, mu: float = 1.81e-5) -> float:
    """Stokes settling with a Cunningham slip correction, m/s, positive downward."""
    if diameter_m <= 0 or density_kg_m3 <= 0:
        raise ValueError("diameter and density must be positive")
    return density_kg_m3 * 9.80665 * diameter_m**2 * cunningham(diameter_m) / (18.0 * mu)


@dataclass(frozen=True)
class Physics:
    kh_day: float = 250.0
    kh_night: float = 40.0
    kh_above: float = 10.0
    kw_day: float = 5.0
    kw_night: float = 1.0
    kw_above: float = 0.3
    vd_extra: float = 0.00015
    z_ref: float = 20.0
    z_min: float = 1.0
    z_max: float = 3000.0
    wet_coef: float = 5.0e-5
    enable_dry: bool = True
    enable_wet: bool = True
    enable_turb: bool = True


@dataclass(frozen=True)
class MemberSpec:
    seed: int
    release_time: datetime
    minute_origin: datetime
    release_lat: float
    release_lon: float
    height_m: float
    diameter_m: float
    density: float
    wind_rotation_deg: float
    wind_speed_factor: float
    dep_scale: float
    wet_scale: float
    turb_scale: float
    n_particles: int
    hours: float
    dt: int


def local_hour(t_unix: float) -> float:
    moment = datetime.fromtimestamp(t_unix, tz=CHI)
    return moment.hour + moment.minute / 60.0 + moment.second / 3600.0


def _reflect(z: np.ndarray, lo: float, hi: float) -> np.ndarray:
    z = np.array(z, dtype=float, copy=True)
    for _ in range(4):
        z = np.where(z < lo, 2.0 * lo - z, z)
        z = np.where(z > hi, 2.0 * hi - z, z)
    return np.clip(z, lo, hi)


def _eddy(z, blh, hour: float, physics: Physics, turb_scale: float):
    if not physics.enable_turb or turb_scale <= 0:
        return np.zeros_like(z), np.zeros_like(z)
    blh = np.where(np.isfinite(blh), blh, 400.0)
    inside = z < np.maximum(blh, 30.0)
    if 8.0 <= hour < 17.0:
        kh = np.where(inside, physics.kh_day, physics.kh_above)
        kw = np.where(inside, physics.kw_day, physics.kw_above)
    else:
        kh = np.where(inside, physics.kh_night, physics.kh_above)
        kw = np.where(inside, physics.kw_night, physics.kw_above)
    return kh * turb_scale, kw * turb_scale


def _rotate(u, v, degrees: float, factor: float):
    theta = math.radians(degrees)
    ur = (u * math.cos(theta) - v * math.sin(theta)) * factor
    vr = (u * math.sin(theta) + v * math.cos(theta)) * factor
    return ur, vr


def run_member(dataset: MetDataset, spec: MemberSpec, grid: Grid, physics: Physics | None = None) -> dict:
    physics = physics or Physics()
    if spec.release_time.tzinfo is None or spec.minute_origin.tzinfo is None:
        raise ValueError("release times must be timezone-aware")
    rng = np.random.default_rng(spec.seed)
    n = spec.n_particles
    lat = np.full(n, spec.release_lat)
    lon = np.full(n, spec.release_lon)
    z = np.full(n, spec.height_m)
    alive = np.ones(n, dtype=bool)
    vs = settling_velocity(spec.diameter_m, spec.density)
    dwell = np.zeros(grid.shape, dtype=np.float64)
    deposited = np.zeros(grid.shape, dtype=np.float64)
    first = np.full(grid.shape, -1, dtype=np.int32)
    n_dep_outside = 0
    offset = int(round((spec.release_time - spec.minute_origin).total_seconds() / 60.0))
    t0 = spec.release_time.astimezone(timezone.utc).timestamp()

    def stamp_cells(which, lat_v, lon_v, minute: int, weight: float):
        if lat_v.size == 0:
            return 0
        ii, jj = grid.index(lat_v, lon_v)
        ok = grid.inside(ii, jj)
        if weight != 0 and np.any(ok):
            np.add.at(which, (ii[ok], jj[ok]), weight)
        if np.any(ok):
            for i, j in zip(ii[ok].tolist(), jj[ok].tolist()):
                if first[i, j] < 0:
                    first[i, j] = minute
        return int((~ok).sum())

    stamp_cells(dwell, lat, lon, offset, 1.0)
    n_steps = int(round(spec.hours * 3600 / spec.dt))
    for step in range(n_steps):
        idx = np.flatnonzero(alive)
        if idx.size == 0:
            break
        moment = t0 + step * spec.dt
        u, v, blh, precip = dataset.sample(lat[idx], lon[idx], z[idx], moment)
        u = np.where(np.isfinite(u), u, 0.0)
        v = np.where(np.isfinite(v), v, 0.0)
        ur, vr = _rotate(u, v, spec.wind_rotation_deg, spec.wind_speed_factor)
        kh, kw = _eddy(z[idx], blh, local_hour(moment), physics, spec.turb_scale)
        du = ur * spec.dt
        dv = vr * spec.dt
        dz = -vs * spec.dt
        if physics.enable_turb:
            du = du + rng.normal(0.0, np.sqrt(np.maximum(2.0 * kh * spec.dt, 0.0)))
            dv = dv + rng.normal(0.0, np.sqrt(np.maximum(2.0 * kh * spec.dt, 0.0)))
            dz = dz + rng.normal(0.0, np.sqrt(np.maximum(2.0 * kw * spec.dt, 0.0)))
        coslat = np.cos(np.deg2rad(lat[idx]))
        lat[idx] = lat[idx] + dv / 111_320.0
        lon[idx] = lon[idx] + du / (111_320.0 * np.maximum(coslat, 0.2))
        z[idx] = _reflect(z[idx] + dz, physics.z_min, physics.z_max)

        remove = np.zeros(idx.size, dtype=bool)
        if physics.enable_dry:
            vd = vs + physics.vd_extra * spec.dep_scale
            probability = 1.0 - math.exp(-max(vd, 0.0) * spec.dt / physics.z_ref)
            near = z[idx] <= physics.z_ref
            remove |= near & (rng.random(idx.size) < probability)
        if physics.enable_wet and dataset.precip_known:
            rate = physics.wet_coef * spec.wet_scale * np.power(np.maximum(precip, 0.0), 0.8)
            wet_p = 1.0 - np.exp(-rate * spec.dt)
            raining = precip > 0.05
            remove |= raining & (z[idx] < 2500.0) & (rng.random(idx.size) < wet_p)
        minute = offset + int(round((step + 1) * spec.dt / 60.0))
        if np.any(remove):
            gone = idx[remove]
            ii, jj = grid.index(lat[gone], lon[gone])
            ok = grid.inside(ii, jj)
            if np.any(ok):
                np.add.at(deposited, (ii[ok], jj[ok]), 1.0)
                for i, j in zip(ii[ok].tolist(), jj[ok].tolist()):
                    if first[i, j] < 0:
                        first[i, j] = minute
            n_dep_outside += int((~ok).sum())
            alive[gone] = False
        still = np.flatnonzero(alive)
        if still.size:
            stamp_cells(dwell, lat[still], lon[still], minute, 1.0)

    airborne = np.flatnonzero(alive)
    n_outside_end = 0
    if airborne.size:
        ii, jj = grid.index(lat[airborne], lon[airborne])
        n_outside_end = int((~grid.inside(ii, jj)).sum())
    return {
        "air_dwell": dwell,
        "deposited": deposited,
        "first_minute": first,
        "n_deposited": int(n - int(alive.sum())),
        "n_airborne_end": int(alive.sum()),
        "n_outside_end": n_outside_end,
        "n_deposited_outside": n_dep_outside,
        "n_particles": n,
        "settling_m_s": vs,
    }
