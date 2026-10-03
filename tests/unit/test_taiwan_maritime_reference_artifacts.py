"""Read-only contract checks for checked-in maritime-reference artifacts."""

from __future__ import annotations

import json
import math
from datetime import date
from numbers import Real
from pathlib import Path
import shutil

import pytest
from shapely.geometry import MultiPolygon, box, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import polygonize_full


PRODUCTION_DIR = (
    Path(__file__).parents[2] / "data" / "gis" / "taiwan_maritime_reference"
)
EEZ_FILE = "eez_reference_areas.geojson"
TERRITORIAL_LINE_FILE = "territorial_sea_12nm_official_line.geojson"
CONTIGUOUS_LINE_FILE = "contiguous_zone_24nm_official_line.geojson"
TERRITORIAL_POLYGON_FILE = "territorial_sea_12nm_reference_polygon.geojson"
BAND_FILE = "contiguous_zone_12_24nm_reference_band.geojson"
EXPECTED_FEATURE_COUNTS = {
    EEZ_FILE: 5,
    TERRITORIAL_LINE_FILE: 3,
    CONTIGUOUS_LINE_FILE: 3,
    TERRITORIAL_POLYGON_FILE: 3,
    BAND_FILE: 3,
}
EXPECTED_FILES = {
    "README.md",
    *EXPECTED_FEATURE_COUNTS,
    "source_metadata.json",
}
EXPECTED_STATUS = {
    EEZ_FILE: "clipped_source",
    TERRITORIAL_LINE_FILE: "clipped_source",
    CONTIGUOUS_LINE_FILE: "clipped_source",
    TERRITORIAL_POLYGON_FILE: "derived_reference",
    BAND_FILE: "derived_reference",
}
EXPECTED_GEOMETRY_TYPES = {
    EEZ_FILE: {"Polygon", "MultiPolygon"},
    TERRITORIAL_LINE_FILE: {"LineString", "MultiLineString"},
    CONTIGUOUS_LINE_FILE: {"LineString", "MultiLineString"},
    TERRITORIAL_POLYGON_FILE: {"Polygon", "MultiPolygon"},
    BAND_FILE: {"Polygon", "MultiPolygon"},
}
AOI_BOUNDS = (115.0, 20.0, 126.0, 27.0)
AOI_METADATA = {
    "min_longitude": 115.0,
    "min_latitude": 20.0,
    "max_longitude": 126.0,
    "max_latitude": 27.0,
}
LEGAL_CAVEAT = (
    "Reference only. Not an adjudication of maritime sovereignty, jurisdiction, "
    "or legal boundaries."
)
NAVIGATION_CAVEAT = "Not for navigation."
MARINE_REGIONS_EEZ_V12_AOI_SEMANTIC_SHA256 = (
    "376e76e650f9680f0dfd0286c614f27f2849eddd890f9125257acc9f31ac7366"
)
MOI_12NM_SHA256 = (
    "60e598850980d50517a424986fa818762f62906610caab070f3613434c1122c9"
)
MOI_24NM_SHA256 = (
    "1ee39e10bc83bf9ad72eaef41644efc8ab106a7cd8d01172a3b17f8f163a72ce"
)
AREA_TOLERANCE = 1e-12

