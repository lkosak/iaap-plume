"""Open-Meteo wind profiles. Not ARL files and not HYSPLIT meteorology.

Wind components follow the meteorological convention: u is eastward, v is
northward, and direction is the direction the wind comes from.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import requests

from pipeline.config import MET_LATS, MET_LONS, MODELS
from pipeline.timeutil import iso

OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
PREVIOUS_RUNS = "https://previous-runs-api.open-meteo.com/v1/forecast"
USER_AGENT = "IAAAPIndependentScreening/1.0 (relative footprint dashboard)"

SURFACE_VARS = (
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_speed_80m",
    "wind_direction_80m",
    "boundary_layer_height",
    "precipitation",
)
UPPER_VARS = (
    "wind_speed_925hPa",
    "wind_direction_925hPa",
    "geopotential_height_925hPa",
    "wind_speed_850hPa",
    "wind_direction_850hPa",
    "geopotential_height_850hPa",
)
ALL_VARS = SURFACE_VARS + UPPER_VARS

# name, speed key, direction key, kind, fixed height or geopotential key
LEVEL_SPECS = (
    ("10 m", "wind_speed_10m", "wind_direction_10m", "fixed", 10.0),
    ("80 m", "wind_speed_80m", "wind_direction_80m", "fixed", 80.0),
    ("925 hPa", "wind_speed_925hPa", "wind_direction_925hPa", "geo", "geopotential_height_925hPa"),
    ("850 hPa", "wind_speed_850hPa", "wind_direction_850hPa", "geo", "geopotential_height_850hPa"),
)


def wind_to_uv(speed_ms, direction_from_deg):
    rad = np.deg2rad(direction_from_deg)
    u = -np.asarray(speed_ms, dtype=float) * np.sin(rad)
    v = -np.asarray(speed_ms, dtype=float) * np.cos(rad)
    return u, v


def forecast_pairs() -> list[tuple[float, float]]:
    return [(lat, lon) for lat in MET_LATS for lon in MET_LONS]


def forecast_url(model_id: str, pairs: list[tuple[float, float]], *, cycle: str, variables: tuple[str, ...], run: str | None = None) -> str:
    """Build an Open-Meteo URL. ``wind_speed_unit=ms`` is required.

    Open-Meteo's default wind unit is km/h. Requesting m/s here, and still
    checking ``hourly_units`` when the body comes back, keeps a forgotten
    parameter from stretching every footprint by 3.6.
    """
    if cycle == "latest":
        host = OPEN_METEO
        names = list(variables)
    elif cycle == "previous_day1":
        host = PREVIOUS_RUNS
        names = [f"{name}_previous_day1" for name in variables]
    else:
        raise ValueError(f"unknown cycle {cycle}")
    lats = ",".join(f"{lat:.4f}" for lat, _ in pairs)
    lons = ",".join(f"{lon:.4f}" for _, lon in pairs)
    url = (
        f"{host}?latitude={lats}&longitude={lons}"
        f"&hourly={','.join(names)}"
        f"&models={model_id}&forecast_days=5&timezone=UTC&wind_speed_unit=ms"
    )
    if run:
        url += f"&run={run}"
    return url


def _num(values) -> np.ndarray:
    out = np.empty(len(values), dtype=float)
    for i, value in enumerate(values):
        out[i] = np.nan if value is None else float(value)
    return out


def _as_locations(payload) -> list[dict]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and payload.get("error"):
        raise RuntimeError(payload.get("reason") or "Open-Meteo error")
    if isinstance(payload, dict) and "hourly" in payload:
        return [payload]
    raise RuntimeError("Open-Meteo response did not contain hourly data")


@dataclass
class MetDataset:
    model_id: str
    model_label: str
    cycle: str
    retrieved_at: str
    times: np.ndarray  # unix seconds, shape (T,)
    lat: np.ndarray
    lon: np.ndarray
    elevation_m: np.ndarray
    level_names: list[str]
    u: np.ndarray  # (T, S, L) m/s
    v: np.ndarray
    height_agl: np.ndarray
    blh: np.ndarray  # (T, S) meters
    precip_mm: np.ndarray  # (T, S) mm per hour
    precip_known: bool
    notes: list[str] = field(default_factory=list)
    valid_start: str = ""
    valid_end: str = ""
    request_urls: list[str] = field(default_factory=list)

    def covers(self, start: datetime, end: datetime) -> tuple[bool, str]:
        if self.times.size < 2:
            return False, "fewer than two forecast times"
        finite = np.isfinite(self.u[:, :, 0]).mean(axis=1) > 0.5
        if not np.any(finite):
            return False, "wind values were missing"
        valid = self.times[finite]
        t0 = start.timestamp()
        t1 = end.timestamp()
        start_iso = datetime.fromtimestamp(int(valid[0]), timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        end_iso = datetime.fromtimestamp(int(valid[-1]), timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        if valid[0] > t0 + 3600:
            return False, f"winds start {start_iso}, after the release window opens"
        if valid[-1] < t1 - 3600:
            return False, f"winds end {end_iso}, before the simulation ends"
        return True, f"covers the window ({start_iso} to {end_iso})"

    def sample(self, lat, lon, z, t_unix: float):
        """Return u, v, boundary-layer height, and precip at the particles."""
        lat = np.asarray(lat, dtype=float)
        lon = np.asarray(lon, dtype=float)
        z = np.asarray(z, dtype=float)
        if z.shape != lat.shape:
            z = np.broadcast_to(z, lat.shape).astype(float)
        n = lat.size
        if n == 0:
            empty = np.zeros(0)
            return empty, empty, empty, empty
        u_s, v_s, h_s, blh_s, pr_s = self._at_time(float(t_unix))
        flat_z = z.reshape(-1)
        u_at = np.full((n, self.lat.size), np.nan)
        v_at = np.full((n, self.lat.size), np.nan)
        for s in range(self.lat.size):
            good = np.isfinite(h_s[s]) & np.isfinite(u_s[s]) & np.isfinite(v_s[s])
            if not np.any(good):
                continue
            order = np.argsort(h_s[s, good])
            heights = h_s[s, good][order]
            u_at[:, s] = np.interp(flat_z, heights, u_s[s, good][order])
            v_at[:, s] = np.interp(flat_z, heights, v_s[s, good][order])
        u, v = _idw(lat.reshape(-1), lon.reshape(-1), self.lat, self.lon, u_at, v_at)
        blh = _idw_scalar(lat.reshape(-1), lon.reshape(-1), self.lat, self.lon, blh_s)
        precip = _idw_scalar(lat.reshape(-1), lon.reshape(-1), self.lat, self.lon, pr_s)
        blh = np.where(np.isfinite(blh), blh, 400.0)
        precip = np.where(np.isfinite(precip), np.maximum(precip, 0.0), 0.0)
        if not self.precip_known:
            precip = np.zeros_like(precip)
        return (
            u.reshape(lat.shape),
            v.reshape(lat.shape),
            blh.reshape(lat.shape),
            precip.reshape(lat.shape),
        )

    def _at_time(self, t_unix: float):
        times = self.times
        if t_unix <= times[0] or len(times) == 1:
            k, f = 0, 0.0
        elif t_unix >= times[-1]:
            k, f = len(times) - 2, 1.0
        else:
            k = int(np.searchsorted(times, t_unix) - 1)
            k = min(max(k, 0), len(times) - 2)
            span = float(times[k + 1] - times[k])
            f = 0.0 if span <= 0 else (t_unix - float(times[k])) / span
        def mix(arr):
            return (1.0 - f) * arr[k] + f * arr[k + 1]
        return mix(self.u), mix(self.v), mix(self.height_agl), mix(self.blh), mix(self.precip_mm)

    def meta(self) -> dict:
        return {
            "model_id": self.model_id,
            "model_label": self.model_label,
            "cycle": self.cycle,
            "retrieved_at": self.retrieved_at,
            "level_names": self.level_names,
            "precip_known": self.precip_known,
            "notes": self.notes,
            "valid_start": self.valid_start,
            "valid_end": self.valid_end,
            "request_urls": self.request_urls,
            "n_stations": int(self.lat.size),
            "n_times": int(self.times.size),
        }


def _idw(lat, lon, slat, slon, primary, secondary):
    """primary and secondary are (n, n_stations)."""
    dlat = (lat[:, None] - slat[None, :]) * 111_320.0
    dlon = (lon[:, None] - slon[None, :]) * 111_320.0 * np.cos(np.deg2rad(lat[:, None]))
    dist2 = dlat ** 2 + dlon ** 2
    valid = np.isfinite(primary) & np.isfinite(secondary)
    weights = np.where(valid, 1.0 / (dist2 + 300.0 ** 2), 0.0)
    total = weights.sum(axis=1)
    u = np.divide((np.where(valid, primary, 0.0) * weights).sum(axis=1), total, out=np.zeros(lat.size), where=total > 0)
    v = np.divide((np.where(valid, secondary, 0.0) * weights).sum(axis=1), total, out=np.zeros(lat.size), where=total > 0)
    return u, v


def _idw_scalar(lat, lon, slat, slon, values):
    dlat = (lat[:, None] - slat[None, :]) * 111_320.0
    dlon = (lon[:, None] - slon[None, :]) * 111_320.0 * np.cos(np.deg2rad(lat[:, None]))
    dist2 = dlat ** 2 + dlon ** 2
    valid = np.isfinite(values)[None, :]
    weights = np.where(valid, 1.0 / (dist2 + 300.0 ** 2), 0.0)
    total = weights.sum(axis=1)
    filled = np.where(np.isfinite(values), values, 0.0)
    return np.divide((filled[None, :] * weights).sum(axis=1), total, out=np.full(lat.size, np.nan), where=total > 0)


def dataset_from_payloads(
    payloads: list[dict],
    *,
    model_id: str,
    model_label: str,
    cycle: str,
    retrieved_at: str,
    request_urls: list[str] | None = None,
) -> MetDataset:
    if not payloads:
        raise RuntimeError(f"{model_label} returned no locations")
    times = payloads[0]["hourly"]["time"]
    for payload in payloads[1:]:
        if payload["hourly"]["time"] != times:
            raise RuntimeError(f"{model_label} locations do not share a time axis")
    t_index = np.array(
        [int(datetime.fromisoformat(item).replace(tzinfo=timezone.utc).timestamp()) for item in times],
        dtype=np.int64,
    )
    suffix = "" if cycle == "latest" else f"_{cycle}"
    units = payloads[0].get("hourly_units") or {}
    unit_key = "wind_speed_10m" + suffix
    reported = units.get(unit_key) or units.get("wind_speed_10m")
    notes: list[str] = []
    if reported is None:
        factor = 1.0
        notes.append("Response did not name wind units; values were taken as m/s because wind_speed_unit=ms was requested.")
    elif "km" in str(reported).lower():
        factor = 1.0 / 3.6
        notes.append(f"Open-Meteo reported wind unit {reported}; converted to m/s.")
    else:
        factor = 1.0

    def series(hourly, name):
        return hourly.get(name + suffix)

    n_time = len(times)
    n_station = len(payloads)
    level_u = []
    level_v = []
    level_h = []
    level_names = []
    for name, speed_key, dir_key, kind, extra in LEVEL_SPECS:
        speeds = []
        dirs = []
        heights = []
        missing = False
        for payload in payloads:
            hourly = payload["hourly"]
            ws = series(hourly, speed_key)
            wd = series(hourly, dir_key)
            if ws is None or wd is None:
                missing = True
                break
            speed = _num(ws) * factor
            direction = np.mod(_num(wd), 360.0)
            speed = np.where(speed < 0, np.nan, speed)
            if kind == "fixed":
                height = np.full(n_time, float(extra))
            else:
                geo = series(hourly, extra)
                if geo is None:
                    missing = True
                    break
                elev = payload.get("elevation")
                elev_m = np.nan if elev is None else float(elev)
                height = _num(geo) - elev_m
            speeds.append(speed)
            dirs.append(direction)
            heights.append(height)
        if missing:
            notes.append(f"Level {name} was absent for at least one point and was omitted.")
            continue
        height_arr = np.vstack(heights)  # (S, T)
        if float(np.nanmedian(height_arr)) < 5.0:
            notes.append(f"Level {name} sits below 5 m above ground and was omitted.")
            continue
        finite_frac = np.isfinite(np.vstack(speeds)).mean()
        if finite_frac < 0.5:
            notes.append(f"Level {name} was mostly missing ({finite_frac:.0%} finite) and was omitted.")
            continue
        u, v = wind_to_uv(np.vstack(speeds), np.vstack(dirs))
        level_u.append(u.T)  # (T, S)
        level_v.append(v.T)
        level_h.append(height_arr.T)
        level_names.append(name)
    if not level_names:
        raise RuntimeError(f"{model_label} {cycle} had no usable wind levels")
    if len(level_names) == 1:
        notes.append("Only one wind level was available, so wind does not change with height in this dataset.")

    order = np.argsort([float(np.nanmedian(item)) for item in level_h])
    u = np.stack([level_u[i] for i in order], axis=2)
    v = np.stack([level_v[i] for i in order], axis=2)
    height = np.stack([level_h[i] for i in order], axis=2)
    level_names = [level_names[i] for i in order]

    blh_rows = []
    blh_missing = False
    precip_rows = []
    precip_missing = False
    lats = []
    lons = []
    elevs = []
    for payload in payloads:
        lats.append(float(payload["latitude"]))
        lons.append(float(payload["longitude"]))
        elev = payload.get("elevation")
        elevs.append(220.0 if elev is None else float(elev))
        raw_blh = series(payload["hourly"], "boundary_layer_height")
        raw_pr = series(payload["hourly"], "precipitation")
        if raw_blh is None:
            blh_missing = True
            blh_rows.append(np.full(n_time, np.nan))
        else:
            blh_rows.append(_num(raw_blh))
        if raw_pr is None:
            precip_missing = True
            precip_rows.append(np.full(n_time, np.nan))
        else:
            precip_rows.append(_num(raw_pr))
    blh = np.vstack(blh_rows).T
    precip = np.vstack(precip_rows).T
    precip_known = bool(not precip_missing and float(np.isfinite(precip).mean()) > 0.5)
    if blh_missing or np.isfinite(blh).mean() < 0.5:
        notes.append("Boundary-layer height was missing; 400 m is used where a particle needs it.")
        blh = np.where(np.isfinite(blh), blh, 400.0)
    if not precip_known:
        notes.append("Precipitation was missing, so wet removal is off for this dataset.")
        precip = np.zeros_like(precip)

    finite = np.isfinite(u[:, :, 0]).mean(axis=1) > 0.5
    if not np.any(finite):
        raise RuntimeError(f"{model_label} {cycle} winds were empty")
    valid_times = t_index[finite]
    dataset = MetDataset(
        model_id=model_id,
        model_label=model_label,
        cycle=cycle,
        retrieved_at=retrieved_at,
        times=t_index,
        lat=np.array(lats),
        lon=np.array(lons),
        elevation_m=np.array(elevs),
        level_names=level_names,
        u=u,
        v=v,
        height_agl=height,
        blh=blh,
        precip_mm=precip,
        precip_known=precip_known,
        notes=notes,
        valid_start=datetime.fromtimestamp(int(valid_times[0]), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        valid_end=datetime.fromtimestamp(int(valid_times[-1]), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        request_urls=list(request_urls or []),
    )
    return dataset


def uniform_met(u: float, v: float, *, lat: float = 41.0, lon: float = -91.5, hours: int = 36, blh: float = 800.0, precip: float = 0.0, t0: int | None = None) -> MetDataset:
    """Spatially uniform wind, for tests and for nothing the dashboard would call a forecast."""
    if t0 is None:
        t0 = int(datetime(2026, 11, 23, 12, tzinfo=timezone.utc).timestamp())
    times = np.arange(t0, t0 + hours * 3600 + 1, 3600, dtype=np.int64)
    n_time = len(times)
    return MetDataset(
        model_id="uniform",
        model_label="Uniform",
        cycle="test",
        retrieved_at="2026-11-20T00:00:00Z",
        times=times,
        lat=np.array([lat]),
        lon=np.array([lon]),
        elevation_m=np.array([220.0]),
        level_names=["10 m"],
        u=np.full((n_time, 1, 1), u),
        v=np.full((n_time, 1, 1), v),
        height_agl=np.full((n_time, 1, 1), 10.0),
        blh=np.full((n_time, 1), blh),
        precip_mm=np.full((n_time, 1), precip),
        precip_known=True,
        notes=["Synthetic uniform wind for tests."],
        valid_start="",
        valid_end="",
    )


def _get_json(session: requests.Session, url: str) -> dict | list:
    last_error = "no attempt"
    for attempt in range(4):
        try:
            response = session.get(url, timeout=60)
        except requests.RequestException as exc:
            last_error = exc.__class__.__name__
            _sleep(attempt)
            continue
        if response.status_code == 200:
            return response.json()
        last_error = f"HTTP {response.status_code}: {response.text[:180]}"
        if response.status_code in {429, 500, 502, 503, 504}:
            _sleep(attempt)
            continue
        break
    raise RuntimeError(last_error)


def _sleep(attempt: int) -> None:
    import time
    time.sleep(min(8, 2 ** attempt))


def _fetch_locations(session: requests.Session, model_id: str, pairs: list[tuple[float, float]], *, cycle: str, run: str | None = None) -> tuple[list[dict], list[str]]:
    variable_sets = (ALL_VARS, SURFACE_VARS, ("wind_speed_10m", "wind_direction_10m", "precipitation"))
    last_error = "no request"
    for variables in variable_sets:
        urls = []
        payloads: list[dict] = []
        try:
            for start in range(0, len(pairs), 10):
                chunk = pairs[start : start + 10]
                url = forecast_url(model_id, chunk, cycle=cycle, variables=variables, run=run)
                urls.append(url)
                payloads.extend(_as_locations(_get_json(session, url)))
            return payloads, urls
        except RuntimeError as exc:
            last_error = str(exc)
            continue
    raise RuntimeError(last_error)


def fetch_datasets(session: requests.Session | None = None, *, now: datetime | None = None) -> tuple[list[MetDataset], list[dict]]:
    """Download HRRR, RRFS, and GFS, plus an older GFS run and yesterday's GFS if they parse."""
    own_session = session is None
    session = session or requests.Session()
    session.headers.setdefault("User-Agent", USER_AGENT)
    retrieved = iso(now or datetime.now(timezone.utc))
    pairs = forecast_pairs()
    datasets: list[MetDataset] = []
    skipped: list[dict] = []
    jobs: list[tuple[str, str, str, str | None]] = [(model_id, label, "latest", None) for model_id, label in MODELS]
    # Open-Meteo's forecast endpoint rejects run=. Older meteorology is the
    # previous_day1 field, which is the forecast made about a day earlier.
    jobs.append(("gfs_seamless", "GFS", "previous_day1", None))
    try:
        for model_id, label, cycle, run in jobs:
            cycle_name = cycle if not run else f"run_{run}"
            try:
                use_cycle = "latest" if run else cycle
                payloads, urls = _fetch_locations(session, model_id, pairs, cycle=use_cycle, run=run)
                dataset = dataset_from_payloads(
                    payloads,
                    model_id=model_id,
                    model_label=label,
                    cycle=cycle_name,
                    retrieved_at=retrieved,
                    request_urls=urls,
                )
                datasets.append(dataset)
                print(f"met {label} {cycle_name}: {dataset.valid_start} → {dataset.valid_end} levels={dataset.level_names}")
            except Exception as exc:  # noqa: BLE001 — one model must not sink the run
                reason = str(exc)
                skipped.append({"model_id": model_id, "label": label, "cycle": cycle_name, "reason": reason[:400]})
                print(f"met skip {label} {cycle_name}: {reason[:200]}")
    finally:
        if own_session:
            session.close()
    return datasets, skipped


