#!/usr/bin/env bash
# Install the public unregistered HYSPLIT Linux build.
# The tarball URL is NOAA's published file. The email acknowledgement is not stored.
set -euo pipefail
ROOT="${HYSPLIT_HOME:-/opt/hysplit}"
URL="https://www.ready.noaa.gov/data/web/models/hysplit4/linux_trial/hysplit.v5.4.2_x86_64_public.tar.gz"
SHA="1e2de556b5794749c950770218751ab863d9f2ce"
mkdir -p "$ROOT"
if [[ -x "$ROOT/exec/hyts_std" && -x "$ROOT/exec/hycs_std" ]]; then
  echo "HYSPLIT already installed at $ROOT"
else
  tmp="$(mktemp)"
  if ! curl -L --fail --retry 3 -o "$tmp" "$URL"; then
    echo "HYSPLIT download failed. The screening run can continue without trajectories."
    rm -f "$tmp"
    exit 0
  fi
  echo "$SHA  $tmp" | sha1sum -c -
  tar -xzf "$tmp" -C "$ROOT"
  rm -f "$tmp"
  hyts="$(find "$ROOT" -type f -name hyts_std -print -quit)"
  if [[ -z "$hyts" ]]; then
    echo "hyts_std was not in the tarball."
    exit 0
  fi
  mkdir -p "$ROOT/exec"
  for name in hyts_std hycs_std con2asc; do
    found="$(find "$ROOT" -type f -name "$name" -print -quit || true)"
    if [[ -n "$found" ]]; then
      chmod +x "$found"
      ln -sfn "$found" "$ROOT/exec/$name"
    fi
  done
fi
if [[ -n "${GITHUB_ENV:-}" ]]; then
  echo "HYSPLIT_HOME=$ROOT" >> "$GITHUB_ENV"
  echo "HYSPLIT_EXEC=$ROOT/exec/hyts_std" >> "$GITHUB_ENV"
fi
echo "HYSPLIT_EXEC=$ROOT/exec/hyts_std"
