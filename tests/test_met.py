import json

import numpy as np
import pytest

from pipeline.met import dataset_from_payloads, forecast_url, uniform_met, wind_to_uv


def test_wind_from_west_blows_east():
    u, v = wind_to_uv(10.0, 270.0)
    assert u == pytest.approx(10.0)
    assert v == pytest.approx(0.0, abs=1e-9)


def test_wind_from_south_blows_north():
    u, v = wind_to_uv(8.0, 180.0)
    assert u == pytest.approx(0.0, abs=1e-9)
    assert v == pytest.approx(8.0)


def test_forecast_url_requests_meters_per_second_and_previous_cycle():
    url = forecast_url("gfs_seamless", [(40.8, -91.2)], cycle="previous_day1", variables=("wind_speed_10m", "precipitation"))
    assert "wind_speed_unit=ms" in url
    assert "wind_speed_10m_previous_day1" in url
    assert "models=gfs_seamless" in url
    assert "previous-runs-api.open-meteo.com" in url


def _point(lat, lon, speed, direction, unit="km/h", precip=0.0):
    return {
        "latitude": lat,
        "longitude": lon,
        "elevation": 220.0,
        "hourly_units": {"wind_speed_10m": unit, "wind_direction_10m": "°"},
        "hourly": {
            "time": ["2026-11-23T14:00", "2026-11-23T15:00"],
            "wind_speed_10m": [speed, speed],
            "wind_direction_10m": [direction, direction],
            "boundary_layer_height": [500, 500],
            "precipitation": [precip, precip],
        },
    }


def test_kmh_is_converted_and_midpoint_wind_is_averaged():
    dataset = dataset_from_payloads(
        [_point(41.0, -92.0, 0.0, 270, precip=0.0), _point(41.0, -91.0, 36.0, 270, precip=3.0)],
        model_id="gfs_seamless",
        model_label="GFS",
        cycle="latest",
        retrieved_at="2026-11-20T00:00:00Z",
    )
    assert any("km/h" in note or "converted" in note for note in dataset.notes)
    when = int(dataset.times[0])
    u, v, blh, precip = dataset.sample([41.0], [-91.5], [100.0], when)
    assert u[0] == pytest.approx(5.0, abs=0.05)
    assert v[0] == pytest.approx(0.0, abs=0.05)
    assert blh[0] == pytest.approx(500.0)
    assert precip[0] == pytest.approx(1.5, abs=0.05)
    assert type(dataset.precip_known) is bool
    json.dumps(dataset.meta())


def test_vertical_interpolation_between_levels():
    dataset = uniform_met(0.0, 0.0, hours=3)
    dataset.level_names = ["10 m", "1000 m"]
    dataset.u = np.zeros((dataset.times.size, 1, 2))
    dataset.v = np.zeros_like(dataset.u)
    dataset.u[:, 0, 0] = 2.0
    dataset.u[:, 0, 1] = 20.0
    dataset.height_agl = np.zeros_like(dataset.u)
    dataset.height_agl[:, 0, 0] = 10.0
    dataset.height_agl[:, 0, 1] = 1000.0
    u, _, _, _ = dataset.sample([41.0], [-91.5], [505.0], int(dataset.times[0]))
    assert u[0] == pytest.approx(11.0, abs=0.2)


def test_short_forecast_does_not_cover_the_window():
    from datetime import datetime, timezone

    dataset = uniform_met(1.0, 0.0, hours=2, t0=int(datetime(2026, 11, 20, 0, tzinfo=timezone.utc).timestamp()))
    ok, reason = dataset.covers(
        datetime(2026, 11, 23, 14, tzinfo=timezone.utc),
        datetime(2026, 11, 23, 22, tzinfo=timezone.utc),
    )
    assert ok is False
    assert "end" in reason
