"""In-memory live vessel store.

A single process-wide store holds the latest real AIS observation per vessel
plus a bounded rolling trajectory (default last 30 minutes). One upstream feed
writes into it; many API reads fan out of it. A :class:`threading.RLock` guards
all mutation so concurrent FastAPI request threads and the ingest task observe a
consistent snapshot.

Nothing is fabricated here: the store only retains what the provider delivered,
and ``observed_at`` always reflects the upstream report time.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from typing import Iterable

from .provider import BoundingBox
from .schema import LiveVesselObservation, TrajectoryPoint, VesselState, utcnow

DEFAULT_TRAJECTORY_WINDOW = timedelta(minutes=30)
DEFAULT_STALE_AFTER = timedelta(minutes=15)
# Minimum movement before we append a new trajectory point (avoid dense dupes).
_MIN_TRAJECTORY_DELTA_DEG = 1e-5


class LiveVesselStore:
    """Thread-safe latest-observation + rolling-trajectory store."""

    def __init__(
        self,
        *,
        trajectory_window: timedelta = DEFAULT_TRAJECTORY_WINDOW,
        stale_after: timedelta = DEFAULT_STALE_AFTER,
        max_trajectory_points: int = 720,
    ) -> None:
        self._lock = threading.RLock()
        self._states: dict[str, VesselState] = {}
        self._trajectory_window = trajectory_window
        self._stale_after = stale_after
        self._max_trajectory_points = max_trajectory_points
        self._last_message_at: datetime | None = None
        self._message_count = 0

    # -- writes ------------------------------------------------------------ #
    def update(self, observation: LiveVesselObservation) -> None:
        """Insert or update a vessel from a normalized observation.

        Deduplicates by ``provider_id``. Appends to the rolling trajectory only
        when the vessel actually moved and the new fix is not older than the one
        already stored (guards against out-of-order frames).
        """

        with self._lock:
            self._message_count += 1
            self._last_message_at = utcnow()
            existing = self._states.get(observation.provider_id)
            if existing is None:
                state = VesselState(
                    provider_id=observation.provider_id,
                    latest=observation,
                    trajectory=[
                        TrajectoryPoint(
                            latitude=observation.latitude,
                            longitude=observation.longitude,
                            observed_at=observation.observed_at,
                            synthesized=observation.synthesized,
                        )
                    ],
                )
                self._states[observation.provider_id] = state
                return

            # Ignore strictly older frames for the "latest" view.
            if observation.observed_at < existing.latest.observed_at:
                return

            moved = (
                abs(observation.latitude - existing.latest.latitude) > _MIN_TRAJECTORY_DELTA_DEG
                or abs(observation.longitude - existing.latest.longitude) > _MIN_TRAJECTORY_DELTA_DEG
            )
            existing.latest = observation
            if moved or not existing.trajectory:
                existing.trajectory.append(
                    TrajectoryPoint(
                        latitude=observation.latitude,
                        longitude=observation.longitude,
                        observed_at=observation.observed_at,
                        synthesized=observation.synthesized,
                    )
                )
                self._trim_trajectory(existing)

    def update_many(self, observations: Iterable[LiveVesselObservation]) -> int:
        count = 0
        for observation in observations:
            self.update(observation)
            count += 1
        return count

    def _trim_trajectory(self, state: VesselState) -> None:
        cutoff = utcnow() - self._trajectory_window
        state.trajectory = [p for p in state.trajectory if p.observed_at >= cutoff]
        if len(state.trajectory) > self._max_trajectory_points:
            state.trajectory = state.trajectory[-self._max_trajectory_points :]

    # -- maintenance ------------------------------------------------------- #
    def cleanup_stale(self, *, now: datetime | None = None) -> int:
        """Remove vessels whose latest observation is older than ``stale_after``.

        Returns the number of vessels removed.
        """

        reference = now or utcnow()
        cutoff = reference - self._stale_after
        with self._lock:
            stale_ids = [
                pid
                for pid, state in self._states.items()
                if state.latest.observed_at < cutoff
            ]
            for pid in stale_ids:
                del self._states[pid]
            return len(stale_ids)

    # -- reads ------------------------------------------------------------- #
    def vessel_count(self) -> int:
        with self._lock:
            return len(self._states)

    def last_message_at(self) -> datetime | None:
        with self._lock:
            return self._last_message_at

    def message_count(self) -> int:
        with self._lock:
            return self._message_count

    def snapshot(self, *, bbox: BoundingBox | None = None) -> list[LiveVesselObservation]:
        """Return the latest observation for every (optionally bbox-filtered) vessel."""

        with self._lock:
            observations = [state.latest for state in self._states.values()]
        if bbox is None:
            return observations
        return [o for o in observations if bbox.contains(o.latitude, o.longitude)]

    def get_trajectory(self, provider_id: str) -> list[TrajectoryPoint] | None:
        """Return a copy of the rolling trajectory for a vessel, or None."""

        with self._lock:
            state = self._states.get(provider_id)
            if state is None:
                return None
            return list(state.trajectory)

    def get_latest(self, provider_id: str) -> LiveVesselObservation | None:
        with self._lock:
            state = self._states.get(provider_id)
            return state.latest if state else None

    def clear(self) -> None:
        with self._lock:
            self._states.clear()
            self._last_message_at = None
            self._message_count = 0