REQUIRED_METADATA_FIELDS = {
    "output_filename",
    "source_organization",
    "original_dataset_name",
    "source_url",
    "source_version",
    "source_date",
    "retrieval_date",
    "source_license",
    "license_url",
    "source_checksum",
    "original_crs",
    "output_crs",
    "AOI",
    "clipping_operation",
    "processing_steps",
    "derivation_method",
    "geometry_status",
    "original_feature_count",
    "output_feature_count",
    "legal_caveat",
    "navigation_caveat",
}
EEZ_HOLE_COUNTS = {8321: 88, 8322: 12, 8486: 555, 8487: 29, 48954: 7}
TERRITORIAL_LINE_STRUCTURE = {
    "moi-12nm-0002": ("LineString", 1),
    "moi-12nm-0003": ("LineString", 1),
    "moi-12nm-0004": ("MultiLineString", 2),
}
TERRITORIAL_POLYGON_STRUCTURE = {
    "moi-12nm-0002": ("Polygon", 1),
    "moi-12nm-0003": ("Polygon", 1),
    "moi-12nm-0004": ("MultiPolygon", 2),
}
BAND_STRUCTURE = {
    "moi-24nm-0002": ("Polygon", 1),
    "moi-24nm-0003": ("Polygon", 1),
    "moi-24nm-0004": ("Polygon", 2),
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_iso_date(value: object, context: str) -> None:
    assert isinstance(value, str) and value, f"{context} must be a non-empty date"
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise AssertionError(f"{context} must be an ISO date: {value!r}") from exc


def _assert_coordinate_tree(coordinates: object, context: str) -> None:
    assert isinstance(coordinates, list) and coordinates, (
        f"{context}: malformed coordinate structure"
    )
    nested = [isinstance(item, list) for item in coordinates]
    if any(nested):
        assert all(nested), f"{context}: malformed coordinate structure"
        for index, child in enumerate(coordinates):
            _assert_coordinate_tree(child, f"{context}[{index}]")
        return

    assert len(coordinates) == 2, (
        f"{context}: every position must be exactly [longitude, latitude]"
    )
    assert all(
        isinstance(value, Real)
        and not isinstance(value, bool)
        and math.isfinite(value)
        for value in coordinates
    ), f"{context}: coordinates must contain finite numeric values"
    longitude, latitude = coordinates
    assert 115 <= longitude <= 126, f"{context}: longitude outside [115, 126]"
    assert 20 <= latitude <= 27, f"{context}: latitude outside [20, 27]"


def _assert_line_coordinates(
    coordinates: object, context: str, *, closed_ring: bool = False
) -> None:
    minimum_positions = 4 if closed_ring else 2
    assert isinstance(coordinates, list) and len(coordinates) >= minimum_positions, (
        f"{context}: line requires at least {minimum_positions} positions"
    )
    assert all(
        isinstance(position, list)
        and len(position) == 2
        and not any(isinstance(value, list) for value in position)
        for position in coordinates
    ), f"{context}: malformed coordinate structure"
    if closed_ring:
        assert coordinates[0] == coordinates[-1], (
            f"{context}: polygon coordinates must form a closed linear ring"
        )


def _assert_geometry_coordinate_structure(geometry: dict, context: str) -> None:
    geometry_type = geometry.get("type")
    coordinates = geometry["coordinates"]
    if geometry_type == "LineString":
        _assert_line_coordinates(coordinates, context)
    elif geometry_type == "MultiLineString":
        assert isinstance(coordinates, list) and coordinates, (
            f"{context}: MultiLineString must contain line parts"
        )
        for index, line in enumerate(coordinates):
            _assert_line_coordinates(line, f"{context} line {index}")
    elif geometry_type == "Polygon":
        assert isinstance(coordinates, list) and coordinates, (
            f"{context}: Polygon must contain linear rings"
        )
        for index, ring in enumerate(coordinates):
            _assert_line_coordinates(
                ring, f"{context} ring {index}", closed_ring=True
            )
    elif geometry_type == "MultiPolygon":
        assert isinstance(coordinates, list) and coordinates, (
            f"{context}: MultiPolygon must contain polygons"
        )
        for polygon_index, polygon in enumerate(coordinates):
            assert isinstance(polygon, list) and polygon, (
                f"{context} polygon {polygon_index}: must contain linear rings"
            )
            for ring_index, ring in enumerate(polygon):
                _assert_line_coordinates(
                    ring,
                    f"{context} polygon {polygon_index} ring {ring_index}",
                    closed_ring=True,
                )
    else:
        raise AssertionError(f"{context}: unexpected geometry type {geometry_type!r}")


def _calculated_bbox(geometries: list[BaseGeometry]) -> list[float]:
    return [
        round(min(geometry.bounds[0] for geometry in geometries), 7),
        round(min(geometry.bounds[1] for geometry in geometries), 7),
        round(max(geometry.bounds[2] for geometry in geometries), 7),
        round(max(geometry.bounds[3] for geometry in geometries), 7),
    ]


def _assert_bbox(
    declared_bbox: object, geometries: list[BaseGeometry], context: str
) -> None:
    assert isinstance(declared_bbox, list) and len(declared_bbox) == 4, (
        f"{context} bbox must contain four values"
    )
    assert all(
        isinstance(value, Real)
        and not isinstance(value, bool)
        and math.isfinite(value)
        for value in declared_bbox
    ), f"{context} bbox must contain finite numeric values"
    expected_bbox = _calculated_bbox(geometries)
    assert declared_bbox == expected_bbox, (
        f"{context} bbox mismatch: declared={declared_bbox}, "
        f"calculated={expected_bbox}"
    )


def _assert_nonempty_string(record: dict, field: str, context: str) -> None:
    value = record[field]
    assert isinstance(value, str) and value.strip(), (
        f"{context}: {field} must be a non-empty string"
    )


def _assert_nonempty_string_or_list(record: dict, field: str, context: str) -> None:
    value = record[field]
    if isinstance(value, str):
        assert value.strip(), f"{context}: {field} must not be empty"
        return
    assert isinstance(value, list) and value, (
        f"{context}: {field} must be a non-empty string or list"
    )
    assert all(isinstance(item, str) and item.strip() for item in value), (
        f"{context}: {field} list entries must be non-empty strings"
    )


def _validate_metadata(metadata: dict) -> dict[str, dict]:
    assert metadata.get("schema_version") == (
        "seawatch-maritime-reference-metadata-1"
    ), "source_metadata.json has an unexpected schema_version"
    outputs = metadata.get("outputs")
    assert isinstance(outputs, list), "source_metadata.json outputs must be a list"
    assert len(outputs) == len(EXPECTED_FEATURE_COUNTS), (
        "source_metadata.json must contain one record per GeoJSON artifact"
    )
    assert all(isinstance(record, dict) for record in outputs), (
        "source_metadata.json output records must be objects"
    )

    filenames = [record.get("output_filename") for record in outputs]
    assert len(set(filenames)) == len(filenames), (
        "source_metadata.json output filenames must be unique"
    )
    assert set(filenames) == set(EXPECTED_FEATURE_COUNTS), (
        "source_metadata.json must describe exactly the production GeoJSON files"
    )
    metadata_by_name = {record["output_filename"]: record for record in outputs}

    string_fields = {
        "source_organization",
        "source_license",
        "license_url",
        "original_crs",
        "output_crs",
        "clipping_operation",
        "legal_caveat",
        "navigation_caveat",
    }
    for filename, expected_count in EXPECTED_FEATURE_COUNTS.items():
        record = metadata_by_name[filename]
        missing = REQUIRED_METADATA_FIELDS - record.keys()
        assert not missing, f"{filename}: missing metadata fields {sorted(missing)}"
        for field in string_fields:
            _assert_nonempty_string(record, field, filename)
        for field in ("original_dataset_name", "source_url", "source_version"):
            _assert_nonempty_string_or_list(record, field, filename)
        source_dates = record["source_date"]
        if isinstance(source_dates, list):
            assert source_dates, f"{filename}: source_date list must not be empty"
            for source_date in source_dates:
                _assert_iso_date(source_date, f"{filename} source_date")
        else:
            _assert_iso_date(source_dates, f"{filename} source_date")
        _assert_iso_date(record["retrieval_date"], f"{filename} retrieval_date")
        source_urls = record["source_url"]
        if isinstance(source_urls, str):
            source_urls = [source_urls]
        assert all(url.startswith("https://") for url in source_urls), (
            f"{filename}: every source_url must use HTTPS"
        )
        assert record["license_url"].startswith("https://"), (
            f"{filename}: license_url must use HTTPS"
        )
        assert record["output_crs"] == "EPSG:4326", (
            f"{filename}: output_crs must be EPSG:4326"
        )
        assert record["AOI"] == AOI_METADATA, f"{filename}: AOI metadata mismatch"
        assert isinstance(record["processing_steps"], list) and record[
            "processing_steps"
        ], f"{filename}: processing_steps must be a non-empty list"
        assert all(
            isinstance(step, str) and step.strip()
            for step in record["processing_steps"]
        ), f"{filename}: processing_steps must contain non-empty strings"
        assert isinstance(record["source_checksum"], dict) and record[
            "source_checksum"
        ], f"{filename}: source_checksum must be present"
        assert record["geometry_status"] == EXPECTED_STATUS[filename], (
            f"{filename}: geometry_status must be {EXPECTED_STATUS[filename]!r}"
        )
        assert isinstance(record["original_feature_count"], int) and not isinstance(
            record["original_feature_count"], bool
        ), f"{filename}: original_feature_count must be an integer"
        assert record["original_feature_count"] >= expected_count, (
            f"{filename}: original_feature_count cannot be below output count"
        )
        assert record["output_feature_count"] == expected_count, (
            f"{filename}: expected {expected_count} features in fixed metadata contract"
        )
        assert record["legal_caveat"] == LEGAL_CAVEAT, (
            f"{filename}: legal caveat mismatch"
        )
        assert record["navigation_caveat"] == NAVIGATION_CAVEAT, (
            f"{filename}: navigation caveat mismatch"
        )
        if EXPECTED_STATUS[filename] == "derived_reference":
            derivation = record["derivation_method"]
            assert isinstance(derivation, str) and derivation.strip(), (
                f"{filename}: derived output requires a derivation_method"
            )
            assert "not an official government polygon" in derivation.casefold(), (
                f"{filename}: derivation must say it is not an official government polygon"
            )
        else:
            assert record["derivation_method"] is None, (
                f"{filename}: clipped source must not claim a derivation method"
            )

    eez_record = metadata_by_name[EEZ_FILE]
    eez_checksum = eez_record["source_checksum"]
    assert eez_checksum.get("semantic_source_sha256") == (
        MARINE_REGIONS_EEZ_V12_AOI_SEMANTIC_SHA256
    ), "Marine Regions semantic_source_sha256 does not match the reviewed v12 pin"
    assert eez_checksum.get("raw_retrieval_sha256") is None, (
        "Marine Regions raw retrieval hash must remain omitted for deterministic output"
    )
    assert eez_record["source_version"] == "World EEZ v12"
    assert eez_record["source_date"] == "2023-10-25"
    assert eez_record["retrieval_date"] == "2026-10-03"
    assert "marine regions" in eez_record["source_organization"].casefold()
    assert eez_record["license_url"] == (
        "https://www.marineregions.org/disclaimer.php"
    )
    assert eez_record.get("source_version_validation") == {
        "strategy": "pinned_semantic_aoi_snapshot",
        "expected_semantic_source_sha256": (
            MARINE_REGIONS_EEZ_V12_AOI_SEMANTIC_SHA256
        ),
        "failure_policy": (
            "Fail closed if canonical WFS feature semantics differ; an explicit "
            "source-version review and pin update is required."
        ),
    }, "Marine Regions World EEZ v12 validation pin was weakened"

    expected_moi_hashes = {
        TERRITORIAL_LINE_FILE: {MOI_12NM_SHA256},
        CONTIGUOUS_LINE_FILE: {MOI_24NM_SHA256},
        TERRITORIAL_POLYGON_FILE: {MOI_12NM_SHA256},
        BAND_FILE: {MOI_12NM_SHA256, MOI_24NM_SHA256},
    }
    for filename, expected_hashes in expected_moi_hashes.items():
        record = metadata_by_name[filename]
        assert record["license_url"] == "https://data.gov.tw/license"
        assert "taiwan ministry of the interior" in record[
            "source_organization"
        ].casefold()
        license_text = record["source_license"].casefold()
        assert "open government data license" in license_text and "1.0" in license_text
        checksum_values = record["source_checksum"].get("values")
        assert isinstance(checksum_values, list) and checksum_values, (
            f"{filename}: source_checksum values must be present"
        )
        recorded_hashes = {item.get("value") for item in checksum_values}
        assert recorded_hashes == expected_hashes, (
            f"{filename}: MOI source checksum mismatch"
        )
    return metadata_by_name


def _validate_readme(readme: str) -> None:
    text = " ".join(readme.casefold().split())
    assert "reference only" in text, "README missing reference only concept"
    assert "not an adjudication" in text and all(
        concept in text
        for concept in ("maritime sovereignty", "jurisdiction", "legal boundaries")
    ), "README missing non-adjudication concepts"
    assert "not for navigation" in text, "README missing not for navigation concept"
    assert "marine regions" in text, "README missing Marine Regions attribution"
    assert "world eez v12" in text, "README missing World EEZ v12 attribution"
    assert "taiwan ministry of the interior" in text, (
        "README missing Taiwan MOI attribution"
    )
    assert "open government data license" in text and "version 1.0" in text, (
        "README missing Government Open Data License Taiwan 1.0 concept"
    )
    assert "https://data.gov.tw/license" in text, (
        "README missing the official Taiwan license URL"
    )
    assert "official_line.geojson" in text and "derived_reference" in text, (
        "README must distinguish official source lines from derived polygons/bands"
    )
    assert "not an official moi polygon" in text, (
        "README must state that derived outputs are not official MOI polygons"
    )


def _validate_collection(
    filename: str, collection: dict, metadata_record: dict
) -> list[BaseGeometry]:
    assert collection.get("type") == "FeatureCollection", (
        f"{filename}: type must be FeatureCollection"
    )
    features = collection.get("features")
    assert isinstance(features, list), f"{filename}: features must be a list"
    expected_count = EXPECTED_FEATURE_COUNTS[filename]
    assert len(features) == expected_count, (
        f"{filename}: expected {expected_count} features, found {len(features)}"
    )
    assert len(features) == metadata_record["output_feature_count"], (
        f"{filename}: GeoJSON and metadata feature counts disagree"
    )
    seawatch = collection.get("seawatch")
    assert isinstance(seawatch, dict), f"{filename}: missing seawatch metadata"
    assert seawatch.get("output_crs") == "EPSG:4326"
    assert seawatch.get("aoi") == list(AOI_BOUNDS)
    assert seawatch.get("geometry_status") == EXPECTED_STATUS[filename], (
        f"{filename}: collection geometry_status must be "
        f"{EXPECTED_STATUS[filename]!r}"
    )
    assert seawatch.get("legal_caveat") == LEGAL_CAVEAT
    assert seawatch.get("navigation_caveat") == NAVIGATION_CAVEAT

    aoi = box(*AOI_BOUNDS)
    geometries: list[BaseGeometry] = []
    for index, feature in enumerate(features):
        context = f"{filename} feature {index}"
        assert isinstance(feature, dict) and feature.get("type") == "Feature", (
            f"{context}: must be a GeoJSON Feature"
        )
        geometry_mapping = feature.get("geometry")
        assert isinstance(geometry_mapping, dict), f"{context}: missing geometry"
        assert "coordinates" in geometry_mapping, (
            f"{context}: geometry must declare coordinates"
        )
        _assert_coordinate_tree(geometry_mapping["coordinates"], context)
        _assert_geometry_coordinate_structure(geometry_mapping, context)
        geometry = shape(geometry_mapping)
        assert not geometry.is_empty, f"{context}: geometry must not be empty"
        assert geometry.is_valid, f"{context}: geometry must be valid"
        assert geometry.geom_type in EXPECTED_GEOMETRY_TYPES[filename], (
            f"{context}: unexpected geometry type {geometry.geom_type}"
        )
        assert aoi.covers(geometry), f"{context}: geometry falls outside the AOI"
        geometries.append(geometry)

        properties = feature.get("properties")
        assert isinstance(properties, dict), f"{context}: properties must be an object"
        assert properties.get("geometry_status") == EXPECTED_STATUS[filename], (
            f"{context}: geometry_status must be {EXPECTED_STATUS[filename]!r}"
        )
        assert properties.get("legal_caveat") == LEGAL_CAVEAT
        assert properties.get("navigation_caveat") == NAVIGATION_CAVEAT
        if EXPECTED_STATUS[filename] == "derived_reference":
            derivation = properties.get("derivation_method")
            assert isinstance(derivation, str) and derivation.strip(), (
                f"{context}: missing derivation_method"
            )
            assert "not an official government polygon" in derivation.casefold(), (
                f"{context}: derived output must say it is not an official "
                "government polygon"
            )
        if "bbox" in feature:
            _assert_bbox(feature["bbox"], [geometry], context)

    assert "bbox" in collection, f"{filename}: collection bbox is required"
    _assert_bbox(collection["bbox"], geometries, filename)
    return geometries


def _part_count(geometry: BaseGeometry) -> int:
    return len(geometry.geoms) if geometry.geom_type.startswith("Multi") else 1


def _hole_count(geometry: BaseGeometry) -> int:
    if geometry.geom_type == "Polygon":
        return len(geometry.interiors)
    if geometry.geom_type == "MultiPolygon":
        return sum(len(polygon.interiors) for polygon in geometry.geoms)
    return 0


def _assert_unique_regions(collection: dict, filename: str) -> None:
    regions: list[str] = []
    for index, feature in enumerate(collection["features"]):
        region = feature["properties"].get("Region")
        assert isinstance(region, str) and region.strip(), (
            f"{filename} feature {index}: Region must be a non-empty string"
        )
        regions.append(region)
    assert len(set(regions)) == len(regions), (
        f"{filename}: features must have unique Region values"
    )


def _validate_overlap_and_structure(collections: dict[str, dict]) -> None:
    for filename in (
        TERRITORIAL_LINE_FILE,
        CONTIGUOUS_LINE_FILE,
        TERRITORIAL_POLYGON_FILE,
        BAND_FILE,
    ):
        _assert_unique_regions(collections[filename], filename)

    eez_features = collections[EEZ_FILE]["features"]
    overlapping_claims = [
        feature
        for feature in eez_features
        if feature["properties"].get("pol_type") == "Overlapping claim"
    ]
    overlapping_ids = {
        feature["properties"].get("mrgid") for feature in overlapping_claims
    }
    assert len(overlapping_claims) == 2 and overlapping_ids == {8321, 48954}, (
        "EEZ overlapping claim MRGIDs must remain separate features: "
        "expected {8321, 48954}"
    )
    assert len({feature.get("id") for feature in overlapping_claims}) == 2, (
        "EEZ overlapping claims must retain separate feature IDs"
    )

    eez_by_mrgid = {
        feature["properties"]["mrgid"]: shape(feature["geometry"])
        for feature in eez_features
    }
    assert set(eez_by_mrgid) == set(EEZ_HOLE_COUNTS), (
        "EEZ reviewed production MRGID structure changed"
    )
    for mrgid, expected_holes in EEZ_HOLE_COUNTS.items():
        geometry = eez_by_mrgid[mrgid]
        assert geometry.geom_type == "Polygon", (
            f"EEZ MRGID {mrgid}: expected reviewed Polygon structure"
        )
        assert _hole_count(geometry) == expected_holes, (
            f"EEZ hole structure changed for MRGID {mrgid}: "
            f"expected {expected_holes}, found {_hole_count(geometry)}"
        )

    for feature in eez_features:
        properties = feature["properties"]
        assert {"area_km2", "x_1", "y_1"}.isdisjoint(properties)
        assert {
            "source_area_km2",
            "source_centroid_x",
            "source_centroid_y",
        } <= properties.keys()

    territorial_line_structure = {
        feature["properties"]["source_feature_id"]: (
            (geometry := shape(feature["geometry"])).geom_type,
            _part_count(geometry),
        )
        for feature in collections[TERRITORIAL_LINE_FILE]["features"]
    }
    assert territorial_line_structure == TERRITORIAL_LINE_STRUCTURE, (
        "12 NM source multipart structure changed: "
        f"{territorial_line_structure!r}"
    )

    territorial_polygon_structure = {
        feature["properties"]["source_feature_id"]: (
            (geometry := shape(feature["geometry"])).geom_type,
            _part_count(geometry),
        )
        for feature in collections[TERRITORIAL_POLYGON_FILE]["features"]
    }
    assert territorial_polygon_structure == TERRITORIAL_POLYGON_STRUCTURE, (
        "derived 12 NM multipart structure changed: "
        f"{territorial_polygon_structure!r}"
    )

    band_structure = {
        feature["properties"]["source_24nm_feature_id"]: (
            (geometry := shape(feature["geometry"])).geom_type,
            _hole_count(geometry),
        )
        for feature in collections[BAND_FILE]["features"]
    }
    assert band_structure == BAND_STRUCTURE, (
        f"12-24 NM band hole structure changed: {band_structure!r}"
    )


def _polygonize_source_line(geometry: BaseGeometry, context: str) -> BaseGeometry:
    lines = list(geometry.geoms) if geometry.geom_type == "MultiLineString" else [geometry]
    assert all(line.is_closed and line.is_simple for line in lines), (
        f"{context}: source line parts must be closed and simple"
    )
    polygons_result, cuts, dangles, invalid = polygonize_full(lines)
    assert cuts.is_empty and dangles.is_empty and invalid.is_empty, (
        f"{context}: source line polygonization has topological remnants"
    )
    polygons = list(polygons_result.geoms)
    assert len(polygons) == len(lines), (
        f"{context}: expected one polygon per source line part"
    )
    for index, polygon in enumerate(polygons):
        for other in polygons[index + 1 :]:
            assert polygon.intersection(other).area <= AREA_TOLERANCE, (
                f"{context}: source line polygons overlap"
            )
    result: BaseGeometry = (
        polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)
    )
    assert result.is_valid, f"{context}: polygonized source line is invalid"
    return result


