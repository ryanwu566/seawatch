from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pandas as pd

from apps.api.seawatch.review_ranking.data import load_split_windows
from apps.api.seawatch.review_ranking.io import preflight_phase3b_outputs, write_json_atomic, write_rankings


def test_role_gated_loader_does_not_open_held_out_artifact(monkeypatch, tmp_path: Path) -> None:
    frames = {}
    dates = (("2024-01-01", "train"), ("2024-01-02", "calibration"), ("2024-01-03", "test"))
    records = []
    for day, role in dates:
        path = tmp_path / f"{role}.parquet"
        frame = pd.DataFrame({
            "window_quality_status": ["sufficient", "insufficient_observations"],
            "window_start_utc": pd.to_datetime([f"{day}T00:00:00Z", f"{day}T00:05:00Z"], utc=True),
            "track_id": ["t", "t"], "window_id": ["w1", "w2"],
        })
        frame.to_parquet(path, index=False)
        import hashlib
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        records.append({"source_date": day, "split_role": role, "feature_artifacts": {"windows": {"path": path.name, "sha256": digest, "size_bytes": path.stat().st_size, "row_count": 2}}})
    manifest = tmp_path / "cohort.json"
    contract = {"crs": "EPSG:4326", "timezone": "UTC", "observed_license": "CC0 1.0 Universal", "feature_schema_version": "trajectory-features-v1", "feature_config_sha256": "70aa8dd26c6f438c5122b48a497aad426fc5e4661829ff54611a266048f92a02"}
    manifest.write_text(json.dumps({"schema_version": "phase3a-multiday-v1", "comparability": {"passed": True}, "shared_contract": contract, "dates": records}), encoding="utf-8")
    original = pd.read_parquet
    opened = []
    def spy(path, *args, **kwargs):
        opened.append(Path(path).name)
        if Path(path).name == "test.parquet":
            raise AssertionError("held-out artifact opened")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(pd, "read_parquet", spy)
    loaded = load_split_windows(manifest, ("train", "calibration"), root=tmp_path)
    assert set(loaded) == {"train", "calibration"}
    assert "test.parquet" not in opened
    assert loaded["train"].rejected_count == 1

    payload = json.loads(manifest.read_text())
    payload["shared_contract"]["crs"] = "EPSG:3857"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    import pytest
    with pytest.raises(ValueError, match="cohort contract"):
        load_split_windows(manifest, ("train",), root=tmp_path)


def test_atomic_json_preflight_and_cli_help(tmp_path: Path) -> None:
    output = tmp_path / "result.json"
    preflight_phase3b_outputs([output], inputs=[], overwrite=False)
    write_json_atomic({"schema_version": "test"}, output)
    assert json.loads(output.read_text())["schema_version"] == "test"
    completed = subprocess.run([sys.executable, "scripts/run_phase3b_review_ranking.py", "--help"], text=True, capture_output=True)
    assert completed.returncode == 0
    assert "{select-features,calibrate,evaluate,report}" in completed.stdout


def test_ranking_parquet_records_provenance(tmp_path: Path) -> None:
    import pyarrow.parquet as pq
    path = tmp_path / "ranking.parquet"
    write_rankings(pd.DataFrame({"review_priority_score": [42.0]}), path, {"config_sha256": "abc"})
    metadata = {key.decode(): value.decode() for key, value in pq.read_schema(path).metadata.items()}
    assert metadata["seawatch_schema_version"] == "phase3b-review-ranking-v1"
    assert metadata["seawatch_config_sha256"] == "abc"
