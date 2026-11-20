from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_assumptions_name_the_places_and_the_models():
    text = (ROOT / "ASSUMPTIONS.md").read_text()
    assert "40.7858281" in text
    assert "41.00761" in text
    assert "-91.96369" in text
    assert "ncep_hrrr_conus" in text
    assert "ncep_rrfs_conus" in text
    assert "gfs_seamless" in text
    assert "0.00015" in text
    assert "NOT HYSPLIT" in text


def test_limitations_are_plain_and_do_not_promise_safety():
    text = (ROOT / "LIMITATIONS.md").read_text().lower()
    assert "not a measurement" in text
    assert "hysplit" in text
    assert "official" in text
    assert "unsafe" not in text
    assert "safe" not in text