def save_met(path, datasets: list[MetDataset]) -> None:
    payload = {"n": np.int32(len(datasets))}
    for i, dataset in enumerate(datasets):
        prefix = f"d{i}_"
        payload[prefix + "times"] = dataset.times
        payload[prefix + "lat"] = dataset.lat
        payload[prefix + "lon"] = dataset.lon
        payload[prefix + "elevation"] = dataset.elevation_m
        payload[prefix + "u"] = dataset.u
        payload[prefix + "v"] = dataset.v
        payload[prefix + "height"] = dataset.height_agl
        payload[prefix + "blh"] = dataset.blh
        payload[prefix + "precip"] = dataset.precip_mm
        payload[prefix + "meta"] = np.asarray(json.dumps(dataset.meta(), default=lambda value: value.item() if isinstance(value, np.generic) else value))
    np.savez_compressed(str(path), **payload)


def load_met(path) -> list[MetDataset]:
    archive = np.load(path, allow_pickle=False)
    count = int(archive["n"])
    loaded = []
    for i in range(count):
        prefix = f"d{i}_"
        meta_raw = archive[prefix + "meta"]
        meta = json.loads(meta_raw.item() if meta_raw.shape == () else str(meta_raw))
        loaded.append(
            MetDataset(
                model_id=meta["model_id"],
                model_label=meta["model_label"],
                cycle=meta["cycle"],
                retrieved_at=meta["retrieved_at"],
                times=archive[prefix + "times"],
                lat=archive[prefix + "lat"],
                lon=archive[prefix + "lon"],
                elevation_m=archive[prefix + "elevation"],
                level_names=list(meta["level_names"]),
                u=archive[prefix + "u"],
                v=archive[prefix + "v"],
                height_agl=archive[prefix + "height"],
                blh=archive[prefix + "blh"],
                precip_mm=archive[prefix + "precip"],
                precip_known=bool(meta["precip_known"]),
                notes=list(meta["notes"]),
                valid_start=meta.get("valid_start", ""),
                valid_end=meta.get("valid_end", ""),
                request_urls=list(meta.get("request_urls") or []),
            )
        )
    return loaded
