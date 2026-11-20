"""Fetch forecasts, run the ensemble, and append the archive."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from pipeline.archive import publish
from pipeline.config import UPDATE_UNTIL_UTC
from pipeline.ensemble import build_run
from pipeline.hysplit import check_hysplit
from pipeline.met import fetch_datasets
from pipeline.official import fetch_official
from pipeline.timeutil import stamp


def past_deadline(now: datetime | None = None) -> bool:
    moment = now or datetime.now(timezone.utc)
    deadline = datetime.fromisoformat(UPDATE_UNTIL_UTC)
    return moment.astimezone(timezone.utc) > deadline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Archive one IAAAP screening ensemble.")
    parser.add_argument("--out", default="web/public/runs", help="Directory that holds run history")
    parser.add_argument("--particles", type=int, default=None)
    parser.add_argument("--honor-deadline", action="store_true", help="Exit 0 after Nov 24 CT without a new run")
    parser.add_argument("--monitoring", default="data/monitoring.csv")
    args = parser.parse_args(argv)
    if args.honor_deadline and past_deadline():
        print(f"Update window ended {UPDATE_UNTIL_UTC}. No new run. Pass without --honor-deadline to override.")
        return 0
    print("Checking HYSPLIT…")
    hysplit = check_hysplit()
    print(hysplit["reason"])
    print("Fetching meteorology…")
    datasets, skipped = fetch_datasets()
    if not datasets:
        print("No meteorological datasets were downloaded.", file=sys.stderr)
        for item in skipped:
            print(f"  {item['label']} {item['cycle']}: {item['reason']}", file=sys.stderr)
        return 1
    print("Fetching official pages…")
    official = fetch_official(monitoring_path=Path(args.monitoring))
    reached = sum(1 for item in official["sources"] if item["status"] != "unavailable")
    print(f"Official sources with a response: {reached} of {len(official['sources'])}")
    kwargs = {}
    if args.particles is not None:
        kwargs["n_particles"] = args.particles
    print("Running ensemble…")
    run = build_run(datasets, official=official, skipped=skipped, hysplit_check=hysplit, **kwargs)
    # build_run also records datasets that do not cover the window. The npz
    # keeps every downloaded dataset, including ones the ensemble skipped.
    dest = publish(Path(args.out), run, datasets)
    receptor = run["receptor"]
    print(f"Archived {run['run_id']} → {dest}")
    print(f"Generated {run['generated_at_chicago']}")
    print(
        f"Fairfield airborne overlap: {receptor['air_hits']} of {receptor['n_members']} members. "
        f"Deposition overlap: {receptor['deposition_hits']} of {receptor['n_members']}."
    )
    print(run["narrative"])
    print("Engine:", run["engine"]["label"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
