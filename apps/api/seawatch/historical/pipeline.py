"""Minimal orchestration for locally downloaded GFW historical presence data.

The pipeline reads daily Parquet files from
``<SEAWATCH_DATA_ROOT>/ais/historical/processed/daily``. Reading local data
does not require or inspect ``GFW_TOKEN``.

Only observations with a valid MMSI can enter a live-joinable per-vessel
baseline. Identity derivation uses either the process's existing
``VesselIdentityRegistry`` or a registry constructed from the same
``SEAWATCH_IDENTITY_KEY`` parsed by ``LiveRuntimeConfig``. If neither is
available, processing fails closed.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import os
from pathlib import Path
import re
from typing import Any

from ..live.config import LiveRuntimeConfig
from ..live.identity import VesselIdentityRegistry
from ..trajectories.contracts import FeatureConfig
from .adapter import GfwPresenceParquetAdapter
from .baseline import build_vessel_baseline
from .schema import HistoricalAisRecord, VesselBaseline


_DATA_ROOT_ENV = "SEAWATCH_DATA_ROOT"
_GFW_DAILY_RELATIVE_PATH = Path("ais") / "historical" / "processed" / "daily"


class HistoricalIdentityUnavailableError(RuntimeError):
    """Raised when historical records cannot share the live identity key."""


class HistoricalBaselinePrivacyError(RuntimeError):
    """Raised without sensitive detail when a public baseline leaks identity."""


@dataclass(frozen=True)
class GfwHistoricalPipelineDiagnostics:
    discovered_parquet_file_count: int
    observations_considered: int
    observations_joinable_by_valid_mmsi: int
    observations_excluded_from_live_identity_join: int
    grouped_vessel_count: int
    vessel_baseline_count: int
    sufficient_baseline_count: int
    insufficient_baseline_count: int


@dataclass(frozen=True)
class GfwHistoricalPipelineResult:
    baselines: dict[str, VesselBaseline]
    diagnostics: GfwHistoricalPipelineDiagnostics


_FORBIDDEN_IDENTIFIER_KEYS = frozenset(
    {
        "mmsi",
        "imo",
        "callsign",
        "shipname",
        "vesselname",
        "vesselid",
        "sourcevesselid",
        "sourceid",
        "name",
    }
)


def _normalized_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def _raise_privacy_error() -> None:
    raise HistoricalBaselinePrivacyError(
        "Serialized historical baseline failed the forbidden-identifier privacy audit"
    )


def _audit_serialized_value(
    value: object,
    *,
    raw_identifiers: frozenset[str],
) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if _normalized_key(key) in _FORBIDDEN_IDENTIFIER_KEYS:
                _raise_privacy_error()
            _audit_serialized_value(nested, raw_identifiers=raw_identifiers)
        return

    if isinstance(value, (list, tuple)):
        for nested in value:
            _audit_serialized_value(nested, raw_identifiers=raw_identifiers)
        return

    if isinstance(value, str):
        if value in raw_identifiers:
            _raise_privacy_error()
        for identifier in raw_identifiers:
            if len(identifier) >= 8 and identifier in value:
                _raise_privacy_error()


def assert_public_baselines_private(
    baselines: Mapping[str, Any],
    *,
    raw_identifiers: Iterable[str] = (),
) -> None:
    """Fail closed if serialized baselines contain direct source identities.

    The raised error is intentionally generic and never includes the leaked
    key or value. Raw identifiers exist only in this in-memory audit call.
    """

    audit_values = frozenset(
        str(identifier)
        for identifier in raw_identifiers
        if str(identifier)
    )
    for baseline in baselines.values():
        _audit_serialized_value(
            baseline.to_dict(),
            raw_identifiers=audit_values,
        )


def resolve_gfw_parquet_dir(
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Resolve the local GFW daily directory without a drive-letter default."""

    values = os.environ if environ is None else environ
    root_text = values.get(_DATA_ROOT_ENV, "").strip()
    if not root_text:
        raise ValueError(
            "SEAWATCH_DATA_ROOT is required for local GFW historical data"
        )
    return Path(root_text).expanduser() / _GFW_DAILY_RELATIVE_PATH


def _configured_identity_registry(
    environ: Mapping[str, str] | None,
) -> VesselIdentityRegistry:
    config = LiveRuntimeConfig.from_env(environ)
    if config.identity_key is None:
        raise HistoricalIdentityUnavailableError(
            "SEAWATCH_IDENTITY_KEY is required when the live identity registry "
            "is not supplied; historical/live identity matching failed closed"
        )
    return VesselIdentityRegistry(config.identity_key)


def run_gfw_historical_pipeline(
    *,
    environ: Mapping[str, str] | None = None,
    identity_registry: VesselIdentityRegistry | None = None,
    feature_config: FeatureConfig | None = None,
) -> GfwHistoricalPipelineResult:
    """Build baselines and aggregate diagnostics without exposing identities.

    Rows without a valid MMSI remain unjoinable and are omitted from this
    per-vessel result. They may still support a future aggregate traffic layer,
    but this function never invents an identity for them.
    """

    registry = identity_registry or _configured_identity_registry(environ)
    adapter = GfwPresenceParquetAdapter(resolve_gfw_parquet_dir(environ))
    parquet_files = adapter.discover_files()

    grouped: dict[str, list[HistoricalAisRecord]] = {}
    raw_identifiers: set[str] = set()
    observations_considered = 0
    observations_joinable = 0
    for record in adapter.load_tracks():
        observations_considered += 1
        raw_identifiers.add(record.vessel_id)
        vessel_key = registry.public_id_for_mmsi(record.mmsi)
        if vessel_key is None:
            continue
        observations_joinable += 1
        raw_identifiers.add(str(record.mmsi))
        grouped.setdefault(vessel_key, []).append(record)

    baselines = {
        vessel_key: build_vessel_baseline(
            vessel_key,
            grouped[vessel_key],
            feature_config=feature_config,
        )
        for vessel_key in sorted(grouped)
    }
    assert_public_baselines_private(
        baselines,
        raw_identifiers=raw_identifiers,
    )

    sufficient_count = sum(
        1 for baseline in baselines.values() if baseline.sufficient
    )
    baseline_count = len(baselines)
    return GfwHistoricalPipelineResult(
        baselines=baselines,
        diagnostics=GfwHistoricalPipelineDiagnostics(
            discovered_parquet_file_count=len(parquet_files),
            observations_considered=observations_considered,
            observations_joinable_by_valid_mmsi=observations_joinable,
            observations_excluded_from_live_identity_join=(
                observations_considered - observations_joinable
            ),
            grouped_vessel_count=len(grouped),
            vessel_baseline_count=baseline_count,
            sufficient_baseline_count=sufficient_count,
            insufficient_baseline_count=baseline_count - sufficient_count,
        ),
    )


def build_gfw_baselines(
    *,
    environ: Mapping[str, str] | None = None,
    identity_registry: VesselIdentityRegistry | None = None,
    feature_config: FeatureConfig | None = None,
) -> dict[str, VesselBaseline]:
    """Preserve the original opaque-ID-to-baseline mapping API."""

    return run_gfw_historical_pipeline(
        environ=environ,
        identity_registry=identity_registry,
        feature_config=feature_config,
    ).baselines
