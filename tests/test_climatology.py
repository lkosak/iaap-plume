import json
from pathlib import Path

from scripts.wind_climatology import angle_difference, sector_name, summarize

ROOT = Path(__file__).resolve().parents[1]


def test_toward_fairfield_sector_is_ese():
    assert sector_name(112.4) == "ESE"
    assert round(angle_difference(90, 112.4), 1) == 22.4
    assert angle_difference(10, 350) == 20


def test_committed_climatology_matches_the_sanity_check():
    document = json.loads((ROOT / "web" / "public" / "climatology.json").read_text())
    assert document["title"] == "Historical wind context (climatology, not a forecast)"
    assert document["not_a_forecast"] is True
    level = document["era5_10m"]
    assert level["toward_fairfield_22_5_pct"] == 6.6
    assert level["toward_fairfield_45_pct"] == 14.6
    assert level["calm_pct"] == 2.2
    assert level["prevailing"][0] == {"sector": "WNW", "from_deg": 292.5, "pct": 12.1}
    assert level["full_window_22_5_pct_of_days"] == 4.4
    assert level["full_window_45_pct_of_days"] == 10.7
    assert document["kbrl"]["toward_fairfield_22_5_pct"] == 6.7
    assert document["kbrl"]["toward_fairfield_45_pct"] == 11.9
    highlighted = [item["sector"] for item in level["rose"] if item["toward_fairfield"]]
    assert highlighted == ["ESE"]


def test_summarize_counts_a_full_window_only_when_every_hour_qualifies():
    samples = []
    for hour_offset, direction in enumerate((112.0, 112.0, 112.0, 112.0, 200.0)):
        samples.append(("2000-11-09", 3.0, direction))
    for direction in (112.0, 112.0, 112.0, 112.0, 112.0):
        samples.append(("2000-11-10", 3.0, direction))
    result = summarize(samples, calm_below=1.0)
    assert result["n_days"] == 2
    assert result["full_window_22_5_pct_of_days"] == 50.0
    assert result["toward_fairfield_22_5_pct"] == 90.0


def test_forecast_workflow_does_not_rerun_climatology():
    text = (ROOT / ".github" / "workflows" / "forecast.yml").read_text()
    assert "wind_climatology" not in text
    assert "climatology.json" not in text
