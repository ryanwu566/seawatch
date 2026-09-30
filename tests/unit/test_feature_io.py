from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest


def _phase1_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "track_id": ["track-demo"],
            "base_date_time": [datetime(2024, 1, 1, tzinfo=timezone.utc)],
            "longitude": [-122.4],
            "latitude": [37.8],
            "sog": [5.0],
            "cog": [90.0],
            "heading": [90.0],
            "vessel_type": [70],
        }
    )


def _write_phase1(
    path: Path,
    *,
    crs: str | None = "EPSG:4326",
    timezone_name: str | None = "UTC",
    extra_column: bool = False,
) -> None:
    frame = _phase1_frame()
    if extra_column:
        frame["unexpected"] = "value"
    table = pa.Table.from_pandas(frame, preserve_index=False)
    metadata = dict(table.schema.metadata or {})
    if crs is not None:
        metadata[b"seawatch_crs"] = crs.encode()
    if timezone_name is not None:
        metadata[b"seawatch_timezone"] = timezone_name.encode()
    pq.write_table(table.replace_schema_metadata(metadata), path)


def _provenance_metadata() -> dict[str, str]:
    from apps.api.seawatch.trajectories.features import FEATURE_UNITS

    return {
        "seawatch_schema_version": "trajectory-features-v1",
        "seawatch_crs": "EPSG:4326",
        "seawatch_timezone": "UTC",
        "seawatch_source_artifact_sha256": "a" * 64,
        "seawatch_source_manifest_sha256": "b" * 64,
        "seawatch_config_sha256": "c" * 64,
        "seawatch_generator_version": "phase2-v1",
        "seawatch_feature_units": json.dumps(FEATURE_UNITS, sort_keys=True),
    }


def test_reader_accepts_exact_phase1_contract_and_preserves_utc(tmp_path: Path) -> None:
    from apps.api.seawatch.trajectories.feature_io import read_phase1_parquet

    path = tmp_path / "phase1.parquet"
    _write_phase1(path)

    result = read_phase1_parquet(path)

    assert result.columns.tolist() == _phase1_frame().columns.tolist()
    assert str(result["base_date_time"].dtype).endswith("UTC]")


@pytest.mark.parametrize(
    ("crs", "timezone_name", "message"),
    [
        (None, "UTC", "seawatch_crs"),
        ("EPSG:4326", None, "seawatch_timezone"),
        ("EPSG:3857", "UTC", "EPSG:4326"),
        ("EPSG:4326", "local", "UTC"),
    ],
)
def test_reader_rejects_missing_or_wrong_spatial_temporal_metadata(
    tmp_path: Path, crs: str | None, timezone_name: str | None, message: str
) -> None:
    from apps.api.seawatch.trajectories.feature_io import read_phase1_parquet

    path = tmp_path / "phase1.parquet"
    _write_phase1(path, crs=crs, timezone_name=timezone_name)

    with pytest.raises(ValueError, match=message):
        read_phase1_parquet(path)


def test_reader_rejects_unexpected_phase1_column(tmp_path: Path) -> None:
    from apps.api.seawatch.trajectories.feature_io import read_phase1_parquet

    path = tmp_path / "phase1.parquet"
    _write_phase1(path, extra_column=True)

    with pytest.raises(ValueError, match="unexpected"):
        read_phase1_parquet(path)


def test_writer_records_provenance_preserves_utc_and_measures_artifact(
    tmp_path: Path,
) -> None:
    from apps.api.seawatch.adapters.noaa_ais import sha256_file
    from apps.api.seawatch.trajectories.feature_io import write_feature_parquet

    path = tmp_path / "features.parquet"
    frame = pd.DataFrame(
        {
            "track_id": ["track-demo"],
            "window_start_utc": [pd.Timestamp("2024-01-01T00:00:00Z")],
            "path_distance_m": [100.0],
        }
    )

    artifact = write_feature_parquet(frame, path, _provenance_metadata())
    schema = pq.read_schema(path)
    decoded = {
        key.decode(): value.decode() for key, value in (schema.metadata or {}).items()
    }
    restored = pq.read_table(path).to_pandas()

    assert artifact.path == path
    assert artifact.row_count == 1
    assert artifact.size_bytes == path.stat().st_size
    assert artifact.sha256 == sha256_file(path)
    assert {key: decoded[key] for key in _provenance_metadata()} == _provenance_metadata()
    assert str(restored["window_start_utc"].dtype).endswith("UTC]")
    assert not path.with_name(path.name + ".partial").exists()


def test_writer_rejects_forbidden_public_identifier(tmp_path: Path) -> None:
    from apps.api.seawatch.trajectories.feature_io import write_feature_parquet

    frame = pd.DataFrame({"track_id": ["track-demo"], "MMSI": ["fixture-source"]})

    with pytest.raises(ValueError, match="forbidden"):
        write_feature_parquet(frame, tmp_path / "features.parquet", _provenance_metadata())


def test_preflight_rejects_final_or_partial_collision_before_writes(
    tmp_path: Path,
) -> None:
    from apps.api.seawatch.trajectories.feature_io import preflight_feature_outputs

    final = tmp_path / "final.parquet"
    partial_target = tmp_path / "other.parquet"
    final.write_bytes(b"keep")
    partial_target.with_name(partial_target.name + ".partial").write_bytes(b"partial")

    with pytest.raises(FileExistsError) as error:
        preflight_feature_outputs([final, partial_target], overwrite=False)

    assert str(final) in str(error.value)
    assert str(partial_target) in str(error.value)
    assert final.read_bytes() == b"keep"


def test_preflight_rejects_duplicate_output_paths_even_with_overwrite(
    tmp_path: Path,
) -> None:
    from apps.api.seawatch.trajectories.feature_io import preflight_feature_outputs

    destination = tmp_path / "shared.parquet"
    with pytest.raises(ValueError, match="duplicate"):
        preflight_feature_outputs([destination, destination], overwrite=True)
    with pytest.raises(ValueError, match="input"):
        preflight_feature_outputs(
            [destination], overwrite=True, reserved_inputs=[destination]
        )
    partial = destination.with_name(destination.name + ".partial")
    with pytest.raises(ValueError, match="input"):
        preflight_feature_outputs(
            [destination], overwrite=True, reserved_inputs=[partial]
        )
    with pytest.raises(ValueError, match="duplicate"):
        preflight_feature_outputs([destination, partial], overwrite=True)


def test_writer_requires_overwrite_and_replaces_stale_partial(tmp_path: Path) -> None:
    from apps.api.seawatch.trajectories.feature_io import write_feature_parquet

    path = tmp_path / "features.parquet"
    path.write_bytes(b"old")
    partial = path.with_name(path.name + ".partial")
    partial.write_bytes(b"partial")
    frame = pd.DataFrame({"track_id": ["track-demo"], "value": [1.0]})

    with pytest.raises(FileExistsError):
        write_feature_parquet(frame, path, _provenance_metadata())
    write_feature_parquet(frame, path, _provenance_metadata(), overwrite=True)

    assert pq.read_table(path).num_rows == 1
    assert not partial.exists()
