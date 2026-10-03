"""Build deterministic Taiwan-area maritime reference GeoJSON.

The official Ministry of the Interior (MOI) 12 NM and 24 NM products are
published *lines*.  Polygon and band outputs made from those lines are separate
SeaWatch-derived references and must never be described as official polygons.

Network acquisition is intentionally separate from :func:`build_from_sources`
so tests and archival rebuilds can transform fixed local inputs without making
external requests.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import shutil
import ssl
import tempfile
from typing import Any, Iterable, Iterator, Literal
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile

from pyproj import CRS, Transformer
import shapefile
from shapely import make_valid, normalize
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPolygon,
    Polygon,
    box,
    mapping,
    shape,
)
from shapely.geometry.base import BaseGeometry
from shapely.ops import polygonize_full, transform


AOI_BOUNDS = (115.0, 20.0, 126.0, 27.0)
AOI = box(*AOI_BOUNDS)
OUTPUT_CRS = "EPSG:4326"
COORDINATE_PRECISION = 7

LEGAL_CAVEAT = (
    "Reference only. Not an adjudication of maritime sovereignty, jurisdiction, "
    "or legal boundaries."
)
NAVIGATION_CAVEAT = "Not for navigation."
OVERLAP_POLICY = (
    "Overlapping maritime claims are preserved as separate source features; "
    "no claimant is selected as legally preferred."
)

EEZ_OUTPUT = "eez_reference_areas.geojson"
TERRITORIAL_LINE_OUTPUT = "territorial_sea_12nm_official_line.geojson"
CONTIGUOUS_LINE_OUTPUT = "contiguous_zone_24nm_official_line.geojson"
TERRITORIAL_POLYGON_OUTPUT = "territorial_sea_12nm_reference_polygon.geojson"
CONTIGUOUS_BAND_OUTPUT = "contiguous_zone_12_24nm_reference_band.geojson"
EXPECTED_OUTPUT_FILENAMES = (
    EEZ_OUTPUT,
    TERRITORIAL_LINE_OUTPUT,
    CONTIGUOUS_LINE_OUTPUT,
    TERRITORIAL_POLYGON_OUTPUT,
    CONTIGUOUS_BAND_OUTPUT,
)

MARINE_REGIONS_WFS_URL = (
    "https://geo.vliz.be/geoserver/MarineRegions/wfs?"
    "service=WFS&version=1.0.0&request=GetFeature&typeName=eez&"
    "bbox=115,20,126,27&outputFormat=application/json&srsName=EPSG:4326"
)
MARINE_REGIONS_DATASET_URL = "https://www.marineregions.org/downloads.php"
MARINE_REGIONS_LICENSE_URL = "https://www.marineregions.org/disclaimer.php"
MOI_12_DATASET_URL = "https://data.gov.tw/dataset/155452"
MOI_24_DATASET_URL = "https://data.gov.tw/dataset/163012"
MOI_LICENSE_URL = "https://data.gov.tw/license"
MOI_12_DOWNLOAD_URL = (
    "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/"
    "DE466003-A5A6-442D-8C55-552A0451D0B5/resource/"
    "F78DBCE4-4CB3-42DA-8A8C-13281A1ECF51/download"
)
MOI_24_DOWNLOAD_URL = (
    "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/"
    "0B62D0ED-D732-4673-AA40-2724631BEFEC/resource/"
    "637A7B8A-0BB3-4662-9605-E747CCE05D78/download"
)

MARINE_REGIONS_LICENSE = (
    "Creative Commons Attribution 4.0 International (CC BY 4.0), subject to "
    "Marine Regions terms of use"
)
MARINE_REGIONS_EEZ_V12_AOI_SEMANTIC_SHA256 = (
    "376e76e650f9680f0dfd0286c614f27f2849eddd890f9125257acc9f31ac7366"
)
MOI_LICENSE = "政府資料開放授權條款－第1版 (Open Government Data License, version 1.0)"


class SourceValidationError(ValueError):
    """Raised when source data cannot be transformed without fabrication."""


@dataclass(frozen=True)
class OutputSummary:
    """Small CLI/reporting summary for one generated GeoJSON layer."""

    output_filename: str
    original_feature_count: int
    output_feature_count: int
    geometry_status: str


@dataclass(frozen=True)
class _GeometryFeature:
    feature_id: str
    properties: dict[str, Any]
    geometry: BaseGeometry


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _checksum_record(sources: Iterable[tuple[str, Path]]) -> dict[str, Any]:
    return {
        "algorithm": "SHA-256",
        "publisher_supplied": False,
        "scope": "exact retrieved source bytes; computed by the SeaWatch build",
        "values": [
            {"source_url": url, "value": _sha256_file(path)}
            for url, path in sources
        ],
    }


def semantic_geojson_sha256(path: Path) -> str:
    """Hash stable WFS dataset content, excluding response transport metadata."""

    try:
        collection = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SourceValidationError(f"Cannot read GeoJSON source: {path}") from exc
    if collection.get("type") != "FeatureCollection" or not isinstance(
        collection.get("features"), list
    ):
        raise SourceValidationError("Semantic GeoJSON source is not a FeatureCollection")

    features = list(collection["features"])
    features.sort(
        key=lambda feature: (
            str(feature.get("id", "")),
            json.dumps(
                feature,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ),
        )
    )
    semantic_collection = {
        "type": "FeatureCollection",
        "crs": collection.get("crs"),
        "features": features,
    }
    serialized = json.dumps(
        semantic_collection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(serialized).hexdigest()


def _semantic_geojson_checksum_record(
    source_url: str, semantic_checksum: str
) -> dict[str, Any]:
    return {
        "algorithm": "SHA-256",
        "publisher_supplied": False,
        "scope": (
            "canonical GeoJSON FeatureCollection semantics: type, CRS, and "
            "deterministically ordered complete features; volatile top-level WFS "
            "response metadata is excluded"
        ),
        "raw_retrieval_sha256": None,
        "raw_retrieval_sha256_note": (
            "Intentionally omitted from deterministic build metadata because the "
            "WFS response contains a changing retrieval timestamp."
        ),
        "semantic_source_sha256": semantic_checksum,
        "values": [
            {
                "source_url": source_url,
                "value": semantic_checksum,
                "value_type": "semantic_source_sha256",
            }
        ],
    }


def _iter_polygons(geometry: BaseGeometry) -> Iterator[Polygon]:
    if isinstance(geometry, Polygon):
        yield geometry
    elif isinstance(geometry, (MultiPolygon, GeometryCollection)):
        for part in geometry.geoms:
            yield from _iter_polygons(part)


def _iter_lines(geometry: BaseGeometry) -> Iterator[LineString]:
    if isinstance(geometry, LineString):
        yield geometry
    elif isinstance(geometry, (MultiLineString, GeometryCollection)):
        for part in geometry.geoms:
            yield from _iter_lines(part)


def _polygonal_only(geometry: BaseGeometry, context: str) -> BaseGeometry:
    polygons = [polygon for polygon in _iter_polygons(geometry) if not polygon.is_empty]
    if not polygons:
        return Polygon()
    result: BaseGeometry = polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)
    if not result.is_valid:
        raise SourceValidationError(f"{context}: polygonal result is invalid")
    return result


def _linear_only(geometry: BaseGeometry) -> BaseGeometry:
    lines = [line for line in _iter_lines(geometry) if not line.is_empty]
    if not lines:
        return LineString()
    return lines[0] if len(lines) == 1 else MultiLineString(lines)


def _reproject_geometry(geometry: BaseGeometry, source_crs: CRS) -> BaseGeometry:
    target_crs = CRS.from_epsg(4326)
    if source_crs.equals(target_crs):
        return geometry
    transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)
    return transform(transformer.transform, geometry)


def _round_coordinates(value: Any) -> Any:
    if isinstance(value, float):
        rounded = round(value, COORDINATE_PRECISION)
        return 0.0 if rounded == 0 else rounded
    if isinstance(value, (tuple, list)):
        return [_round_coordinates(child) for child in value]
    return value


def _canonical_geometry(geometry: BaseGeometry, context: str) -> dict[str, Any]:
    if geometry.is_empty:
        raise SourceValidationError(f"{context}: empty output geometry")
    if not geometry.is_valid:
        raise SourceValidationError(f"{context}: invalid output geometry")
    normalized = normalize(geometry)
    serialized = mapping(normalized)
    output = {
        "type": serialized["type"],
        "coordinates": _round_coordinates(serialized["coordinates"]),
    }
    reconstructed = shape(output)
    if reconstructed.is_empty or not reconstructed.is_valid:
        raise SourceValidationError(
            f"{context}: fixed-precision serialization produced invalid geometry"
        )
    return output


def _feature(
    feature: _GeometryFeature,
    *,
    geometry_status: Literal["clipped_source", "derived_reference"],
) -> dict[str, Any]:
    properties = dict(feature.properties)
    properties.update(
        {
            "geometry_status": geometry_status,
            "legal_caveat": LEGAL_CAVEAT,
            "navigation_caveat": NAVIGATION_CAVEAT,
        }
    )
    return {
        "type": "Feature",
        "id": feature.feature_id,
        "properties": properties,
        "geometry": _canonical_geometry(feature.geometry, feature.feature_id),
    }


def _collection(
    *,
    filename: str,
    features: list[_GeometryFeature],
    geometry_status: Literal["clipped_source", "derived_reference"],
) -> dict[str, Any]:
    if not features:
        raise SourceValidationError(f"{filename}: no features intersect the AOI")
    geojson_features = [
        _feature(item, geometry_status=geometry_status) for item in features
    ]
    bounds = [item.geometry.bounds for item in features]
    bbox = [
        round(min(item[0] for item in bounds), COORDINATE_PRECISION),
        round(min(item[1] for item in bounds), COORDINATE_PRECISION),
        round(max(item[2] for item in bounds), COORDINATE_PRECISION),
        round(max(item[3] for item in bounds), COORDINATE_PRECISION),
    ]
    return {
        "type": "FeatureCollection",
        "name": Path(filename).stem,
        "bbox": bbox,
        "seawatch": {
            "aoi": list(AOI_BOUNDS),
            "geometry_status": geometry_status,
            "legal_caveat": LEGAL_CAVEAT,
            "navigation_caveat": NAVIGATION_CAVEAT,
            "output_crs": OUTPUT_CRS,
            "overlap_policy": OVERLAP_POLICY,
        },
        "features": geojson_features,
    }


def _parse_geojson_crs(collection: dict[str, Any]) -> CRS:
    crs_member = collection.get("crs")
    if crs_member is None:
        # RFC 7946 GeoJSON uses WGS84 longitude/latitude when no legacy CRS
        # member is present.
        return CRS.from_epsg(4326)
    try:
        name = crs_member["properties"]["name"]
        return CRS.from_user_input(name)
    except (KeyError, TypeError, ValueError) as exc:
        raise SourceValidationError("Marine Regions GeoJSON has an invalid CRS") from exc


def _load_eez_features(path: Path) -> tuple[list[_GeometryFeature], int, int]:
    try:
        collection = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SourceValidationError(f"Cannot read Marine Regions GeoJSON: {path}") from exc
    if collection.get("type") != "FeatureCollection" or not isinstance(
        collection.get("features"), list
    ):
        raise SourceValidationError("Marine Regions source is not a FeatureCollection")

    source_crs = _parse_geojson_crs(collection)
    output: list[_GeometryFeature] = []
    repair_count = 0
    for index, source_feature in enumerate(collection["features"]):
        source_id = str(source_feature.get("id") or f"eez-{index + 1:04d}")
        try:
            geometry = shape(source_feature["geometry"])
            properties = dict(source_feature["properties"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SourceValidationError(f"{source_id}: malformed EEZ feature") from exc
        if geometry.is_empty or geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            raise SourceValidationError(f"{source_id}: EEZ geometry must be polygonal")

        repaired = False
        if not geometry.is_valid:
            geometry = _polygonal_only(make_valid(geometry), f"{source_id} repair")
            repaired = True
        geometry = _reproject_geometry(geometry, source_crs)
        clipped = _polygonal_only(geometry.intersection(AOI), f"{source_id} clip")
        if clipped.is_empty:
            continue
        if not clipped.is_valid:
            clipped = _polygonal_only(make_valid(clipped), f"{source_id} clip repair")
            repaired = True
        if repaired:
            repair_count += 1
        for source_name, qualified_name in (
            ("area_km2", "source_area_km2"),
            ("x_1", "source_centroid_x"),
            ("y_1", "source_centroid_y"),
        ):
            if source_name not in properties:
                continue
            if qualified_name in properties:
                raise SourceValidationError(
                    f"{source_id}: source property names collide at {qualified_name!r}"
                )
            properties[qualified_name] = properties.pop(source_name)
        properties.update(
            {
                "source_feature_id": source_id,
                "source_dataset": "World EEZ v12",
                "geometry_repaired": repaired,
                "geometry_repair_method": "Shapely make_valid" if repaired else None,
            }
        )
        output.append(_GeometryFeature(source_id, properties, clipped))

    output.sort(
        key=lambda item: (
            int(item.properties.get("mrgid", 2**63 - 1)),
            item.feature_id,
        )
    )
    return output, len(collection["features"]), repair_count


def _zip_member(archive: ZipFile, suffix: str) -> bytes:
    matches = [name for name in archive.namelist() if name.lower().endswith(suffix)]
    if len(matches) != 1:
        raise SourceValidationError(
            f"MOI archive must contain exactly one {suffix} member; found {len(matches)}"
        )
    return archive.read(matches[0])


def _load_moi_lines(path: Path, prefix: str) -> list[_GeometryFeature]:
    try:
        with ZipFile(path) as archive:
            shp = BytesIO(_zip_member(archive, ".shp"))
            shx = BytesIO(_zip_member(archive, ".shx"))
            dbf = BytesIO(_zip_member(archive, ".dbf"))
    except (OSError, BadZipFile, KeyError) as exc:
        raise SourceValidationError(f"Cannot read MOI shapefile archive: {path}") from exc

    output: list[_GeometryFeature] = []
    try:
        with shapefile.Reader(
            shp=shp,
            shx=shx,
            dbf=dbf,
            encoding="utf-8",
        ) as reader:
            if reader.shapeType not in {
                shapefile.POLYLINE,
                shapefile.POLYLINEM,
                shapefile.POLYLINEZ,
            }:
                raise SourceValidationError("MOI source geometry must be PolyLine")
            field_names = [field[0] for field in reader.fields[1:]]
            if "Region" not in field_names:
                raise SourceValidationError("MOI DBF is missing the Region field")
            for index, shape_record in enumerate(reader.iterShapeRecords()):
                source_id = f"{prefix}-{index + 1:04d}"
                source_shape = shape_record.shape
                starts = list(source_shape.parts) + [len(source_shape.points)]
                parts = [
                    LineString(source_shape.points[start:end])
                    for start, end in zip(starts, starts[1:])
                    if end - start >= 2
                ]
                if not parts:
                    raise SourceValidationError(f"{source_id}: empty MOI line geometry")
                geometry: BaseGeometry = (
                    parts[0] if len(parts) == 1 else MultiLineString(parts)
                )
                if geometry.is_empty or not geometry.is_valid:
                    raise SourceValidationError(f"{source_id}: invalid MOI line geometry")
                region = shape_record.record.as_dict().get("Region")
                if not isinstance(region, str) or not region.strip():
                    raise SourceValidationError(f"{source_id}: missing Region value")
                output.append(
                    _GeometryFeature(
                        source_id,
                        {
                            "Region": region.strip(),
                            "source_feature_id": source_id,
                            "source_record_index": index,
                            "source_geometry_type": "PolyLine",
                            "geometry_repaired": False,
                            "geometry_repair_method": None,
                        },
                        geometry,
                    )
                )
    except (OSError, UnicodeError, shapefile.ShapefileException) as exc:
        raise SourceValidationError(f"Cannot parse MOI shapefile archive: {path}") from exc
    return output


def _clip_lines(features: list[_GeometryFeature]) -> list[_GeometryFeature]:
    output: list[_GeometryFeature] = []
    for feature in features:
        clipped = _linear_only(feature.geometry.intersection(AOI))
        if clipped.is_empty:
            continue
        output.append(_GeometryFeature(feature.feature_id, feature.properties, clipped))
    output.sort(key=lambda item: (item.properties["Region"], item.feature_id))
    return output


def _polygonize_moi_lines(
    features: list[_GeometryFeature], source_line_filename: str
) -> list[_GeometryFeature]:
    output: list[_GeometryFeature] = []
    for feature in features:
        lines = list(_iter_lines(feature.geometry))
        for part_index, line in enumerate(lines):
            if not line.is_closed:
                raise SourceValidationError(
                    f"{feature.feature_id} part {part_index}: outer-limit line is not closed"
                )
            if not line.is_simple:
                raise SourceValidationError(
                    f"{feature.feature_id} part {part_index}: outer-limit line is not simple"
                )

        polygons_result, cuts, dangles, invalid = polygonize_full(lines)
        if not cuts.is_empty or not dangles.is_empty or not invalid.is_empty:
            raise SourceValidationError(
                f"{feature.feature_id}: outer-limit polygonization is topologically ambiguous"
            )
        polygons = list(_iter_polygons(polygons_result))
        if len(polygons) != len(lines):
            raise SourceValidationError(
                f"{feature.feature_id}: expected one polygon per closed line part"
            )
        for index, polygon in enumerate(polygons):
            for other in polygons[index + 1 :]:
                if polygon.intersection(other).area > 0:
                    raise SourceValidationError(
                        f"{feature.feature_id}: nested or overlapping line parts are ambiguous"
                    )
        geometry: BaseGeometry = (
            polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)
        )
        if not geometry.is_valid:
            raise SourceValidationError(
                f"{feature.feature_id}: polygonized geometry is invalid"
            )
        clipped = _polygonal_only(geometry.intersection(AOI), f"{feature.feature_id} clip")
        if clipped.is_empty:
            continue
        properties = dict(feature.properties)
        properties.update(
            {
                "source_line_output": source_line_filename,
                "official_source_geometry": "published outer-limit line",
                "derivation_method": (
                    "Strict polygonization of closed, simple MOI outer-limit line parts, "
                    "followed by AOI clipping; SeaWatch-derived reference, not an "
                    "official government polygon."
                ),
            }
        )
        output.append(_GeometryFeature(feature.feature_id, properties, clipped))
    output.sort(key=lambda item: (item.properties["Region"], item.feature_id))
    return output


def _build_band(
    territorial: list[_GeometryFeature], contiguous: list[_GeometryFeature]
) -> list[_GeometryFeature]:
    territorial_by_region = {item.properties["Region"]: item for item in territorial}
    contiguous_by_region = {item.properties["Region"]: item for item in contiguous}
    output: list[_GeometryFeature] = []
    for region in sorted(contiguous_by_region):
        outer = contiguous_by_region[region]
        inner = territorial_by_region.get(region)
        if inner is None:
            raise SourceValidationError(
                f"24 NM region {region!r} has no matching 12 NM reference polygon"
            )
        if not outer.geometry.covers(inner.geometry):
            raise SourceValidationError(
                f"24 NM region {region!r} does not cover its matching 12 NM geometry"
            )
        band = _polygonal_only(
            outer.geometry.difference(inner.geometry), f"24 NM band {region!r}"
        )
        if band.is_empty:
            raise SourceValidationError(f"24 NM band {region!r} is empty")
        feature_id = f"band-{outer.feature_id}"
        output.append(
            _GeometryFeature(
                feature_id,
                {
                    "Region": region,
                    "source_12nm_feature_id": inner.feature_id,
                    "source_24nm_feature_id": outer.feature_id,
                    "official_source_geometry": "published 12 NM and 24 NM outer-limit lines",
                    "geometry_repaired": False,
                    "geometry_repair_method": None,
                    "derivation_method": (
                        "Region-matched derived 24 NM polygon minus derived 12 NM "
                        "polygon, after strict line polygonization and AOI clipping; "
                        "SeaWatch-derived reference, not an official government polygon."
                    ),
                },
                band,
            )
        )
    extra_territorial = sorted(set(territorial_by_region) - set(contiguous_by_region))
    if extra_territorial:
        raise SourceValidationError(
            "12 NM AOI regions have no matching 24 NM geometry: "
            + ", ".join(repr(item) for item in extra_territorial)
        )
    return output


def _metadata_record(
    *,
    output_filename: str,
    source_organization: Any,
    original_dataset_name: Any,
    source_url: Any,
    source_version: Any,
    source_date: Any,
    retrieval_date: str,
    source_license: str,
    source_checksum: dict[str, Any],
    original_crs: str,
    geometry_status: Literal["clipped_source", "derived_reference"],
    original_feature_count: int,
    output_feature_count: int,
    processing_steps: list[str],
    derivation_method: str | None,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "output_filename": output_filename,
        "source_organization": source_organization,
        "original_dataset_name": original_dataset_name,
        "source_url": source_url,
        "source_version": source_version,
        "source_date": source_date,
        "retrieval_date": retrieval_date,
        "source_license": source_license,
        "source_checksum": source_checksum,
        "original_crs": original_crs,
        "output_crs": OUTPUT_CRS,
        "AOI": {
            "min_longitude": AOI_BOUNDS[0],
            "min_latitude": AOI_BOUNDS[1],
            "max_longitude": AOI_BOUNDS[2],
            "max_latitude": AOI_BOUNDS[3],
        },
        "clipping_operation": (
            "Per-feature Shapely intersection with the closed AOI bbox "
            "[115, 20, 126, 27] in EPSG:4326; empty intersections removed."
        ),
        "processing_steps": processing_steps,
        "derivation_method": derivation_method,
        "geometry_status": geometry_status,
        "original_feature_count": original_feature_count,
        "output_feature_count": output_feature_count,
        "legal_caveat": LEGAL_CAVEAT,
        "navigation_caveat": NAVIGATION_CAVEAT,
        **extra,
    }


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _write_atomic(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def build_from_sources(
    *,
    eez_path: Path,
    territorial_zip_path: Path,
    contiguous_zip_path: Path,
    output_dir: Path,
    retrieval_date: str,
    expected_eez_semantic_sha256: str | None = None,
) -> dict[str, OutputSummary]:
    """Transform fixed local source files into deterministic reference outputs."""

    try:
        date.fromisoformat(retrieval_date)
    except ValueError as exc:
        raise SourceValidationError("retrieval_date must be YYYY-MM-DD") from exc
    eez_path = Path(eez_path)
    territorial_zip_path = Path(territorial_zip_path)
    contiguous_zip_path = Path(contiguous_zip_path)
    output_dir = Path(output_dir)
    for source_path in (eez_path, territorial_zip_path, contiguous_zip_path):
        if not source_path.is_file() or source_path.stat().st_size == 0:
            raise SourceValidationError(f"Missing or empty source file: {source_path}")
    if expected_eez_semantic_sha256 is None:
        raise SourceValidationError(
            "An expected Marine Regions semantic source checksum is required"
        )

    eez_semantic_checksum = semantic_geojson_sha256(eez_path)
    if eez_semantic_checksum != expected_eez_semantic_sha256:
        raise SourceValidationError(
            "Marine Regions semantic source checksum does not match the expected "
            "release snapshot"
        )

    eez, eez_original_count, eez_repairs = _load_eez_features(eez_path)
    territorial_source = _load_moi_lines(territorial_zip_path, "moi-12nm")
    contiguous_source = _load_moi_lines(contiguous_zip_path, "moi-24nm")
    territorial_lines = _clip_lines(territorial_source)
    contiguous_lines = _clip_lines(contiguous_source)
    territorial_polygons = _polygonize_moi_lines(
        territorial_source, TERRITORIAL_LINE_OUTPUT
    )
    contiguous_polygons = _polygonize_moi_lines(
        contiguous_source, CONTIGUOUS_LINE_OUTPUT
    )
    contiguous_band = _build_band(territorial_polygons, contiguous_polygons)

    collections = {
        EEZ_OUTPUT: _collection(
            filename=EEZ_OUTPUT,
            features=eez,
            geometry_status="clipped_source",
        ),
        TERRITORIAL_LINE_OUTPUT: _collection(
            filename=TERRITORIAL_LINE_OUTPUT,
            features=territorial_lines,
            geometry_status="clipped_source",
        ),
        CONTIGUOUS_LINE_OUTPUT: _collection(
            filename=CONTIGUOUS_LINE_OUTPUT,
            features=contiguous_lines,
            geometry_status="clipped_source",
        ),
        TERRITORIAL_POLYGON_OUTPUT: _collection(
            filename=TERRITORIAL_POLYGON_OUTPUT,
            features=territorial_polygons,
            geometry_status="derived_reference",
        ),
        CONTIGUOUS_BAND_OUTPUT: _collection(
            filename=CONTIGUOUS_BAND_OUTPUT,
            features=contiguous_band,
            geometry_status="derived_reference",
        ),
    }

    eez_checksum = _semantic_geojson_checksum_record(
        MARINE_REGIONS_WFS_URL, eez_semantic_checksum
    )
    territorial_checksum = _checksum_record(
        [(MOI_12_DOWNLOAD_URL, territorial_zip_path)]
    )
    contiguous_checksum = _checksum_record([(MOI_24_DOWNLOAD_URL, contiguous_zip_path)])
    combined_checksum = _checksum_record(
        [
            (MOI_12_DOWNLOAD_URL, territorial_zip_path),
            (MOI_24_DOWNLOAD_URL, contiguous_zip_path),
        ]
    )
    line_common = [
        "Validated ZIP members and PolyLine shapefile/DBF schema.",
        "Assigned EPSG:4326 from official TGOS metadata because the archive has no .prj file.",
        "Decoded the Region field as UTF-8 and retained source record identity.",
        "Clipped each source feature independently to the AOI; removed empty intersections.",
        "Normalized geometry and serialized coordinates at 7 decimal places in stable order.",
    ]
    metadata = [
        _metadata_record(
            output_filename=EEZ_OUTPUT,
            source_organization="Flanders Marine Institute (VLIZ) / Marine Regions",
            original_dataset_name="Maritime Boundaries and Exclusive Economic Zones (200NM)",
            source_url=MARINE_REGIONS_WFS_URL,
            source_version="World EEZ v12",
            source_date="2023-10-25",
            retrieval_date=retrieval_date,
            source_license=MARINE_REGIONS_LICENSE,
            source_checksum=eez_checksum,
            original_crs="EPSG:4326",
            geometry_status="clipped_source",
            original_feature_count=eez_original_count,
            output_feature_count=len(eez),
            processing_steps=[
                "Requested only features whose WFS envelopes intersect the AOI bbox.",
                (
                    "Validated polygonal source geometry and retained source attributes; "
                    "qualified full-source area/centroid fields with source_ names."
                ),
                f"Applied Shapely make_valid only where required ({eez_repairs} repaired feature(s)).",
                "Reprojected to EPSG:4326 when necessary.",
                "Clipped each claim independently; did not dissolve or select a claimant.",
                "Normalized geometry and serialized coordinates at 7 decimal places in stable order.",
            ],
            derivation_method=None,
            dataset_information_url=MARINE_REGIONS_DATASET_URL,
            license_url=MARINE_REGIONS_LICENSE_URL,
            overlap_policy=OVERLAP_POLICY,
            source_version_validation={
                "strategy": "pinned_semantic_aoi_snapshot",
                "expected_semantic_source_sha256": expected_eez_semantic_sha256,
                "failure_policy": (
                    "Fail closed if canonical WFS feature semantics differ; an "
                    "explicit source-version review and pin update is required."
                ),
            },
        ),
        _metadata_record(
            output_filename=TERRITORIAL_LINE_OUTPUT,
            source_organization="Taiwan Ministry of the Interior, Department of Land Administration",
            original_dataset_name="中華民國12浬領海外界線",
            source_url=MOI_12_DOWNLOAD_URL,
            source_version="98年修正; archive revision ver1090623",
            source_date="2009-11-18",
            retrieval_date=retrieval_date,
            source_license=MOI_LICENSE,
            source_checksum=territorial_checksum,
            original_crs="EPSG:4326 (official TGOS metadata; source ZIP contains no .prj)",
            geometry_status="clipped_source",
            original_feature_count=len(territorial_source),
            output_feature_count=len(territorial_lines),
            processing_steps=line_common,
            derivation_method=None,
            dataset_information_url=MOI_12_DATASET_URL,
            license_url=MOI_LICENSE_URL,
        ),
        _metadata_record(
            output_filename=CONTIGUOUS_LINE_OUTPUT,
            source_organization="Taiwan Ministry of the Interior, Department of Land Administration",
            original_dataset_name="中華民國24浬鄰接區外界線",
            source_url=MOI_24_DOWNLOAD_URL,
            source_version="98年修正; archive revision ver1090623",
            source_date="2019-11-18",
            retrieval_date=retrieval_date,
            source_license=MOI_LICENSE,
            source_checksum=contiguous_checksum,
            original_crs="EPSG:4326 (official TGOS metadata; source ZIP contains no .prj)",
            geometry_status="clipped_source",
            original_feature_count=len(contiguous_source),
            output_feature_count=len(contiguous_lines),
            processing_steps=line_common,
            derivation_method=None,
            dataset_information_url=MOI_24_DATASET_URL,
            license_url=MOI_LICENSE_URL,
            source_date_note=(
                "TGOS metadata reports 2019-11-18; the archive filename separately says "
                "98年修正 and is retained verbatim in source_version."
            ),
        ),
        _metadata_record(
            output_filename=TERRITORIAL_POLYGON_OUTPUT,
            source_organization="Taiwan Ministry of the Interior, Department of Land Administration",
            original_dataset_name="中華民國12浬領海外界線",
            source_url=MOI_12_DOWNLOAD_URL,
            source_version="98年修正; archive revision ver1090623",
            source_date="2009-11-18",
            retrieval_date=retrieval_date,
            source_license=MOI_LICENSE,
            source_checksum=territorial_checksum,
            original_crs="EPSG:4326 (official TGOS metadata; source ZIP contains no .prj)",
            geometry_status="derived_reference",
            original_feature_count=len(territorial_source),
            output_feature_count=len(territorial_polygons),
            processing_steps=[
                *line_common[:3],
                "Required every source part to be closed and simple.",
                "Required polygonize_full to produce exactly one polygon per part with no cuts, dangles, or invalid remnants.",
                "Rejected nested/overlapping parts; clipped valid polygonal results independently to the AOI.",
                line_common[-1],
            ],
            derivation_method=(
                "Strict polygonization of the published MOI 12 NM outer-limit lines. "
                "SeaWatch-derived visualization/reference polygon; not an official government polygon."
            ),
            dataset_information_url=MOI_12_DATASET_URL,
            license_url=MOI_LICENSE_URL,
        ),
        _metadata_record(
            output_filename=CONTIGUOUS_BAND_OUTPUT,
            source_organization="Taiwan Ministry of the Interior, Department of Land Administration",
            original_dataset_name=[
                "中華民國12浬領海外界線",
                "中華民國24浬鄰接區外界線",
            ],
            source_url=[MOI_12_DOWNLOAD_URL, MOI_24_DOWNLOAD_URL],
            source_version=[
                "12 NM: 98年修正; archive revision ver1090623",
                "24 NM: 98年修正; archive revision ver1090623",
            ],
            source_date=["2009-11-18", "2019-11-18"],
            retrieval_date=retrieval_date,
            source_license=MOI_LICENSE,
            source_checksum=combined_checksum,
            original_crs="EPSG:4326 (official TGOS metadata; source ZIPs contain no .prj)",
            geometry_status="derived_reference",
            original_feature_count=len(territorial_source) + len(contiguous_source),
            output_feature_count=len(contiguous_band),
            processing_steps=[
                "Strictly polygonized both official outer-limit line datasets.",
                "Matched AOI polygons by the preserved Region field.",
                "Required each 24 NM polygon to cover its matching 12 NM polygon.",
                "Subtracted the 12 NM polygon from the 24 NM polygon without combining regions.",
                "Validated and normalized each band independently in stable order.",
            ],
            derivation_method=(
                "Region-matched derived 24 NM polygon minus derived 12 NM polygon. "
                "SeaWatch-derived visualization/reference band; not an official government polygon."
            ),
            input_feature_counts={
                "territorial_12nm": len(territorial_source),
                "contiguous_24nm": len(contiguous_source),
            },
            source_date_note=(
                "The 24 NM TGOS date and archive naming are recorded independently; "
                "no reconciliation is inferred."
            ),
            license_url=MOI_LICENSE_URL,
        ),
    ]
    metadata.sort(key=lambda item: item["output_filename"])
    metadata_document = {
        "schema_version": "seawatch-maritime-reference-metadata-1",
        "outputs": metadata,
    }

    # All source/geometry validation completes before the first output write.
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename in EXPECTED_OUTPUT_FILENAMES:
        _write_atomic(output_dir / filename, _json_bytes(collections[filename]))
    _write_atomic(output_dir / "source_metadata.json", _json_bytes(metadata_document))

    metadata_by_filename = {item["output_filename"]: item for item in metadata}
    return {
        filename: OutputSummary(
            output_filename=filename,
            original_feature_count=metadata_by_filename[filename]["original_feature_count"],
            output_feature_count=metadata_by_filename[filename]["output_feature_count"],
            geometry_status=metadata_by_filename[filename]["geometry_status"],
        )
        for filename in EXPECTED_OUTPUT_FILENAMES
    }


def _download(url: str, destination: Path, *, refresh: bool) -> Path:
    if destination.is_file() and destination.stat().st_size > 0 and not refresh:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.part")
    request = Request(url, headers={"User-Agent": "SeaWatch-reference-builder/1.0"})
    try:
        with urlopen(
            request,
            context=_https_context_for_url(url),
            timeout=180,
        ) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output, length=1024 * 1024)
        if temporary.stat().st_size == 0:
            raise SourceValidationError(f"Downloaded empty source: {url}")
        temporary.replace(destination)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise
    return destination


def _https_context_for_url(url: str) -> ssl.SSLContext:
    """Return a verified TLS context compatible with the official MOI host.

    Python 3.13 enables OpenSSL's strict-X.509 flag in its default context.
    The MOI chain served by ``opdadm.moi.gov.tw`` currently omits a Subject Key
    Identifier and is rejected only by that optional strict flag.  Clearing the
    flag for this one official host retains trust-store validation,
    ``CERT_REQUIRED``, and hostname checks; certificate verification is never
    disabled.
    """

    context = ssl.create_default_context()
    if (
        urlparse(url).hostname == "opdadm.moi.gov.tw"
        and hasattr(ssl, "VERIFY_X509_STRICT")
    ):
        context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return context


def acquire_sources(cache_dir: Path, *, refresh: bool = False) -> tuple[Path, Path, Path]:
    """Acquire only the AOI WFS response and the two small MOI archives."""

    cache_dir = Path(cache_dir)
    eez = _download(
        MARINE_REGIONS_WFS_URL,
        cache_dir / "marine_regions_world_eez_v12_taiwan_aoi.geojson",
        refresh=refresh,
    )
    territorial = _download(
        MOI_12_DOWNLOAD_URL,
        cache_dir / "moi_12nm_official_line.zip",
        refresh=refresh,
    )
    contiguous = _download(
        MOI_24_DOWNLOAD_URL,
        cache_dir / "moi_24nm_official_line.zip",
        refresh=refresh,
    )
    return eez, territorial, contiguous


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(tempfile.gettempdir()) / "seawatch-taiwan-maritime-reference",
        help="Source cache (default: an OS temporary directory).",
    )
    parser.add_argument(
        "--retrieval-date",
        default=date.today().isoformat(),
        help="ISO retrieval date recorded in metadata (default: today).",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Redownload source files even when the cache is populated.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    eez, territorial, contiguous = acquire_sources(args.cache_dir, refresh=args.refresh)
    summaries = build_from_sources(
        eez_path=eez,
        territorial_zip_path=territorial,
        contiguous_zip_path=contiguous,
        output_dir=args.output_dir,
        retrieval_date=args.retrieval_date,
        expected_eez_semantic_sha256=(
            MARINE_REGIONS_EEZ_V12_AOI_SEMANTIC_SHA256
        ),
    )
    print(
        json.dumps(
            {name: summary.__dict__ for name, summary in summaries.items()},
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
