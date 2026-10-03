"""Validated, deterministic geometry support for manual live area scans."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import logging
import math
import threading
import time
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel
from pyproj import CRS, Geod, Transformer
from shapely.geometry import Point, Polygon, box
from shapely.ops import transform

from .datalastic import RadiusQuery
from .datalastic import (
    DatalasticAreaScanProvider,
    DatalasticStatusCache,
    DatalasticVessel,
    ProviderError,
    ProviderErrorCategory,
)
from .active_view import ActiveTrack
from .area_scan_access import AreaScanAdmissionController
from .identity import VesselIdentityRegistry, is_valid_mmsi
from .schema import LiveVesselObservation, TrajectoryPoint, utcnow


SCAN_RADIUS_NM = 45.0
MAX_PROVIDER_CIRCLES = 16
SCAN_CACHE_TTL_SECONDS = 45.0
MAX_POLYGON_COORDINATES = 512
MAX_SCAN_CACHE_ENTRIES = 128
MAX_SCAN_VESSELS = 1_000
MAX_TRACK_VESSELS = 1_000
MAX_TRACK_POINTS = 120
TRACK_TTL_SECONDS = 1_800.0
AREA_SCAN_FRESH_SECONDS = 900.0
_METERS_PER_NM = 1852.0
_GRID_MARGIN = 0.95
_CACHE_ALGORITHM_VERSION = b"datalastic-area-cover-v2:"
_SINGLE_CIRCLE_MARGIN_NM = 0.1
_SINGLE_CIRCLE_RELATIVE_MARGIN = 0.0025
_SINGLE_CIRCLE_ROUNDING_NM = 0.1
_MAX_BOUNDARY_SAMPLE_STEP_DEGREES = 0.01
_TOO_LARGE = "Selected area is too large. Draw a smaller region."
_LOGGER = logging.getLogger("seawatch.live.area_scan")


class ScanValidationError(ValueError):
    """Safe client-visible geometry validation failure."""


class PolygonGeometry(BaseModel):
    type: Literal["Polygon"]
    coordinates: list[list[list[float]]]


class AreaScanRequest(BaseModel):
    geometry: PolygonGeometry


@dataclass(frozen=True)
class ValidatedPolygon:
    polygon: Polygon


@dataclass(frozen=True)
class AreaScanSummary:
    geometry_type: str
    provider_queries: int


@dataclass(frozen=True)
class AreaScanPlan:
    area_square_km: float
    provider_queries: int | None
    max_provider_queries: int
    can_scan: bool
    reason: str | None = None

    def to_public_dict(self) -> dict:
        return {
            "area_square_km": self.area_square_km,
            "provider_queries": self.provider_queries,
            "max_provider_queries": self.max_provider_queries,
            "can_scan": self.can_scan,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class AreaScanResult:
    source: str
    scanned_at: datetime
    cached: bool
    scan: AreaScanSummary
    vessels: tuple[dict, ...]

    @property
    def total(self) -> int:
        return len(self.vessels)

    def to_public_dict(self) -> dict:
        return {
            "source": self.source,
            "scanned_at": self.scanned_at.isoformat(),
            "cached": self.cached,
            "scan": {
                "geometry_type": self.scan.geometry_type,
                "provider_queries": self.scan.provider_queries,
            },
            "total": self.total,
            "vessels": list(self.vessels),
        }


@dataclass(frozen=True)
class _CacheEntry:
    result: AreaScanResult
    expires_at: float


@dataclass
class _TrackEntry:
    source_keys: set[str]
    points: list[TrajectoryPoint]
    latest_observed_at: datetime | None
    latest_latitude: float
    latest_longitude: float
    expires_at: float


@dataclass(frozen=True)
class _NormalizedAreaScanObservation:
    observation: LiveVesselObservation
    provider_observed_at: datetime | None
    provider_vessel_type: str | None
    provider_vessel_type_specific: str | None


class AreaScanService:
    """Run explicit scans with isolated state, identity, tracks, and TTL cache."""

    def __init__(
        self,
        *,
        provider: DatalasticAreaScanProvider | None,
        identity_registry: VesselIdentityRegistry,
        status_cache: DatalasticStatusCache | None = None,
        admission: AreaScanAdmissionController | None = None,
        monotonic=time.monotonic,
        clock=utcnow,
        max_cache_entries: int = MAX_SCAN_CACHE_ENTRIES,
        max_scan_vessels: int = MAX_SCAN_VESSELS,
        max_track_vessels: int = MAX_TRACK_VESSELS,
        max_track_points: int = MAX_TRACK_POINTS,
        track_ttl_seconds: float = TRACK_TTL_SECONDS,
        observation_sink=None,
    ) -> None:
        if min(
            max_cache_entries,
            max_scan_vessels,
            max_track_vessels,
            max_track_points,
        ) <= 0 or track_ttl_seconds <= 0:
            raise ValueError("Area Scan retention limits must be positive")
        self._provider = provider
        self._identity_registry = identity_registry
        self._status_cache = status_cache
        self._admission = admission
        self._monotonic = monotonic
        self._clock = clock
        self._max_cache_entries = max_cache_entries
        self._max_scan_vessels = max_scan_vessels
        self._max_track_vessels = max_track_vessels
        self._max_track_points = max_track_points
        self._track_ttl_seconds = track_ttl_seconds
        self._observation_sink = observation_sink
        self._cache: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._inflight: dict[str, asyncio.Task[_CacheEntry]] = {}
        self._cache_lock = asyncio.Lock()
        self._tracks: OrderedDict[str, _TrackEntry] = OrderedDict()
        self._track_lock = threading.RLock()
        self._last_message_at: datetime | None = None
        self._last_message_monotonic: float | None = None

    def set_provider(self, provider) -> None:
        """Replace the request provider (dependency seam used by runtime tests)."""

        self._provider = provider

    def clear_cache(self) -> None:
        self._cache.clear()

    async def scan(self, request: AreaScanRequest) -> AreaScanResult:
        validated = validate_scan_geometry(request)
        circles = cover_polygon(validated.polygon)
        cache_key = canonical_geometry_key(validated.polygon)
        now_monotonic = self._monotonic()

        async with self._cache_lock:
            self._sweep_expired_cache(now_monotonic)
            cached = self._cache.get(cache_key)
            if cached is not None and cached.expires_at > now_monotonic:
                if self._admission is not None:
                    self._admission.authorize(provider_requests=0)
                self._cache.move_to_end(cache_key)
                return _with_cached(cached.result, True)
            task = self._inflight.get(cache_key)
            owner = task is None
            if task is None:
                if self._admission is not None:
                    self._admission.authorize(
                        provider_requests=len(circles) + 1
                    )
                task = asyncio.create_task(
                    self._perform_and_publish(
                        cache_key, validated.polygon, circles
                    )
                )
                task.add_done_callback(_consume_task_exception)
                self._inflight[cache_key] = task
            elif self._admission is not None:
                self._admission.authorize(provider_requests=0)

        entry = await asyncio.shield(task)
        return _with_cached(entry.result, not owner)

    async def _perform_and_publish(
        self,
        cache_key: str,
        polygon: Polygon,
        circles: tuple[RadiusQuery, ...],
    ) -> _CacheEntry:
        current_task = asyncio.current_task()
        try:
            entry = await self._perform_scan(polygon, circles)
        except BaseException:
            async with self._cache_lock:
                if self._inflight.get(cache_key) is current_task:
                    self._inflight.pop(cache_key, None)
            raise
        async with self._cache_lock:
            if self._inflight.get(cache_key) is current_task:
                self._cache[cache_key] = entry
                self._cache.move_to_end(cache_key)
                while len(self._cache) > self._max_cache_entries:
                    self._cache.popitem(last=False)
                self._inflight.pop(cache_key, None)
        return entry

    def _sweep_expired_cache(self, now_monotonic: float) -> None:
        for key in tuple(self._cache):
            if self._cache[key].expires_at <= now_monotonic:
                del self._cache[key]

    async def _perform_scan(
        self, polygon: Polygon, circles: tuple[RadiusQuery, ...]
    ) -> _CacheEntry:
        if self._provider is None:
            raise ProviderError(ProviderErrorCategory.NOT_CONFIGURED)
        try:
            candidates = await self._provider.scan(circles)
        except ProviderError as exc:
            if self._status_cache is not None:
                self._status_cache.record_failure(exc.category)
            raise
        if self._status_cache is not None:
            self._status_cache.record_reachable()
        received_at = self._clock()
        observations = self._normalize_candidates(
            candidates, polygon, received_at=received_at
        )
        if len(observations) > self._max_scan_vessels:
            raise ProviderError(ProviderErrorCategory.UPSTREAM)
        await self._deliver_observations(observations, received_at)
        features: list[dict] = []
        for normalized in observations:
            observation = normalized.observation
            provider_observed_at = normalized.provider_observed_at
            public_id = self._identity_registry.public_id_for(observation)
            self._record_track(
                public_id,
                observation,
                provider_observed_at=provider_observed_at,
            )
            properties = observation.to_public_properties(public_id=public_id)
            properties["provider_vessel_type"] = normalized.provider_vessel_type
            properties["provider_vessel_type_specific"] = (
                normalized.provider_vessel_type_specific
            )
            properties["observed_at"] = (
                provider_observed_at.isoformat()
                if provider_observed_at is not None
                else None
            )
            data_age_seconds = (
                round(observation.age_seconds(now=received_at), 1)
                if provider_observed_at is not None
                else None
            )
            properties["data_age_seconds"] = data_age_seconds
            properties["freshness_state"] = (
                "unknown"
                if data_age_seconds is None
                else (
                    "fresh"
                    if data_age_seconds < AREA_SCAN_FRESH_SECONDS
                    else "stale"
                )
            )
            features.append(
                {
                    "type": "Feature",
                    "id": public_id,
                    "geometry": {
                        "type": "Point",
                        "coordinates": [
                            observation.longitude,
                            observation.latitude,
                        ],
                    },
                    "properties": properties,
                }
            )
        result = AreaScanResult(
            source="datalastic",
            scanned_at=received_at,
            cached=False,
            scan=AreaScanSummary(
                geometry_type="Polygon", provider_queries=len(circles)
            ),
            vessels=tuple(features),
        )
        return _CacheEntry(
            result=result,
            expires_at=self._monotonic() + SCAN_CACHE_TTL_SECONDS,
        )

    async def _deliver_observations(
        self,
        observations: tuple[_NormalizedAreaScanObservation, ...],
        scanned_at: datetime,
    ) -> None:
        """Send one real-timestamped batch to Detection without coupling failures."""

        if self._observation_sink is None:
            return
        detection_batch = tuple(
            normalized.observation
            for normalized in observations
            if normalized.provider_observed_at is not None
        )
        try:
            outcome = self._observation_sink(detection_batch, scanned_at)
            if inspect.isawaitable(outcome):
                await outcome
        except Exception:  # noqa: BLE001 - a paid provider result remains usable
            _LOGGER.warning("Live Detection update failed")

    def _normalize_candidates(
        self,
        candidates: tuple[DatalasticVessel, ...],
        polygon: Polygon,
        *,
        received_at: datetime,
    ) -> tuple[_NormalizedAreaScanObservation, ...]:
        filtered = tuple(
            candidate
            for candidate in candidates
            if polygon.covers(Point(candidate.longitude, candidate.latitude))
        )
        reconciled = _reconcile_candidates(filtered)
        normalized: list[_NormalizedAreaScanObservation] = []
        for key, candidate, trusted_mmsi in reconciled:
            internal_digest = hashlib.sha256(
                f"datalastic:{key[0]}:{key[1]}".encode("utf-8")
            ).hexdigest()[:32]
            normalized.append(
                _NormalizedAreaScanObservation(
                    observation=LiveVesselObservation(
                        provider_id=f"datalastic_{internal_digest}",
                        latitude=candidate.latitude,
                        longitude=candidate.longitude,
                        observed_at=candidate.observed_at or received_at,
                        received_at=received_at,
                        source="datalastic",
                        sog_knots=candidate.speed_knots,
                        cog_deg=candidate.course_deg,
                        heading_deg=candidate.heading_deg,
                        nav_status=None,
                        vessel_type=None,
                        name=candidate.name,
                        destination=candidate.destination,
                        synthesized=False,
                        mmsi=trusted_mmsi,
                    ),
                    provider_observed_at=candidate.observed_at,
                    provider_vessel_type=candidate.vessel_type,
                    provider_vessel_type_specific=candidate.vessel_type_specific,
                )
            )
        return tuple(normalized)

    def track(self, public_id: str) -> ActiveTrack | None:
        with self._track_lock:
            self._sweep_expired_tracks(self._monotonic())
            entry = self._tracks.get(public_id)
            if entry is None:
                return None
            return ActiveTrack(
                public_id=public_id,
                source_name="datalastic",
                points=list(entry.points),
            )

    def vessel_count(self) -> int:
        with self._track_lock:
            self._sweep_expired_tracks(self._monotonic())
            return len(self._tracks)

    def last_message_at(self) -> datetime | None:
        with self._track_lock:
            return self._last_message_at

    def last_message_monotonic(self) -> float | None:
        with self._track_lock:
            return self._last_message_monotonic

    def _record_track(
        self,
        public_id: str,
        observation: LiveVesselObservation,
        *,
        provider_observed_at: datetime | None,
    ) -> None:
        now_monotonic = self._monotonic()
        point = (
            TrajectoryPoint(
                latitude=observation.latitude,
                longitude=observation.longitude,
                observed_at=provider_observed_at,
                synthesized=observation.synthesized,
            )
            if provider_observed_at is not None
            else None
        )
        with self._track_lock:
            self._sweep_expired_tracks(now_monotonic)
            entry = self._tracks.get(public_id)
            if entry is None:
                entry = _TrackEntry(
                    source_keys={observation.provider_id},
                    points=[point] if point is not None else [],
                    latest_observed_at=provider_observed_at,
                    latest_latitude=observation.latitude,
                    latest_longitude=observation.longitude,
                    expires_at=now_monotonic + self._track_ttl_seconds,
                )
                self._tracks[public_id] = entry
            else:
                entry.source_keys.add(observation.provider_id)
                entry.expires_at = now_monotonic + self._track_ttl_seconds
                if provider_observed_at is not None and (
                    entry.latest_observed_at is None
                    or provider_observed_at >= entry.latest_observed_at
                ):
                    moved = (
                        abs(observation.latitude - entry.latest_latitude) > 1e-5
                        or abs(observation.longitude - entry.latest_longitude) > 1e-5
                    )
                    if point is not None and (moved or not entry.points):
                        entry.points.append(point)
                        if len(entry.points) > self._max_track_points:
                            entry.points = entry.points[-self._max_track_points :]
                    entry.latest_observed_at = provider_observed_at
                    entry.latest_latitude = observation.latitude
                    entry.latest_longitude = observation.longitude
                self._tracks.move_to_end(public_id)
            self._last_message_at = self._clock()
            self._last_message_monotonic = now_monotonic
            while len(self._tracks) > self._max_track_vessels:
                expired_id, expired = self._tracks.popitem(last=False)
                self._expire_track_identity(expired_id, expired)

    def _sweep_expired_tracks(self, now_monotonic: float) -> None:
        expired_ids = [
            public_id
            for public_id, entry in self._tracks.items()
            if entry.expires_at <= now_monotonic
        ]
        for public_id in expired_ids:
            entry = self._tracks.pop(public_id)
            self._expire_track_identity(public_id, entry)

    def _expire_track_identity(self, public_id: str, entry: _TrackEntry) -> None:
        for source_key in entry.source_keys:
            self._identity_registry.expire_source(
                public_id, "datalastic", source_key
            )


def validate_scan_geometry(request: AreaScanRequest) -> ValidatedPolygon:
    """Validate a WGS84 GeoJSON Polygon without silently repairing it."""

    rings = request.geometry.coordinates
    if not rings:
        raise ScanValidationError("Polygon coordinates are required")
    coordinate_count = sum(len(ring) for ring in rings)
    if coordinate_count > MAX_POLYGON_COORDINATES:
        raise ScanValidationError("Polygon has too many coordinates")

    normalized_rings: list[list[tuple[float, float]]] = []
    all_longitudes: list[float] = []
    for ring in rings:
        if len(ring) < 4:
            raise ScanValidationError("Polygon rings require at least four coordinates")
        normalized_ring: list[tuple[float, float]] = []
        for coordinate in ring:
            if len(coordinate) != 2:
                raise ScanValidationError("Coordinates must be [longitude, latitude]")
            longitude, latitude = float(coordinate[0]), float(coordinate[1])
            if not math.isfinite(longitude) or not math.isfinite(latitude):
                raise ScanValidationError("Coordinates must be finite")
            if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
                raise ScanValidationError("Coordinates are outside WGS84 bounds")
            normalized_ring.append((longitude, latitude))
            all_longitudes.append(longitude)
        if normalized_ring[0] != normalized_ring[-1]:
            raise ScanValidationError("Polygon rings must be closed")
        if any(
            abs(current[0] - previous[0]) > 180
            for previous, current in zip(normalized_ring, normalized_ring[1:])
        ):
            raise ScanValidationError("Antimeridian-crossing polygons are unsupported")
        normalized_rings.append(normalized_ring)

    if max(all_longitudes) - min(all_longitudes) > 180:
        raise ScanValidationError("Antimeridian-crossing polygons are unsupported")

    polygon = Polygon(normalized_rings[0], holes=normalized_rings[1:])
    if polygon.is_empty or polygon.area <= 0 or not polygon.is_valid:
        raise ScanValidationError("Polygon geometry is invalid")
    return ValidatedPolygon(polygon=polygon)


def plan_scan_geometry(request: AreaScanRequest) -> AreaScanPlan:
    """Validate and price a scan locally without contacting Datalastic."""

    validated = validate_scan_geometry(request)
    area_square_meters, _ = Geod(ellps="WGS84").geometry_area_perimeter(
        validated.polygon
    )
    area_square_km = round(abs(area_square_meters) / 1_000_000.0, 2)
    try:
        circles = cover_polygon(validated.polygon)
    except ScanValidationError as exc:
        if str(exc) != _TOO_LARGE:
            raise
        return AreaScanPlan(
            area_square_km=area_square_km,
            provider_queries=None,
            max_provider_queries=MAX_PROVIDER_CIRCLES,
            can_scan=False,
            reason="too_large",
        )
    return AreaScanPlan(
        area_square_km=area_square_km,
        provider_queries=len(circles),
        max_provider_queries=MAX_PROVIDER_CIRCLES,
        can_scan=True,
    )


def canonical_geometry_key(polygon: Polygon) -> str:
    """Hash an orientation/start-order independent normalized polygon."""

    normalized = polygon.normalize()
    return hashlib.sha256(_CACHE_ALGORITHM_VERSION + normalized.wkb).hexdigest()


def cover_polygon(polygon: Polygon) -> tuple[RadiusQuery, ...]:
    """Cover a polygon with deterministic, safety-margined 45-NM circles."""

    min_lon, min_lat, max_lon, max_lat = polygon.bounds
    center_lon = (min_lon + max_lon) / 2.0
    center_lat = (min_lat + max_lat) / 2.0
    local_crs = CRS.from_proj4(
        f"+proj=aeqd +lat_0={center_lat:.12f} +lon_0={center_lon:.12f} "
        "+datum=WGS84 +units=m +no_defs"
    )
    forward = Transformer.from_crs("EPSG:4326", local_crs, always_xy=True)
    inverse = Transformer.from_crs(local_crs, "EPSG:4326", always_xy=True)
    projected = transform(forward.transform, polygon)

    radius_m = SCAN_RADIUS_NM * _METERS_PER_NM
    p_min_x, p_min_y, p_max_x, p_max_y = projected.bounds
    bounds_center_x = (p_min_x + p_max_x) / 2.0
    bounds_center_y = (p_min_y + p_max_y) / 2.0
    longitude, latitude = inverse.transform(bounds_center_x, bounds_center_y)
    required_radius_nm = _required_geodesic_radius_nm(
        polygon, center_longitude=float(longitude), center_latitude=float(latitude)
    )
    radius_with_margin = required_radius_nm + max(
        _SINGLE_CIRCLE_MARGIN_NM,
        required_radius_nm * _SINGLE_CIRCLE_RELATIVE_MARGIN,
    )
    tight_radius_nm = (
        math.ceil(radius_with_margin / _SINGLE_CIRCLE_ROUNDING_NM)
        * _SINGLE_CIRCLE_ROUNDING_NM
    )
    if tight_radius_nm <= SCAN_RADIUS_NM:
        return (
            RadiusQuery(
                latitude=float(latitude),
                longitude=float(longitude),
                radius_nm=tight_radius_nm,
            ),
        )

    cell_size = radius_m * math.sqrt(2.0) * _GRID_MARGIN
    min_column = math.floor(p_min_x / cell_size)
    max_column = math.floor(p_max_x / cell_size)
    min_row = math.floor(p_min_y / cell_size)
    max_row = math.floor(p_max_y / cell_size)
    centers: list[tuple[float, float]] = []
    for row in range(min_row, max_row + 1):
        for column in range(min_column, max_column + 1):
            cell_min_x = column * cell_size
            cell_min_y = row * cell_size
            cell = box(
                cell_min_x,
                cell_min_y,
                cell_min_x + cell_size,
                cell_min_y + cell_size,
            )
            if not projected.intersects(cell):
                continue
            centers.append(
                (cell_min_x + cell_size / 2.0, cell_min_y + cell_size / 2.0)
            )
            if len(centers) > MAX_PROVIDER_CIRCLES:
                raise ScanValidationError(_TOO_LARGE)

    if not centers or len(centers) > MAX_PROVIDER_CIRCLES:
        raise ScanValidationError(_TOO_LARGE)

    queries: list[RadiusQuery] = []
    for center_x, center_y in centers:
        longitude, latitude = inverse.transform(center_x, center_y)
        queries.append(
            RadiusQuery(
                latitude=float(latitude),
                longitude=float(longitude),
                radius_nm=SCAN_RADIUS_NM,
            )
        )
    return tuple(queries)


def _required_geodesic_radius_nm(
    polygon: Polygon, *, center_longitude: float, center_latitude: float
) -> float:
    """Conservatively sample every WGS84 boundary segment from the center."""

    geod = Geod(ellps="WGS84")
    maximum_meters = 0.0
    rings = (polygon.exterior, *polygon.interiors)
    for ring in rings:
        coordinates = list(ring.coords)
        for start, end in zip(coordinates, coordinates[1:]):
            longitude_delta = end[0] - start[0]
            latitude_delta = end[1] - start[1]
            steps = max(
                1,
                math.ceil(
                    max(abs(longitude_delta), abs(latitude_delta))
                    / _MAX_BOUNDARY_SAMPLE_STEP_DEGREES
                ),
            )
            for index in range(steps + 1):
                fraction = index / steps
                longitude = start[0] + longitude_delta * fraction
                latitude = start[1] + latitude_delta * fraction
                _, _, distance_meters = geod.inv(
                    center_longitude,
                    center_latitude,
                    longitude,
                    latitude,
                )
                maximum_meters = max(maximum_meters, abs(distance_meters))
    return maximum_meters / _METERS_PER_NM


def _reconcile_candidates(
    candidates: tuple[DatalasticVessel, ...],
) -> tuple[tuple[tuple[str, str], DatalasticVessel, int | None], ...]:
    """Deduplicate provider rows without promoting ambiguous cross-source IDs."""

    uuid_groups: dict[tuple[str, str], list[DatalasticVessel]] = defaultdict(list)
    without_uuid: list[DatalasticVessel] = []
    for candidate in sorted(candidates, key=_candidate_sort_key):
        if candidate.uuid:
            uuid_groups[("uuid", candidate.uuid)].append(candidate)
        else:
            without_uuid.append(candidate)

    mmsi_to_uuid_groups: dict[int, set[tuple[str, str]]] = defaultdict(set)
    for key, group in uuid_groups.items():
        for candidate in group:
            if is_valid_mmsi(candidate.mmsi):
                assert candidate.mmsi is not None
                mmsi_to_uuid_groups[candidate.mmsi].add(key)

    groups = dict(uuid_groups)
    for candidate in without_uuid:
        valid_mmsi = candidate.mmsi if is_valid_mmsi(candidate.mmsi) else None
        if valid_mmsi is not None:
            matching_uuid_groups = mmsi_to_uuid_groups.get(valid_mmsi, set())
            if len(matching_uuid_groups) == 1:
                key = next(iter(matching_uuid_groups))
            elif len(matching_uuid_groups) == 0:
                key = ("mmsi", str(valid_mmsi))
            else:
                key = ("ambiguous", _fallback_fingerprint(candidate))
        elif candidate.imo is not None:
            key = ("imo", str(candidate.imo))
        else:
            key = ("fallback", _fallback_fingerprint(candidate))
        groups.setdefault(key, []).append(candidate)

    reconciled: list[tuple[tuple[str, str], DatalasticVessel, int | None]] = []
    for key in sorted(groups):
        group = groups[key]
        mmsis = {
            candidate.mmsi
            for candidate in group
            if is_valid_mmsi(candidate.mmsi)
        }
        has_invalid_present_mmsi = any(
            candidate.mmsi is not None and not is_valid_mmsi(candidate.mmsi)
            for candidate in group
        )
        trusted_mmsi: int | None = None
        if len(mmsis) == 1 and not has_invalid_present_mmsi:
            only_mmsi = next(iter(mmsis))
            if len(mmsi_to_uuid_groups.get(only_mmsi, set())) <= 1:
                trusted_mmsi = only_mmsi
        latest = max(group, key=_candidate_latest_key)
        reconciled.append((key, latest, trusted_mmsi))
    reconciled.sort(
        key=lambda item: (
            0 if item[2] is not None else 1,
            str(item[2]) if item[2] is not None else item[0][0],
            item[0][1],
        )
    )
    return tuple(reconciled)


def _candidate_sort_key(vessel: DatalasticVessel) -> tuple:
    return (
        vessel.uuid or "",
        vessel.mmsi if vessel.mmsi is not None else -1,
        vessel.imo if vessel.imo is not None else -1,
        vessel.observed_at.isoformat() if vessel.observed_at is not None else "",
        vessel.longitude,
        vessel.latitude,
        vessel.name or "",
        vessel.destination or "",
    )


def _candidate_latest_key(vessel: DatalasticVessel) -> tuple:
    return (
        vessel.observed_at is not None,
        vessel.observed_at,
        _candidate_sort_key(vessel),
    )


def _fallback_fingerprint(vessel: DatalasticVessel) -> str:
    fallback = "|".join(
        (
            vessel.name or "",
            vessel.destination or "",
            str(vessel.imo) if vessel.imo is not None else "",
            vessel.observed_at.isoformat() if vessel.observed_at is not None else "",
            repr(vessel.latitude),
            repr(vessel.longitude),
        )
    )
    return hashlib.sha256(fallback.encode("utf-8")).hexdigest()


def _with_cached(result: AreaScanResult, cached: bool) -> AreaScanResult:
    return AreaScanResult(
        source=result.source,
        scanned_at=result.scanned_at,
        cached=cached,
        scan=result.scan,
        vessels=result.vessels,
    )


def _consume_task_exception(task: asyncio.Task) -> None:
    """Retrieve background failures when the waiter that created a task left."""

    if not task.cancelled():
        task.exception()
