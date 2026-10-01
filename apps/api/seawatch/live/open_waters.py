"""Open Waters AIS provider.

Open Waters (https://openwaters.io/) exposes a free, anonymous real-time AIS
WebSocket at ``wss://ais.openwaters.io/v1/stream`` and a REST snapshot at
``https://ais.openwaters.io/v1/vessels``. Phase 7A smoke tests confirmed dense,
fresh Taiwan coverage (~1,465 unique vessels over the Taiwan bbox, timestamps
seconds old) with no credential required.

Observed frame schemas (Phase 7A, 2026-10-01):

Welcome ack::

    {"type": "welcome", "role": "anonymous", "limits": {"area": 100, ...}}

Position event (flat top-level + nested ITU-1371 ``message``)::

    {"type": "event", "mmsi": 257083750, "msg_type": "PositionReport",
     "lat": 22.3, "lon": 120.0, "time": "2026-10-01T00:48:39Z",
     "source": "aishub", "synthesized": false,
     "message": {"Sog": 16.3, "Cog": 322.2, "TrueHeading": 319,
                 "NavigationalStatus": 0, ...}}

The ``synthesized`` flag indicates the provider interpolated the position; it is
preserved so the UI never presents interpolation as a measured AIS fix.

Subscription (bbox is [[minLat, minLon, maxLat, maxLon]])::

    {"type": "subscribe", "bbox": [[21.5, 118.0, 26.5, 123.5]], "snapshot": true}
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .provider import BoundingBox, LiveAisProvider, ParsedFrame
from .schema import LiveVesselObservation, utcnow

OPEN_WATERS_WS_URL = "wss://ais.openwaters.io/v1/stream"
OPEN_WATERS_REST_URL = "https://ais.openwaters.io/v1/vessels"

# AIS "not available" sentinels we normalize to None.
_HEADING_UNAVAILABLE = 511
_SOG_UNAVAILABLE = 102.3  # 1023 * 0.1 knots
_COG_UNAVAILABLE = 360.0


def _parse_timestamp(value: Any) -> datetime | None:
    """Parse an ISO-8601 (possibly ``Z``-suffixed) timestamp into aware UTC."""

    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _clean_float(value: Any, *, unavailable: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if unavailable is not None and abs(number - unavailable) < 1e-6:
        return None
    return number


def _clean_int(value: Any, *, unavailable: int | None = None) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if unavailable is not None and number == unavailable:
        return None
    return number


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class OpenWatersProvider(LiveAisProvider):
    """Anonymous Open Waters real-time AIS provider."""

    name = "open_waters"

    @property
    def websocket_url(self) -> str:
        return OPEN_WATERS_WS_URL

    def requires_credentials(self) -> bool:
        return False

    def subscription_message(self, bbox: BoundingBox) -> dict[str, Any]:
        return {
            "type": "subscribe",
            "bbox": [[bbox.min_lat, bbox.min_lon, bbox.max_lat, bbox.max_lon]],
            "snapshot": True,
        }

    def parse_frame(self, frame: Any) -> ParsedFrame:
        if not isinstance(frame, dict):
            return ParsedFrame(kind="other")

        ftype = frame.get("type")
        if ftype in {"welcome", "subscribed", "ack"}:
            return ParsedFrame(kind="ack", detail={"limits": frame.get("limits")})

        # Position event: either a flat WS "event" or a GeoJSON Feature (REST).
        observation = self._observation_from_ws_event(frame)
        if observation is None:
            observation = self._observation_from_feature(frame)
        if observation is None:
            return ParsedFrame(kind="other")
        return ParsedFrame(kind="position", observation=observation)

    # -- WebSocket flat "event" frames ------------------------------------- #
    def _observation_from_ws_event(self, frame: dict[str, Any]) -> LiveVesselObservation | None:
        if frame.get("msg_type") not in {"PositionReport", "StandardClassBPositionReport", None}:
            # Non-position message type (e.g. ShipStaticData) — skip for live map.
            if frame.get("msg_type") is not None:
                return None
        lat = _clean_float(frame.get("lat"))
        lon = _clean_float(frame.get("lon"))
        if lat is None or lon is None:
            return None
        mmsi = _clean_int(frame.get("mmsi"))
        provider_id = str(frame.get("id") or mmsi or "")
        if not provider_id:
            return None
        observed_at = _parse_timestamp(frame.get("time")) or utcnow()

        message = frame.get("message") if isinstance(frame.get("message"), dict) else {}
        sog = _clean_float(message.get("Sog"), unavailable=_SOG_UNAVAILABLE)
        cog = _clean_float(message.get("Cog"), unavailable=_COG_UNAVAILABLE)
        heading = _clean_int(message.get("TrueHeading"), unavailable=_HEADING_UNAVAILABLE)
        nav_status = _clean_int(message.get("NavigationalStatus"))

        return LiveVesselObservation(
            provider_id=provider_id,
            latitude=lat,
            longitude=lon,
            observed_at=observed_at,
            received_at=utcnow(),
            source=_clean_str(frame.get("source")) or self.name,
            sog_knots=sog,
            cog_deg=cog,
            heading_deg=float(heading) if heading is not None else None,
            nav_status=nav_status,
            vessel_type=_clean_int(frame.get("type")),
            name=_clean_str(frame.get("name")),
            destination=_clean_str(frame.get("destination")),
            synthesized=bool(frame.get("synthesized", False)),
            mmsi=mmsi,
        )

    # -- REST / GeoJSON Feature frames ------------------------------------- #
    def _observation_from_feature(self, frame: dict[str, Any]) -> LiveVesselObservation | None:
        if frame.get("type") != "Feature":
            return None
        geometry = frame.get("geometry")
        if not isinstance(geometry, dict):
            return None
        coords = geometry.get("coordinates")
        if not isinstance(coords, (list, tuple)) or len(coords) < 2:
            return None
        lon = _clean_float(coords[0])
        lat = _clean_float(coords[1])
        if lat is None or lon is None:
            return None
        props = frame.get("properties") if isinstance(frame.get("properties"), dict) else {}
        mmsi = _clean_int(props.get("mmsi") or frame.get("id"))
        provider_id = str(frame.get("id") or mmsi or "")
        if not provider_id:
            return None
        observed_at = _parse_timestamp(props.get("seen")) or utcnow()
        heading = _clean_int(props.get("heading"), unavailable=_HEADING_UNAVAILABLE)
        return LiveVesselObservation(
            provider_id=provider_id,
            latitude=lat,
            longitude=lon,
            observed_at=observed_at,
            received_at=utcnow(),
            source=_clean_str(props.get("source")) or self.name,
            sog_knots=_clean_float(props.get("sog"), unavailable=_SOG_UNAVAILABLE),
            cog_deg=_clean_float(props.get("cog"), unavailable=_COG_UNAVAILABLE),
            heading_deg=float(heading) if heading is not None else None,
            nav_status=_clean_int(props.get("nav_status")),
            vessel_type=_clean_int(props.get("type")),
            name=_clean_str(props.get("name")),
            destination=_clean_str(props.get("destination")),
            synthesized=bool(props.get("synthesized", False)),
            mmsi=mmsi,
        )
