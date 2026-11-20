"""Keep every run on disk. Later runs do not replace earlier ones."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from pipeline.met import MetDataset, load_met, save_met


def _json_default(value):
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, default=_json_default) + "\n")
    temporary.replace(path)


def summary_for(run: dict) -> dict:
    receptor = run.get("receptor") or {}
    forecast = run.get("forecast") or {}
    return {
        "id": run["run_id"],
        "generated_at": run.get("generated_at"),
        "generated_at_chicago": run.get("generated_at_chicago"),
        "engine_label": (run.get("engine") or {}).get("label"),
        "is_hysplit": bool((run.get("engine") or {}).get("is_hysplit")),
        "models": [item.get("label") + " " + item.get("cycle", "") for item in forecast.get("used", [])],
        "fairfield_air_hits": receptor.get("air_hits"),
        "fairfield_deposition_hits": receptor.get("deposition_hits"),
        "n_members": receptor.get("n_members"),
        "forecast_retrieved_at": forecast.get("retrieved_at"),
        "forecast_retrieved_at_chicago": forecast.get("retrieved_at_chicago"),
    }


def publish(out_dir: Path, run: dict, datasets: list[MetDataset]) -> Path:
    out_dir = Path(out_dir)
    run_id = run["run_id"]
    dest = out_dir / run_id
    dest.mkdir(parents=True, exist_ok=True)
    save_met(dest / "met.npz", datasets)
    _write_json(dest / "run.json", run)
    index_path = out_dir / "index.json"
    if index_path.exists():
        index = json.loads(index_path.read_text())
    else:
        index = {"runs": []}
    runs = [item for item in index.get("runs", []) if item.get("id") != run_id]
    runs.append(summary_for(run))
    runs.sort(key=lambda item: item["id"])
    latest_id = runs[-1]["id"]
    index = {
        "updated_at": run.get("generated_at"),
        "updated_at_chicago": run.get("generated_at_chicago"),
        "latest_id": latest_id,
        "runs": runs,
    }
    _write_json(index_path, index)
    if latest_id == run_id:
        _write_json(out_dir / "latest.json", run)
    else:
        latest_run = json.loads((out_dir / latest_id / "run.json").read_text())
        _write_json(out_dir / "latest.json", latest_run)
    # Touch the npz through the public loader so a corrupt write fails here.
    load_met(dest / "met.npz")
    return dest