def _validate_band_equation(collections: dict[str, dict]) -> None:
    outer_by_region = {
        feature["properties"]["Region"]: _polygonize_source_line(
            shape(feature["geometry"]),
            f"24 NM region {feature['properties']['Region']!r}",
        )
        for feature in collections[CONTIGUOUS_LINE_FILE]["features"]
    }
    inner_by_region = {
        feature["properties"]["Region"]: shape(feature["geometry"])
        for feature in collections[TERRITORIAL_POLYGON_FILE]["features"]
    }
    band_by_region = {
        feature["properties"]["Region"]: shape(feature["geometry"])
        for feature in collections[BAND_FILE]["features"]
    }
    assert set(outer_by_region) == set(inner_by_region) == set(band_by_region), (
        "band equation requires identical 12 NM, 24 NM, and band regions"
    )

    for region, actual_band in band_by_region.items():
        outer = outer_by_region[region]
        inner = inner_by_region[region]
        assert outer.covers(inner), (
            f"band equation {region!r}: derived 24 NM polygon must cover 12 NM"
        )
        expected_band = outer.difference(inner)
        symmetric_difference_area = actual_band.symmetric_difference(
            expected_band
        ).area
        assert symmetric_difference_area <= AREA_TOLERANCE, (
            f"band equation {region!r}: symmetric difference area "
            f"{symmetric_difference_area} exceeds {AREA_TOLERANCE}"
        )
        overlap_area = actual_band.intersection(inner).area
        assert overlap_area <= AREA_TOLERANCE, (
            f"band equation {region!r}: band overlaps inner 12 NM by {overlap_area}"
        )
        reconstruction_error = actual_band.union(inner).symmetric_difference(
            outer
        ).area
        assert reconstruction_error <= AREA_TOLERANCE, (
            f"band equation {region!r}: inner plus band does not reconstruct 24 NM; "
            f"difference area is {reconstruction_error}"
        )


