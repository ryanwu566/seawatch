"""Focused, network-free tests for the maritime-reference build pipeline."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
import ssl
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
import shapefile
from shapely.geometry import shape

import scripts.build_taiwan_maritime_reference as maritime_reference

from scripts.build_taiwan_maritime_reference import (
    AOI_BOUNDS,
    EXPECTED_OUTPUT_FILENAMES,
    LEGAL_CAVEAT,
    NAVIGATION_CAVEAT,
    SourceValidationError,
    _https_context_for_url,
    build_from_sources,
)


FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "gis"
EEZ_FIXTURE = FIXTURE_DIR / "marine_regions_eez_aoi.geojson"


def _closed_ring(min_lon: float, min_lat: float, max_lon: float, max_lat: float):
    return [
        [min_lon, min_lat],
        [max_lon, min_lat],
        [max_lon, max_lat],
        [min_lon, max_lat],
        [min_lon, min_lat],
    ]


def _write_moi_zip(
    tmp_path: Path,
    name: str,
    records: list[tuple[str, list[list[list[float]]]]],
) -> Path:
    """Create a tiny UTF-8 PolyLine shapefile with the real MOI field shape."""

    source_dir = tmp_path / f"{name}-source"
    source_dir.mkdir()
    stem = source_dir / name
    with shapefile.Writer(str(stem), shapeType=shapefile.POLYLINE, encoding="utf-8") as writer:
        writer.field("Region", "C", size=40)
        for region, parts in records:
            writer.line(parts)
            writer.record(region)

    archive = tmp_path / f"{name}.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED) as output:
        for suffix in (".shp", ".shx", ".dbf"):
            output.write(stem.with_suffix(suffix), arcname=f"{name}{suffix}")
    return archive


def _valid_moi_sources(tmp_path: Path) -> tuple[Path, Path]:
    territorial = _write_moi_zip(
        tmp_path,
        "territorial",
        [
            ("臺灣本島", [_closed_ring(119.0, 21.0, 122.0, 25.0)]),
            (
                "釣魚臺列嶼",
                [
                    _closed_ring(123.0, 25.0, 123.4, 25.4),
                    _closed_ring(124.0, 25.2, 124.4, 25.6),
                ],
            ),
            ("黃岩島", [_closed_ring(117.0, 15.0, 118.0, 16.0)]),
        ],
    )
    contiguous = _write_moi_zip(
        tmp_path,
        "contiguous",
        [
            ("臺灣本島", [_closed_ring(118.5, 20.5, 122.5, 25.5)]),
            ("釣魚臺列嶼", [_closed_ring(122.7, 24.7, 124.7, 26.0)]),
            ("黃岩島", [_closed_ring(116.8, 14.8, 118.2, 16.2)]),
        ],
    )
    return territorial, contiguous


def _build(tmp_path: Path, output_name: str = "output") -> Path:
    territorial, contiguous = _valid_moi_sources(tmp_path)
    output_dir = tmp_path / output_name
    build_from_sources(
        eez_path=EEZ_FIXTURE,
        territorial_zip_path=territorial,
        contiguous_zip_path=contiguous,
        output_dir=output_dir,
        retrieval_date="2026-10-03",
        expected_eez_semantic_sha256=maritime_reference.semantic_geojson_sha256(
            EEZ_FIXTURE
        ),
    )
    return output_dir


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: dict) -> Path:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    return path


def _iter_positions(coordinates):
    if coordinates and isinstance(coordinates[0], (int, float)):
        yield coordinates
        return
    for child in coordinates:
        yield from _iter_positions(child)


def test_semantic_checksum_ignores_wfs_timestamp_but_raw_checksum_does_not(
    tmp_path: Path,
) -> None:
    first_payload = _load(EEZ_FIXTURE)
    second_payload = _load(EEZ_FIXTURE)
    first_payload["timeStamp"] = "2026-10-03T01:00:00Z"
    second_payload["timeStamp"] = "2026-10-03T02:00:00Z"
    first = _write_json(tmp_path / "first.geojson", first_payload)
    second = _write_json(tmp_path / "second.geojson", second_payload)

    assert sha256(first.read_bytes()).hexdigest() != sha256(second.read_bytes()).hexdigest()
    assert maritime_reference.semantic_geojson_sha256(
        first
    ) == maritime_reference.semantic_geojson_sha256(second)


def test_semantic_checksum_normalizes_feature_and_property_order(tmp_path: Path) -> None:
    first_payload = _load(EEZ_FIXTURE)
    second_payload = _load(EEZ_FIXTURE)
    second_payload["features"].reverse()
    for feature in second_payload["features"]:
        feature["properties"] = dict(reversed(feature["properties"].items()))
    first = _write_json(tmp_path / "first.geojson", first_payload)
    second = _write_json(tmp_path / "second.geojson", second_payload)

    assert maritime_reference.semantic_geojson_sha256(
        first
    ) == maritime_reference.semantic_geojson_sha256(second)


def test_wfs_timestamp_does_not_change_generated_bytes(tmp_path: Path) -> None:
    first_payload = _load(EEZ_FIXTURE)
    second_payload = _load(EEZ_FIXTURE)
    first_payload["timeStamp"] = "2026-10-03T01:00:00Z"
    second_payload["timeStamp"] = "2026-10-03T02:00:00Z"
    first_source = _write_json(tmp_path / "first-source.geojson", first_payload)
    second_source = _write_json(tmp_path / "second-source.geojson", second_payload)
    expected_checksum = maritime_reference.semantic_geojson_sha256(first_source)
    territorial, contiguous = _valid_moi_sources(tmp_path)

    for source, output_name in (
        (first_source, "first-output"),
        (second_source, "second-output"),
    ):
        build_from_sources(
            eez_path=source,
            territorial_zip_path=territorial,
            contiguous_zip_path=contiguous,
            output_dir=tmp_path / output_name,
            retrieval_date="2026-10-03",
            expected_eez_semantic_sha256=expected_checksum,
        )

    for filename in (*EXPECTED_OUTPUT_FILENAMES, "source_metadata.json"):
        assert (tmp_path / "first-output" / filename).read_bytes() == (
            tmp_path / "second-output" / filename
        ).read_bytes()
    metadata = _load(tmp_path / "first-output" / "source_metadata.json")
    eez_metadata = next(
        item
        for item in metadata["outputs"]
        if item["output_filename"] == "eez_reference_areas.geojson"
    )
    assert eez_metadata["source_checksum"]["semantic_source_sha256"] == expected_checksum
    assert eez_metadata["source_checksum"]["raw_retrieval_sha256"] is None


def test_build_emits_valid_nonempty_epsg4326_geojson_inside_aoi(tmp_path: Path) -> None:
    output_dir = _build(tmp_path)
    metadata = _load(output_dir / "source_metadata.json")
    metadata_by_name = {item["output_filename"]: item for item in metadata["outputs"]}

    assert set(metadata_by_name) == set(EXPECTED_OUTPUT_FILENAMES)
    for filename in EXPECTED_OUTPUT_FILENAMES:
        collection = _load(output_dir / filename)
        assert collection["type"] == "FeatureCollection"
        assert collection["features"]
        assert collection["seawatch"]["output_crs"] == "EPSG:4326"
        assert metadata_by_name[filename]["output_crs"] == "EPSG:4326"
        for feature in collection["features"]:
            geometry = shape(feature["geometry"])
            assert not geometry.is_empty
            assert geometry.is_valid
            for lon, lat in _iter_positions(feature["geometry"]["coordinates"]):
                assert AOI_BOUNDS[0] <= lon <= AOI_BOUNDS[2]
                assert AOI_BOUNDS[1] <= lat <= AOI_BOUNDS[3]


def test_output_order_and_bytes_are_deterministic(tmp_path: Path) -> None:
    first = _build(tmp_path, "first")
    second = tmp_path / "second"
    territorial = tmp_path / "territorial.zip"
    contiguous = tmp_path / "contiguous.zip"
    build_from_sources(
        eez_path=EEZ_FIXTURE,
        territorial_zip_path=territorial,
        contiguous_zip_path=contiguous,
        output_dir=second,
        retrieval_date="2026-10-03",
        expected_eez_semantic_sha256=maritime_reference.semantic_geojson_sha256(
            EEZ_FIXTURE
        ),
    )

    for filename in (*EXPECTED_OUTPUT_FILENAMES, "source_metadata.json"):
        assert (first / filename).read_bytes() == (second / filename).read_bytes()
    eez = _load(first / "eez_reference_areas.geojson")
    assert [feature["properties"]["mrgid"] for feature in eez["features"]] == [100, 200]


def test_metadata_is_complete_for_every_output(tmp_path: Path) -> None:
    output_dir = _build(tmp_path)
    outputs = _load(output_dir / "source_metadata.json")["outputs"]
    required = {
        "output_filename",
        "source_organization",
        "original_dataset_name",
        "source_url",
        "source_version",
        "source_date",
        "retrieval_date",
        "source_license",
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
    assert len(outputs) == len(EXPECTED_OUTPUT_FILENAMES)
    for item in outputs:
        assert required <= item.keys()
        assert item["retrieval_date"] == "2026-10-03"
        assert item["source_license"]
        assert item["source_organization"]
        assert item["source_version"]
        assert item["source_date"]
        assert item["source_checksum"]
        assert item["source_checksum"]["publisher_supplied"] is False
        assert item["legal_caveat"] == LEGAL_CAVEAT
        assert item["navigation_caveat"] == NAVIGATION_CAVEAT


def test_moi_metadata_includes_the_official_license_url(tmp_path: Path) -> None:
    output_dir = _build(tmp_path)
    outputs = _load(output_dir / "source_metadata.json")["outputs"]

    moi_outputs = [
        item
        for item in outputs
        if item["output_filename"] != "eez_reference_areas.geojson"
    ]
    assert len(moi_outputs) == 4
    assert {item["license_url"] for item in moi_outputs} == {
        "https://data.gov.tw/license"
    }


def test_source_lines_and_derived_polygons_are_not_mislabeled(tmp_path: Path) -> None:
    output_dir = _build(tmp_path)
    for filename in (
        "territorial_sea_12nm_official_line.geojson",
        "contiguous_zone_24nm_official_line.geojson",
    ):
        collection = _load(output_dir / filename)
        assert collection["seawatch"]["geometry_status"] == "clipped_source"
        assert {shape(f["geometry"]).geom_type for f in collection["features"]} <= {
            "LineString",
            "MultiLineString",
        }
        assert {f["properties"]["geometry_status"] for f in collection["features"]} == {
            "clipped_source"
        }

    for filename in (
        "territorial_sea_12nm_reference_polygon.geojson",
        "contiguous_zone_12_24nm_reference_band.geojson",
    ):
        collection = _load(output_dir / filename)
        assert collection["seawatch"]["geometry_status"] == "derived_reference"
        assert {shape(f["geometry"]).geom_type for f in collection["features"]} <= {
            "Polygon",
            "MultiPolygon",
        }
        assert {f["properties"]["geometry_status"] for f in collection["features"]} == {
            "derived_reference"
        }
        assert all(f["properties"]["derivation_method"] for f in collection["features"])


def test_overlapping_eez_claims_and_multipart_source_are_preserved(tmp_path: Path) -> None:
    output_dir = _build(tmp_path)
    eez = _load(output_dir / "eez_reference_areas.geojson")
    assert len(eez["features"]) == 2
    assert all("Overlapping claim" in f["properties"]["geoname"] for f in eez["features"])
    assert {f["properties"]["sovereign1"] for f in eez["features"]} == {"Japan", "Taiwan"}
    assert "China" in {f["properties"]["sovereign2"] for f in eez["features"]}
    eez_with_hole = next(f for f in eez["features"] if f["properties"]["mrgid"] == 200)
    assert len(shape(eez_with_hole["geometry"]).interiors) == 1

    territorial = _load(output_dir / "territorial_sea_12nm_official_line.geojson")
    multipart = next(f for f in territorial["features"] if f["properties"]["Region"] == "釣魚臺列嶼")
    assert shape(multipart["geometry"]).geom_type == "MultiLineString"
    derived = _load(output_dir / "territorial_sea_12nm_reference_polygon.geojson")
    derived_multipart = next(
        f for f in derived["features"] if f["properties"]["Region"] == "釣魚臺列嶼"
    )
    assert shape(derived_multipart["geometry"]).geom_type == "MultiPolygon"


def test_clipping_counts_and_no_global_source_artifact(tmp_path: Path) -> None:
    output_dir = _build(tmp_path)
    metadata = {
        item["output_filename"]: item
        for item in _load(output_dir / "source_metadata.json")["outputs"]
    }
    assert metadata["eez_reference_areas.geojson"]["original_feature_count"] == 3
    assert metadata["eez_reference_areas.geojson"]["output_feature_count"] == 2
    assert metadata["territorial_sea_12nm_official_line.geojson"]["original_feature_count"] == 3
    assert metadata["territorial_sea_12nm_official_line.geojson"]["output_feature_count"] == 2
    assert {path.name for path in output_dir.iterdir()} == {
        *EXPECTED_OUTPUT_FILENAMES,
        "source_metadata.json",
    }
    assert not any(path.suffix in {".zip", ".shp", ".dbf", ".shx"} for path in output_dir.iterdir())


def test_every_feature_and_collection_has_caveats(tmp_path: Path) -> None:
    output_dir = _build(tmp_path)
    for filename in EXPECTED_OUTPUT_FILENAMES:
        collection = _load(output_dir / filename)
        assert collection["seawatch"]["legal_caveat"] == LEGAL_CAVEAT
        assert collection["seawatch"]["navigation_caveat"] == NAVIGATION_CAVEAT
        assert all(f["properties"]["legal_caveat"] == LEGAL_CAVEAT for f in collection["features"])
        assert all(
            f["properties"]["navigation_caveat"] == NAVIGATION_CAVEAT
            for f in collection["features"]
        )


def test_open_outer_limit_line_is_rejected_instead_of_polygonized(tmp_path: Path) -> None:
    territorial, contiguous = _valid_moi_sources(tmp_path)
    open_territorial = _write_moi_zip(
        tmp_path,
        "open-territorial",
        [("臺灣本島", [[[119.0, 21.0], [122.0, 21.0], [122.0, 25.0]]])],
    )
    with pytest.raises(SourceValidationError, match="closed"):
        build_from_sources(
            eez_path=EEZ_FIXTURE,
            territorial_zip_path=open_territorial,
            contiguous_zip_path=contiguous,
            output_dir=tmp_path / "bad-open",
            retrieval_date="2026-10-03",
            expected_eez_semantic_sha256=maritime_reference.semantic_geojson_sha256(
                EEZ_FIXTURE
            ),
        )
    assert territorial.exists()


def test_noncovering_24nm_geometry_is_rejected_instead_of_banded(tmp_path: Path) -> None:
    territorial, _ = _valid_moi_sources(tmp_path)
    noncovering = _write_moi_zip(
        tmp_path,
        "noncovering-contiguous",
        [("臺灣本島", [_closed_ring(120.0, 22.0, 121.0, 23.0)])],
    )
    with pytest.raises(SourceValidationError, match="does not cover"):
        build_from_sources(
            eez_path=EEZ_FIXTURE,
            territorial_zip_path=territorial,
            contiguous_zip_path=noncovering,
            output_dir=tmp_path / "bad-band",
            retrieval_date="2026-10-03",
            expected_eez_semantic_sha256=maritime_reference.semantic_geojson_sha256(
                EEZ_FIXTURE
            ),
        )


def test_build_requires_an_expected_eez_semantic_snapshot(tmp_path: Path) -> None:
    territorial, contiguous = _valid_moi_sources(tmp_path)

    with pytest.raises(SourceValidationError, match="expected.*required"):
        build_from_sources(
            eez_path=EEZ_FIXTURE,
            territorial_zip_path=territorial,
            contiguous_zip_path=contiguous,
            output_dir=tmp_path / "unpinned",
            retrieval_date="2026-10-03",
        )


def test_changed_eez_semantics_fail_the_pinned_snapshot(tmp_path: Path) -> None:
    original_checksum = maritime_reference.semantic_geojson_sha256(EEZ_FIXTURE)
    changed_payload = _load(EEZ_FIXTURE)
    changed_payload["features"][0]["properties"]["geoname"] = "Changed claim"
    changed_source = _write_json(tmp_path / "changed.geojson", changed_payload)
    territorial, contiguous = _valid_moi_sources(tmp_path)

    assert maritime_reference.semantic_geojson_sha256(changed_source) != original_checksum
    with pytest.raises(SourceValidationError, match="does not match"):
        build_from_sources(
            eez_path=changed_source,
            territorial_zip_path=territorial,
            contiguous_zip_path=contiguous,
            output_dir=tmp_path / "changed-output",
            retrieval_date="2026-10-03",
            expected_eez_semantic_sha256=original_checksum,
        )


def test_clipped_eez_source_geometry_attributes_are_qualified(
    tmp_path: Path,
) -> None:
    payload = _load(EEZ_FIXTURE)
    payload["features"][0]["properties"].update(
        {"area_km2": 12345, "x_1": 120.25, "y_1": 23.75}
    )
    source = _write_json(tmp_path / "source-attributes.geojson", payload)
    territorial, contiguous = _valid_moi_sources(tmp_path)
    output_dir = tmp_path / "qualified-output"
    build_from_sources(
        eez_path=source,
        territorial_zip_path=territorial,
        contiguous_zip_path=contiguous,
        output_dir=output_dir,
        retrieval_date="2026-10-03",
        expected_eez_semantic_sha256=maritime_reference.semantic_geojson_sha256(
            source
        ),
    )

    eez = _load(output_dir / "eez_reference_areas.geojson")
    properties = next(
        feature["properties"]
        for feature in eez["features"]
        if feature["id"] == payload["features"][0]["id"]
    )
    assert properties["source_area_km2"] == 12345
    assert properties["source_centroid_x"] == 120.25
    assert properties["source_centroid_y"] == 23.75
    assert "area_km2" not in properties
    assert "x_1" not in properties
    assert "y_1" not in properties


def test_moi_https_context_keeps_identity_checks_without_strict_x509() -> None:
    context = _https_context_for_url(
        "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/download"
    )

    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    if hasattr(ssl, "VERIFY_X509_STRICT"):
        assert not context.verify_flags & ssl.VERIFY_X509_STRICT

    marine_regions_context = _https_context_for_url("https://geo.vliz.be/data")
    assert marine_regions_context.verify_flags == ssl.create_default_context().verify_flags
