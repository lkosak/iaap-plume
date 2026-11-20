#!/usr/bin/env bash
# Install, test, archive a forecast if needed, and serve the dashboard.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
python3 -m pip install --user -r requirements.txt
python3 -m pytest -q
if [[ ! -f web/public/runs/latest.json ]]; then
  python3 -m pipeline.run_snapshot --out web/public/runs
fi
cd web
if [[ ! -d node_modules ]]; then
  npm ci
fi
exec npm run dev
