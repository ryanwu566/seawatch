"""Process-owned live Detection state fed by normalized Area Scan observations."""

from __future__ import annotations

import re
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

import numpy as np

from ..live.identity import VesselIdentityRegistry
from ..live.schema import LiveVesselObservation, utcnow
from .alerts import Alert
from .config import DetectionConfig
from .context import DetectionContext
from .engine import AnalysisResult
from .live_adapter import LiveDetectionAnalyzer, RollingTrackBuffer
from .models import Track
from .state import FeedbackStore


LiveDetectionStatus = Literal[
    "ready",
    "insufficient_history",
    "context_unavailable",
    "degraded",
    "error",
]
ContextQuality = Literal["historical", "static_only"]
MLScorer = Callable[[list[Track], list[Alert]], None]


@dataclass(frozen=True)
class LiveDetectionSnapshot:
    """Safe status metadata for Area Scan and Watch Floor clients."""

    status: LiveDetectionStatus
    scanned_at: datetime | None = None
    analysis_at: datetime | None = None
    n_tracks: int = 0
    n_analyzed: int = 0
    event_count: int = 0
    alert_count: int = 0
    context_quality: str | None = None
    context_source: str | None = None
    ml_available: bool = False
    error_code: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "source": "live",
            "live_source": "datalastic",
            "analysis_source": "live_detection",
            "status": self.status,
            "scanned_at": self.scanned_at.isoformat() if self.scanned_at else None,
            "analysis_at": self.analysis_at.isoformat() if self.analysis_at else None,
            "n_tracks": self.n_tracks,
            "n_analyzed": self.n_analyzed,
            "event_count": self.event_count,
            "alert_count": self.alert_count,
            "context_quality": self.context_quality,
            "context_source": self.context_source,
            "ml_available": self.ml_available,
            "error_code": self.error_code,
        }


@dataclass(frozen=True)
class LiveDetectionComponents:
    """Long-lived dependencies created together for one live Detection runtime."""

    analyzer: Any
    context: DetectionContext
    context_quality: ContextQuality
    context_source: str | None = None
    feedback: FeedbackStore | None = None
    ml_scorer: MLScorer | None = None
    ml_available: bool = False


def _clone_context(source: DetectionContext) -> DetectionContext:
    """Reuse learned objects without sharing mutable analysis counters."""

    context = DetectionContext(
        list(source.zones),
        list(source.receivers),
        source.baseline,
        set(source.allowlist),
        learned=source.learned,
        bounds=source.bounds,
    )
    context.territory = source.territory
    context.habits = source.habits
    context.habitual = dict(source.habitual)
    return context


def _build_ml_scorer(models: Any, context: DetectionContext) -> MLScorer:
    """Reuse the existing window features and alert-scoring contract."""

    from . import ml as ml_module
    from .features import window_features

    config = DetectionConfig()

    def score(tracks: list[Track], alerts: list[Alert]) -> None:
        if not tracks or not alerts:
            return
        t0 = min(float(track.t[0]) for track in tracks if len(track))
        t1 = max(float(track.t[-1]) for track in tracks if len(track))
        windows = window_features(
            tracks,
            t0,
            t1,
            context,
            learned=context.learned,
            cfg=config,
        )
        if windows.empty:
            return
        windows["gb"] = models.gb_score(windows)
        windows["if"] = models.if_score(windows)
        for alert in alerts:
            alert.ml = ml_module.score_alert(
                models,
                windows,
                alert.mmsis,
                alert.t_start,
                alert.t_end,
                alert.risk,
            )

    return score


def build_live_detection_components() -> LiveDetectionComponents:
    """Build live dependencies once without substituting simulated context."""

    from .service import get_service
    from .territory import Territory

    service = get_service()
    data_kind = service.info.get("data_kind")
    if data_kind == "simulated":
        context = DetectionContext([], [], None, set(service.store.allowlist))
        context.territory = Territory.default()
        context_quality: ContextQuality = "static_only"
    else:
        context = _clone_context(service._context())
        context_quality = "historical"

    analyzer = LiveDetectionAnalyzer(
        context,
        buffer=RollingTrackBuffer(stale_after=timedelta(minutes=15)),
        density="sparse_live",
        feedback=service.store,
        watch=service.watch,
    )
    models = service.ml_models
    return LiveDetectionComponents(
        analyzer=analyzer,
        context=context,
        context_quality=context_quality,
        context_source=service.region if context_quality == "historical" else None,
        feedback=service.store,
        ml_scorer=_build_ml_scorer(models, context) if models is not None else None,
        ml_available=models is not None,
    )


