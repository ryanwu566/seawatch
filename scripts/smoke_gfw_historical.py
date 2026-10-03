"""Read-only operational smoke test for local GFW historical baselines.

The script resolves input only through ``SEAWATCH_DATA_ROOT`` and identity only
through the existing live configuration. It emits aggregate diagnostics; no
vessel identifier, source identifier, or configured identity secret is logged.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
import os
from pathlib import Path
import sys
from time import perf_counter
from typing import TextIO


# Direct ``python scripts/...`` execution places ``scripts`` on sys.path. Add
# the repository root so the existing ``apps`` package is importable.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from apps.api.seawatch.historical.pipeline import (  # noqa: E402
    HistoricalBaselinePrivacyError,
    HistoricalIdentityUnavailableError,
    assert_public_baselines_private,
    run_gfw_historical_pipeline,
)


def main(
    *,
    environ: Mapping[str, str] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    clock: Callable[[], float] = perf_counter,
) -> int:
    """Run the read-only smoke test and return a process-style exit code."""

    output = sys.stdout if stdout is None else stdout
    errors = sys.stderr if stderr is None else stderr
    values = os.environ if environ is None else environ
    started = clock()

    try:
        result = run_gfw_historical_pipeline(environ=values)
        # Defense in depth at the operational boundary. The pipeline performs
        # the stronger audit while raw source identifiers are still in memory.
        assert_public_baselines_private(result.baselines)
    except HistoricalBaselinePrivacyError:
        print(
            "ERROR: historical baseline privacy audit failed",
            file=errors,
        )
        return 2
    except HistoricalIdentityUnavailableError as exc:
        print(f"ERROR: {exc}", file=errors)
        return 2
    except (
        FileNotFoundError,
        NotADirectoryError,
        OSError,
        ValueError,
        RuntimeError,
    ) as exc:
        print(f"ERROR: {exc}", file=errors)
        return 1

    elapsed_seconds = max(0.0, clock() - started)
    diagnostics = result.diagnostics
    aggregate_rows = (
        (
            "discovered_parquet_file_count",
            diagnostics.discovered_parquet_file_count,
        ),
        ("observations_considered", diagnostics.observations_considered),
        (
            "observations_joinable_by_valid_mmsi",
            diagnostics.observations_joinable_by_valid_mmsi,
        ),
        (
            "observations_excluded_from_live_identity_join",
            diagnostics.observations_excluded_from_live_identity_join,
        ),
        ("grouped_vessel_count", diagnostics.grouped_vessel_count),
        ("vessel_baseline_count", diagnostics.vessel_baseline_count),
        ("sufficient_baseline_count", diagnostics.sufficient_baseline_count),
        (
            "insufficient_baseline_count",
            diagnostics.insufficient_baseline_count,
        ),
    )
    for label, value in aggregate_rows:
        print(f"{label}: {value}", file=output)
    print(f"elapsed_runtime_seconds: {elapsed_seconds:.3f}", file=output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
