from __future__ import annotations

import math
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
import httpx
from pyproj import Geod
from shapely.geometry import Point
from fastapi.testclient import TestClient

from apps.api.seawatch.live.area_scan import (
    MAX_PROVIDER_CIRCLES,
    SCAN_RADIUS_NM,
    AreaScanService,
    AreaScanRequest,
    ScanValidationError,
    canonical_geometry_key,
    cover_polygon,
    plan_scan_geometry,
    validate_scan_geometry,
)
from apps.api.seawatch.live.area_scan_access import mint_area_scan_capability
from apps.api.seawatch.live.datalastic import (
    DatalasticClient,
    DatalasticStatus,
    DatalasticStatusCache,
    DatalasticVessel,
    ProviderError,
    ProviderErrorCategory,
)
from apps.api.seawatch.live.active_view import ActiveTrack
from apps.api.seawatch.live.identity import VesselIdentityRegistry
from apps.api.seawatch.live.runtime import get_live_runtime, reset_live_runtime
from apps.api.seawatch.live.schema import TrajectoryPoint
from apps.api.seawatch.main import create_app


TEST_SIGNING_KEY = "signing-secret-at-least-32-bytes"
TEST_OPERATOR_KEY = "operator-secret-at-least-32-bytes"


def _request(rings: list[list[list[float]]]) -> AreaScanRequest:
    return AreaScanRequest.model_validate(
        {"geometry": {"type": "Polygon", "coordinates": rings}}
    )


def _rectangle(
    west: float, south: float, east: float, north: float
) -> AreaScanRequest:
    return _request(
        [
            [
                [west, south],
                [east, south],
                [east, north],
                [west, north],
                [west, south],
            ]
        ]
    )


def test_validation_preserves_lon_lat_and_polygon_holes() -> None:
    request = _request(
        [
            [[120.0, 22.0], [121.0, 22.0], [121.0, 23.0], [120.0, 23.0], [120.0, 22.0]],
            [[120.4, 22.4], [120.6, 22.4], [120.6, 22.6], [120.4, 22.6], [120.4, 22.4]],
        ]
    )

    validated = validate_scan_geometry(request)

    assert validated.polygon.bounds == (120.0, 22.0, 121.0, 23.0)
    assert len(validated.polygon.interiors) == 1
    assert validated.polygon.covers(Point(120.0, 22.0)) is True
    assert validated.polygon.covers(Point(120.5, 22.5)) is False


@pytest.mark.parametrize(
    "coordinates",
    [
        [[[120.0, 22.0], [121.0, 22.0], [121.0, 23.0], [120.0, 23.0]]],
        [[[120.0, 22.0], [121.0, 23.0], [121.0, 22.0], [120.0, 23.0], [120.0, 22.0]]],
        [[[120.0, 22.0], [120.0, 22.0], [120.0, 22.0], [120.0, 22.0]]],
        [[[181.0, 22.0], [181.0, 23.0], [179.0, 23.0], [181.0, 22.0]]],
        [[[120.0, 91.0], [121.0, 22.0], [120.0, 22.0], [120.0, 91.0]]],
        [[[170.0, 20.0], [-170.0, 20.0], [-170.0, 21.0], [170.0, 20.0]]],
    ],
)
def test_invalid_geometry_is_rejected_before_covering(coordinates) -> None:
    request = _request(coordinates)
    with pytest.raises(ScanValidationError):
        validate_scan_geometry(request)


def test_non_finite_coordinate_is_rejected() -> None:
    request = _request(
        [[[120.0, 22.0], [math.inf, 22.0], [121.0, 23.0], [120.0, 22.0]]]
    )
    with pytest.raises(ScanValidationError):
        validate_scan_geometry(request)


def test_only_polygon_is_accepted() -> None:
    with pytest.raises(ValueError):
        AreaScanRequest.model_validate(
            {"geometry": {"type": "Point", "coordinates": [120.0, 22.0]}}
        )


def test_excessive_coordinate_count_is_rejected() -> None:
    points = []
    for index in range(513):
        angle = index * 2 * math.pi / 513
        points.append([120.0 + math.cos(angle), 22.0 + math.sin(angle)])
    points.append(points[0])
    with pytest.raises(ScanValidationError, match="too many coordinates"):
        validate_scan_geometry(_request([points]))


def test_non_billable_scan_plan_returns_area_query_count_and_limit() -> None:
    plan = plan_scan_geometry(_rectangle(120.0, 22.0, 120.1, 22.1))

    assert plan.can_scan is True
    assert plan.area_square_km > 0
    assert plan.provider_queries == 1
    assert plan.max_provider_queries == MAX_PROVIDER_CIRCLES
    assert plan.reason is None


def test_non_billable_scan_plan_marks_oversized_geometry_without_provider_work() -> None:
    plan = plan_scan_geometry(_rectangle(115.0, 15.0, 130.0, 30.0))

    assert plan.can_scan is False
    assert plan.area_square_km > 0
    assert plan.provider_queries is None
    assert plan.max_provider_queries == MAX_PROVIDER_CIRCLES
    assert plan.reason == "too_large"


def test_canonical_key_ignores_ring_start_and_orientation() -> None:
    original = validate_scan_geometry(
        _request(
            [[[120.0, 22.0], [121.0, 22.0], [121.0, 23.0], [120.0, 23.0], [120.0, 22.0]]]
        )
    ).polygon
    rotated_reversed = validate_scan_geometry(
        _request(
            [[[121.0, 23.0], [121.0, 22.0], [120.0, 22.0], [120.0, 23.0], [121.0, 23.0]]]
        )
    ).polygon
    different = validate_scan_geometry(_rectangle(120.0, 22.0, 121.1, 23.0)).polygon

    assert canonical_geometry_key(original) == canonical_geometry_key(rotated_reversed)
    assert canonical_geometry_key(original) != canonical_geometry_key(different)


def test_canonical_key_preserves_sub_microdegree_geometry_differences() -> None:
    first = validate_scan_geometry(
        _rectangle(120.0, 22.0, 121.0000001, 23.0)
    ).polygon
    second = validate_scan_geometry(
        _rectangle(120.0, 22.0, 121.0000004, 23.0)
    ).polygon

    assert first.equals_exact(second, tolerance=0.0) is False
    assert canonical_geometry_key(first) != canonical_geometry_key(second)


