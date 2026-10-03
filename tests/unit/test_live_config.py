from __future__ import annotations

from pathlib import Path

from apps.api.seawatch.live.config import LiveRuntimeConfig
from apps.api.seawatch.live.resilience import PowerMode


def test_runtime_config_uses_secure_offline_safe_defaults() -> None:
    config = LiveRuntimeConfig.from_env({})

    assert config.cloud_stale_seconds == 30.0
    assert config.edge_stale_seconds == 30.0
    assert config.cloud_recovery_seconds == 20.0
    assert config.edge_host == "127.0.0.1"
    assert config.edge_port == 10110
    assert config.edge_ingest_enabled is False
    assert config.edge_replay_enabled is False
    assert config.edge_replay_file is None
    assert config.serve_web is False
    assert config.web_dist == Path("apps/web/dist")
    assert config.pmtiles_file is None
    assert config.power_mode is PowerMode.EXTERNAL
    assert config.offline_demo is False
    assert config.warnings == ()


def test_runtime_config_parses_explicit_edge_and_local_web_settings() -> None:
    config = LiveRuntimeConfig.from_env(
        {
            "SEAWATCH_LIVE_INGEST": "yes",
            "SEAWATCH_EDGE_INGEST": "true",
            "SEAWATCH_EDGE_HOST": "127.0.0.1",
            "SEAWATCH_EDGE_PORT": "12000",
            "SEAWATCH_EDGE_REPLAY_ENABLED": "1",
            "SEAWATCH_EDGE_REPLAY_FILE": "tests/fixtures/ais/edge_nmea.txt",
            "SEAWATCH_EDGE_REPLAY_INTERVAL_SECONDS": "0.25",
            "SEAWATCH_CLOUD_STALE_SECONDS": "45",
            "SEAWATCH_EDGE_STALE_SECONDS": "12.5",
            "SEAWATCH_CLOUD_RECOVERY_SECONDS": "8",
            "SEAWATCH_IDENTITY_KEY": "test-only-key",
            "SEAWATCH_POWER_MODE": "battery_ups",
            "SEAWATCH_OFFLINE_DEMO": "on",
            "SEAWATCH_RESILIENCE_DRILL_ENABLED": "true",
            "SEAWATCH_SERVE_WEB": "true",
            "SEAWATCH_WEB_DIST": "prepared/web",
            "SEAWATCH_PMTILES_FILE": "C:/maps/taiwan.pmtiles",
        }
    )

    assert config.live_ingest_enabled is True
    assert config.edge_ingest_enabled is True
    assert config.edge_port == 12000
    assert config.edge_replay_enabled is True
    assert config.edge_replay_file == Path("tests/fixtures/ais/edge_nmea.txt")
    assert config.edge_replay_interval_seconds == 0.25
    assert config.cloud_stale_seconds == 45.0
    assert config.edge_stale_seconds == 12.5
    assert config.cloud_recovery_seconds == 8.0
    assert config.identity_key == "test-only-key"
    assert config.power_mode is PowerMode.BATTERY_UPS
    assert config.offline_demo is True
    assert config.drill_enabled is True
    assert config.serve_web is True
    assert config.web_dist == Path("prepared/web")
    assert config.pmtiles_file == Path("C:/maps/taiwan.pmtiles")


def test_invalid_numeric_and_power_values_fall_back_with_unique_warnings() -> None:
    config = LiveRuntimeConfig.from_env(
        {
            "SEAWATCH_CLOUD_STALE_SECONDS": "nan",
            "SEAWATCH_EDGE_STALE_SECONDS": "-1",
            "SEAWATCH_CLOUD_RECOVERY_SECONDS": "infinity",
            "SEAWATCH_EDGE_REPLAY_INTERVAL_SECONDS": "0",
            "SEAWATCH_EDGE_PORT": "70000",
            "SEAWATCH_POWER_MODE": "solar_guess",
        }
    )

    assert config.cloud_stale_seconds == 30.0
    assert config.edge_stale_seconds == 30.0
    assert config.cloud_recovery_seconds == 20.0
    assert config.edge_replay_interval_seconds == 1.0
    assert config.edge_port == 10110
    assert config.power_mode is PowerMode.EXTERNAL
    assert len(config.warnings) == 6
    assert len(set(config.warnings)) == len(config.warnings)


def test_replay_needs_both_enable_flag_and_file() -> None:
    enabled_without_file = LiveRuntimeConfig.from_env(
        {"SEAWATCH_EDGE_REPLAY_ENABLED": "true"}
    )
    file_without_enable = LiveRuntimeConfig.from_env(
        {"SEAWATCH_EDGE_REPLAY_FILE": "fixture.txt"}
    )

    assert enabled_without_file.edge_replay_enabled is False
    assert any("replay file" in warning.lower() for warning in enabled_without_file.warnings)
    assert file_without_enable.edge_replay_enabled is False
    assert file_without_enable.warnings == ()


def test_non_loopback_bind_is_never_default_and_emits_one_warning() -> None:
    config = LiveRuntimeConfig.from_env({"SEAWATCH_EDGE_HOST": "0.0.0.0"})

    assert config.edge_host == "0.0.0.0"
    assert len(config.warnings) == 1
    assert "non-loopback" in config.warnings[0].lower()
