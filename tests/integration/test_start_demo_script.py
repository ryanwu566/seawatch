from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "start_demo.ps1"
POWERSHELL = shutil.which("powershell.exe") or shutil.which("pwsh")


pytestmark = pytest.mark.skipif(
    os.name != "nt" or POWERSHELL is None,
    reason="Windows PowerShell is required to exercise start_demo.ps1",
)


def _run_preflight(
    tmp_path: Path,
    *,
    identity_key: str | None,
    live_ingest: str | None,
):
    isolated_root = tmp_path / "demo-repo"
    isolated_script = isolated_root / "start_demo.ps1"
    python = isolated_root / ".venv" / "Scripts" / "python.exe"
    web_index = isolated_root / "apps" / "web" / "dist" / "index.html"
    python.parent.mkdir(parents=True)
    web_index.parent.mkdir(parents=True)
    python.touch()
    web_index.write_text('<div id="root"></div>', encoding="utf-8")
    shutil.copy2(SCRIPT, isolated_script)

    environ = os.environ.copy()
    if identity_key is None:
        environ.pop("SEAWATCH_IDENTITY_KEY", None)
    else:
        environ["SEAWATCH_IDENTITY_KEY"] = identity_key
    if live_ingest is None:
        environ.pop("SEAWATCH_LIVE_INGEST", None)
    else:
        environ["SEAWATCH_LIVE_INGEST"] = live_ingest

    return subprocess.run(
        [
            str(POWERSHELL),
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(isolated_script),
            "-PreflightOnly",
            "-SkipWebBuild",
        ],
        cwd=isolated_root,
        env=environ,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )


def test_demo_start_defaults_anonymous_live_ingest_only_when_unconfigured(
    tmp_path: Path,
) -> None:
    identity_key = "stable-test-key-not-for-output"
    result = _run_preflight(
        tmp_path,
        identity_key=identity_key,
        live_ingest=None,
    )

    assert result.returncode == 0, result.stderr
    assert "SEAWATCH_LIVE_INGEST=true (demo default)" in result.stdout
    assert identity_key not in result.stdout
    assert identity_key not in result.stderr


def test_demo_start_preserves_explicitly_disabled_live_ingest(tmp_path: Path) -> None:
    result = _run_preflight(
        tmp_path,
        identity_key="stable-test-key",
        live_ingest="false",
    )

    assert result.returncode == 0, result.stderr
    assert "SEAWATCH_LIVE_INGEST=false (explicit configuration preserved)" in result.stdout
    assert "SEAWATCH_LIVE_INGEST=true" not in result.stdout


def test_demo_start_requires_supplied_identity_key_without_generating_one(
    tmp_path: Path,
) -> None:
    result = _run_preflight(
        tmp_path,
        identity_key=None,
        live_ingest="false",
    )

    assert result.returncode != 0
    combined = f"{result.stdout}\n{result.stderr}"
    assert "SEAWATCH_IDENTITY_KEY" in combined
    assert "same stable key" in combined
    assert "generated" not in combined.casefold()
