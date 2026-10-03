"""Fail-closed access policy for the paid Area Scan endpoint."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import os
import secrets
import threading
import time
from collections import deque
from collections.abc import Callable
from collections.abc import Mapping
from dataclasses import dataclass, field


AREA_SCAN_CAPABILITY_SCOPE = "area-scan"
DEFAULT_CAPABILITY_TTL_SECONDS = 900
MAX_CAPABILITY_TTL_SECONDS = 3_600
DEFAULT_MAX_SCAN_BODY_BYTES = 65_536
DEFAULT_MAX_SCANS_PER_MINUTE = 4
DEFAULT_MAX_PROVIDER_REQUESTS_PER_MINUTE = 32
DEFAULT_ADMISSION_WINDOW_SECONDS = 60.0
AREA_SCAN_CAPABILITY_COOKIE = "seawatch_area_scan_capability"
MIN_ACCESS_SECRET_BYTES = 32


@dataclass(frozen=True)
class AreaScanAccessConfig:
    """Server-only configuration for short-lived Area Scan capabilities."""

    signing_key: str | None = field(default=None, repr=False)
    operator_credential: str | None = field(default=None, repr=False)
    autoauth_loopback: bool = False
    allow_insecure_cookie: bool = False
    max_body_bytes: int = DEFAULT_MAX_SCAN_BODY_BYTES
    max_scans_per_window: int = DEFAULT_MAX_SCANS_PER_MINUTE
    max_provider_requests_per_window: int = DEFAULT_MAX_PROVIDER_REQUESTS_PER_MINUTE
    window_seconds: float = DEFAULT_ADMISSION_WINDOW_SECONDS
    valid_configuration: bool = field(default=True, repr=False)

    def __post_init__(self) -> None:
        normalized = self.signing_key.strip() if self.signing_key else None
        normalized_operator = (
            self.operator_credential.strip() if self.operator_credential else None
        )
        object.__setattr__(self, "signing_key", normalized or None)
        object.__setattr__(self, "operator_credential", normalized_operator or None)
        signing_valid = _strong_secret(normalized)
        object.__setattr__(
            self,
            "valid_configuration",
            self.valid_configuration and signing_valid,
        )

    @property
    def configured(self) -> bool:
        return self.signing_key is not None and self.valid_configuration

    @property
    def operator_configured(self) -> bool:
        return self.configured and _strong_secret(self.operator_credential)

    @property
    def secure_cookie(self) -> bool:
        return not self.allow_insecure_cookie

    @classmethod
    def from_env(
        cls, values: Mapping[str, str] | None = None
    ) -> "AreaScanAccessConfig":
        env = os.environ if values is None else values
        max_body, body_valid = _positive_int(
            env.get("SEAWATCH_AREA_SCAN_MAX_BODY_BYTES"),
            DEFAULT_MAX_SCAN_BODY_BYTES,
            maximum=DEFAULT_MAX_SCAN_BODY_BYTES,
        )
        max_scans, scans_valid = _positive_int(
            env.get("SEAWATCH_AREA_SCAN_MAX_SCANS_PER_MINUTE"),
            DEFAULT_MAX_SCANS_PER_MINUTE,
        )
        max_provider_requests, requests_valid = _positive_int(
            env.get("SEAWATCH_AREA_SCAN_MAX_PROVIDER_REQUESTS_PER_MINUTE"),
            DEFAULT_MAX_PROVIDER_REQUESTS_PER_MINUTE,
        )
        allow_insecure_cookie, cookie_valid = _boolean(
            env.get("SEAWATCH_AREA_SCAN_ALLOW_INSECURE_COOKIE"),
            False,
        )
        autoauth_loopback, autoauth_valid = _boolean(
            env.get("SEAWATCH_AREA_SCAN_AUTOAUTH_LOOPBACK"),
            False,
        )
        return cls(
            signing_key=env.get("SEAWATCH_AREA_SCAN_SIGNING_KEY"),
            operator_credential=env.get("SEAWATCH_AREA_SCAN_OPERATOR_KEY"),
            autoauth_loopback=autoauth_loopback,
            allow_insecure_cookie=allow_insecure_cookie,
            max_body_bytes=max_body,
            max_scans_per_window=max_scans,
            max_provider_requests_per_window=max_provider_requests,
            valid_configuration=(
                body_valid
                and scans_valid
                and requests_valid
                and cookie_valid
                and autoauth_valid
            ),
        )


class AreaScanAdmissionError(RuntimeError):
    """Safe local admission rejection raised before any provider request."""

    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__("Area Scan request budget exhausted")


class AreaScanAdmissionController:
    """Process-wide fixed-window limits for scans and reserved provider calls."""

    def __init__(
        self,
        *,
        max_scans: int,
        max_provider_requests: int,
        window_seconds: float = DEFAULT_ADMISSION_WINDOW_SECONDS,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_scans <= 0 or max_provider_requests <= 0 or window_seconds <= 0:
            raise ValueError("Area Scan admission limits must be positive")
        self._max_scans = max_scans
        self._max_provider_requests = max_provider_requests
        self._window_seconds = window_seconds
        self._monotonic = monotonic
        self._scan_events: deque[float] = deque()
        self._provider_events: deque[tuple[float, int]] = deque()
        self._provider_request_total = 0
        self._lock = threading.Lock()

    def authorize(self, *, provider_requests: int) -> None:
        """Atomically reserve one scan and its maximum paid request cost."""

        if provider_requests < 0:
            raise ValueError("provider request reservation cannot be negative")
        now = self._monotonic()
        with self._lock:
            self._sweep(now)
            if len(self._scan_events) >= self._max_scans:
                raise AreaScanAdmissionError(self._retry_after(now, self._scan_events[0]))
            if provider_requests > self._max_provider_requests:
                raise AreaScanAdmissionError(math.ceil(self._window_seconds))
            if (
                self._provider_request_total + provider_requests
                > self._max_provider_requests
            ):
                oldest = self._provider_events[0][0]
                raise AreaScanAdmissionError(self._retry_after(now, oldest))
            self._scan_events.append(now)
            if provider_requests:
                self._provider_events.append((now, provider_requests))
                self._provider_request_total += provider_requests

    def snapshot(self) -> dict[str, int]:
        """Return safe counters for deterministic tests and diagnostics."""

        now = self._monotonic()
        with self._lock:
            self._sweep(now)
            return {
                "scans": len(self._scan_events),
                "provider_requests": self._provider_request_total,
            }

    def _sweep(self, now: float) -> None:
        cutoff = now - self._window_seconds
        while self._scan_events and self._scan_events[0] <= cutoff:
            self._scan_events.popleft()
        while self._provider_events and self._provider_events[0][0] <= cutoff:
            _, count = self._provider_events.popleft()
            self._provider_request_total -= count

    def _retry_after(self, now: float, oldest: float) -> int:
        return max(1, math.ceil(oldest + self._window_seconds - now))


def mint_area_scan_capability(
    config: AreaScanAccessConfig,
    *,
    now: int | float | None = None,
    ttl_seconds: int = DEFAULT_CAPABILITY_TTL_SECONDS,
    nonce: str | None = None,
) -> str:
    """Mint a short-lived bearer capability without exposing the signing key."""

    if not config.configured or config.signing_key is None:
        raise ValueError("Area Scan access is not configured")
    if isinstance(ttl_seconds, bool) or not 1 <= ttl_seconds <= MAX_CAPABILITY_TTL_SECONDS:
        raise ValueError("capability TTL is outside the allowed range")
    issued_at = int(time.time() if now is None else now)
    payload = {
        "exp": issued_at + ttl_seconds,
        "iat": issued_at,
        "nonce": nonce or secrets.token_urlsafe(12),
        "scope": AREA_SCAN_CAPABILITY_SCOPE,
        "v": 1,
    }
    encoded_payload = _base64url_encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    signature = hmac.new(
        config.signing_key.encode("utf-8"),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{encoded_payload}.{_base64url_encode(signature)}"


def verify_area_scan_capability(
    token: str,
    config: AreaScanAccessConfig,
    *,
    now: int | float | None = None,
) -> bool:
    """Verify signature, scope, version, issuance, and expiry; never raise."""

    if not config.configured or config.signing_key is None or len(token) > 2_048:
        return False
    try:
        encoded_payload, encoded_signature = token.split(".")
        signature = _base64url_decode(encoded_signature)
        expected = hmac.new(
            config.signing_key.encode("utf-8"),
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(signature, expected):
            return False
        payload = json.loads(_base64url_decode(encoded_payload))
        if not isinstance(payload, dict):
            return False
        issued_at = payload.get("iat")
        expires_at = payload.get("exp")
        if (
            isinstance(issued_at, bool)
            or not isinstance(issued_at, int)
            or isinstance(expires_at, bool)
            or not isinstance(expires_at, int)
            or expires_at <= issued_at
            or expires_at - issued_at > MAX_CAPABILITY_TTL_SECONDS
        ):
            return False
        reference = int(time.time() if now is None else now)
        return (
            payload.get("v") == 1
            and payload.get("scope") == AREA_SCAN_CAPABILITY_SCOPE
            and isinstance(payload.get("nonce"), str)
            and 1 <= len(payload["nonce"]) <= 256
            and issued_at - 30 <= reference < expires_at
        )
    except (UnicodeError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return False


def verify_operator_credential(
    credential: str,
    config: AreaScanAccessConfig,
) -> bool:
    """Compare the operator credential without variable-length string timing."""

    if (
        not config.operator_configured
        or config.operator_credential is None
        or not isinstance(credential, str)
        or len(credential) > 4_096
    ):
        return False
    expected = hashlib.sha256(config.operator_credential.encode("utf-8")).digest()
    presented = hashlib.sha256(credential.encode("utf-8")).digest()
    return hmac.compare_digest(presented, expected)


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _base64url_decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.b64decode(padded, altchars=b"-_", validate=True)


def _positive_int(
    raw: str | None,
    default: int,
    *,
    maximum: int | None = None,
) -> tuple[int, bool]:
    if raw is None:
        return default, True
    try:
        value = int(raw.strip())
    except (TypeError, ValueError):
        return default, False
    if value <= 0 or (maximum is not None and value > maximum):
        return default, False
    return value, True


def _strong_secret(value: str | None) -> bool:
    return value is not None and len(value.encode("utf-8")) >= MIN_ACCESS_SECRET_BYTES


def _boolean(raw: str | None, default: bool) -> tuple[bool, bool]:
    if raw is None:
        return default, True
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True, True
    if normalized in {"0", "false", "no", "off"}:
        return False, True
    return default, False
