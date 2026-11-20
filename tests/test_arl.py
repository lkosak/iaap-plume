from datetime import date, datetime, timezone

from pathlib import Path

from pipeline.arl import MAX_MET_BYTES, RemoteFile, download, enforce_met_cap, select_archive, select_forecast


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


def test_nam_is_preferred_when_the_dedicated_job_asks_for_it_first():
    files = [
        _file("20261123", "hysplit.t06z.hrrrf00"),
        _file("20261123", "hysplit.t06z.hrrrf06"),
        _file("20261123", "hysplit.t06z.hrrrf12"),
        _file("20261123", "hysplit.t06z.hrrrf18"),
        _file("20261120", "hysplit.t12z.namf"),
        _file("20261120", "hysplit.t12z.gfsf"),
    ]
    choice = select_forecast(
        files,
        datetime(2026, 11, 23, 16, tzinfo=timezone.utc),
        datetime(2026, 11, 23, 20, tzinfo=timezone.utc),
        priority=("NAM", "HRRR", "GFS"),
    )
    assert choice.model == "NAM"
    assert choice.files[0].name == "hysplit.t12z.namf"


def test_ensemble_workflow_does_not_download_hysplit_met():
    text = Path(__file__).resolve().parents[1].joinpath(".github/workflows/forecast.yml").read_text()
    assert 'SKIP_HYSPLIT: "1"' in text
    assert "install_hysplit.sh" not in text


def test_forecast_workflow_bounds_a_hung_snapshot():
    text = Path(__file__).resolve().parents[1].joinpath(".github/workflows/forecast.yml").read_text()
    assert "timeout-minutes: 20" in text
    assert "timeout-minutes: 10" in text
    assert "cancel-in-progress: true" in text
    assert "PYTHONUNBUFFERED" in text


def test_met_cap_rejects_the_oversized_gfs_forecast_before_a_download():
    enforce_met_cap(1000, "small.arl")
    try:
        enforce_met_cap(MAX_MET_BYTES + 1, "hysplit.t12z.gfsf")
    except RuntimeError as exc:
        assert "hysplit.t12z.gfsf" in str(exc)
        assert "cap" in str(exc)
    else:
        raise AssertionError("oversized file was accepted")


def test_download_stops_when_the_server_announces_a_huge_body(tmp_path: Path):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", str(MAX_MET_BYTES + 50_000_000))
            self.end_headers()
            try:
                self.wfile.write(b"x" * 1024)
            except Exception:
                pass

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        item = RemoteFile(name="huge.arl", day=__import__("datetime").date(2026, 11, 20), url=f"http://127.0.0.1:{port}/huge.arl")
        try:
            download(item, tmp_path)
        except RuntimeError as exc:
            assert "cap" in str(exc)
        else:
            raise AssertionError("huge download was stored")
        assert not (tmp_path / "huge.arl").exists()
        assert not (tmp_path / "huge.partial").exists()
    finally:
        server.shutdown()
