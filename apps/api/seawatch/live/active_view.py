"""Public, provenance-aware facade over live vessel stores."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from .identity import VesselIdentityRegistry
from .provider import BoundingBox
from .resilience import CoverageKind, DisplayState, ObservationOrigin
from .schema import LiveVesselObservation, TrajectoryPoint
from .store import LiveVesselStore


@dataclass(frozen=True)
class PublicVesselObservation:
    public_id: str
    observation: LiveVesselObservation
    origin: ObservationOrigin
    display_state: DisplayState
    active_source: bool
    coverage: CoverageKind


@dataclass(frozen=True)
class ActiveTrack:
    public_id: str
    source_name: str
    points: list[TrajectoryPoint]


class ActiveVesselView:
    """Cloud-only public view; later slices add source selection and caching."""

    def __init__(
        self,
        cloud_store: LiveVesselStore,
        identity_registry: VesselIdentityRegistry,
        *,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._cloud_store = cloud_store
        self._identity_registry = identity_registry
        self._monotonic = monotonic

    def snapshot(
        self,
        bbox: BoundingBox | None = None,
        now: datetime | None = None,
    ) -> list[PublicVesselObservation]:
        del now
        return [
            PublicVesselObservation(
                public_id=self._identity_registry.public_id_for(observation),
                observation=observation,
                origin=ObservationOrigin.CLOUD,
                display_state=DisplayState.LIVE,
                active_source=True,
                coverage=CoverageKind.CLOUD,
            )
            for observation in self._cloud_store.snapshot(bbox=bbox)
        ]

    def track(self, public_id: str) -> ActiveTrack | None:
        binding = self._identity_registry.resolve(public_id)
        if binding is None:
            return None
        points = self._cloud_store.get_trajectory(binding.source_key)
        if points is None:
            return None
        return ActiveTrack(public_id=public_id, source_name="cloud", points=points)
