from __future__ import annotations

import base64
import json

import pytest

from apps.api.seawatch.live import area_scan_access as access


SIGNING_KEY = "operator-signing-secret-at-least-32-bytes"
OPERATOR_CREDENTIAL = "operator-login-secret-at-least-32-bytes"


def _tamper_scope(token: str) -> str:
    encoded_payload, encoded_signature = token.split(".")
    padded = encoded_payload + "=" * (-len(encoded_payload) % 4)
    payload = json.loads(base64.urlsafe_b64decode(padded))
    payload["scope"] = "other"
    changed = base64.urlsafe_b64encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    return f"{changed}.{encoded_signature}"


def test_capability_is_scoped_signed_and_expires() -> None:
    config = access.AreaScanAccessConfig(
        signing_key=SIGNING_KEY,
        operator_credential=OPERATOR_CREDENTIAL,
    )
    token = access.mint_area_scan_capability(
        config,
        now=1_000,
        ttl_seconds=60,
        nonce="test-nonce",
    )

    assert access.verify_area_scan_capability(token, config, now=1_059) is True
    assert access.verify_area_scan_capability(token, config, now=1_060) is False
    assert (
        access.verify_area_scan_capability(
            token,
            access.AreaScanAccessConfig(
                signing_key="wrong-key-that-is-at-least-32-bytes",
                operator_credential=OPERATOR_CREDENTIAL,
            ),
            now=1_001,
        )
        is False
    )
    assert access.verify_area_scan_capability(_tamper_scope(token), config, now=1_001) is False
    assert SIGNING_KEY not in token
    assert SIGNING_KEY not in repr(config)


def test_operator_credential_is_verified_constant_time_and_hidden() -> None:
    config = access.AreaScanAccessConfig(
        signing_key=SIGNING_KEY,
        operator_credential=OPERATOR_CREDENTIAL,
    )

    assert access.verify_operator_credential(OPERATOR_CREDENTIAL, config) is True
    assert access.verify_operator_credential("incorrect-operator-credential", config) is False
    assert OPERATOR_CREDENTIAL not in repr(config)


@pytest.mark.parametrize("token", ["", "not-a-token", "a.b.c", "@@.@@"])
def test_malformed_capability_fails_closed(token: str) -> None:
    config = access.AreaScanAccessConfig(
        signing_key=SIGNING_KEY,
        operator_credential=OPERATOR_CREDENTIAL,
    )
    assert access.verify_area_scan_capability(token, config, now=1_000) is False


def test_admission_atomically_limits_scans_and_provider_requests() -> None:
    now = [100.0]
    gate = access.AreaScanAdmissionController(
        max_scans=2,
        max_provider_requests=5,
        window_seconds=60.0,
        monotonic=lambda: now[0],
    )

    gate.authorize(provider_requests=2)
    gate.authorize(provider_requests=2)
    with pytest.raises(access.AreaScanAdmissionError) as scan_error:
        gate.authorize(provider_requests=1)
    assert scan_error.value.retry_after_seconds == 60

    assert gate.snapshot() == {"scans": 2, "provider_requests": 4}

    now[0] = 160.1
    gate.authorize(provider_requests=5)
    assert gate.snapshot() == {"scans": 1, "provider_requests": 5}


def test_invalid_access_limits_disable_admission_instead_of_opening_it() -> None:
    config = access.AreaScanAccessConfig.from_env(
        {
            "SEAWATCH_AREA_SCAN_SIGNING_KEY": SIGNING_KEY,
            "SEAWATCH_AREA_SCAN_OPERATOR_KEY": OPERATOR_CREDENTIAL,
            "SEAWATCH_AREA_SCAN_MAX_SCANS_PER_MINUTE": "not-a-number",
        }
    )

    assert config.configured is False
    assert config.max_scans_per_window == access.DEFAULT_MAX_SCANS_PER_MINUTE


@pytest.mark.parametrize(
    ("name", "value", "expected"),
    [
        ("SEAWATCH_AREA_SCAN_MAX_BODY_BYTES", "65537", access.DEFAULT_MAX_SCAN_BODY_BYTES),
        ("SEAWATCH_AREA_SCAN_MAX_BODY_BYTES", "0", access.DEFAULT_MAX_SCAN_BODY_BYTES),
        ("SEAWATCH_AREA_SCAN_MAX_SCANS_PER_MINUTE", "0", access.DEFAULT_MAX_SCANS_PER_MINUTE),
        (
            "SEAWATCH_AREA_SCAN_MAX_PROVIDER_REQUESTS_PER_MINUTE",
            "-1",
            access.DEFAULT_MAX_PROVIDER_REQUESTS_PER_MINUTE,
        ),
    ],
)
def test_invalid_access_limits_fail_closed_with_safe_runtime_defaults(
    name: str,
    value: str,
    expected: int,
) -> None:
    config = access.AreaScanAccessConfig.from_env(
        {
            "SEAWATCH_AREA_SCAN_SIGNING_KEY": SIGNING_KEY,
            "SEAWATCH_AREA_SCAN_OPERATOR_KEY": OPERATOR_CREDENTIAL,
            name: value,
        }
    )

    assert config.configured is False
    field_by_env = {
        "SEAWATCH_AREA_SCAN_MAX_BODY_BYTES": "max_body_bytes",
        "SEAWATCH_AREA_SCAN_MAX_SCANS_PER_MINUTE": "max_scans_per_window",
        "SEAWATCH_AREA_SCAN_MAX_PROVIDER_REQUESTS_PER_MINUTE": (
            "max_provider_requests_per_window"
        ),
    }
    assert getattr(config, field_by_env[name]) == expected
    access.AreaScanAdmissionController(
        max_scans=config.max_scans_per_window,
        max_provider_requests=config.max_provider_requests_per_window,
    )


@pytest.mark.parametrize(
    "values",
    [
        {
            "SEAWATCH_AREA_SCAN_SIGNING_KEY": "short",
            "SEAWATCH_AREA_SCAN_OPERATOR_KEY": OPERATOR_CREDENTIAL,
        },
        {
            "SEAWATCH_AREA_SCAN_SIGNING_KEY": SIGNING_KEY,
            "SEAWATCH_AREA_SCAN_OPERATOR_KEY": "short",
        },
    ],
)
def test_short_access_secrets_fail_closed(values: dict[str, str]) -> None:
    config = access.AreaScanAccessConfig.from_env(values)
    assert config.operator_configured is False


def test_access_module_has_no_cli_that_prints_raw_capabilities() -> None:
    assert not hasattr(access, "main")