def test_canonical_key_normalizes_hole_order_rotation_and_orientation() -> None:
    first = validate_scan_geometry(
        _request(
            [
                [[120.0, 22.0], [122.0, 22.0], [122.0, 24.0], [120.0, 24.0], [120.0, 22.0]],
                [[120.2, 22.2], [120.4, 22.2], [120.4, 22.4], [120.2, 22.4], [120.2, 22.2]],
                [[121.2, 23.2], [121.4, 23.2], [121.4, 23.4], [121.2, 23.4], [121.2, 23.2]],
            ]
        )
    ).polygon
    reordered = validate_scan_geometry(
        _request(
            [
                [[122.0, 24.0], [122.0, 22.0], [120.0, 22.0], [120.0, 24.0], [122.0, 24.0]],
                [[121.4, 23.4], [121.4, 23.2], [121.2, 23.2], [121.2, 23.4], [121.4, 23.4]],
                [[120.4, 22.4], [120.4, 22.2], [120.2, 22.2], [120.2, 22.4], [120.4, 22.4]],
            ]
        )
    ).polygon
    different_hole = validate_scan_geometry(
        _request(
            [
                [[120.0, 22.0], [122.0, 22.0], [122.0, 24.0], [120.0, 24.0], [120.0, 22.0]],
                [[120.2, 22.2], [120.5, 22.2], [120.5, 22.4], [120.2, 22.4], [120.2, 22.2]],
                [[121.2, 23.2], [121.4, 23.2], [121.4, 23.4], [121.2, 23.4], [121.2, 23.2]],
            ]
        )
    ).polygon

    assert canonical_geometry_key(first) == canonical_geometry_key(reordered)
    assert canonical_geometry_key(first) != canonical_geometry_key(different_hole)


def test_small_polygon_uses_one_circle_no_larger_than_45_nm() -> None:
    polygon = validate_scan_geometry(_rectangle(120.1, 22.4, 120.3, 22.6)).polygon
    circles = cover_polygon(polygon)

    assert len(circles) == 1
    assert circles[0].radius_nm <= SCAN_RADIUS_NM
    assert 120.1 <= circles[0].longitude <= 120.3
    assert 22.4 <= circles[0].latitude <= 22.6


@pytest.mark.parametrize(
    ("bounds", "maximum_radius"),
    [
        ((120.0, 22.0, 120.02, 22.02), 1.5),
        ((120.0, 22.0, 120.5, 22.5), 25.0),
    ],
)
def test_single_circle_uses_tight_radius_with_geodesic_margin(
    bounds: tuple[float, float, float, float], maximum_radius: float
) -> None:
    polygon = validate_scan_geometry(_rectangle(*bounds)).polygon
    circle = cover_polygon(polygon)[0]
    geod = Geod(ellps="WGS84")
    corner_distances = [
        geod.inv(circle.longitude, circle.latitude, lon, lat)[2] / 1852.0
        for lon, lat in polygon.exterior.coords
    ]

    assert circle.radius_nm < maximum_radius
    assert circle.radius_nm <= 45.0
    assert max(corner_distances) < circle.radius_nm


def test_large_polygon_uses_deterministic_multiple_circle_cover() -> None:
    polygon = validate_scan_geometry(_rectangle(119.5, 21.8, 122.0, 24.2)).polygon

    first = cover_polygon(polygon)
    second = cover_polygon(polygon)

    assert first == second
    assert 1 < len(first) <= MAX_PROVIDER_CIRCLES
    assert all(circle.radius_nm <= 45.0 for circle in first)

    # Hand-sample the selected area. Every sample must be inside at least one
    # real provider circle according to WGS84 geodesic distance.
    geod = Geod(ellps="WGS84")
    for lon_index in range(11):
        for lat_index in range(11):
            lon = 119.5 + (122.0 - 119.5) * lon_index / 10
            lat = 21.8 + (24.2 - 21.8) * lat_index / 10
            distances_nm = [
                geod.inv(lon, lat, circle.longitude, circle.latitude)[2] / 1852.0
                for circle in first
            ]
            assert min(distances_nm) <= 45.0


def test_polygon_requiring_more_than_16_circles_is_rejected() -> None:
    polygon = validate_scan_geometry(_rectangle(110.0, 10.0, 130.0, 30.0)).polygon
    with pytest.raises(
        ScanValidationError,
        match="Selected area is too large. Draw a smaller region.",
    ):
        cover_polygon(polygon)


def test_polygon_requiring_exactly_16_circles_is_accepted() -> None:
    polygon = validate_scan_geometry(_rectangle(120.0, 20.0, 123.0, 23.0)).polygon
    circles = cover_polygon(polygon)
    assert len(circles) == MAX_PROVIDER_CIRCLES


OBSERVED = datetime.now(timezone.utc)


def _vessel(
    *,
    uuid: str | None = "raw-uuid-1",
    mmsi: int | None = 416000001,
    imo: int | None = 9876543,
    latitude: float = 22.5,
    longitude: float = 120.5,
    observed_at: datetime | None = OBSERVED,
) -> DatalasticVessel:
    return DatalasticVessel(
        uuid=uuid,
        name="REAL SHIP",
        mmsi=mmsi,
        imo=imo,
        latitude=latitude,
        longitude=longitude,
        speed_knots=8.0,
        course_deg=180.0,
        heading_deg=179.0,
        navigation_status="Under way using engine",
        vessel_type="Cargo",
        vessel_type_specific="Container Ship",
        destination="KHH",
        observed_at=observed_at,
    )


class _Provider:
    def __init__(self, results=(), error: ProviderError | None = None) -> None:
        self.results = tuple(results)
        self.error = error
        self.calls = 0
        self.queries = ()

    async def scan(self, queries):
        self.calls += 1
        self.queries = tuple(queries)
        if self.error:
            raise self.error
        return self.results


async def _healthy_stat(_client) -> DatalasticStatus:
    return DatalasticStatus(
        configured=True,
        reachable=True,
        key_status="valid",
        addons=False,
        requests_remaining=100,
        rate_limit_remaining=100,
        last_success_at=datetime.now(timezone.utc),
        last_error_category=None,
    )


def _service(provider: _Provider, **kwargs) -> AreaScanService:
    return AreaScanService(
        provider=provider,
        identity_registry=VesselIdentityRegistry("stable-test-key"),
        **kwargs,
    )


def _auth_headers(runtime) -> dict[str, str]:
    return {
        "Authorization": (
            "Bearer " + mint_area_scan_capability(runtime.area_scan_access)
        )
    }


def test_service_deduplicates_overlaps_keeps_latest_and_filters_exact_polygon() -> None:
    older = _vessel(observed_at=OBSERVED - timedelta(minutes=2), longitude=120.4)
    latest = _vessel(observed_at=OBSERVED, longitude=120.6)
    boundary = _vessel(
        uuid="boundary-uuid",
        mmsi=416000002,
        imo=9876544,
        longitude=121.0,
    )
    in_hole = _vessel(
        uuid="hole-uuid",
        mmsi=416000003,
        imo=9876545,
        longitude=120.5,
        latitude=22.5,
    )
    outside = _vessel(
        uuid="outside-uuid",
        mmsi=416000004,
        imo=9876546,
        longitude=122.0,
    )
    provider = _Provider((older, latest, boundary, in_hole, outside))
    service = _service(provider)
    request = _request(
        [
            [[120.0, 22.0], [121.0, 22.0], [121.0, 23.0], [120.0, 23.0], [120.0, 22.0]],
            [[120.4, 22.4], [120.6, 22.4], [120.6, 22.6], [120.4, 22.6], [120.4, 22.4]],
        ]
    )

    result = asyncio.run(service.scan(request))
    payload = result.to_public_dict()

    assert payload["total"] == 2
    assert [feature["geometry"]["coordinates"] for feature in payload["vessels"]] == [
        [120.6, 22.5],
        [121.0, 22.5],
    ]
    assert provider.calls == 1
    assert payload["scan"]["provider_queries"] == len(provider.queries)


