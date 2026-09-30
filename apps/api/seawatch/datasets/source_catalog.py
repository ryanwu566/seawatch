"""Strict approved-source catalog for the Phase 3A NOAA AIS cohort."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
from typing import Literal, cast
from urllib.parse import urlparse


SplitRole = Literal["train", "calibration", "test"]
CATALOG_SCHEMA_VERSION = "phase3a-source-catalog-v1"
EXPECTED_DATES = (date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3))
EXPECTED_ROLES = ("train", "calibration", "test")
APPROVED_HOST = "ocmgeodatastor1.blob.core.windows.net"


@dataclass(frozen=True)
class ApprovedDailySource:
    date: date
    source_url: str
    raw_filename: str
    split_role: SplitRole


@dataclass(frozen=True)
class Phase3ACatalog:
    schema_version: str
    entries: tuple[ApprovedDailySource, ...]

    def for_date(self, source_date: date) -> ApprovedDailySource:
        for entry in self.entries:
            if entry.date == source_date:
                return entry
        raise ValueError(f"NOAA AIS date {source_date.isoformat()} is not approved")


def _parse_entry(payload: object, index: int) -> ApprovedDailySource:
    if not isinstance(payload, dict):
        raise ValueError(f"catalog entry {index} must be an object")
    expected = {"date", "source_url", "raw_filename", "split_role"}
    actual = set(payload)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing:
        raise ValueError(f"catalog entry {index} missing keys: {', '.join(missing)}")
    if unknown:
        raise ValueError(f"catalog entry {index} has unknown keys: {', '.join(unknown)}")
    try:
        source_date = date.fromisoformat(str(payload["date"]))
    except ValueError as error:
        raise ValueError(f"catalog entry {index} has invalid date") from error
    source_url = str(payload["source_url"])
    raw_filename = str(payload["raw_filename"])
    split_role = str(payload["split_role"])
    if split_role not in EXPECTED_ROLES:
        raise ValueError(f"catalog entry {index} has invalid split role")
    parsed = urlparse(source_url)
    if parsed.scheme != "https":
        raise ValueError(f"catalog entry {index} source URL must use HTTPS")
    if parsed.hostname != APPROVED_HOST:
        raise ValueError(f"catalog entry {index} source URL has unapproved host")
    expected_filename = f"ais-{source_date.isoformat()}.parquet"
    expected_path = f"/marinecadastre/ais2024/{expected_filename}"
    if parsed.path != expected_path or parsed.params or parsed.query or parsed.fragment:
        raise ValueError(f"catalog entry {index} source URL does not match its date")
    if raw_filename != expected_filename:
        raise ValueError(f"catalog entry {index} raw filename does not match its date")
    return ApprovedDailySource(
        date=source_date,
        source_url=source_url,
        raw_filename=raw_filename,
        split_role=cast(SplitRole, split_role),
    )


def load_phase3a_catalog(path: Path) -> Phase3ACatalog:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("source catalog must be a JSON object")
    expected = {"schema_version", "entries"}
    actual = set(payload)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing:
        raise ValueError(f"source catalog missing keys: {', '.join(missing)}")
    if unknown:
        raise ValueError(f"source catalog has unknown keys: {', '.join(unknown)}")
    if payload["schema_version"] != CATALOG_SCHEMA_VERSION:
        raise ValueError("source catalog schema_version is not supported")
    raw_entries = payload["entries"]
    if not isinstance(raw_entries, list) or len(raw_entries) != 3:
        raise ValueError("source catalog must contain exactly three entries")
    entries = tuple(_parse_entry(value, index) for index, value in enumerate(raw_entries))
    dates = tuple(entry.date for entry in entries)
    if len(set(dates)) != len(dates):
        raise ValueError("source catalog contains a duplicate date")
    roles = tuple(entry.split_role for entry in entries)
    if roles != EXPECTED_ROLES:
        raise ValueError("source catalog roles must be train, calibration, test")
    if dates != EXPECTED_DATES:
        raise ValueError("source catalog dates must be exactly 2024-01-01 through 2024-01-03")
    return Phase3ACatalog(schema_version=CATALOG_SCHEMA_VERSION, entries=entries)