def _write(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )


def _refresh_declared_bboxes(collection: dict) -> None:
    geometries = [shape(feature["geometry"]) for feature in collection["features"]]
    if "bbox" in collection:
        collection["bbox"] = [
            round(min(geometry.bounds[0] for geometry in geometries), 7),
            round(min(geometry.bounds[1] for geometry in geometries), 7),
            round(max(geometry.bounds[2] for geometry in geometries), 7),
            round(max(geometry.bounds[3] for geometry in geometries), 7),
        ]
    for feature, geometry in zip(collection["features"], geometries, strict=True):
        if "bbox" in feature:
            feature["bbox"] = [round(value, 7) for value in geometry.bounds]


@pytest.fixture
def artifact_copy(tmp_path: Path) -> Path:
    artifact_dir = tmp_path / "taiwan_maritime_reference"
    shutil.copytree(PRODUCTION_DIR, artifact_dir)
    return artifact_dir


def _validate_artifacts(artifact_dir: Path) -> None:
    entries = list(artifact_dir.iterdir())
    actual_files = {path.name for path in entries}
    assert actual_files == EXPECTED_FILES, (
        f"production file set mismatch: missing={sorted(EXPECTED_FILES - actual_files)}, "
        f"unexpected={sorted(actual_files - EXPECTED_FILES)}"
    )
    assert all(path.is_file() for path in entries), (
        "production file set must contain files only"
    )

    metadata_by_name = _validate_metadata(
        _load(artifact_dir / "source_metadata.json")
    )
    _validate_readme((artifact_dir / "README.md").read_text(encoding="utf-8"))

    collections: dict[str, dict] = {}
    for filename in EXPECTED_FEATURE_COUNTS:
        collection = _load(artifact_dir / filename)
        collections[filename] = collection
        _validate_collection(filename, collection, metadata_by_name[filename])

    _validate_overlap_and_structure(collections)
    _validate_band_equation(collections)