def test_valid_mmsi_uses_existing_identity_and_raw_ids_never_serialize() -> None:
    registry = VesselIdentityRegistry("stable-test-key")
    provider = _Provider((_vessel(),))
    service = AreaScanService(provider=provider, identity_registry=registry)

    payload = asyncio.run(service.scan(_rectangle(120.0, 22.0, 121.0, 23.0))).to_public_dict()
    feature = payload["vessels"][0]

    assert feature["id"] == registry.public_id_for_mmsi(416000001)
    assert feature["properties"]["provider_vessel_type"] == "Cargo"
    assert feature["properties"]["provider_vessel_type_specific"] == "Container Ship"
    serialized = str(payload).lower()
    for forbidden in ("mmsi", "416000001", "imo", "9876543", "raw-uuid-1"):
        assert forbidden not in serialized


def test_missing_mmsi_is_provider_scoped_and_never_joins_history() -> None:
    registry = VesselIdentityRegistry("stable-test-key")
    provider = _Provider((_vessel(mmsi=None),))
    service = AreaScanService(provider=provider, identity_registry=registry)

    result = asyncio.run(service.scan(_rectangle(120.0, 22.0, 121.0, 23.0)))
    public_id = result.to_public_dict()["vessels"][0]["id"]

    assert public_id.startswith("v_")
    assert public_id != registry.public_id_for_mmsi(416000001)
    binding = registry.resolve(public_id)
    assert binding is not None
    assert binding.mmsi is None


def test_same_uuid_with_mmsi_and_missing_mmsi_reconciles_to_one_trusted_vessel() -> None:
    registry = VesselIdentityRegistry("stable-test-key")
    candidates = (
        _vessel(uuid="same-uuid", mmsi=416000001, longitude=120.4),
        _vessel(
            uuid="same-uuid",
            mmsi=None,
            longitude=120.6,
            observed_at=OBSERVED + timedelta(minutes=1),
        ),
    )
    service = AreaScanService(provider=_Provider(candidates), identity_registry=registry)

    payload = asyncio.run(
        service.scan(_rectangle(120.0, 22.0, 121.0, 23.0))
    ).to_public_dict()

    assert payload["total"] == 1
    assert payload["vessels"][0]["id"] == registry.public_id_for_mmsi(416000001)
    assert payload["vessels"][0]["geometry"]["coordinates"] == [120.6, 22.5]


def test_conflicting_mmsi_for_same_uuid_fails_closed_to_provider_identity() -> None:
    registry = VesselIdentityRegistry("stable-test-key")
    candidates = (
        _vessel(uuid="same-uuid", mmsi=416000001, longitude=120.4),
        _vessel(uuid="same-uuid", mmsi=416000002, longitude=120.6),
    )
    service = AreaScanService(provider=_Provider(candidates), identity_registry=registry)

    payload = asyncio.run(
        service.scan(_rectangle(120.0, 22.0, 121.0, 23.0))
    ).to_public_dict()

    assert payload["total"] == 1
    assert payload["vessels"][0]["id"] not in {
        registry.public_id_for_mmsi(416000001),
        registry.public_id_for_mmsi(416000002),
    }
    assert registry.resolve(payload["vessels"][0]["id"]).mmsi is None


def test_same_mmsi_with_conflicting_uuids_never_joins_historical_identity() -> None:
    registry = VesselIdentityRegistry("stable-test-key")
    candidates = (
        _vessel(uuid="uuid-a", mmsi=416000001, longitude=120.4),
        _vessel(uuid="uuid-b", mmsi=416000001, longitude=120.6),
    )
    service = AreaScanService(provider=_Provider(candidates), identity_registry=registry)

    payload = asyncio.run(
        service.scan(_rectangle(120.0, 22.0, 121.0, 23.0))
    ).to_public_dict()

    assert payload["total"] == 2
    historical_id = registry.public_id_for_mmsi(416000001)
    assert all(feature["id"] != historical_id for feature in payload["vessels"])
    assert all(registry.resolve(feature["id"]).mmsi is None for feature in payload["vessels"])


def test_placeholder_mmsi_never_joins_and_reconciliation_is_order_independent() -> None:
    registry_one = VesselIdentityRegistry("stable-test-key", token_factory=lambda: "one")
    registry_two = VesselIdentityRegistry("stable-test-key", token_factory=lambda: "one")
    candidates = (
        _vessel(uuid="placeholder", mmsi=111111111, longitude=120.4),
        _vessel(uuid="valid", mmsi=416000001, longitude=120.6),
    )
    first = AreaScanService(
        provider=_Provider(candidates),
        identity_registry=registry_one,
        clock=lambda: OBSERVED,
    )
    second = AreaScanService(
        provider=_Provider(tuple(reversed(candidates))),
        identity_registry=registry_two,
        clock=lambda: OBSERVED,
    )

    first_payload = asyncio.run(
        first.scan(_rectangle(120.0, 22.0, 121.0, 23.0))
    ).to_public_dict()
    second_payload = asyncio.run(
        second.scan(_rectangle(120.0, 22.0, 121.0, 23.0))
    ).to_public_dict()

    assert first_payload["vessels"] == second_payload["vessels"]
    placeholder_feature = next(
        feature
        for feature in first_payload["vessels"]
        if feature["geometry"]["coordinates"] == [120.4, 22.5]
    )
    assert placeholder_feature["id"] != registry_one.public_id_for_mmsi(111111111)
    assert registry_one.resolve(placeholder_feature["id"]).mmsi is None


def test_placeholder_mmsi_conflicting_with_valid_mmsi_on_same_uuid_fails_closed() -> None:
    registry = VesselIdentityRegistry("stable-test-key")
    candidates = (
        _vessel(uuid="mixed-uuid", mmsi=416000001, longitude=120.4),
        _vessel(uuid="mixed-uuid", mmsi=111111111, longitude=120.6),
    )
    service = AreaScanService(
        provider=_Provider(candidates),
        identity_registry=registry,
    )

    payload = asyncio.run(
        service.scan(_rectangle(120.0, 22.0, 121.0, 23.0))
    ).to_public_dict()

    assert payload["total"] == 1
    feature = payload["vessels"][0]
    assert feature["id"] != registry.public_id_for_mmsi(416000001)
    assert registry.resolve(feature["id"]).mmsi is None


def test_scan_track_contains_only_real_normalized_positions() -> None:
    registry = VesselIdentityRegistry("stable-test-key")
    provider = _Provider((_vessel(longitude=120.4),))
    service = AreaScanService(provider=provider, identity_registry=registry)
    request = _rectangle(120.0, 22.0, 121.0, 23.0)

    first = asyncio.run(service.scan(request))
    provider.results = (_vessel(longitude=120.6, observed_at=OBSERVED + timedelta(minutes=1)),)
    service.clear_cache()
    second = asyncio.run(service.scan(request))
    public_id = second.to_public_dict()["vessels"][0]["id"]
    track = service.track(public_id)

    assert first.total == second.total == 1
    assert track is not None
    assert track.source_name == "datalastic"
    assert [(point.longitude, point.latitude) for point in track.points] == [
        (120.4, 22.5),
        (120.6, 22.5),
    ]


