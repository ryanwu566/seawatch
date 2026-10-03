"""Validated environment configuration for live resilience features."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .resilience import PowerMode


_TRUE_VALUES = {"1", "true", "yes", "on"}
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _enabled(value: str | None) -> bool:
    return bool(value and value.strip().lower() in _TRUE_VALUES)


def _positive_float(
    environ: Mapping[str, str],
    name: str,
    default: float,
    warnings: list[str],
) -> float:
    raw = environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        value = math.nan
    if not math.isfinite(value) or value <= 0:
        warnings.append(f"{name} must be a positive finite number; using {default}")
        return default
    return value


def _port(
    environ: Mapping[str, str],
    name: str,
    default: int,
    warnings: list[str],
) -> int:
    raw = environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if not 1 <= value <= 65535:
        warnings.append(f"{name} must be between 1 and 65535; using {default}")
        return default
    return value


@dataclass(frozen=True)
class LiveRuntimeConfig:
    live_ingest_enabled: bool
    edge_ingest_enabled: bool
    edge_host: str
    edge_port: int
    edge_replay_enabled: bool
    edge_replay_file: Path | None
    edge_replay_interval_seconds: float
    cloud_stale_seconds: float
    edge_stale_seconds: float
    cloud_recovery_seconds: float
    identity_key: str | None
    power_mode: PowerMode
    offline_demo: bool
    drill_enabled: bool
    serve_web: bool
    web_dist: Path
    pmtiles_file: Path | None
    warnings: tuple[str, ...]

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> "LiveRuntimeConfig":
        values = os.environ if environ is None else environ
        warnings: list[str] = []

        host = values.get("SEAWATCH_EDGE_HOST", "127.0.0.1").strip() or "127.0.0.1"
        if host.lower() not in _LOOPBACK_HOSTS:
            warnings.append(
                "SEAWATCH_EDGE_HOST uses a non-loopback address; local NMEA ingest is unauthenticated"
            )

        replay_file_text = values.get("SEAWATCH_EDGE_REPLAY_FILE", "").strip()
        replay_file = Path(replay_file_text) if replay_file_text else None
        replay_enabled = _enabled(values.get("SEAWATCH_EDGE_REPLAY_ENABLED"))
        if replay_enabled and replay_file is None:
            replay_enabled = False
            warnings.append(
                "SEAWATCH_EDGE_REPLAY_ENABLED requires a replay file; replay remains disabled"
            )

        power_text = values.get("SEAWATCH_POWER_MODE", PowerMode.EXTERNAL.value).strip().lower()
        try:
            power_mode = PowerMode(power_text)
        except ValueError:
            power_mode = PowerMode.EXTERNAL
            warnings.append(
                "SEAWATCH_POWER_MODE must be external or battery_ups; using external"
            )

        pmtiles_text = values.get("SEAWATCH_PMTILES_FILE", "").strip()
        identity_text = values.get("SEAWATCH_IDENTITY_KEY", "").strip()

        return cls(
            live_ingest_enabled=_enabled(values.get("SEAWATCH_LIVE_INGEST")),
            edge_ingest_enabled=_enabled(values.get("SEAWATCH_EDGE_INGEST")),
            edge_host=host,
            edge_port=_port(values, "SEAWATCH_EDGE_PORT", 10110, warnings),
            edge_replay_enabled=replay_enabled,
            edge_replay_file=replay_file,
            edge_replay_interval_seconds=_positive_float(
                values,
                "SEAWATCH_EDGE_REPLAY_INTERVAL_SECONDS",
                1.0,
                warnings,
            ),
            cloud_stale_seconds=_positive_float(
                values, "SEAWATCH_CLOUD_STALE_SECONDS", 30.0, warnings
            ),
            edge_stale_seconds=_positive_float(
                values, "SEAWATCH_EDGE_STALE_SECONDS", 30.0, warnings
            ),
            cloud_recovery_seconds=_positive_float(
                values, "SEAWATCH_CLOUD_RECOVERY_SECONDS", 20.0, warnings
            ),
            identity_key=identity_text or None,
            power_mode=power_mode,
            offline_demo=_enabled(values.get("SEAWATCH_OFFLINE_DEMO")),
            drill_enabled=_enabled(values.get("SEAWATCH_RESILIENCE_DRILL_ENABLED")),
            serve_web=_enabled(values.get("SEAWATCH_SERVE_WEB")),
            web_dist=Path(values.get("SEAWATCH_WEB_DIST", "apps/web/dist")),
            pmtiles_file=Path(pmtiles_text) if pmtiles_text else None,
            warnings=tuple(warnings),
        )