def test_checked_in_production_artifacts_satisfy_the_reference_contract() -> None:
    _validate_artifacts(PRODUCTION_DIR)


def test_validator_rejects_unexpected_raw_file(artifact_copy: Path) -> None:
    (artifact_copy / "source.zip").write_bytes(b"unexpected raw source")

    with pytest.raises(AssertionError, match="production file set"):
        _validate_artifacts(artifact_copy)


def test_validator_rejects_wrong_fixed_count_even_when_metadata_matches(
    artifact_copy: Path,
) -> None:
    eez_path = artifact_copy / "eez_reference_areas.geojson"
    eez = _load(eez_path)
    eez["features"].pop()
    _refresh_declared_bboxes(eez)
    _write(eez_path, eez)

    metadata_path = artifact_copy / "source_metadata.json"
    metadata = _load(metadata_path)
    record = next(
        item
        for item in metadata["outputs"]
        if item["output_filename"] == "eez_reference_areas.geojson"
    )
    record["output_feature_count"] = 4
    _write(metadata_path, metadata)

    with pytest.raises(AssertionError, match="expected 5 features"):
        _validate_artifacts(artifact_copy)


def test_validator_rejects_three_dimensional_coordinate(artifact_copy: Path) -> None:
    eez_path = artifact_copy / "eez_reference_areas.geojson"
    eez = _load(eez_path)
    position = eez["features"][0]["geometry"]["coordinates"]
    while isinstance(position[0], list):
        position = position[0]
    position.append(0.0)
    _write(eez_path, eez)

    with pytest.raises(AssertionError, match=r"exactly \[longitude, latitude\]"):
        _validate_artifacts(artifact_copy)