@pytest.mark.parametrize(
    ("age_seconds", "expected_freshness"),
    [
        (30, "fresh"),
        (61, "fresh"),
        (300, "fresh"),
        (899, "fresh"),
        (900, "stale"),
        (1_200, "stale"),
    ],
)
def test_scan_result_uses_backend_freshness_contract(
    age_seconds: int,
    expected_freshness: str,
) -> None:
    scan_time = OBSERVED + timedelta(seconds=age_seconds)
    service = AreaScanService(
        provider=_Provider((_vessel(observed_at=OBSERVED),)),
        identity_registry=VesselIdentityRegistry("stable-test-key"),
        clock=lambda: scan_time,
    )

    payload = asyncio.run(
        service.scan(_rectangle(120.0, 22.0, 121.0, 23.0))
    ).to_public_dict()
    properties = payload["vessels"][0]["properties"]

    assert payload["scanned_at"] == scan_time.isoformat()
    assert properties["observed_at"] == OBSERVED.isoformat()
    assert properties["freshness_state"] == expected_freshness
    assert properties["data_age_seconds"] == float(age_seconds)


def test_scan_result_with_unknown_provider_timestamp_is_unknown() -> None:
    service = AreaScanService(
        provider=_Provider((_vessel(observed_at=None),)),
        identity_registry=VesselIdentityRegistry("stable-test-key"),
        clock=lambda: OBSERVED,
    )

    payload = asyncio.run(
        service.scan(_rectangle(120.0, 22.0, 121.0, 23.0))
    ).to_public_dict()
    feature = payload["vessels"][0]
    properties = feature["properties"]

    assert payload["scanned_at"] == OBSERVED.isoformat()
    assert properties["observed_at"] is None
    assert properties["data_age_seconds"] is None
    assert properties["freshness_state"] == "unknown"
    track = service.track(feature["id"])
    assert track is not None
    assert track.points == []


def test_cache_hit_avoids_provider_call_and_expires_after_45_seconds() -> None:
    now = [100.0]
    provider = _Provider((_vessel(),))
    service = _service(provider, monotonic=lambda: now[0])
    request = _rectangle(120.0, 22.0, 121.0, 23.0)

    first = asyncio.run(service.scan(request)).to_public_dict()
    equivalent = _request(
        [[[121.0, 23.0], [121.0, 22.0], [120.0, 22.0], [120.0, 23.0], [121.0, 23.0]]]
    )
    now[0] = 144.9
    second = asyncio.run(service.scan(equivalent)).to_public_dict()
    now[0] = 145.1
    third = asyncio.run(service.scan(request)).to_public_dict()

    assert first["cached"] is False
    assert second["cached"] is True
    assert third["cached"] is False
    assert provider.calls == 2
    assert "cache_key" not in str(second)


def test_cache_has_deterministic_entry_cap() -> None:
    provider = _Provider((_vessel(),))
    service = _service(provider, max_cache_entries=2)
    requests = [
        _rectangle(120.0 + offset, 22.0, 121.0 + offset, 23.0)
        for offset in (0.0, 0.01, 0.02)
    ]

    for request in requests:
        asyncio.run(service.scan(request))
    asyncio.run(service.scan(requests[0]))

    assert provider.calls == 4


def test_tracks_expire_and_release_provider_local_identity() -> None:
    monotonic_now = [100.0]
    registry = VesselIdentityRegistry("stable-test-key", token_factory=lambda: "local")
    service = AreaScanService(
        provider=_Provider((_vessel(uuid="uuid-local", mmsi=None),)),
        identity_registry=registry,
        monotonic=lambda: monotonic_now[0],
        track_ttl_seconds=10.0,
    )
    result = asyncio.run(service.scan(_rectangle(120.0, 22.0, 121.0, 23.0)))
    public_id = result.vessels[0]["id"]

    monotonic_now[0] = 110.1

    assert service.track(public_id) is None
    assert registry.resolve(public_id) is None


def test_tracks_have_deterministic_vessel_and_point_caps() -> None:
    monotonic_now = [100.0]
    provider = _Provider()
    service = AreaScanService(
        provider=provider,
        identity_registry=VesselIdentityRegistry("stable-test-key"),
        monotonic=lambda: monotonic_now[0],
        max_track_vessels=2,
        max_track_points=2,
    )
    request = _rectangle(120.0, 22.0, 121.0, 23.0)
    public_ids: list[str] = []
    for index in range(3):
        provider.results = (
            _vessel(
                uuid=f"uuid-{index}",
                mmsi=None,
                longitude=120.2 + index / 10,
                observed_at=OBSERVED + timedelta(minutes=index),
            ),
        )
        service.clear_cache()
        public_ids.append(asyncio.run(service.scan(request)).vessels[0]["id"])
        monotonic_now[0] += 1

    assert service.track(public_ids[0]) is None
    assert service.track(public_ids[1]) is not None
    assert service.track(public_ids[2]) is not None

    provider.results = (
        _vessel(
            uuid="uuid-2",
            mmsi=None,
            longitude=120.7,
            observed_at=OBSERVED + timedelta(minutes=4),
        ),
    )
    service.clear_cache()
    asyncio.run(service.scan(request))
    provider.results = (
        _vessel(
            uuid="uuid-2",
            mmsi=None,
            longitude=120.8,
            observed_at=OBSERVED + timedelta(minutes=5),
        ),
    )
    service.clear_cache()
    asyncio.run(service.scan(request))

    latest_track = service.track(public_ids[2])
    assert latest_track is not None
    assert [point.longitude for point in latest_track.points] == [120.7, 120.8]


def test_scan_vessel_cap_rejects_before_retaining_any_track() -> None:
    provider = _Provider(
        tuple(
            _vessel(uuid=f"uuid-{index}", mmsi=None, longitude=120.2 + index / 10)
            for index in range(3)
        )
    )
    service = AreaScanService(
        provider=provider,
        identity_registry=VesselIdentityRegistry("stable-test-key"),
        max_scan_vessels=2,
    )

    with pytest.raises(ProviderError) as raised:
        asyncio.run(service.scan(_rectangle(120.0, 22.0, 121.0, 23.0)))

    assert raised.value.category is ProviderErrorCategory.UPSTREAM
    assert service.vessel_count() == 0


def test_identical_concurrent_scans_coalesce() -> None:
    class BlockingProvider(_Provider):
        def __init__(self) -> None:
            super().__init__((_vessel(),))
            self.entered = asyncio.Event()
            self.release = asyncio.Event()

        async def scan(self, queries):
            self.calls += 1
            self.queries = tuple(queries)
            self.entered.set()
            await self.release.wait()
            return self.results

    async def scenario() -> None:
        provider = BlockingProvider()
        service = _service(provider)
        request = _rectangle(120.0, 22.0, 121.0, 23.0)
        first = asyncio.create_task(service.scan(request))
        await provider.entered.wait()
        second = asyncio.create_task(service.scan(request))
        await asyncio.sleep(0)
        provider.release.set()
        one, two = await asyncio.gather(first, second)
        assert provider.calls == 1
        assert one.cached is False
        assert two.cached is True

    asyncio.run(scenario())


