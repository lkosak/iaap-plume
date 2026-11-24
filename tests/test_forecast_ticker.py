"""The forecast ticker dispatches on a cadence and hands off before the job limit."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "forecast_ticker.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "forecast-ticker.yml"
FORECAST = ROOT / ".github" / "workflows" / "forecast.yml"


def _run(mode, handoff="false", interval="2", budget="5", deadline="2026-11-28 06:00:00 UTC", others="0"):
    log = Path(os.environ.get("TMPDIR", "/tmp")) / f"ticker-{mode}-{os.getpid()}.log"
    if log.exists():
        log.unlink()
    env = os.environ.copy()
    env.update(
        {
            "MODE": mode,
            "HANDOFF": handoff,
            "INTERVAL_SECONDS": interval,
            "HANDOFF_SECONDS": budget,
            "TICKER_DEADLINE": deadline,
            "GITHUB_REPOSITORY": "lkosak/iaap-plume",
            "GITHUB_RUN_ID": "42",
            "GITHUB_OUTPUT": str(log) + ".out",
            "GH_TOKEN": "test-token",
            "GH_LOG": str(log),
            "MOCK_OTHERS": others,
            "PATH": f"{ROOT / 'tests' / 'bin'}:{env['PATH']}",
        }
    )
    Path(env["GITHUB_OUTPUT"]).write_text("")
    completed = subprocess.run(
        ["bash", str(SCRIPT), "run"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    calls = log.read_text() if log.exists() else ""
    assert completed.returncode == 0, completed.stderr
    return completed.stdout, calls


def test_a_closed_window_does_not_dispatch_anything():
    stdout, calls = _run("live", deadline="2020-01-01 00:00:00 UTC")
    assert "Stopping" in stdout
    assert "workflow run" not in calls


def test_dry_run_child_proves_the_handoff_without_a_forecast():
    stdout, calls = _run("dry-run-child")
    assert "Self-redispatch works" in stdout
    assert "workflow run" not in calls


def test_dry_run_dispatches_only_a_successor():
    stdout, calls = _run("dry-run", interval="1", budget="30")
    assert "would dispatch forecast.yml" in stdout
    assert "forecast-ticker.yml" in calls
    assert "mode=dry-run-child" in calls
    assert "handoff=true" in calls
    assert "forecast.yml" not in calls


def test_live_mode_dispatches_forecasts_then_the_next_ticker():
    stdout, calls = _run("live", interval="1", budget="3")
    assert calls.count("workflow run forecast.yml") >= 2
    assert "mode=live" in calls
    assert "handoff=true" in calls
    assert "Next forecast dispatch around" in stdout or "Dispatching forecast.yml" in stdout


def test_gate_exits_when_another_ticker_is_running(tmp_path):
    output = tmp_path / "out"
    env = os.environ.copy()
    env.update(
        {
            "MODE": "live",
            "HANDOFF": "false",
            "GITHUB_REPOSITORY": "lkosak/iaap-plume",
            "GITHUB_RUN_ID": "7",
            "GITHUB_OUTPUT": str(output),
            "GH_TOKEN": "test-token",
            "MOCK_OTHERS": "1",
            "GH_LOG": str(tmp_path / "gh.log"),
            "PATH": f"{ROOT / 'tests' / 'bin'}:{env['PATH']}",
        }
    )
    completed = subprocess.run(
        ["bash", str(SCRIPT), "gate"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "proceed=false" in output.read_text()
    assert "already in progress" in completed.stdout


def test_gate_lets_the_successor_through_while_one_is_running(tmp_path):
    output = tmp_path / "out"
    env = os.environ.copy()
    env.update(
        {
            "MODE": "live",
            "HANDOFF": "true",
            "GITHUB_REPOSITORY": "lkosak/iaap-plume",
            "GITHUB_RUN_ID": "7",
            "GITHUB_OUTPUT": str(output),
            "GH_TOKEN": "test-token",
            "MOCK_OTHERS": "1",
            "GH_LOG": str(tmp_path / "gh.log"),
            "PATH": f"{ROOT / 'tests' / 'bin'}:{env['PATH']}",
        }
    )
    completed = subprocess.run(
        ["bash", str(SCRIPT), "gate"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "proceed=true" in output.read_text()


def test_workflow_keeps_one_ticker_and_forecast_keeps_its_cron():
    ticker = WORKFLOW.read_text()
    forecast = FORECAST.read_text()
    assert "actions: write" in ticker
    assert "contents: read" in ticker
    assert "cancel-in-progress: false" in ticker
    assert "forecast-ticker" in ticker
    assert 'cron: "25 */2 * * *"' in ticker
    assert "2026-11-28 06:00:00 UTC" in (ROOT / "scripts" / "forecast_ticker.sh").read_text()
    assert 'cron: "10 */2 * * *"' in forecast
    assert "cancel-in-progress: true" in forecast
