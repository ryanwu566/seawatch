"""Role-gated Phase 3A cohort loading."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from apps.api.seawatch.trajectories.features import FEATURE_COLUMNS

from .contracts import SplitWindows


_ROLES = {"train": "2024-01-01", "calibration": "2024-01-02", "test": "2024-01-03"}
_FORBIDDEN = {"mmsi", "imo", "name", "callsign"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_split_windows(cohort_manifest_path: Path, requested_roles: tuple[str, ...], *, root: Path) -> dict[str, SplitWindows]:
    if not requested_roles or len(requested_roles) != len(set(requested_roles)) or not set(requested_roles).issubset(_ROLES):
        raise ValueError("unknown or duplicate requested split role")
    payload = json.loads(Path(cohort_manifest_path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != "phase3a-multiday-v1" or not isinstance(payload.get("dates"), list):
        raise ValueError("invalid Phase 3A cohort manifest")
    contract = payload.get("shared_contract")
    expected_contract = {
        "crs": "EPSG:4326",
        "timezone": "UTC",
        "observed_license": "CC0 1.0 Universal",
        "feature_schema_version": "trajectory-features-v1",
        "feature_config_sha256": "70aa8dd26c6f438c5122b48a497aad426fc5e4661829ff54611a266048f92a02",
    }
    if not isinstance(contract, dict) or any(contract.get(key) != value for key, value in expected_contract.items()):
        raise ValueError("Phase 3A cohort contract differs from the approved CRS, timezone, license, schema, or feature configuration")
    if "feature_columns" in contract and tuple(contract["feature_columns"]) != FEATURE_COLUMNS:
        raise ValueError("Phase 3A cohort contract feature schema differs")
    if payload.get("comparability", {}).get("passed") is not True:
        raise ValueError("Phase 3A cohort comparability checks did not pass")
    records = {str(item.get("split_role")): item for item in payload["dates"] if str(item.get("split_role")) in requested_roles}
    if set(records) != set(requested_roles):
        raise ValueError("requested split role is missing from cohort")
    output: dict[str, SplitWindows] = {}
    for role in requested_roles:
        record = records[role]
        if record.get("source_date") != _ROLES[role]:
            raise ValueError(f"{role} date mismatch")
        artifact = record.get("feature_artifacts", {}).get("windows", {})
        path = Path(str(artifact.get("path")))
        path = path if path.is_absolute() else Path(root) / path
        if not path.is_file() or path.stat().st_size != int(artifact.get("size_bytes", -1)) or _sha256(path) != artifact.get("sha256"):
            raise ValueError(f"{role} artifact provenance mismatch")
        frame = pd.read_parquet(path)
        if len(frame) != int(artifact.get("row_count", -1)) or "window_quality_status" not in frame:
            raise ValueError(f"{role} artifact row/schema mismatch")
        exposed = _FORBIDDEN.intersection(str(name).casefold() for name in frame.columns)
        if exposed:
            raise ValueError(f"forbidden public columns: {sorted(exposed)}")
        utc_columns = [name for name in frame if str(name).endswith("_utc")]
        for name in utc_columns:
            values = pd.to_datetime(frame[name], errors="raise")
            if values.dt.tz is None or str(values.dt.tz) != "UTC":
                raise ValueError(f"{name} must be UTC")
        accepted = frame["window_quality_status"].eq("sufficient")
        output[role] = SplitWindows(pd.Timestamp(_ROLES[role]).date(), role, path, str(artifact["sha256"]), frame.loc[accepted].reset_index(drop=True), int((~accepted).sum()))
    return output
