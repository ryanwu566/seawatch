from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest


def _write_source(path: Path) -> None:
    start = pd.Timestamp("2024-01-01T00:00:00Z")
    first = [start + pd.Timedelta(minutes=3 * index) for index in range(11)]
    second_start = first[-1] + pd.Timedelta(seconds=601)
    second = [second_start + pd.Timedelta(minutes=3 * index) for index in range(11)]
    timestamps = first + second
    frame = pd.DataFrame(
        {
            "track_id": ["track-fixture"] * len(timestamps),
            "base_date_time": timestamps,
            "longitude": [-122.4 + 0.001 * index for index in range(len(timestamps))],
            "latitude": [37.8] * len(timestamps),
            "sog": [5.0] * len(timestamps),
            "cog": [90.0] * len(timestamps),
            "heading": [90.0] * len(timestamps),
            "vessel_type": [70] * len(timestamps),
        }
    )
    table = pa.Table.from_pandas(frame, preserve_index=False)
    metadata = dict(table.schema.metadata or {})
    metadata[b"seawatch_crs"] = b"EPSG:4326"
    metadata[b"seawatch_timezone"] = b"UTC"
    pq.write_table(table.replace_schema_metadata(metadata), path)


def _cli_module():
    from scripts import prepare_trajectory_features

    return prepare_trajectory_features


def _paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "source": tmp_path / "phase1.parquet",
        "source_manifest": tmp_path / "phase1-manifest.json",
        "segmented": tmp_path / "segmented.parquet",
        "segments": tmp_path / "segments.parquet",
        "windows": tmp_path / "windows.parquet",
        "manifest": tmp_path / "features-manifest.json",
        "report": tmp_path / "report.md",
    }


def _argv(paths: dict[str, Path], *, config: Path | None = None) -> list[str]:
    return [
        "prepare_trajectory_features.py",
        "--source", str(paths["source"]),
        "--source-manifest", str(paths["source_manifest"]),
        "--config", str(config or Path("config/trajectory_features_v1.json")),
        "--segmented-output", str(paths["segmented"]),
        "--segments-output", str(paths["segments"]),
        "--windows-output", str(paths["windows"]),
        "--manifest-output", str(paths["manifest"]),
        "--report-output", str(paths["report"]),
    ]


def _prepare_inputs(paths: dict[str, Path]) -> None:
    _write_source(paths["source"])
    paths["source_manifest"].write_text(
        json.dumps(
            {
                "dataset_id": "synthetic-phase1",
                "source_date": "2024-01-01",
                "output_rows": 22,
                "notes": ["synthetic fixture"],
            }
        ),
        encoding="utf-8",
    )


def test_cli_builds_three_consistent_private_safe_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    _prepare_inputs(paths)
    monkeypatch.setattr(sys, "argv", _argv(paths))

    assert _cli_module().main() == 0

    segmented = pq.read_table(paths["segmented"]).to_pandas()
    segments = pq.read_table(paths["segments"]).to_pandas()
    windows = pq.read_table(paths["windows"]).to_pandas()
    manifest_text = paths["manifest"].read_text(encoding="utf-8")
    report_text = paths["report"].read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)

    assert len(segmented) == 22
    assert len(segments) == 2
    assert len(windows) == 2
    assert windows["window_quality_status"].tolist() == ["sufficient", "sufficient"]
    assert (windows["window_start_utc"] >= windows["first_observation_utc"]).all()
    assert (windows["last_observation_utc"] < windows["window_end_utc"]).all()
    assert manifest["input_rows"] == 22
    assert manifest["segment_count"] == len(segments)
    assert manifest["candidate_window_count"] == len(windows)
    assert manifest["accepted_window_count"] == 2
    assert manifest["rejected_window_count"] == 0
    assert manifest["artifacts"]["windows"]["row_count"] == len(windows)
    assert "Candidate windows | 2" in report_text
    assert "Accepted windows | 2" in report_text
    assert "Planning estimate reconciliation" in report_text
    assert "does not apply to source dataset `synthetic-phase1`" in report_text
    public_aggregate_text = (manifest_text + report_text).casefold()
    for forbidden in (
        "mmsi",
        "vessel_name",
        '"imo"',
        "call_sign",
        "track-fixture",
    ):
        assert forbidden not in public_aggregate_text


def test_cli_preflights_every_output_before_reading_or_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    paths["manifest"].write_text("committed report", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", _argv(paths))

    with pytest.raises(SystemExit) as error:
        _cli_module().main()

    assert error.value.code == 1
    assert paths["manifest"].read_text(encoding="utf-8") == "committed report"
    for name in ("segmented", "segments", "windows", "report"):
        assert not paths[name].exists()


def test_cli_reports_zero_window_tracks_and_formats_empty_feature_rates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    _prepare_inputs(paths)
    table = pq.read_table(paths["source"]).slice(0, 1)
    pq.write_table(table, paths["source"])
    monkeypatch.setattr(sys, "argv", _argv(paths))

    assert _cli_module().main() == 0

    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    report = paths["report"].read_text(encoding="utf-8")
    assert manifest["candidate_window_count"] == 0
    assert manifest["distributions"]["windows_per_track"]["count"] == 1
    assert manifest["distributions"]["windows_per_track"]["minimum"] == 0.0
    assert manifest["distributions"]["windows_per_segment"]["count"] == 1
    assert manifest["distributions"]["windows_per_segment"]["minimum"] == 0.0
    assert "not measured" in report


def test_cli_help_exits_without_artifacts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["prepare_trajectory_features.py", "--help"])

    with pytest.raises(SystemExit) as error:
        _cli_module().main()

    assert error.value.code == 0


def test_cli_invalid_config_fails_before_artifact_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    _prepare_inputs(paths)
    invalid_config = tmp_path / "invalid.json"
    invalid_config.write_text('{"window_duration_seconds": 0}', encoding="utf-8")
    monkeypatch.setattr(sys, "argv", _argv(paths, config=invalid_config))

    with pytest.raises(SystemExit) as error:
        _cli_module().main()

    assert error.value.code == 1
    for name in ("segmented", "segments", "windows", "manifest", "report"):
        assert not paths[name].exists()
