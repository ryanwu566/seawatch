from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import datetime, timezone

from apps.api.seawatch.live.identity import VesselIdentityRegistry
from apps.api.seawatch.live.schema import LiveVesselObservation


def _observation(provider_id: str, mmsi: int | None) -> LiveVesselObservation:
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    return LiveVesselObservation(
        provider_id=provider_id,
        latitude=22.5,
        longitude=120.2,
        observed_at=now,
        received_at=now,
        source="aishub",
        mmsi=mmsi,
    )


def test_keyed_mmsi_identity_is_stable_opaque_and_key_specific() -> None:
    observation = _observation("raw-source-416000001", 416000001)
    first = VesselIdentityRegistry("fixed-test-key")
    second = VesselIdentityRegistry("other-test-key")

    public_id = first.public_id_for(observation)
    expected_digest = hmac.new(
        b"fixed-test-key", b"mmsi:416000001", hashlib.sha256
    ).digest()
    expected = "v_" + base64.urlsafe_b64encode(expected_digest[:18]).decode().rstrip("=")

    assert public_id == expected
    assert first.public_id_for(observation) == public_id
    assert second.public_id_for(observation) != public_id
    assert public_id.startswith("v_")
    assert "416000001" not in public_id
    assert "raw-source" not in public_id


def test_same_valid_mmsi_has_one_public_identity_across_sources() -> None:
    registry = VesselIdentityRegistry("fixed-test-key")

    cloud_id = registry.public_id_for(_observation("cloud-key", 416000001))
    edge = _observation("edge-key", 416000001)
    object.__setattr__(edge, "source", "edge_ais")

    assert registry.public_id_for(edge) == cloud_id


def test_internal_mmsi_identity_entry_point_matches_live_observations() -> None:
    registry = VesselIdentityRegistry("fixed-test-key")

    historical_id = registry.public_id_for_mmsi(416000001)
    live_id = registry.public_id_for(_observation("cloud-key", 416000001))

    assert historical_id == live_id
    assert registry.public_id_for_mmsi(None) is None
    assert registry.public_id_for_mmsi(123) is None


def test_uncertain_identity_is_process_local_stable_and_collision_checked() -> None:
    tokens = iter(("same", "same", "different"))
    registry = VesselIdentityRegistry(
        "fixed-test-key", token_factory=lambda: next(tokens)
    )
    first = _observation("unknown-a", None)
    second = _observation("unknown-b", None)

    first_id = registry.public_id_for(first)
    second_id = registry.public_id_for(second)

    assert first_id == "v_same"
    assert registry.public_id_for(first) == first_id
    assert second_id == "v_different"
    assert second_id != first_id


def test_reverse_binding_can_be_resolved_and_expired() -> None:
    registry = VesselIdentityRegistry("fixed-test-key")
    observation = _observation("internal-cloud-key", 416000001)

    public_id = registry.public_id_for(observation)
    binding = registry.resolve(public_id)

    assert binding is not None
    assert binding.public_id == public_id
    assert binding.source_key == "internal-cloud-key"
    assert binding.source_name == "aishub"
    assert binding.mmsi == 416000001

    registry.expire(public_id)
    assert registry.resolve(public_id) is None