@pytest.mark.parametrize("bad_value", [math.nan, math.inf])
def test_validator_rejects_nonfinite_coordinate(
    artifact_copy: Path, bad_value: float
) -> None:
    eez_path = artifact_copy / "eez_reference_areas.geojson"
    eez = _load(eez_path)
    position = eez["features"][0]["geometry"]["coordinates"]
    while isinstance(position[0], list):
        position = position[0]
    position[0] = bad_value
    _write(eez_path, eez)

    with pytest.raises(AssertionError, match="finite numeric values"):
        _validate_artifacts(artifact_copy)


def test_validator_rejects_malformed_coordinate_structure(
    artifact_copy: Path,
) -> None:
    eez_path = artifact_copy / "eez_reference_areas.geojson"
    eez = _load(eez_path)
    position = eez["features"][0]["geometry"]["coordinates"]
    while isinstance(position[0], list):
        position = position[0]
    position[1] = [position[1]]
    _write(eez_path, eez)

    with pytest.raises(AssertionError, match="malformed coordinate structure"):
        _validate_artifacts(artifact_copy)


def test_validator_rejects_unclosed_serialized_polygon_ring(
    artifact_copy: Path,
) -> None:
    eez_path = artifact_copy / EEZ_FILE
    eez = _load(eez_path)
    eez["features"][0]["geometry"]["coordinates"][0].pop()
    _write(eez_path, eez)

    with pytest.raises(AssertionError, match="closed linear ring"):
        _validate_artifacts(artifact_copy)


