"""Provider-independent bridge from normalized live AIS to detection tracks."""

from __future__ import annotations

import math
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from itertools import islice
from numbers import Integral
from typing import Any

import numpy as np

from ..live.schema import LiveVesselObservation, utcnow
from . import engine
from .config import DetectionConfig
from .context import DetectionContext
from .engine import AnalysisResult
from .history import ship_category
from .models import Track


@dataclass(frozen=True)
class LiveTrackIdentity:
    """Stable backend-only grouping key for a live vessel.

    A validated MMSI joins observations across sources. Without one, the source
    and its provider-local key remain isolated and are never presented as MMSI.
    """

    mmsi: str | None
    source: str | None = None
    provider_id: str | None = None

    def sort_key(self) -> tuple[str, str, str]:
        return (self.mmsi or "", self.source or "", self.provider_id or "")


@dataclass(frozen=True)
class BufferedLiveTrack:
    """Immutable snapshot of one vessel's retained observations."""

    identity: LiveTrackIdentity
    observations: tuple[LiveVesselObservation, ...]


def _valid_mmsi(value: object) -> bool:
    return isinstance(value, Integral) and not isinstance(value, bool) and 100_000_000 <= int(value) <= 999_999_999


def _identity_for(observation: LiveVesselObservation) -> LiveTrackIdentity:
    if _valid_mmsi(observation.mmsi):
        return LiveTrackIdentity(mmsi=str(int(observation.mmsi)))
    source = observation.source.strip()
    provider_id = observation.provider_id.strip()
    if not source or not provider_id:
        raise ValueError("source and provider_id are required when MMSI is unavailable")
    return LiveTrackIdentity(mmsi=None, source=source, provider_id=provider_id)


def _optional_number(value: object) -> tuple[str, float | str]:
    if value is None:
        return ("missing", "")
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ("invalid", repr(value))
    if not math.isfinite(number):
        return ("missing", "")
    return ("value", number)


def _fingerprint(observation: LiveVesselObservation) -> tuple[Any, ...]:
    return (
        observation.observed_at,
        observation.received_at,
        observation.source,
        observation.provider_id,
        float(observation.latitude),
        float(observation.longitude),
        _optional_number(observation.sog_knots),
        _optional_number(observation.cog_deg),
        _optional_number(observation.heading_deg),
        observation.nav_status,
        observation.vessel_type,
        observation.name,
        observation.destination,
        observation.synthesized,
        (type(observation.mmsi).__name__, repr(observation.mmsi)),
    )


def _observation_order(observation: LiveVesselObservation) -> tuple[Any, ...]:
    fingerprint = _fingerprint(observation)
    comparable = tuple((type(value).__name__, repr(value)) for value in fingerprint)
    return (observation.observed_at, comparable)


