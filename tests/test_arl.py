from datetime import date, datetime, timezone

from pipeline.arl import RemoteFile, select_archive, select_forecast


def _file(day: str, name: str) -> RemoteFile:
    year, month, stamp = int(day[:4]), int(day[4:6]), int(day[6:8])
    return RemoteFile(name=name, day=date(year, month, stamp), url=f"https://example.test/{day}/{name}")


def test_hrrr_that_ends_early_falls_through_to_gfs():
    files = [
        _file("20261120", "hysplit.t15z.hrrrf00"),
        _file("20261120", "hysplit.t15z.hrrrf06"),
        _file("20261120", "hysplit.t15z.hrrrf12"),
        _file("20261120", "hysplit.t15z.hrrrf18"),
        _file("20261120", "hysplit.t12z.gfsf"),
    ]
    choice = select_forecast(
        files,
        datetime(2026, 11, 23, 16, tzinfo=timezone.utc),
        datetime(2026, 11, 24, 4, tzinfo=timezone.utc),
    )
    assert choice.model == "GFS"
    assert choice.files[0].name == "hysplit.t12z.gfsf"
    assert any(item["model"] == "HRRR" for item in choice.skipped)
    assert any(item["model"] == "NAM" and "no NAM" in item["reason"] for item in choice.skipped)


def test_newest_covering_hrrr_cycle_is_used_and_nam_is_not_required():
    files = [
        _file("20261123", "hysplit.t06z.hrrrf00"),
        _file("20261123", "hysplit.t06z.hrrrf06"),
        _file("20261123", "hysplit.t06z.hrrrf12"),
        _file("20261123", "hysplit.t06z.hrrrf18"),
        _file("20261123", "hysplit.t12z.hrrrf00"),
        _file("20261123", "hysplit.t12z.hrrrf06"),
        _file("20261123", "hysplit.t12z.hrrrf12"),
        _file("20261123", "hysplit.t12z.hrrrf18"),
        _file("20261123", "hysplit.t12z.gfsf"),
        _file("20261123", "hysplit.t12z.namf"),
    ]
    choice = select_forecast(
        files,
        datetime(2026, 11, 23, 16, tzinfo=timezone.utc),
        datetime(2026, 11, 24, 4, tzinfo=timezone.utc),
    )
    assert choice.model == "HRRR"
    assert choice.cycle == "2026-11-23T12:00:00Z"
    names = [item.name for item in choice.files]
    assert "hysplit.t12z.hrrrf00" in names
    assert "hysplit.t12z.hrrrf06" in names
    assert "hysplit.t12z.hrrrf12" in names
    assert all(not name.endswith("hrrrf18") for name in names)


def test_nam_is_used_when_it_covers_and_hrrr_does_not():
    files = [
        _file("20261120", "hysplit.t12z.hrrrf18"),
        _file("20261120", "hysplit.t18z.namf"),
        _file("20261120", "hysplit.t12z.gfsf"),
    ]
    choice = select_forecast(
        files,
        datetime(2026, 11, 23, 16, tzinfo=timezone.utc),
        datetime(2026, 11, 24, 4, tzinfo=timezone.utc),
    )
    assert choice.model == "NAM"
    assert choice.files[0].name == "hysplit.t18z.namf"


def test_archive_prefers_nam12_day_files_and_otherwise_hrrr_chunks():
    start = datetime(2026, 11, 23, 16, tzinfo=timezone.utc)
    end = datetime(2026, 11, 24, 4, tzinfo=timezone.utc)
    nam = select_archive(["20261123_nam12", "20261124_nam12", "20261123_12-17_hrrr"], start, end)
    assert nam.model == "NAM12"
    assert [item.name for item in nam.files] == ["20261123_nam12", "20261124_nam12"]
    hrrr = select_archive(
        [
            "20261123_12-17_hrrr",
            "20261123_18-23_hrrr",
            "20261124_00-05_hrrr",
        ],
        start,
        end,
    )
    assert hrrr.model == "HRRR"
    assert len(hrrr.files) == 3