class LiveDetectionRuntime:
    """Synchronize repeated live batches and cache the latest successful analysis."""

    def __init__(
        self,
        identity_registry: VesselIdentityRegistry,
        *,
        component_factory: Callable[[], LiveDetectionComponents] = build_live_detection_components,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._identity_registry = identity_registry
        self._component_factory = component_factory
        self._clock = clock
        self._lock = threading.RLock()
        self._components: LiveDetectionComponents | None = None
        self._latest_result: AnalysisResult | None = None
        self._snapshot = LiveDetectionSnapshot(status="insufficient_history")

    @property
    def latest_result(self) -> AnalysisResult | None:
        with self._lock:
            return self._latest_result

    def snapshot(self) -> LiveDetectionSnapshot:
        with self._lock:
            return self._snapshot

    def _load_components(self) -> LiveDetectionComponents:
        if self._components is None:
            self._components = self._component_factory()
        return self._components

    def update(
        self,
        observations: Iterable[LiveVesselObservation],
        *,
        scanned_at: datetime,
    ) -> LiveDetectionSnapshot:
        """Ingest one finite batch and analyze once without leaking failures."""

        batch = tuple(observations)
        with self._lock:
            try:
                components = self._load_components()
            except Exception:  # noqa: BLE001 - context failure must not break a paid scan
                self._snapshot = LiveDetectionSnapshot(
                    status="context_unavailable",
                    scanned_at=scanned_at,
                    analysis_at=self._snapshot.analysis_at,
                    error_code="context_unavailable",
                )
                return self._snapshot

            if components.feedback is not None:
                components.context.allowlist = set(components.feedback.allowlist)
            try:
                result = components.analyzer.update(
                    batch,
                    as_of=scanned_at.timestamp(),
                )
            except Exception:  # noqa: BLE001 - analysis failure is an isolated domain
                previous = self._snapshot
                self._snapshot = LiveDetectionSnapshot(
                    status="error",
                    scanned_at=scanned_at,
                    analysis_at=previous.analysis_at,
                    n_tracks=previous.n_tracks,
                    n_analyzed=previous.n_analyzed,
                    event_count=previous.event_count,
                    alert_count=previous.alert_count,
                    context_quality=components.context_quality,
                    context_source=components.context_source,
                    ml_available=components.ml_available,
                    error_code="analysis_error",
                )
                return self._snapshot

            for alert in result.alerts:
                timed_events = [
                    event for event in alert.events if event.kind != "dark_rendezvous"
                ] or list(alert.events)
                alert.raised_at = (
                    min(
                        float(event.metrics.get("detected_at", event.t_end))
                        for event in timed_events
                    )
                    if timed_events
                    else float(alert.t_end)
                )

            ml_failed = False
            if result.alerts and components.ml_scorer is not None:
                try:
                    components.ml_scorer(components.analyzer.tracks(), result.alerts)
                except Exception:  # noqa: BLE001 - ML is optional second opinion
                    ml_failed = True
                    for alert in result.alerts:
                        alert.ml = None
            if components.feedback is not None:
                for alert in result.alerts:
                    components.feedback.apply(alert)

            self._latest_result = result
            if result.n_tracks == 0 or result.n_analyzed == 0:
                status: LiveDetectionStatus = "insufficient_history"
            elif components.context_quality != "historical" or ml_failed:
                status = "degraded"
            else:
                status = "ready"
            self._snapshot = LiveDetectionSnapshot(
                status=status,
                scanned_at=scanned_at,
                analysis_at=self._clock(),
                n_tracks=result.n_tracks,
                n_analyzed=result.n_analyzed,
                event_count=len(result.events),
                alert_count=len(result.alerts),
                context_quality=components.context_quality,
                context_source=components.context_source,
                ml_available=components.ml_available,
                error_code="ml_unavailable" if ml_failed else None,
            )
            return self._snapshot

    # Public serialization is implemented here so raw identities never cross
    # the API boundary. API-facing methods are completed with the live routes.
    def _public_id(self, value: str) -> str:
        try:
            public_id = self._identity_registry.public_id_for_mmsi(int(value))
        except (TypeError, ValueError):
            public_id = None
        if public_id is None:
            raise ValueError("live Detection identity is not joinable")
        return public_id

    def _redact_text(self, value: str) -> str:
        def replace(match: re.Match[str]) -> str:
            raw = match.group(0)
            try:
                return self._public_id(raw)
            except ValueError:
                return raw

        return re.sub(r"(?<!\d)\d{9}(?!\d)", replace, value)

    def _redact(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: self._redact(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._redact(item) for item in value]
        if isinstance(value, tuple):
            return [self._redact(item) for item in value]
        if isinstance(value, str):
            return self._redact_text(value)
        return value

    def _current_tracks(self) -> list[Track]:
        if self._components is None:
            return []
        return list(self._components.analyzer.tracks())

    def public_meta(self) -> dict[str, Any]:
        """Return a Watch Floor-compatible live scenario envelope."""

        with self._lock:
            tracks = self._current_tracks()
            timestamps = [float(value) for track in tracks for value in track.t]
            if tracks:
                min_lat = min(float(track.lat.min()) for track in tracks)
                min_lon = min(float(track.lon.min()) for track in tracks)
                max_lat = max(float(track.lat.max()) for track in tracks)
                max_lon = max(float(track.lon.max()) for track in tracks)
                bounds = [
                    [min_lon - 0.05, min_lat - 0.05],
                    [max_lon + 0.05, max_lat + 0.05],
                ]
            else:
                bounds = [[119.0, 21.0], [123.0, 26.5]]
            context = self._components.context if self._components is not None else None
            status = self._snapshot
            return {
                "region": "live",
                "region_label": "Live Datalastic Area Scan",
                "timezone": "Asia/Taipei",
                "data_kind": "real",
                "note": (
                    "Live behavioral review candidates from explicit Datalastic "
                    "Area Scans; no intent or legality determination."
                ),
                "bounds": bounds,
                "name": "Live Datalastic Area Scan",
                "t0": min(timestamps) if timestamps else 0.0,
                "t1": max(timestamps) if timestamps else 0.0,
                "vessels": len(tracks),
                "fixes": len(timestamps),
                "simulated": False,
                "hourly": False,
                "tracks_sampled": False,
                "zones": [
                    {
                        "id": zone.id,
                        "name": zone.name,
                        "kind": zone.kind,
                        "description": zone.description,
                        "polygon": [
                            [round(float(lat), 4), round(float(lon), 4)]
                            for lat, lon in zone.polygon
                        ],
                    }
                    for zone in (context.zones if context is not None else [])
                ],
                "receivers": [
                    {
                        "id": receiver.id,
                        "lat": receiver.lat,
                        "lon": receiver.lon,
                        "range_nm": receiver.range_nm,
                    }
                    for receiver in (
                        context.receivers if context is not None else []
                    )
                ],
                "source": "live",
                "detection_status": status.status,
                "scanned_at": (
                    status.scanned_at.isoformat() if status.scanned_at else None
                ),
                "analysis_at": (
                    status.analysis_at.isoformat() if status.analysis_at else None
                ),
                "context_quality": status.context_quality,
                "context_source": status.context_source,
                "ml_available": status.ml_available,
            }

    def public_tracks(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                self._redact(track_to_public_dict(track, self._public_id(track.mmsi)))
                for track in self._current_tracks()
            ]

    def _public_alert(self, alert: Alert, *, detail: bool) -> dict[str, Any]:
        payload = self._redact(alert.detail() if detail else alert.summary())
        public_ids = list(payload.get("mmsis", []))
        payload["public_ids"] = public_ids
        for vessel in payload.get("vessels", []):
            if isinstance(vessel, dict) and isinstance(vessel.get("mmsi"), str):
                vessel["public_id"] = vessel["mmsi"]
        payload["source"] = "live"
        payload["analysis_at"] = (
            self._snapshot.analysis_at.isoformat()
            if self._snapshot.analysis_at is not None
            else None
        )
        if detail:
            payload["path_reviews"] = []
        return payload

    def public_alerts(self, *, include_dismissed: bool = False) -> list[dict[str, Any]]:
        with self._lock:
            alerts = list(self._latest_result.alerts) if self._latest_result else []
            if not include_dismissed:
                alerts = [alert for alert in alerts if alert.status != "false_alarm"]
            return [self._public_alert(alert, detail=False) for alert in alerts]

    def public_alert(self, alert_id: str) -> dict[str, Any] | None:
        with self._lock:
            if self._latest_result is None:
                return None
            alert = next(
                (item for item in self._latest_result.alerts if item.id == alert_id),
                None,
            )
            return self._public_alert(alert, detail=True) if alert is not None else None

    def _internal_alert(self, alert_id: str) -> Alert | None:
        if self._latest_result is None:
            return None
        return next(
            (item for item in self._latest_result.alerts if item.id == alert_id),
            None,
        )

    def set_alert_status(
        self,
        alert_id: str,
        status: str,
        *,
        operator: str = "operator",
        note: str | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            alert = self._internal_alert(alert_id)
            feedback = self._components.feedback if self._components else None
            if alert is None or feedback is None:
                return None
            feedback.set_status(alert, status, operator)
            if note:
                feedback.add_note(alert, note, operator)
            feedback.apply(alert)
            return self._public_alert(alert, detail=True)

    def add_alert_note(
        self,
        alert_id: str,
        text: str,
        *,
        operator: str = "operator",
    ) -> dict[str, Any] | None:
        with self._lock:
            alert = self._internal_alert(alert_id)
            feedback = self._components.feedback if self._components else None
            if alert is None or feedback is None:
                return None
            feedback.add_note(alert, text, operator)
            feedback.apply(alert)
            return self._public_alert(alert, detail=True)


def track_to_public_dict(
    track: Track,
    public_id: str,
) -> dict[str, Any]:
    """Return the existing Watch Floor track shape with an opaque identity."""

    return {
        "mmsi": public_id,
        "public_id": public_id,
        "name": track.name,
        "type": track.ship_type,
        "flag": track.flag,
        "t": [int(value) for value in track.t],
        "lat": [round(float(value), 4) for value in track.lat],
        "lon": [round(float(value), 4) for value in track.lon],
        "sog": [
            round(float(value), 1) if np.isfinite(value) else None
            for value in track.sog
        ],
    }
