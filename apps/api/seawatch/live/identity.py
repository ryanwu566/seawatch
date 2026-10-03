"""Opaque public vessel identities with internal reverse bindings."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass

from .schema import LiveVesselObservation


_KNOWN_MMSI_PLACEHOLDERS = {123_456_789}


def is_valid_mmsi(mmsi: int | None) -> bool:
    """Return whether an integer is safe to use as cross-source vessel identity."""

    if isinstance(mmsi, bool) or mmsi is None or not 100_000_000 <= mmsi <= 999_999_999:
        return False
    digits = str(mmsi)
    return mmsi not in _KNOWN_MMSI_PLACEHOLDERS and len(set(digits)) > 1


@dataclass(frozen=True)
class IdentityBinding:
    public_id: str
    source_key: str
    source_name: str
    mmsi: int | None


class VesselIdentityRegistry:
    """Map internal source identities to collision-checked opaque public IDs."""

    def __init__(
        self,
        identity_key: str | bytes | None = None,
        *,
        token_factory: Callable[[], str] | None = None,
    ) -> None:
        if isinstance(identity_key, str):
            key = identity_key.encode("utf-8")
        else:
            key = identity_key
        self._identity_key = key or secrets.token_bytes(32)
        self._token_factory = token_factory or (lambda: secrets.token_urlsafe(18))
        self._lock = threading.RLock()
        self._bindings: dict[str, IdentityBinding] = {}
        self._source_bindings: dict[str, dict[tuple[str, str], IdentityBinding]] = {}
        self._source_ids: dict[tuple[str, str], str] = {}

    @staticmethod
    def _valid_mmsi(mmsi: int | None) -> bool:
        return is_valid_mmsi(mmsi)

    def _mmsi_public_id(self, mmsi: int) -> str:
        digest = hmac.new(
            self._identity_key,
            f"mmsi:{mmsi}".encode("ascii"),
            hashlib.sha256,
        ).digest()
        token = base64.urlsafe_b64encode(digest[:18]).decode("ascii").rstrip("=")
        return f"v_{token}"

    def public_id_for_mmsi(self, mmsi: int | None) -> str | None:
        """Return the configured deterministic identity for a valid MMSI.

        Historical processing uses this narrow entry point so it shares the
        live layer's validation and HMAC implementation. Invalid or absent
        MMSIs fail closed instead of receiving an unrelated public identity.
        """

        if not self._valid_mmsi(mmsi):
            return None
        return self._mmsi_public_id(mmsi)  # type: ignore[arg-type]

    def public_id_for(self, observation: LiveVesselObservation) -> str:
        source_identity = (observation.source, observation.provider_id)
        with self._lock:
            existing_source_id = self._source_ids.get(source_identity)
            if existing_source_id is not None:
                return existing_source_id

            if self._valid_mmsi(observation.mmsi):
                public_id = self.public_id_for_mmsi(observation.mmsi)
                assert public_id is not None
                collision = self._bindings.get(public_id)
                if collision is not None and collision.mmsi != observation.mmsi:
                    raise RuntimeError("opaque vessel identity collision")
            else:
                while True:
                    public_id = f"v_{self._token_factory()}"
                    if public_id not in self._bindings:
                        break

            binding = IdentityBinding(
                public_id=public_id,
                source_key=observation.provider_id,
                source_name=observation.source,
                mmsi=observation.mmsi if self._valid_mmsi(observation.mmsi) else None,
            )
            self._bindings.setdefault(public_id, binding)
            self._source_bindings.setdefault(public_id, {})[source_identity] = binding
            self._source_ids[source_identity] = public_id
            return public_id

    def resolve(self, public_id: str) -> IdentityBinding | None:
        with self._lock:
            return self._bindings.get(public_id)

    def resolve_for_source(
        self, public_id: str, source_name: str, source_key: str
    ) -> IdentityBinding | None:
        with self._lock:
            return self._source_bindings.get(public_id, {}).get(
                (source_name, source_key)
            )

    def bindings(self, public_id: str) -> tuple[IdentityBinding, ...]:
        with self._lock:
            return tuple(self._source_bindings.get(public_id, {}).values())

    def expire(self, public_id: str) -> None:
        with self._lock:
            self._bindings.pop(public_id, None)
            self._source_bindings.pop(public_id, None)
            stale_sources = [
                source for source, bound_id in self._source_ids.items() if bound_id == public_id
            ]
            for source in stale_sources:
                del self._source_ids[source]

    def expire_source(
        self, public_id: str, source_name: str, source_key: str
    ) -> None:
        """Remove one source binding without disturbing the same MMSI elsewhere."""

        source_identity = (source_name, source_key)
        with self._lock:
            bindings = self._source_bindings.get(public_id)
            if bindings is None or source_identity not in bindings:
                return
            del bindings[source_identity]
            self._source_ids.pop(source_identity, None)
            if not bindings:
                self._source_bindings.pop(public_id, None)
                self._bindings.pop(public_id, None)
                return
            current = self._bindings.get(public_id)
            if (
                current is not None
                and (current.source_name, current.source_key) == source_identity
            ):
                self._bindings[public_id] = bindings[sorted(bindings)[0]]
