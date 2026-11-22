#!/usr/bin/env bash
# Keep Forecast archive refreshing every 2 hours without relying on GitHub cron.
# A job cannot run for the whole window (the limit is 6 hours), so this process
# dispatches forecast.yml on a 2-hour cadence and, before it exits, dispatches
# the next ticker. The chain stops after 2026-11-25 06:00Z.
set -euo pipefail

MODE="${MODE:-live}"
HANDOFF="${HANDOFF:-false}"
INTERVAL="${INTERVAL_SECONDS:-7200}"
BUDGET="${HANDOFF_SECONDS:-20400}"
DEADLINE="${TICKER_DEADLINE:-2026-11-25 06:00:00 UTC}"
REPO="${GITHUB_REPOSITORY:-lkosak/iaap-plume}"
RUN_ID="${GITHUB_RUN_ID:-0}"

deadline_epoch="$(date -u -d "$DEADLINE" +%s)"

log() {
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*"
}

window_open() {
  [ "$(date -u +%s)" -lt "$deadline_epoch" ]
}

others_in_progress() {
  gh api "repos/${REPO}/actions/workflows/forecast-ticker.yml/runs?status=in_progress&per_page=20" \
    --jq "[.workflow_runs[] | select(.id != ${RUN_ID})] | length"
}

write_output() {
  local key="$1"
  local value="$2"
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    echo "${key}=${value}" >> "$GITHUB_OUTPUT"
  else
    echo "${key}=${value}"
  fi
}

dispatch_forecast() {
  if ! window_open; then
    log "Past ${DEADLINE}. Not dispatching Forecast archive."
    return 1
  fi
  if [ "$MODE" = "dry-run" ]; then
    log "DRY-RUN would dispatch forecast.yml"
    return 0
  fi
  log "Dispatching forecast.yml"
  gh workflow run forecast.yml --ref main
}

dispatch_next() {
  if ! window_open; then
    log "Past ${DEADLINE}. Not continuing the ticker chain."
    return 0
  fi
  if [ "$MODE" = "dry-run" ]; then
    log "DRY-RUN dispatching the successor ticker"
    gh workflow run forecast-ticker.yml --ref main -f mode=dry-run-child -f handoff=true
    return 0
  fi
  log "Dispatching the next ticker"
  gh workflow run forecast-ticker.yml --ref main -f mode=live -f handoff=true
}

gate() {
  if ! window_open; then
    log "Past ${DEADLINE}. Not starting a ticker."
    write_output proceed false
    return 0
  fi
  # The successor is dispatched while this job is still in progress, so it
  # must be allowed through. Concurrency on the long job then waits until
  # this one exits. Any other start, while a ticker is running, leaves.
  if [ "$HANDOFF" = "true" ] || [ "$MODE" = "dry-run-child" ]; then
    log "Successor start (mode=${MODE})."
    write_output proceed true
    return 0
  fi
  local others="0"
  if [ -n "${GH_TOKEN:-}" ]; then
    others="$(others_in_progress)"
  fi
  if [ "${others:-0}" != "0" ]; then
    log "Another ticker is already in progress (${others}). Exiting."
    write_output proceed false
    return 0
  fi
  log "No ticker is in progress. Starting."
  write_output proceed true
}

run_ticker() {
  log "Ticker mode=${MODE} interval=${INTERVAL}s budget=${BUDGET}s deadline=${DEADLINE} run=${RUN_ID}"
  if ! window_open; then
    log "Past ${DEADLINE}. Stopping."
    return 0
  fi
  if [ "$MODE" = "dry-run-child" ]; then
    log "Dry-run successor is running. Self-redispatch works. Not dispatching a forecast and not continuing."
    return 0
  fi

  local started next_at elapsed
  started="$(date -u +%s)"
  dispatch_forecast
  if [ "$MODE" = "dry-run" ]; then
    log "DRY-RUN sleeping ${INTERVAL}s before the successor dispatch"
    sleep "$INTERVAL"
    dispatch_next
    return 0
  fi

  while true; do
    elapsed="$(( $(date -u +%s) - started ))"
    if [ $((elapsed + INTERVAL)) -gt "$BUDGET" ]; then
      local rest="$((BUDGET - elapsed))"
      if [ "$rest" -gt 0 ]; then
        log "Sleeping ${rest}s until the handoff"
        sleep "$rest"
      fi
      break
    fi
    next_at="$(( $(date -u +%s) + INTERVAL ))"
    if [ "$next_at" -ge "$deadline_epoch" ]; then
      log "The next refresh would be after ${DEADLINE}. Stopping the chain."
      return 0
    fi
    log "Sleeping ${INTERVAL}s. Next forecast dispatch around $(date -u -d "@${next_at}" +%Y-%m-%dT%H:%M:%SZ)"
    sleep "$INTERVAL"
    dispatch_forecast
  done
  dispatch_next
}

case "${1:-run}" in
  gate) gate ;;
  run) run_ticker ;;
  *) echo "usage: forecast_ticker.sh gate|run" >&2; exit 2 ;;
esac