def test_cancelled_owner_does_not_cancel_or_duplicate_shared_scan() -> None:
    class BlockingProvider(_Provider):
        def __init__(self) -> None:
            super().__init__((_vessel(),))
            self.entered = asyncio.Event()
            self.release = asyncio.Event()

        async def scan(self, queries):
            self.calls += 1
            self.queries = tuple(queries)
            self.entered.set()
            await self.release.wait()
            return self.results

    async def scenario() -> None:
        provider = BlockingProvider()
        service = _service(provider)
        request = _rectangle(120.0, 22.0, 121.0, 23.0)
        owner = asyncio.create_task(service.scan(request))
        await provider.entered.wait()
        owner.cancel()
        with pytest.raises(asyncio.CancelledError):
            await owner

        follower = asyncio.create_task(service.scan(request))
        await asyncio.sleep(0)
        assert provider.calls == 1
        provider.release.set()
        result = await follower
        third = await service.scan(request)

        assert result.total == 1
        assert third.cached is True
        assert provider.calls == 1

    asyncio.run(scenario())


def test_failed_shared_scan_is_removed_and_next_request_can_retry() -> None:
    provider = _Provider(error=ProviderError(ProviderErrorCategory.TIMEOUT))
    service = _service(provider)
    request = _rectangle(120.0, 22.0, 121.0, 23.0)

    with pytest.raises(ProviderError):
        asyncio.run(service.scan(request))
    provider.error = None
    provider.results = (_vessel(),)

    result = asyncio.run(service.scan(request))

    assert result.total == 1
    assert provider.calls == 2


def test_scan_updates_cached_provider_reachability_without_exposing_details() -> None:
    status_cache = DatalasticStatusCache(configured=True)
    service = AreaScanService(
        provider=_Provider((_vessel(),)),
        identity_registry=VesselIdentityRegistry("stable-test-key"),
        status_cache=status_cache,
    )

    asyncio.run(service.scan(_rectangle(120.0, 22.0, 121.0, 23.0)))

    snapshot = status_cache.snapshot()
    assert snapshot.reachable is True
    assert snapshot.last_success_at is not None
    assert snapshot.last_error_category is None


def test_scan_failure_updates_cached_provider_error_category() -> None:
    status_cache = DatalasticStatusCache(configured=True)
    service = AreaScanService(
        provider=_Provider(error=ProviderError(ProviderErrorCategory.TIMEOUT)),
        identity_registry=VesselIdentityRegistry("stable-test-key"),
        status_cache=status_cache,
    )

    with pytest.raises(ProviderError):
        asyncio.run(service.scan(_rectangle(120.0, 22.0, 121.0, 23.0)))

    snapshot = status_cache.snapshot()
    assert snapshot.reachable is False
    assert snapshot.last_error_category is ProviderErrorCategory.TIMEOUT


def test_area_scan_route_returns_safe_features_and_track(monkeypatch) -> None:
    monkeypatch.setenv("DATALASTIC_API_KEY", "route-secret")
    monkeypatch.setenv("SEAWATCH_IDENTITY_KEY", "stable-test-key")
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_SIGNING_KEY", TEST_SIGNING_KEY)
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_OPERATOR_KEY", TEST_OPERATOR_KEY)
    monkeypatch.setattr(DatalasticClient, "stat", _healthy_stat)
    reset_live_runtime()
    runtime = get_live_runtime()
    provider = _Provider((_vessel(),))
    runtime.area_scan_service.set_provider(provider)

    try:
        with TestClient(create_app()) as client:
            response = client.post(
                "/live/area-scan",
                json=_rectangle(120.0, 22.0, 121.0, 23.0).model_dump(),
                headers=_auth_headers(runtime),
            )
            assert response.status_code == 200
            body = response.json()
            public_id = body["vessels"][0]["id"]
            track = client.get(f"/live/vessels/{public_id}/track")
            preflight = client.options(
                "/live/area-scan",
                headers={
                    "Origin": "http://localhost:5173",
                    "Access-Control-Request-Method": "POST",
                },
            )
        assert body["source"] == "datalastic"
        assert track.status_code == 200
        assert preflight.status_code == 200
        assert "route-secret" not in response.text
    finally:
        reset_live_runtime()


def test_area_scan_plan_route_never_contacts_provider(monkeypatch) -> None:
    monkeypatch.setenv("DATALASTIC_API_KEY", "route-secret")
    monkeypatch.setenv("SEAWATCH_IDENTITY_KEY", "stable-test-key")
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_SIGNING_KEY", TEST_SIGNING_KEY)
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_OPERATOR_KEY", TEST_OPERATOR_KEY)
    monkeypatch.setattr(DatalasticClient, "stat", _healthy_stat)
    reset_live_runtime()
    runtime = get_live_runtime()
    provider = _Provider((_vessel(),))
    runtime.area_scan_service.set_provider(provider)

    try:
        with TestClient(create_app()) as client:
            response = client.post(
                "/live/area-scan/plan",
                json=_rectangle(120.0, 22.0, 120.1, 22.1).model_dump(),
                headers=_auth_headers(runtime),
            )
        assert response.status_code == 200
        assert response.json()["provider_queries"] == 1
        assert response.json()["max_provider_queries"] == MAX_PROVIDER_CIRCLES
        assert provider.calls == 0
    finally:
        reset_live_runtime()


def test_area_scan_route_maps_provider_failure_to_sanitized_503(monkeypatch) -> None:
    monkeypatch.setenv("DATALASTIC_API_KEY", "route-secret")
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_SIGNING_KEY", TEST_SIGNING_KEY)
    monkeypatch.setattr(DatalasticClient, "stat", _healthy_stat)
    reset_live_runtime()
    runtime = get_live_runtime()
    runtime.area_scan_service.set_provider(
        _Provider(error=ProviderError(ProviderErrorCategory.RATE_LIMITED, retry_after_seconds=30))
    )

    try:
        with TestClient(create_app()) as client:
            response = client.post(
                "/live/area-scan",
                json=_rectangle(120.0, 22.0, 121.0, 23.0).model_dump(),
                headers=_auth_headers(runtime),
            )
        assert response.status_code == 503
        assert "Retry-After" not in response.headers
        assert response.json()["detail"] == "Datalastic Live AIS currently unavailable"
        assert "route-secret" not in response.text
    finally:
        reset_live_runtime()


