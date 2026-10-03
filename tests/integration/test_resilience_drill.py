from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


SCRIPT = Path("scripts/resilience_drill.py")


def _run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )


def test_drill_refuses_to_run_without_explicit_simulation_flag() -> None:
    result = _run()

    assert result.returncode != 0
    assert "--enable-simulation" in result.stderr


def test_drill_uses_real_policy_for_exact_labeled_seven_stage_sequence(
    tmp_path: Path,
) -> None:
    output = tmp_path / "drill.json"
    env = {**os.environ, "SEAWATCH_CLOUD_RECOVERY_SECONDS": "7"}

    result = _run("--enable-simulation", "--json-output", str(output), env=env)

    assert result.returncode == 0, result.stderr
    records = json.loads(output.read_text(encoding="utf-8"))
    assert [record["stage"] for record in records] == [
        "cloud_live",
        "cloud_outage",
        "explicit_replay",
        "edge_replay",
        "cloud_restored_held",
        "recovery_elapsed",
        "cloud_live_restored",
    ]
    assert [record["mode"] for record in records] == [
        "CLOUD_LIVE",
        "NO_LIVE_SOURCE",
        "NO_LIVE_SOURCE",
        "EDGE_REPLAY",
        "EDGE_REPLAY",
        "EDGE_REPLAY",
        "CLOUD_LIVE",
    ]
    assert records[5]["elapsed_seconds"] == 7.0
    assert records[-1]["recovery_seconds"] == 7.0
    assert all(record["simulated"] is True for record in records)
    assert all(record["label"].startswith("SIMULATED") for record in records)
    assert all(record["mode"] != "EDGE_LIVE" for record in records)
    assert records[2]["decoded_observations"] > 0
    assert records[2]["stored_vessels"] > 0
    assert "SIMULATED" in result.stdout


def test_drill_has_no_runtime_socket_or_server_control_surface() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "get_live_runtime" not in source
    assert "socket" not in source
    assert "FastAPI" not in source
