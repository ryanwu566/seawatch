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
    datalastic_key: str | None = None,
    area_scan_signing_key: str | None = None,
    area_scan_operator_key: str | None = None,
    autoauth_loopback: str | None = None,
    allow_insecure_cookie: str | None = None,
    skip_web_build: bool = True,
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
    if not skip_web_build:
        npm = isolated_root / "npm.cmd"
        npm.write_text(
            "@echo off\r\n"
            "if defined DATALASTIC_API_KEY exit /b 41\r\n"
            "if defined SEAWATCH_AREA_SCAN_SIGNING_KEY exit /b 42\r\n"
            "if defined SEAWATCH_AREA_SCAN_OPERATOR_KEY exit /b 43\r\n"
            "if defined SEAWATCH_IDENTITY_KEY exit /b 44\r\n"
            "exit /b 0\r\n",
            encoding="utf-8",
        )

    environ = os.environ.copy()
    if identity_key is None:
        environ.pop("SEAWATCH_IDENTITY_KEY", None)
    else:
        environ["SEAWATCH_IDENTITY_KEY"] = identity_key
    if live_ingest is None:
        environ.pop("SEAWATCH_LIVE_INGEST", None)
    else:
        environ["SEAWATCH_LIVE_INGEST"] = live_ingest
    if datalastic_key is None:
        environ.pop("DATALASTIC_API_KEY", None)
    else:
        environ["DATALASTIC_API_KEY"] = datalastic_key
    if area_scan_signing_key is None:
        environ.pop("SEAWATCH_AREA_SCAN_SIGNING_KEY", None)
    else:
        environ["SEAWATCH_AREA_SCAN_SIGNING_KEY"] = area_scan_signing_key
    if area_scan_operator_key is None:
        environ.pop("SEAWATCH_AREA_SCAN_OPERATOR_KEY", None)
    else:
        environ["SEAWATCH_AREA_SCAN_OPERATOR_KEY"] = area_scan_operator_key
    if autoauth_loopback is None:
        environ.pop("SEAWATCH_AREA_SCAN_AUTOAUTH_LOOPBACK", None)
    else:
        environ["SEAWATCH_AREA_SCAN_AUTOAUTH_LOOPBACK"] = autoauth_loopback
    if allow_insecure_cookie is None:
        environ.pop("SEAWATCH_AREA_SCAN_ALLOW_INSECURE_COOKIE", None)
    else:
        environ["SEAWATCH_AREA_SCAN_ALLOW_INSECURE_COOKIE"] = allow_insecure_cookie
    if not skip_web_build:
        environ["PATH"] = str(isolated_root) + os.pathsep + environ.get("PATH", "")

    arguments = [
        str(POWERSHELL),
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(isolated_script),
        "-PreflightOnly",
    ]
    if skip_web_build:
        arguments.append("-SkipWebBuild")

    return subprocess.run(
        arguments,
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
    assert "Datalastic API key: not configured" in result.stdout
    assert identity_key not in result.stdout
    assert identity_key not in result.stderr


def test_demo_start_preserves_explicitly_disabled_live_ingest(tmp_path: Path) -> None:
    datalastic_key = "provider-test-key-not-for-output"
    result = _run_preflight(
        tmp_path,
        identity_key="stable-test-key",
        live_ingest="false",
        datalastic_key=datalastic_key,
    )

    assert result.returncode == 0, result.stderr
    assert "SEAWATCH_LIVE_INGEST=false (explicit configuration preserved)" in result.stdout
    assert "SEAWATCH_LIVE_INGEST=true" not in result.stdout
    assert "Datalastic API key: configured" in result.stdout
    assert datalastic_key not in result.stdout
    assert datalastic_key not in result.stderr


def test_demo_start_defaults_open_waters_off_when_datalastic_is_configured(
    tmp_path: Path,
) -> None:
    result = _run_preflight(
        tmp_path,
        identity_key="stable-test-key",
        live_ingest=None,
        datalastic_key="provider-test-key-not-for-output",
    )

    assert result.returncode == 0, result.stderr
    assert "Datalastic API key: configured" in result.stdout
    assert "SEAWATCH_LIVE_INGEST=false (Datalastic Area Scan default)" in result.stdout
    assert "SEAWATCH_LIVE_INGEST=true" not in result.stdout


def test_demo_start_reports_area_scan_access_without_printing_signing_key(
    tmp_path: Path,
) -> None:
    signing_key = "area-scan-signing-key-not-for-output"
    operator_key = "area-scan-operator-key-not-for-output"
    result = _run_preflight(
        tmp_path,
        identity_key="stable-test-key",
        live_ingest="false",
        datalastic_key="provider-test-key-not-for-output",
        area_scan_signing_key=signing_key,
        area_scan_operator_key=operator_key,
        allow_insecure_cookie="true",
    )

    assert result.returncode == 0, result.stderr
    assert "Area Scan operator session: configured" in result.stdout
    assert "Area Scan cookie: local HTTP opt-in enabled" in result.stdout
    assert signing_key not in result.stdout
    assert signing_key not in result.stderr
    assert operator_key not in result.stdout
    assert operator_key not in result.stderr


def test_demo_start_reports_area_scan_disabled_without_signing_key(
    tmp_path: Path,
) -> None:
    result = _run_preflight(
        tmp_path,
        identity_key="stable-test-key",
        live_ingest="false",
        datalastic_key="provider-test-key-not-for-output",
    )

    assert result.returncode == 0, result.stderr
    assert "Area Scan operator session: not configured (endpoint fails closed)" in result.stdout
    assert "Area Scan cookie: HTTPS required (secure default)" in result.stdout


def test_demo_start_accepts_explicit_loopback_autoauth_without_operator_key(
    tmp_path: Path,
) -> None:
    result = _run_preflight(
        tmp_path,
        identity_key="stable-test-key",
        live_ingest="false",
        datalastic_key="provider-test-key-not-for-output",
        area_scan_signing_key="signing-secret-not-for-output-32-bytes",
        autoauth_loopback="true",
    )

    assert result.returncode == 0, result.stderr
    assert "Area Scan loopback auto-auth: enabled" in result.stdout
    assert "Area Scan session: configured" in result.stdout


def test_demo_start_rejects_invalid_loopback_autoauth_setting(tmp_path: Path) -> None:
    result = _run_preflight(
        tmp_path,
        identity_key="stable-test-key",
        live_ingest="false",
        datalastic_key="provider-test-key-not-for-output",
        area_scan_signing_key="signing-secret-not-for-output-32-bytes",
        area_scan_operator_key="operator-secret-not-for-output-32-bytes",
        autoauth_loopback="sometimes",
    )

    assert result.returncode == 0, result.stderr
    assert "Area Scan loopback auto-auth: invalid (session fails closed)" in result.stdout
    assert "Area Scan operator session: not configured (endpoint fails closed)" in result.stdout


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


def test_demo_start_removes_backend_secrets_from_frontend_build_child(
    tmp_path: Path,
) -> None:
    result = _run_preflight(
        tmp_path,
        identity_key="stable-identity-secret-not-for-build",
        live_ingest="false",
        datalastic_key="provider-secret-not-for-build",
        area_scan_signing_key="signing-secret-not-for-build-32-bytes",
        area_scan_operator_key="operator-secret-not-for-build-32-bytes",
        allow_insecure_cookie="true",
        skip_web_build=False,
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert "SeaWatch demo preflight passed." in result.stdout


def test_example_environment_keeps_loopback_autoauth_disabled_by_default() -> None:
    lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    settings = dict(
        line.split("=", 1)
        for line in lines
        if line and not line.startswith("#")
    )

    assert settings["DATALASTIC_API_KEY"] == ""
    assert settings["SEAWATCH_AREA_SCAN_AUTOAUTH_LOOPBACK"] == "false"
    assert settings["SEAWATCH_HISTORICAL_RUNTIME"] == ""
    assert settings["SEAWATCH_DATA_ROOT"] == ""
