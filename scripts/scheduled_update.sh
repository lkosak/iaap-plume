#!/usr/bin/env bash
# One forecast archive. Exits 0 without writing after 24 Nov 2026 CT.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
exec python3 -m pipeline.run_snapshot --out web/public/runs --honor-deadline