def test_area_scan_route_reports_quota_exhaustion_as_a_distinct_safe_category(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATALASTIC_API_KEY", "route-secret")
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_SIGNING_KEY", TEST_SIGNING_KEY)
    monkeypatch.setattr(DatalasticClient, "stat", _healthy_stat)
    reset_live_runtime()
    runtime = get_live_runtime()
    runtime.area_scan_service.set_provider(
        _Provider(error=ProviderError(ProviderErrorCategory.QUOTA_EXHAUSTED))
    )

    try:
        with TestClient(create_app()) as client:
            response = client.post(
                "/live/area-scan",
                json=_rectangle(120.0, 22.0, 121.0, 23.0).model_dump(),
                headers=_auth_headers(runtime),
            )
        assert response.status_code == 503
        assert response.json()["detail"] == "Datalastic quota exhausted"
        assert "route-secret" not in response.text
    finally:
        reset_live_runtime()


def test_area_scan_route_is_unavailable_without_key(monkeypatch) -> None:
    monkeypatch.delenv("DATALASTIC_API_KEY", raising=False)
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_SIGNING_KEY", TEST_SIGNING_KEY)
    reset_live_runtime()
    runtime = get_live_runtime()
    try:
        with TestClient(create_app()) as client:
            response = client.post(
                "/live/area-scan",
                json=_rectangle(120.0, 22.0, 121.0, 23.0).model_dump(),
                headers=_auth_headers(runtime),
            )
        assert response.status_code == 503
        assert response.json()["detail"] == "Datalastic Live AIS is not configured"
    finally:
        reset_live_runtime()


def test_area_scan_route_fails_closed_when_access_signing_key_is_unconfigured(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATALASTIC_API_KEY", "route-secret")
    monkeypatch.delenv("SEAWATCH_AREA_SCAN_SIGNING_KEY", raising=False)
    monkeypatch.setattr(DatalasticClient, "stat", _healthy_stat)
    reset_live_runtime()
    runtime = get_live_runtime()
    provider = _Provider((_vessel(),))
    runtime.area_scan_service.set_provider(provider)

    try:
        with TestClient(create_app()) as client:
            response = client.post(
                "/live/area-scan",
                json=_rectangle(120.0, 22.0, 121.0, 23.0).model_dump(),
            )
        assert response.status_code == 503
        assert response.json()["detail"] == "Area Scan access is not configured"
        assert provider.calls == 0
    finally:
        reset_live_runtime()


def test_area_scan_route_rejects_missing_capability_before_provider_call(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATALASTIC_API_KEY", "route-secret")
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_SIGNING_KEY", TEST_SIGNING_KEY)
    monkeypatch.setattr(DatalasticClient, "stat", _healthy_stat)
    reset_live_runtime()
    runtime = get_live_runtime()
    provider = _Provider((_vessel(),))
    runtime.area_scan_service.set_provider(provider)

    try:
        with TestClient(create_app()) as client:
            response = client.post(
                "/live/area-scan",
                json=_rectangle(120.0, 22.0, 121.0, 23.0).model_dump(),
            )
        assert response.status_code == 401
        assert response.json()["detail"] == "Area Scan authorization required"
        assert provider.calls == 0
    finally:
        reset_live_runtime()


@pytest.mark.parametrize(
    "authorization",
    [
        "Bearer invalid-capability",
        "expired",
    ],
)
def test_area_scan_route_rejects_invalid_or_expired_capability_before_provider_call(
    monkeypatch, authorization: str
) -> None:
    monkeypatch.setenv("DATALASTIC_API_KEY", "route-secret")
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_SIGNING_KEY", TEST_SIGNING_KEY)
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_OPERATOR_KEY", TEST_OPERATOR_KEY)
    monkeypatch.setattr(DatalasticClient, "stat", _healthy_stat)
    reset_live_runtime()
    runtime = get_live_runtime()
    provider = _Provider((_vessel(),))
    runtime.area_scan_service.set_provider(provider)
    if authorization == "expired":
        authorization = "Bearer " + mint_area_scan_capability(
            runtime.area_scan_access,
            now=1,
            ttl_seconds=1,
            nonce="expired-test",
        )

    try:
        with TestClient(create_app()) as client:
            response = client.post(
                "/live/area-scan",
                json=_rectangle(120.0, 22.0, 121.0, 23.0).model_dump(),
                headers={"Authorization": authorization},
            )
        assert response.status_code == 403
        assert response.json()["detail"] == "Area Scan authorization invalid or expired"
        assert provider.calls == 0
    finally:
        reset_live_runtime()


def test_operator_session_issues_httponly_capability_and_enables_scan(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATALASTIC_API_KEY", "route-secret")
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_SIGNING_KEY", TEST_SIGNING_KEY)
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_OPERATOR_KEY", TEST_OPERATOR_KEY)
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_ALLOW_INSECURE_COOKIE", "true")
    monkeypatch.setattr(DatalasticClient, "stat", _healthy_stat)
    reset_live_runtime()
    runtime = get_live_runtime()
    provider = _Provider((_vessel(),))
    runtime.area_scan_service.set_provider(provider)

    async def scenario() -> tuple[httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(
            app=create_app(),
            client=("127.0.0.1", 55123),
        )
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://127.0.0.1",
        ) as client:
            session = await client.post(
                "/live/area-scan/session",
                json={"operator_credential": TEST_OPERATOR_KEY},
            )
            response = await client.post(
                "/live/area-scan",
                json=_rectangle(120.0, 22.0, 121.0, 23.0).model_dump(),
                headers={"X-SeaWatch-Area-Scan": "1"},
            )
            return session, response

    try:
        session, response = asyncio.run(scenario())
        assert session.status_code == 200
        assert session.json() == {"authenticated": True, "expires_in_seconds": 900}
        set_cookie = session.headers["set-cookie"]
        assert "HttpOnly" in set_cookie
        assert "SameSite=strict" in set_cookie
        assert session.headers["cache-control"] == "no-store"
        assert TEST_OPERATOR_KEY not in session.text
        assert TEST_SIGNING_KEY not in session.text
        assert response.status_code == 200
        assert provider.calls == 1
    finally:
        reset_live_runtime()


def test_loopback_autoauth_issues_session_without_operator_credential(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATALASTIC_API_KEY", "route-secret")
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_SIGNING_KEY", TEST_SIGNING_KEY)
    monkeypatch.delenv("SEAWATCH_AREA_SCAN_OPERATOR_KEY", raising=False)
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_AUTOAUTH_LOOPBACK", "true")
    monkeypatch.delenv("SEAWATCH_AREA_SCAN_ALLOW_INSECURE_COOKIE", raising=False)
    reset_live_runtime()
    runtime = get_live_runtime()
    provider = _Provider((_vessel(),))
    runtime.area_scan_service.set_provider(provider)

    async def scenario() -> tuple[httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(
            app=create_app(),
            client=("127.0.0.1", 55123),
        )
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://localhost",
        ) as client:
            session = await client.post("/live/area-scan/session", json={})
            scan = await client.post(
                "/live/area-scan",
                json=_rectangle(120.0, 22.0, 121.0, 23.0).model_dump(),
                headers={"X-SeaWatch-Area-Scan": "1"},
            )
            return session, scan

    try:
        session, scan = asyncio.run(scenario())
        assert session.status_code == 200
        assert session.json() == {"authenticated": True, "expires_in_seconds": 900}
        assert "HttpOnly" in session.headers["set-cookie"]
        assert scan.status_code == 200
        assert provider.calls == 1
    finally:
        reset_live_runtime()


def test_loopback_without_autoauth_still_requires_operator_authentication(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATALASTIC_API_KEY", "route-secret")
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_SIGNING_KEY", TEST_SIGNING_KEY)
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_OPERATOR_KEY", TEST_OPERATOR_KEY)
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_AUTOAUTH_LOOPBACK", "false")
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_ALLOW_INSECURE_COOKIE", "true")
    reset_live_runtime()
    runtime = get_live_runtime()
    provider = _Provider((_vessel(),))
    runtime.area_scan_service.set_provider(provider)

    async def scenario() -> tuple[httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(
            app=create_app(),
            client=("127.0.0.1", 55123),
        )
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://localhost",
        ) as client:
            session = await client.post("/live/area-scan/session", json={})
            scan = await client.post(
                "/live/area-scan",
                json=_rectangle(120.0, 22.0, 121.0, 23.0).model_dump(),
                headers={"X-SeaWatch-Area-Scan": "1"},
            )
            return session, scan

    try:
        session, scan = asyncio.run(scenario())
        assert session.status_code == 401
        assert "set-cookie" not in session.headers
        assert scan.status_code == 401
        assert provider.calls == 0
    finally:
        reset_live_runtime()


@pytest.mark.parametrize(
    ("base_url", "peer"),
    [
        ("http://localhost", "203.0.113.17"),
        ("http://public.example", "127.0.0.1"),
        ("http://127.0.0.2", "127.0.0.1"),
    ],
)
def test_non_loopback_request_cannot_bypass_auth_when_autoauth_is_enabled(
    monkeypatch,
    base_url: str,
    peer: str,
) -> None:
    monkeypatch.setenv("DATALASTIC_API_KEY", "route-secret")
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_SIGNING_KEY", TEST_SIGNING_KEY)
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_OPERATOR_KEY", TEST_OPERATOR_KEY)
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_AUTOAUTH_LOOPBACK", "true")
    reset_live_runtime()
    runtime = get_live_runtime()
    provider = _Provider((_vessel(),))
    runtime.area_scan_service.set_provider(provider)

    async def scenario() -> tuple[httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(
            app=create_app(),
            client=(peer, 55123),
        )
        async with httpx.AsyncClient(
            transport=transport,
            base_url=base_url,
        ) as client:
            session = await client.post("/live/area-scan/session", json={})
            scan = await client.post(
                "/live/area-scan",
                json=_rectangle(120.0, 22.0, 121.0, 23.0).model_dump(),
                headers={"X-SeaWatch-Area-Scan": "1"},
            )
            return session, scan

    try:
        session, scan = asyncio.run(scenario())
        assert session.status_code == 401
        assert "set-cookie" not in session.headers
        assert scan.status_code == 401
        assert provider.calls == 0
    finally:
        reset_live_runtime()


def test_operator_session_rejects_invalid_credential_without_capability_or_provider_call(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATALASTIC_API_KEY", "route-secret")
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_SIGNING_KEY", TEST_SIGNING_KEY)
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_OPERATOR_KEY", TEST_OPERATOR_KEY)
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_ALLOW_INSECURE_COOKIE", "true")
    monkeypatch.setattr(DatalasticClient, "stat", _healthy_stat)
    reset_live_runtime()
    runtime = get_live_runtime()
    provider = _Provider((_vessel(),))
    runtime.area_scan_service.set_provider(provider)

    try:
        with TestClient(create_app()) as client:
            session = client.post(
                "/live/area-scan/session",
                json={"operator_credential": "incorrect-operator-credential"},
            )
            response = client.post(
                "/live/area-scan",
                json=_rectangle(120.0, 22.0, 121.0, 23.0).model_dump(),
            )
        assert session.status_code == 401
        assert "set-cookie" not in session.headers
        assert "incorrect-operator-credential" not in session.text
        assert response.status_code == 401
        assert provider.calls == 0
    finally:
        reset_live_runtime()


def test_operator_session_rejects_oversized_secret_without_echoing_it(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATALASTIC_API_KEY", "route-secret")
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_SIGNING_KEY", TEST_SIGNING_KEY)
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_OPERATOR_KEY", TEST_OPERATOR_KEY)
    monkeypatch.setattr(DatalasticClient, "stat", _healthy_stat)
    reset_live_runtime()
    runtime = get_live_runtime()
    provider = _Provider((_vessel(),))
    runtime.area_scan_service.set_provider(provider)
    oversized_secret = "operator-secret-marker-" + "x" * 8_192

    try:
        with TestClient(create_app()) as client:
            session = client.post(
                "/live/area-scan/session",
                json={"operator_credential": oversized_secret},
            )
        assert session.status_code == 413
        assert "operator-secret-marker" not in session.text
        assert "set-cookie" not in session.headers
        assert provider.calls == 0
    finally:
        reset_live_runtime()


def test_operator_session_cookie_is_secure_by_default(monkeypatch) -> None:
    monkeypatch.setenv("DATALASTIC_API_KEY", "route-secret")
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_SIGNING_KEY", TEST_SIGNING_KEY)
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_OPERATOR_KEY", TEST_OPERATOR_KEY)
    monkeypatch.delenv("SEAWATCH_AREA_SCAN_ALLOW_INSECURE_COOKIE", raising=False)
    monkeypatch.setattr(DatalasticClient, "stat", _healthy_stat)
    reset_live_runtime()

    try:
        with TestClient(create_app()) as client:
            session = client.post(
                "/live/area-scan/session",
                json={"operator_credential": TEST_OPERATOR_KEY},
            )
        assert session.status_code == 200
        assert "Secure" in session.headers["set-cookie"]
    finally:
        reset_live_runtime()


def test_insecure_cookie_opt_in_is_ignored_for_non_loopback_hosts(monkeypatch) -> None:
    monkeypatch.setenv("DATALASTIC_API_KEY", "route-secret")
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_SIGNING_KEY", TEST_SIGNING_KEY)
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_OPERATOR_KEY", TEST_OPERATOR_KEY)
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_ALLOW_INSECURE_COOKIE", "true")
    monkeypatch.setattr(DatalasticClient, "stat", _healthy_stat)
    reset_live_runtime()

    try:
        with TestClient(create_app(), base_url="http://public.example") as client:
            session = client.post(
                "/live/area-scan/session",
                json={"operator_credential": TEST_OPERATOR_KEY},
            )
        assert session.status_code == 200
        assert "Secure" in session.headers["set-cookie"]
    finally:
        reset_live_runtime()


def test_cookie_authenticated_scan_requires_non_simple_csrf_header_before_provider(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATALASTIC_API_KEY", "route-secret")
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_SIGNING_KEY", TEST_SIGNING_KEY)
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_OPERATOR_KEY", TEST_OPERATOR_KEY)
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_ALLOW_INSECURE_COOKIE", "true")
    monkeypatch.setattr(DatalasticClient, "stat", _healthy_stat)
    reset_live_runtime()
    runtime = get_live_runtime()
    provider = _Provider((_vessel(),))
    runtime.area_scan_service.set_provider(provider)

    async def scenario() -> tuple[httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(
            app=create_app(),
            client=("127.0.0.1", 55123),
        )
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://127.0.0.1",
        ) as client:
            session = await client.post(
                "/live/area-scan/session",
                json={"operator_credential": TEST_OPERATOR_KEY},
            )
            response = await client.post(
                "/live/area-scan",
                json=_rectangle(120.0, 22.0, 121.0, 23.0).model_dump(),
            )
            return session, response

    try:
        session, response = asyncio.run(scenario())
        assert session.status_code == 200
        assert response.status_code == 403
        assert provider.calls == 0
    finally:
        reset_live_runtime()


def test_area_scan_route_rejects_malformed_and_oversized_bodies_before_provider(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATALASTIC_API_KEY", "route-secret")
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_SIGNING_KEY", TEST_SIGNING_KEY)
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_MAX_BODY_BYTES", "128")
    monkeypatch.setattr(DatalasticClient, "stat", _healthy_stat)
    reset_live_runtime()
    runtime = get_live_runtime()
    provider = _Provider((_vessel(),))
    runtime.area_scan_service.set_provider(provider)

    try:
        with TestClient(create_app()) as client:
            malformed = client.post(
                "/live/area-scan",
                content=b"{not-json",
                headers={**_auth_headers(runtime), "Content-Type": "application/json"},
            )
            oversized = client.post(
                "/live/area-scan",
                content=b"{" + b"x" * 256 + b"}",
                headers={**_auth_headers(runtime), "Content-Type": "application/json"},
            )
        assert malformed.status_code == 422
        assert oversized.status_code == 413
        assert provider.calls == 0
    finally:
        reset_live_runtime()


def test_area_scan_route_rejects_simple_cross_origin_content_type_before_provider(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATALASTIC_API_KEY", "route-secret")
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_SIGNING_KEY", TEST_SIGNING_KEY)
    monkeypatch.setattr(DatalasticClient, "stat", _healthy_stat)
    reset_live_runtime()
    runtime = get_live_runtime()
    provider = _Provider((_vessel(),))
    runtime.area_scan_service.set_provider(provider)
    payload = _rectangle(120.0, 22.0, 121.0, 23.0).model_dump_json()

    try:
        with TestClient(create_app()) as client:
            response = client.post(
                "/live/area-scan",
                content=payload,
                headers={**_auth_headers(runtime), "Content-Type": "text/plain"},
            )
        assert response.status_code == 415
        assert provider.calls == 0
    finally:
        reset_live_runtime()


def test_invalid_admission_limit_disables_area_scan_without_breaking_api(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATALASTIC_API_KEY", "route-secret")
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_SIGNING_KEY", TEST_SIGNING_KEY)
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_MAX_SCANS_PER_MINUTE", "0")
    monkeypatch.setattr(DatalasticClient, "stat", _healthy_stat)
    reset_live_runtime()

    try:
        with TestClient(create_app()) as client:
            health = client.get("/health")
            response = client.post(
                "/live/area-scan",
                json=_rectangle(120.0, 22.0, 121.0, 23.0).model_dump(),
            )
        assert health.status_code == 200
        assert response.status_code == 503
        assert response.json()["detail"] == "Area Scan access is not configured"
    finally:
        reset_live_runtime()


def test_area_scan_route_scan_budget_rejects_before_second_provider_call(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATALASTIC_API_KEY", "route-secret")
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_SIGNING_KEY", TEST_SIGNING_KEY)
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_MAX_SCANS_PER_MINUTE", "1")
    monkeypatch.setattr(DatalasticClient, "stat", _healthy_stat)
    reset_live_runtime()
    runtime = get_live_runtime()
    provider = _Provider((_vessel(),))
    runtime.area_scan_service.set_provider(provider)

    try:
        with TestClient(create_app()) as client:
            first = client.post(
                "/live/area-scan",
                json=_rectangle(120.0, 22.0, 121.0, 23.0).model_dump(),
                headers=_auth_headers(runtime),
            )
            second = client.post(
                "/live/area-scan",
                json=_rectangle(120.1, 22.1, 121.1, 23.1).model_dump(),
                headers=_auth_headers(runtime),
            )
        assert first.status_code == 200
        assert second.status_code == 429
        assert provider.calls == 1
    finally:
        reset_live_runtime()


def test_area_scan_route_provider_request_budget_rejects_with_zero_provider_calls(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATALASTIC_API_KEY", "route-secret")
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_SIGNING_KEY", TEST_SIGNING_KEY)
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_MAX_PROVIDER_REQUESTS_PER_MINUTE", "1")
    monkeypatch.setattr(DatalasticClient, "stat", _healthy_stat)
    reset_live_runtime()
    runtime = get_live_runtime()
    provider = _Provider((_vessel(),))
    runtime.area_scan_service.set_provider(provider)

    try:
        with TestClient(create_app()) as client:
            response = client.post(
                "/live/area-scan",
                json=_rectangle(120.0, 22.0, 121.0, 23.0).model_dump(),
                headers=_auth_headers(runtime),
            )
        assert response.status_code == 429
        assert provider.calls == 0
    finally:
        reset_live_runtime()


def test_track_route_source_qualifier_disambiguates_same_public_id(monkeypatch) -> None:
    monkeypatch.setenv("DATALASTIC_API_KEY", "route-secret")
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_SIGNING_KEY", TEST_SIGNING_KEY)
    monkeypatch.setenv("SEAWATCH_IDENTITY_KEY", "stable-test-key")
    monkeypatch.setattr(DatalasticClient, "stat", _healthy_stat)
    reset_live_runtime()
    runtime = get_live_runtime()
    runtime.area_scan_service.set_provider(_Provider((_vessel(),)))
    public_id = runtime.identity_registry.public_id_for_mmsi(416000001)
    assert public_id is not None
    live_track = ActiveTrack(
        public_id=public_id,
        source_name="open_waters",
        points=[
            TrajectoryPoint(
                latitude=21.0,
                longitude=119.0,
                observed_at=OBSERVED,
            )
        ],
    )
    monkeypatch.setattr(runtime.active_view, "track", lambda _public_id: live_track)

    try:
        with TestClient(create_app()) as client:
            scan = client.post(
                "/live/area-scan",
                json=_rectangle(120.0, 22.0, 121.0, 23.0).model_dump(),
                headers=_auth_headers(runtime),
            )
            assert scan.status_code == 200
            ordinary = client.get(f"/live/vessels/{public_id}/track")
            datalastic = client.get(
                f"/live/vessels/{public_id}/track?source=datalastic"
            )
        assert ordinary.json()["geometry"]["coordinates"] == [[119.0, 21.0]]
        assert ordinary.json()["properties"]["source"] == "open_waters"
        assert datalastic.json()["geometry"]["coordinates"] == [[120.5, 22.5]]
        assert datalastic.json()["properties"]["source"] == "datalastic"
    finally:
        reset_live_runtime()


@pytest.mark.parametrize("public_id", ["not-valid", "v_abcdefghijklmnopqrstuvwx"])
def test_track_route_returns_generic_error_for_invalid_or_unknown_public_id(
    monkeypatch, public_id: str
) -> None:
    monkeypatch.delenv("DATALASTIC_API_KEY", raising=False)
    reset_live_runtime()
    try:
        with TestClient(create_app()) as client:
            response = client.get(f"/live/vessels/{public_id}/track?source=datalastic")
        assert response.status_code == 404
        assert response.json()["detail"] == "Vessel track not found"
        assert public_id not in response.text
    finally:
        reset_live_runtime()
