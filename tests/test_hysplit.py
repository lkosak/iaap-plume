from pipeline.hysplit import check_hysplit, write_trajectory_control


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
