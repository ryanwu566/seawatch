"""Atomic local artifact IO."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


def preflight_phase3b_outputs(outputs: Iterable[Path], *, inputs: Iterable[Path], overwrite: bool) -> None:
    outputs = tuple(Path(value) for value in outputs)
    candidates = tuple(item for path in outputs for item in (path, path.with_name(path.name + ".partial")))
    resolved = [str(path.resolve()).casefold() for path in candidates]
    if len(resolved) != len(set(resolved)):
        raise ValueError("duplicate Phase 3B output paths")
    inputs_resolved = {str(Path(path).resolve()).casefold() for path in inputs}
    if inputs_resolved.intersection(resolved):
        raise ValueError("Phase 3B output aliases an input")
    if not overwrite and any(path.exists() for path in candidates):
        raise FileExistsError("Phase 3B output already exists")


def write_json_atomic(payload: Mapping[str, object], path: Path, *, overwrite: bool = False) -> None:
    path = Path(path)
    partial = path.with_name(path.name + ".partial")
    preflight_phase3b_outputs([path], inputs=[], overwrite=overwrite)
    if partial.exists():
        partial.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    partial.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    partial.replace(path)


def write_rankings(frame: pd.DataFrame, path: Path, provenance: Mapping[str, str], *, overwrite: bool = False) -> None:
    forbidden = {"mmsi", "imo", "name", "callsign"}.intersection(str(name).casefold() for name in frame.columns)
    if forbidden:
        raise ValueError(f"ranking contains forbidden identifiers: {sorted(forbidden)}")
    path = Path(path)
    partial = path.with_name(path.name + ".partial")
    preflight_phase3b_outputs([path], inputs=[], overwrite=overwrite)
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(frame, preserve_index=False)
    metadata = dict(table.schema.metadata or {})
    metadata[b"seawatch_schema_version"] = b"phase3b-review-ranking-v1"
    metadata.update({f"seawatch_{key}".encode(): str(value).encode() for key, value in provenance.items()})
    pq.write_table(table.replace_schema_metadata(metadata), partial)
    partial.replace(path)