def test_validator_rejects_missing_required_metadata(artifact_copy: Path) -> None:
    metadata_path = artifact_copy / "source_metadata.json"
    metadata = _load(metadata_path)
    metadata["outputs"][0].pop("source_organization")
    _write(metadata_path, metadata)

    with pytest.raises(AssertionError, match="missing metadata fields"):
        _validate_artifacts(artifact_copy)


def test_validator_rejects_removed_readme_caveat(artifact_copy: Path) -> None:
    readme_path = artifact_copy / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    readme_path.write_text(
        readme.replace("**Not for navigation.**", ""), encoding="utf-8"
    )

    with pytest.raises(AssertionError, match="README.*not for navigation"):
        _validate_artifacts(artifact_copy)


def test_validator_rejects_removed_overlapping_claim(artifact_copy: Path) -> None:
    eez_path = artifact_copy / "eez_reference_areas.geojson"
    eez = _load(eez_path)
    claim = next(
        feature
        for feature in eez["features"]
        if feature["properties"]["mrgid"] == 8321
    )
    claim["properties"]["mrgid"] = 99999
    _write(eez_path, eez)

    with pytest.raises(AssertionError, match="overlapping claim MRGIDs"):
        _validate_artifacts(artifact_copy)


def test_validator_rejects_lost_source_multipart_structure(
    artifact_copy: Path,
) -> None:
    line_path = artifact_copy / "territorial_sea_12nm_official_line.geojson"
    collection = _load(line_path)
    feature = next(
        item
        for item in collection["features"]
        if item["properties"]["source_feature_id"] == "moi-12nm-0004"
    )
    feature["geometry"] = {
        "type": "LineString",
        "coordinates": feature["geometry"]["coordinates"][0],
    }
    _refresh_declared_bboxes(collection)
    _write(line_path, collection)

    with pytest.raises(AssertionError, match="12 NM source multipart structure"):
        _validate_artifacts(artifact_copy)