class RollingTrackBuffer:
    """Thread-safe bounded retention for normalized live observations."""

    def __init__(
        self,
        *,
        max_vessels: int = 1_000,
        max_points_per_vessel: int = 720,
        max_batch_observations: int = 100_000,
        retention: timedelta = timedelta(hours=24),
        stale_after: timedelta | None = None,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        if max_vessels <= 0:
            raise ValueError("max_vessels must be positive")
        if max_points_per_vessel <= 0:
            raise ValueError("max_points_per_vessel must be positive")
        if max_batch_observations <= 0:
            raise ValueError("max_batch_observations must be positive")
        if retention <= timedelta(0):
            raise ValueError("retention must be positive")
        effective_stale_after = retention if stale_after is None else stale_after
        if effective_stale_after <= timedelta(0):
            raise ValueError("stale_after must be positive")
        self._max_vessels = max_vessels
        self._max_points_per_vessel = max_points_per_vessel
        self._max_batch_observations = max_batch_observations
        self._retention = retention
        self._stale_after = effective_stale_after
        self._clock = clock
        self._tracks: dict[LiveTrackIdentity, dict[tuple[Any, ...], LiveVesselObservation]] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _validate(observation: LiveVesselObservation) -> None:
        latitude = float(observation.latitude)
        longitude = float(observation.longitude)
        if not math.isfinite(latitude) or not -90.0 <= latitude <= 90.0:
            raise ValueError("latitude must be finite and between -90 and 90")
        if not math.isfinite(longitude) or not -180.0 <= longitude <= 180.0:
            raise ValueError("longitude must be finite and between -180 and 180")
        if observation.observed_at.tzinfo is None or observation.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")

    def update(
        self,
        observation: LiveVesselObservation,
        *,
        as_of: datetime | None = None,
    ) -> bool:
        """Retain one observation; return ``False`` for a duplicate/expired fix."""

        now = as_of if as_of is not None else self._clock()
        with self._lock:
            self._maintain(now)
            retained = self._retain(observation, now)
            identity = _identity_for(observation)
            fingerprint = _fingerprint(observation)
            self._enforce_vessel_cap()
            return retained and identity in self._tracks and fingerprint in self._tracks[identity]

    def _retain(self, observation: LiveVesselObservation, now: datetime) -> bool:
        """Retain one validated-against-batch-time observation under the lock."""

        self._validate(observation)
        identity = _identity_for(observation)
        fingerprint = _fingerprint(observation)
        if self._is_expired(observation.observed_at, now):
            return False
        points = self._tracks.setdefault(identity, {})
        if fingerprint in points:
            return False
        points[fingerprint] = observation
        if len(points) > self._max_points_per_vessel:
            keep = sorted(points.values(), key=_observation_order)[-self._max_points_per_vessel :]
            self._tracks[identity] = {_fingerprint(item): item for item in keep}
        return identity in self._tracks and fingerprint in self._tracks[identity]

    def update_many(
        self,
        observations: Iterable[LiveVesselObservation],
        *,
        as_of: datetime | None = None,
    ) -> int:
        """Retain a finite batch; return new points surviving the final caps."""

        batch = list(islice(observations, self._max_batch_observations + 1))
        if len(batch) > self._max_batch_observations:
            raise ValueError(
                f"batch exceeds max_batch_observations={self._max_batch_observations}"
            )
        now = as_of if as_of is not None else self._clock()
        with self._lock:
            self._maintain(now)
            accepted: set[tuple[LiveTrackIdentity, tuple[Any, ...]]] = set()
            try:
                for observation in batch:
                    if self._retain(observation, now):
                        accepted.add((_identity_for(observation), _fingerprint(observation)))
            finally:
                self._enforce_vessel_cap()
            return sum(
                1
                for identity, fingerprint in accepted
                if identity in self._tracks and fingerprint in self._tracks[identity]
            )

    def _is_expired(self, observed_at: datetime, now: datetime) -> bool:
        return (
            observed_at < now - self._retention
            or observed_at < now - self._stale_after
        )

    def _maintain(self, now: datetime) -> int:
        """Apply retention and vessel staleness cutoffs under the caller's lock."""

        retention_cutoff = now - self._retention
        stale_cutoff = now - self._stale_after
        before = len(self._tracks)
        for identity, points in list(self._tracks.items()):
            retained = {
                fingerprint: observation
                for fingerprint, observation in points.items()
                if observation.observed_at >= retention_cutoff
            }
            if (
                not retained
                or max(observation.observed_at for observation in retained.values())
                < stale_cutoff
            ):
                del self._tracks[identity]
            elif len(retained) != len(points):
                self._tracks[identity] = retained
        return before - len(self._tracks)

    def evict_stale(self, *, now: datetime | None = None) -> int:
        """Evict vessels whose newest retained fix is older than ``stale_after``."""

        with self._lock:
            reference = now if now is not None else self._clock()
            return self._maintain(reference)

    def _enforce_vessel_cap(self) -> None:
        if len(self._tracks) <= self._max_vessels:
            return
        retained = sorted(
            self._tracks,
            key=lambda identity: (
                max(
                    observation.observed_at
                    for observation in self._tracks[identity].values()
                ),
                identity.sort_key(),
            ),
            reverse=True,
        )[: self._max_vessels]
        retained_set = set(retained)
        for victim in set(self._tracks) - retained_set:
            del self._tracks[victim]

    def snapshot(
        self,
        *,
        as_of: datetime | None = None,
    ) -> tuple[BufferedLiveTrack, ...]:
        """Return immutable tracks ordered by stable backend identity."""

        with self._lock:
            reference = as_of if as_of is not None else self._clock()
            if as_of is None:
                self._maintain(reference)
            retention_cutoff = reference - self._retention
            stale_cutoff = reference - self._stale_after
            tracks: list[BufferedLiveTrack] = []
            for identity, points in sorted(
                self._tracks.items(), key=lambda item: item[0].sort_key()
            ):
                visible = tuple(
                    sorted(
                        (
                            observation
                            for observation in points.values()
                            if observation.observed_at >= retention_cutoff
                            and (
                                as_of is None
                                or observation.observed_at <= reference
                            )
                        ),
                        key=_observation_order,
                    )
                )
                if visible and visible[-1].observed_at >= stale_cutoff:
                    tracks.append(BufferedLiveTrack(identity, visible))
            return tuple(tracks)

    def vessel_count(self) -> int:
        with self._lock:
            self._maintain(self._clock())
            return len(self._tracks)

    def point_count(self) -> int:
        with self._lock:
            self._maintain(self._clock())
            return sum(len(points) for points in self._tracks.values())


def _finite_or_nan(value: object) -> float:
    kind, normalized = _optional_number(value)
    return float(normalized) if kind == "value" else float("nan")


def _finite_or_none(value: object) -> float | None:
    number = _finite_or_nan(value)
    return number if math.isfinite(number) else None


class DetectionTrackAdapter:
    """Convert buffered live observations to the teammate Detection model."""

    def to_track(self, buffered: BufferedLiveTrack) -> Track | None:
        """Build one time-ordered `Track`, or ``None`` without a valid MMSI."""

        if buffered.identity.mmsi is None:
            return None
        ordered = sorted(buffered.observations, key=_observation_order)
        by_time: dict[datetime, LiveVesselObservation] = {}
        for observation in ordered:
            by_time[observation.observed_at] = observation
        selected = list(by_time.values())
        if not selected:
            return None

        def last_text(field: str) -> str:
            return next(
                (
                    str(value).strip()
                    for observation in reversed(selected)
                    if (value := getattr(observation, field)) is not None and str(value).strip()
                ),
                "",
            )

        vessel_type = next(
            (observation.vessel_type for observation in reversed(selected) if observation.vessel_type is not None),
            None,
        )
        status = (
            np.asarray([observation.nav_status if observation.nav_status is not None else -1 for observation in selected], dtype=int)
            if any(observation.nav_status is not None for observation in selected)
            else None
        )
        destination = last_text("destination")
        extra: dict[str, Any] = {
            "sources": tuple(sorted({observation.source for observation in ordered})),
            "point_sources": tuple(observation.source for observation in selected),
            "heading_deg": tuple(_finite_or_none(observation.heading_deg) for observation in selected),
            "synthesized": tuple(bool(observation.synthesized) for observation in selected),
        }
        if destination:
            extra["destination"] = destination
        return Track(
            mmsi=buffered.identity.mmsi,
            name=last_text("name") or buffered.identity.mmsi,
            ship_type=ship_category(vessel_type),
            flag="",
            t=np.asarray([observation.observed_at.timestamp() for observation in selected], dtype=float),
            lat=np.asarray([observation.latitude for observation in selected], dtype=float),
            lon=np.asarray([observation.longitude for observation in selected], dtype=float),
            sog=np.asarray([_finite_or_nan(observation.sog_knots) for observation in selected], dtype=float),
            cog=np.asarray([_finite_or_nan(observation.cog_deg) for observation in selected], dtype=float),
            status=status,
            imo="",
            extra=extra,
        )

    def to_tracks(self, buffered_tracks: Iterable[BufferedLiveTrack]) -> list[Track]:
        """Adapt every MMSI-backed track while preserving fleet-level order."""

        return [track for buffered in buffered_tracks if (track := self.to_track(buffered)) is not None]

    @staticmethod
    def eligibility(track: Track, density: str) -> dict[str, str | None]:
        """Delegate live-data capability decisions to the engine's matrix."""

        return engine.eligibility(track, density)


class LiveDetectionAnalyzer:
    """Reusable one-shot/continuous seam from normalized fixes to analysis.

    The caller owns construction and refresh of the historical context.  This
    object deliberately retains that same context and analyzes the current
    fleet in one engine call so proximity detectors retain cross-vessel scope.
    """

    def __init__(
        self,
        context: DetectionContext,
        *,
        buffer: RollingTrackBuffer | None = None,
        adapter: DetectionTrackAdapter | None = None,
        density: str = "message_level",
        config: DetectionConfig | None = None,
        feedback: Any = None,
        watch: Any = None,
    ) -> None:
        if context is None:
            raise ValueError("a caller-supplied DetectionContext is required")
        if density not in engine.DENSITIES:
            raise ValueError(f"density must be one of {engine.DENSITIES}")
        self._context = context
        self._buffer = buffer or RollingTrackBuffer()
        self._adapter = adapter or DetectionTrackAdapter()
        self._density = density
        self._config = config
        self._feedback = feedback
        self._watch = watch
        self._lock = threading.RLock()

    def ingest(self, observations: Iterable[LiveVesselObservation]) -> int:
        """Add one finite normalized batch and return newly retained fix count."""

        with self._lock:
            return self._buffer.update_many(observations)

    def tracks(self) -> list[Track]:
        """Return the current MMSI-backed fleet in the Detection Track model."""

        with self._lock:
            return self._adapted_tracks()

    def _adapted_tracks(self, *, as_of: float | None = None) -> list[Track]:
        buffer_as_of = (
            datetime.fromtimestamp(as_of, tz=timezone.utc)
            if as_of is not None
            else None
        )
        buffered = self._buffer.snapshot(as_of=buffer_as_of)
        return self._adapter.to_tracks(buffered)

    def eligibility(self) -> dict[str, dict[str, str | None]]:
        """Return the engine's detector capability decision for each track."""

        with self._lock:
            return {
                track.mmsi: self._adapter.eligibility(track, self._density)
                for track in self._adapted_tracks()
            }

    def analyze(self, *, as_of: float | None = None) -> AnalysisResult:
        """Analyze the entire current fleet once using the retained context."""

        with self._lock:
            tracks = self._adapted_tracks(as_of=as_of)
            return engine.analyze(
                tracks,
                self._context,
                cfg=self._config,
                as_of=as_of,
                density=self._density,
                feedback=self._feedback,
                watch=self._watch,
            )

    def update(
        self,
        observations: Iterable[LiveVesselObservation],
        *,
        as_of: float | None = None,
    ) -> AnalysisResult:
        """Ingest one batch and analyze accumulated tracks (one-shot or repeat)."""

        with self._lock:
            buffer_as_of = (
                datetime.fromtimestamp(as_of, tz=timezone.utc)
                if as_of is not None
                else None
            )
            self._buffer.update_many(observations, as_of=buffer_as_of)
            return self.analyze(as_of=as_of)
