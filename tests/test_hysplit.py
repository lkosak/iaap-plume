from datetime import datetime, timezone

import numpy as np

from pipeline.encoding import pack_u8, unpack_u8
from pipeline.hindcast import _ascii_from, accumulate, hourly_grids, normalize, publish_hindcast
from pipeline.hysplit import (
    check_hysplit,
    parse_concentration_ascii,
    parse_hysplit_columns,
    parse_tdump,
    write_concentration_control,
    write_multi_trajectory_control,
    write_trajectory_control,
)
from pipeline.hysplit_traj import empty_product


def test_missing_executable_is_not_called_hysplit():
    result = check_hysplit({})
    assert result["forecast_dispersion"] is False
    assert result["ran"] is False
    assert "HYSPLIT_EXEC" in result["reason"]


def test_stub_that_rejects_forecast_dispersion(tmp_path):
    script = tmp_path / "hycs_std"
    script.write_text(
        "#!/bin/sh\n"
        "echo 'dispersion will not work with forecast meteorological data' >&2\n"
        "exit 1\n"
    )
    script.chmod(0o755)
    result = check_hysplit({"HYSPLIT_EXEC": str(script)})
    assert result["ran"] is True
    assert result["forecast_dispersion"] is False
    assert "forecast" in result["reason"].lower()


def test_trajectory_control_has_the_release_and_met_file(tmp_path):
    path = tmp_path / "CONTROL"
    write_trajectory_control(
        path,
        year=2026,
        month=11,
        day=23,
        hour=14,
        lat=40.7858281,
        lon=-91.2444371,
        height_m=50,
        hours=8,
        met_dir="/data/arl",
        met_files=["hrrr.arl"],
    )
    lines = path.read_text().splitlines()
    assert lines[0] == "26 11 23 14"
    assert lines[1] == "1"
    assert "40.7858281" in lines[2]
    assert "-91.2444371" in lines[2]
    assert lines[3] == "8"
    assert "/data/arl/" in lines
    assert "hrrr.arl" in lines
    assert lines[-1] == "tdump"


def test_three_heights_share_one_start_time(tmp_path):
    path = tmp_path / "CONTROL"
    write_multi_trajectory_control(
        path,
        when=datetime(2026, 11, 23, 16, tzinfo=timezone.utc),
        points=[(40.7858281, -91.2444371, 50), (40.7858281, -91.2444371, 250), (40.7858281, -91.2444371, 500)],
        hours=8,
        met_dir="/data/arl",
        met_files=["hysplit.t12z.gfsf"],
    )
    lines = path.read_text().splitlines()
    assert lines[0] == "26 11 23 16"
    assert lines[1] == "3"
    assert lines[2].endswith(" 50")
    assert lines[4].endswith(" 500")
    assert lines[5] == "8"
    assert lines[6] == "0"


def test_tdump_points_keep_time_and_height():
    text = """
     1
 hysplit.t12z.gfsf
     2
     1     1    40.7858   -91.2444     50.0    26    11    23    16
     2     1    40.7858   -91.2444    250.0    26    11    23    16
     1     1    26    11    23    16     0     0.0     0.0    40.7858   -91.2444      50.0
     1     1    26    11    23    17     0     1.0     1.0    40.9000   -91.1000     120.0
     2     1    26    11    23    16     0     0.0     0.0    40.7858   -91.2444     250.0
"""
    parsed = parse_tdump(text)
    assert [item["number"] for item in parsed] == [1, 2]
    assert parsed[0]["points"][1]["time"] == "2026-11-23T17:00:00Z"
    assert parsed[0]["points"][1]["lat"] == 40.9
    assert parsed[1]["points"][0]["height_m"] == 250.0


def test_concentration_control_is_a_unit_rate_and_not_a_lead_inventory(tmp_path):
    path = tmp_path / "CONTROL"
    write_concentration_control(
        path,
        when=datetime(2026, 11, 23, 16, tzinfo=timezone.utc),
        lat=40.7858281,
        lon=-91.2444371,
        height_m=50,
        hours=12,
        emit_hours=1,
        met_dir="/data/arl",
        met_files=["20261123_nam12"],
        center_lat=41.3,
        center_lon=-91.5,
        spacing=0.06,
        span_lat=4.2,
        span_lon=5.4,
    )
    text = path.read_text()
    assert "REL" in text
    assert "\n1.0\n" in text
    assert "lead" not in text.lower()
    assert "ug" not in text.lower()


def test_relative_field_is_a_percent_of_its_own_peak():
    scaled = normalize(np.array([[0.0, 2.0], [4.0, np.nan]]))
    assert scaled.dtype == np.uint8
    assert int(scaled.max()) == 100
    assert int(scaled[0, 0]) == 0
    assert int(scaled[0, 1]) == 50
    packed = unpack_u8(pack_u8(scaled), 4)
    assert list(packed) == [0, 50, 100, 0]


def test_con2asc_keeps_deposition_apart_from_the_air_column():
    text = """DAY HR LAT LON REL00000 REL00100
289 19 40.23 -91.50 2.0 8.0
289 19 40.29 -91.44 0.0 4.0
"""
    columns = parse_hysplit_columns(text)
    assert columns["REL00100"][0] == (40.23, -91.50, 8.0)
    assert columns["REL00000"][0][2] == 2.0
    air = parse_concentration_ascii(text)
    assert air[0][2] == 8.0
    assert air[1][2] == 4.0


def test_triplet_parser_and_archive_round_trip(tmp_path):
    points = parse_concentration_ascii("40.23 -91.50 0\n40.29 -91.44 8\n")
    from pipeline.grid import Grid

    field = accumulate(points, Grid())
    assert field.max() == 8
    product = {
        "label": "post-event hindcast",
        "real_hysplit": True,
        "generated_at_chicago": "Nov 24, 2026, 9:00 AM CT (America/Chicago)",
        "note": "relative",
        "reason": "",
        "met": {"model": "NAM12"},
        "grid": {"relative_air": "AA==", "relative_deposition": "AA==", "scale": "percent of the peak in this run"},
    }
    dest = publish_hindcast(tmp_path, product)
    assert dest is not None
    assert (tmp_path / "latest.json").exists()
    assert "post-event hindcast" in (tmp_path / "latest.json").read_text()
    assert publish_hindcast(tmp_path, empty_product("not yet")) is None


def test_hindcast_hours_use_sample_end_and_share_peak(tmp_path):
    header = "DAY HR LAT LON REL00000 REL00100\n"
    (tmp_path / "conc_329_16").write_text(header + "329 16 40.23 -91.50 2 4\n")
    (tmp_path / "conc_329_17").write_text(header + "329 17 40.23 -91.50 8 20\n")
    start = datetime(2026, 11, 25, 15, tzinfo=timezone.utc)
    end = datetime(2026, 11, 25, 17, tzinfo=timezone.utc)
    grid = hourly_grids(_ascii_from(tmp_path, "conc"), start, end)
    first, second = grid["hourly"]
    assert first["end_utc"] == "2026-11-25T16:00:00Z"
    assert "9:00 AM" in first["label"] and "10:00 AM" in first["label"]
    cells = grid["nlat"] * grid["nlon"]
    assert max(unpack_u8(first["relative_air"], cells)) == 20
    assert max(unpack_u8(first["relative_deposition"], cells)) == 25
    assert max(unpack_u8(second["relative_air"], cells)) == 100