def test_validator_rejects_lost_eez_hole_structure(artifact_copy: Path) -> None:
    eez_path = artifact_copy / "eez_reference_areas.geojson"
    eez = _load(eez_path)
    feature = next(
        item for item in eez["features"] if item["properties"]["mrgid"] == 8321
    )
    feature["geometry"]["coordinates"].pop()
    _write(eez_path, eez)

    with pytest.raises(AssertionError, match="EEZ hole structure"):
        _validate_artifacts(artifact_copy)


def test_validator_rejects_corrupted_band_geometry(artifact_copy: Path) -> None:
    band_path = artifact_copy / "contiguous_zone_12_24nm_reference_band.geojson"
    band = _load(band_path)
    feature = band["features"][0]
    feature["geometry"]["coordinates"][1][1][0] += 0.0001
    assert shape(feature["geometry"]).is_valid
    _write(band_path, band)

    with pytest.raises(AssertionError, match="band equation"):
        _validate_artifacts(artifact_copy)


def test_validator_rejects_duplicate_region_keys(artifact_copy: Path) -> None:
    for filename in (
        TERRITORIAL_LINE_FILE,
        CONTIGUOUS_LINE_FILE,
        TERRITORIAL_POLYGON_FILE,
        BAND_FILE,
    ):
        path = artifact_copy / filename
        collection = _load(path)
        for feature in collection["features"]:
            feature["properties"]["Region"] = "duplicate"
        _write(path, collection)

    with pytest.raises(AssertionError, match="unique Region"):
        _validate_artifacts(artifact_copy)


def test_validator_rejects_wrong_geometry_status(artifact_copy: Path) -> None:
    filename = "territorial_sea_12nm_reference_polygon.geojson"
    collection_path = artifact_copy / filename
    collection = _load(collection_path)
    collection["seawatch"]["geometry_status"] = "clipped_source"
    for feature in collection["features"]:
        feature["properties"]["geometry_status"] = "clipped_source"
    _write(collection_path, collection)

    metadata_path = artifact_copy / "source_metadata.json"
    metadata = _load(metadata_path)
    record = next(
        item for item in metadata["outputs"] if item["output_filename"] == filename
    )
    record["geometry_status"] = "clipped_source"
    _write(metadata_path, metadata)

    with pytest.raises(AssertionError, match="geometry_status"):
        _validate_artifacts(artifact_copy)


def test_validator_rejects_unwanted_production_file(artifact_copy: Path) -> None:
    (artifact_copy / "review-notes.txt").write_text("not production", encoding="utf-8")

    with pytest.raises(AssertionError, match="production file set"):
        _validate_artifacts(artifact_copy)


def test_validator_rejects_incorrect_declared_bbox(artifact_copy: Path) -> None:
    eez_path = artifact_copy / "eez_reference_areas.geojson"
    eez = _load(eez_path)
    eez["bbox"][0] += 0.01
    _write(eez_path, eez)

    with pytest.raises(AssertionError, match="bbox"):
        _validate_artifacts(artifact_copy)


def test_validator_accepts_equivalent_readme_heading(artifact_copy: Path) -> None:
    readme_path = artifact_copy / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    readme_path.write_text(
        readme.replace(
            "Source lines versus derived references",
            "Official source lines and derived references",
        ),
        encoding="utf-8",
    )

    _validate_artifacts(artifact_copy)
