"""Public, provenance-aware facade over independent live vessel stores."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime

from .identity import VesselIdentityRegistry
from .provider import BoundingBox
from .resilience import (
    CoverageKind,
    DisplayState,
    ObservationOrigin,
    OperatingMode,
    ResilienceStatus,
)
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
    operating_mode: OperatingMode


@dataclass(frozen=True)
class ActiveTrack:
    public_id: str
    source_name: str
    points: list[TrajectoryPoint]


@dataclass(frozen=True)
class _Ownership:
    source_name: str
    source_key: str


@dataclass(frozen=True)
class _CachedObservation:
    item: PublicVesselObservation
    ownership: _Ownership
    expires_at: float


class ActiveVesselView:
    """Select the active store and retain bounded, source-owned transition cache."""

    def __init__(
        self,
        cloud_store: LiveVesselStore,
        edge_store: LiveVesselStore,
        identity_registry: VesselIdentityRegistry,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        cache_seconds: float = 300.0,
    ) -> None:
        self._cloud_store = cloud_store
        self._edge_store = edge_store
        self._identity_registry = identity_registry
        self._monotonic = monotonic
        self._cache_seconds = cache_seconds
        self._previous_mode: OperatingMode | None = None
        self._last_active: list[PublicVesselObservation] = []
        self._last_active_ownership: dict[str, _Ownership] = {}
        self._cache: dict[str, _CachedObservation] = {}
        self._display_ownership: dict[str, _Ownership] = {}

    @staticmethod
    def _source_for_mode(
        mode: OperatingMode,
    ) -> tuple[str, ObservationOrigin, CoverageKind] | None:
        if mode is OperatingMode.CLOUD_LIVE:
            return "cloud", ObservationOrigin.CLOUD, CoverageKind.CLOUD
        if mode is OperatingMode.EDGE_LIVE:
            return "edge", ObservationOrigin.EDGE_RF, CoverageKind.EDGE
        if mode is OperatingMode.EDGE_REPLAY:
            return "edge", ObservationOrigin.EDGE_REPLAY, CoverageKind.EDGE
        return None

    def _purge_expired(self, now: float) -> None:
        expired = [
            public_id
            for public_id, cached in self._cache.items()
            if cached.expires_at <= now
        ]
        for public_id in expired:
            del self._cache[public_id]
            self._identity_registry.expire(public_id)

    def _cache_prior_active(self, now: float) -> None:
        for item in self._last_active:
            ownership = self._last_active_ownership[item.public_id]
            self._cache[item.public_id] = _CachedObservation(
                item=item,
                ownership=ownership,
                expires_at=now + self._cache_seconds,
            )

    def snapshot(
        self,
        status: ResilienceStatus,
        bbox: BoundingBox | None = None,
        now: datetime | None = None,
    ) -> list[PublicVesselObservation]:
        del now
        monotonic_now = self._monotonic()
        self._purge_expired(monotonic_now)
        if self._previous_mode is not None and self._previous_mode is not status.mode:
            self._cache_prior_active(monotonic_now)

        source = self._source_for_mode(status.mode)
        active: list[PublicVesselObservation] = []
        active_ownership: dict[str, _Ownership] = {}
        if source is not None:
            source_name, origin, coverage = source
            store = self._cloud_store if source_name == "cloud" else self._edge_store
            for observation in store.snapshot():
                public_id = self._identity_registry.public_id_for(observation)
                active.append(
                    PublicVesselObservation(
                        public_id=public_id,
                        observation=observation,
                        origin=origin,
                        display_state=DisplayState.LIVE,
                        active_source=True,
                        coverage=coverage,
                        operating_mode=status.mode,
                    )
                )
                active_ownership[public_id] = _Ownership(
                    source_name=source_name,
                    source_key=observation.provider_id,
                )

        active_ids = {item.public_id for item in active}
        cached_items: list[PublicVesselObservation] = []
        cached_ownership: dict[str, _Ownership] = {}
        for public_id, cached in self._cache.items():
            if public_id in active_ids:
                continue
            source_fresh = (
                status.cloud.fresh
                if cached.item.origin is ObservationOrigin.CLOUD
                else status.edge.fresh
            )
            cached_items.append(
                replace(
                    cached.item,
                    display_state=(
                        DisplayState.CACHED if source_fresh else DisplayState.STALE
                    ),
                    active_source=False,
                    operating_mode=status.mode,
                )
            )
            cached_ownership[public_id] = cached.ownership

        self._last_active = active
        self._last_active_ownership = active_ownership
        self._previous_mode = status.mode
        self._display_ownership = {**cached_ownership, **active_ownership}
        displayed = active + cached_items
        if bbox is not None:
            displayed = [
                item
                for item in displayed
                if bbox.contains(item.observation.latitude, item.observation.longitude)
            ]
        return displayed

    def track(self, public_id: str) -> ActiveTrack | None:
        ownership = self._display_ownership.get(public_id)
        if ownership is None:
            return None
        store = (
            self._cloud_store
            if ownership.source_name == "cloud"
            else self._edge_store
        )
        points = store.get_trajectory(ownership.source_key)
        if points is None:
            return None
        return ActiveTrack(
            public_id=public_id,
            source_name=ownership.source_name,
            points=points,
        )
