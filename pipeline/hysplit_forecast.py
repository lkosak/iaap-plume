"""Attach real HYSPLIT trajectories without blocking the ensemble archive.

The screening job sets SKIP_HYSPLIT=1. This command downloads the smallest
ARL forecast that covers 16:00–20:00 UTC on 23 November 2026 (10 AM–2 PM CT),
in the order NAM 12 km, HRRR, then the 1-degree GFS file, and writes the
trajectories onto the newest archived run.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipeline.config import EVENT_DATE, HYSPLIT_TRAJECTORY_LABEL
from pipeline.hysplit_traj import build_trajectories
from pipeline.timeutil import iso

# 10:00 AM–2:00 PM CT on the event date, fixed as 16:00–20:00 UTC.
RELEASE_WINDOW_START = datetime(EVENT_DATE.year, EVENT_DATE.month, EVENT_DATE.day, 16, tzinfo=timezone.utc)
RELEASE_WINDOW_END = RELEASE_WINDOW_START + timedelta(hours=4)
# Large enough for the ~1.4 GB GFS file and a NAM 12 km file. Not for a 10 GB HRRR bundle.
DEDICATED_MAX_BYTES = 2 * 1024 * 1024 * 1024
DEDICATED_DEADLINE_SECONDS = 18 * 60
PRIORITY = ("NAM", "HRRR", "GFS")


def compute(met_dir: Path) -> dict:
    product = build_trajectories(
        met_dir,
        priority=PRIORITY,
        max_bytes=DEDICATED_MAX_BYTES,
        deadline_seconds=DEDICATED_DEADLINE_SECONDS,
        need_start=RELEASE_WINDOW_START,
        need_end=RELEASE_WINDOW_END,
    )
    product["attached_at"] = iso(datetime.now(timezone.utc))
    if product.get("real_hysplit"):
        tuesday = (product.get("by_day") or {}).get("2026-11-24") or {}
        day_note = (
            "Paths are included for Monday Nov 23 and Tuesday Nov 24."
            if tuesday.get("real_hysplit")
            else "Paths are for Monday Nov 23. " + (tuesday.get("reason") or "Tuesday was not run.")
        )
        product["note"] = (
            f"{HYSPLIT_TRAJECTORY_LABEL}. "
            f"Meteorology: {product['met']['model']} cycle {product['met']['cycle']} "
            f"({', '.join(product['met']['files'])}). "
            f"{day_note} "
            "These are trajectories, not concentrations and not measurements of lead. "
            "The colored screening footprint stays labeled NOT HYSPLIT."
        )
    return product


def attach(out_dir: Path, product: dict) -> str:
    latest_path = out_dir / "latest.json"
    run = json.loads(latest_path.read_text())
    run_id = run["run_id"]
    run["hysplit"] = product
    text = json.dumps(run, indent=2) + "\n"
    run_path = out_dir / run_id / "run.json"
    run_path.write_text(text)
    latest_path.write_text(text)
    print(f"attached HYSPLIT status={product.get('status')} to {run_id}", flush=True)
    return run_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download ARL met and attach HYSPLIT trajectories.")
    parser.add_argument("--out", default="web/public/runs")
    parser.add_argument("--met-dir", default="data/arl")
    parser.add_argument("--compute", help="Write the trajectory product JSON and do not touch the archive")
    parser.add_argument("--attach", help="Attach a previously computed product JSON to the newest run")
    args = parser.parse_args(argv)
    if args.attach:
        product = json.loads(Path(args.attach).read_text())
        attach(Path(args.out), product)
        return 0 if product.get("real_hysplit") else 0
    product = compute(Path(args.met_dir))
    print(product.get("status"), product.get("reason", ""), flush=True)
    met = product.get("met") or {}
    print(f"met {met.get('model')} {met.get('cycle')} {met.get('files')}", flush=True)
    if args.compute:
        path = Path(args.compute)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(product) + "\n")
        print(f"wrote {path}", flush=True)
        return 0
    attach(Path(args.out), product)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
