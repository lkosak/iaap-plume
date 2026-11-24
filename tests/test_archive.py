import json
from datetime import datetime, timezone

from pipeline.archive import publish
from pipeline.encoding import unpack_u16
from pipeline.met import load_met, uniform_met
from pipeline.run_snapshot import past_deadline


def _run(run_id, hits):
    return {
        "run_id": run_id,
        "generated_at": run_id.replace("Z", "") and "2026-11-20T00:00:00Z",
        "generated_at_chicago": "Nov 20, 2026, 12:00 AM CT (America/Chicago)",
        "engine": {"label": "NOT HYSPLIT", "is_hysplit": False},
        "receptor": {"air_hits": hits, "deposition_hits": 0, "n_members": 4},
        "forecast": {"used": [{"label": "GFS", "cycle": "latest"}], "retrieved_at": "2026-11-20T00:00:00Z"},
    }


def test_history_is_kept_when_a_newer_run_is_published(tmp_path):
    dataset = uniform_met(1.0, 0.0)
    publish(tmp_path, _run("20261120T010000Z", 0), [dataset])
    publish(tmp_path, _run("20261120T020000Z", 2), [dataset])
    index = json.loads((tmp_path / "index.json").read_text())
    assert [item["id"] for item in index["runs"]] == ["20261120T010000Z", "20261120T020000Z"]
    assert (tmp_path / "20261120T010000Z" / "run.json").exists()
    assert (tmp_path / "20261120T010000Z" / "met.npz").exists()
    latest = json.loads((tmp_path / "latest.json").read_text())
    assert latest["run_id"] == "20261120T020000Z"
    assert latest["receptor"]["air_hits"] == 2
    loaded = load_met(tmp_path / "20261120T020000Z" / "met.npz")
    assert loaded[0].model_label == "Uniform"
    u, _, _, _ = loaded[0].sample([41.0], [-91.5], [50.0], int(loaded[0].times[0]))
    assert u[0] == 1.0


def test_republishing_an_id_does_not_duplicate_the_index(tmp_path):
    dataset = uniform_met(2.0, 0.0)
    publish(tmp_path, _run("20261120T030000Z", 1), [dataset])
    publish(tmp_path, _run("20261120T030000Z", 3), [dataset])
    index = json.loads((tmp_path / "index.json").read_text())
    assert len(index["runs"]) == 1
    assert index["runs"][0]["fairfield_air_hits"] == 3


def test_u16_roundtrip_keeps_the_no_arrival_flag():
    import numpy as np
    from pipeline.encoding import pack_u16

    values = np.array([0, 90, 65535], dtype=np.uint16)
    unpacked = unpack_u16(pack_u16(values), 3)
    assert list(unpacked) == [0, 90, 65535]


def test_deadline_stops_after_nov_27_chicago():
    assert past_deadline(datetime(2026, 11, 28, 7, tzinfo=timezone.utc)) is True
    assert past_deadline(datetime(2026, 11, 26, 7, tzinfo=timezone.utc)) is False
    assert past_deadline(datetime(2026, 11, 23, 18, tzinfo=timezone.utc)) is False
