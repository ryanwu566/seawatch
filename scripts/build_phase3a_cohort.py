"""Build the offline three-date Phase 3A AIS cohort manifest and QA report."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.api.seawatch.datasets.multiday_manifest import (
    build_phase3a_manifest,
    load_daily_lineage,
    render_phase3a_report,
)
from apps.api.seawatch.datasets.source_catalog import load_phase3a_catalog


DEFAULT_CATALOG = Path("config/noaa_ais_phase3a_dates.json")
DEFAULT_OUTPUT = Path(
    "data/manifests/noaa_ais_2024-01-01_to_2024-01-03_sf_bay_phase3a.json"
)
DEFAULT_REPORT = Path("docs/phase3a-data-expansion-report.md")


def _rooted(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def _parse_assignments(
    values: list[str] | None,
    *,
    root: Path,
    suffix: str,
    approved_dates: tuple[date, ...],
) -> dict[date, Path]:
    if values is None:
        return {
            source_date: root
            / "data"
            / "manifests"
            / f"noaa_ais_{source_date.isoformat()}_sf_bay{suffix}.json"
            for source_date in approved_dates
        }
    result: dict[date, Path] = {}
    for value in values:
        raw_date, separator, raw_path = value.partition("=")
        if not separator or not raw_path:
            raise ValueError("manifest arguments must use YYYY-MM-DD=PATH")
        try:
            source_date = date.fromisoformat(raw_date)
        except ValueError as error:
            raise ValueError(f"invalid manifest date: {raw_date}") from error
        if source_date not in approved_dates:
            raise ValueError(f"manifest date is not approved: {source_date}")
        if source_date in result:
            raise ValueError(f"duplicate manifest date: {source_date}")
        result[source_date] = _rooted(root, Path(raw_path))
    if tuple(sorted(result)) != approved_dates:
        raise ValueError("manifest arguments must include all three approved dates")
    return result


def preflight_cohort_outputs(
    outputs: tuple[Path, Path], *, inputs: tuple[Path, ...], overwrite: bool
) -> None:
    write_paths = tuple(
        candidate
        for output in outputs
        for candidate in (output, output.with_name(output.name + ".partial"))
    )
    resolved = [str(path.resolve()).casefold() for path in write_paths]
    if len(resolved) != len(set(resolved)):
        raise ValueError("duplicate cohort output or partial paths are not allowed")
    input_paths = {str(path.resolve()).casefold() for path in inputs}
    if input_paths.intersection(resolved):
        raise ValueError("cohort output path aliases an input path")
    if not overwrite:
        collisions = [path for path in write_paths if path.exists()]
        if collisions:
            raise FileExistsError(
                "cohort output destination already exists: "
                + ", ".join(str(path) for path in collisions)
            )


def _write_outputs(
    output: Path,
    report_output: Path,
    payload: str,
    report: str,
    *,
    overwrite: bool,
) -> None:
    partials = (
        output.with_name(output.name + ".partial"),
        report_output.with_name(report_output.name + ".partial"),
    )
    for partial in partials:
        if partial.exists():
            if not overwrite:
                raise FileExistsError(f"partial output already exists: {partial}")
            partial.unlink()
    output.parent.mkdir(parents=True, exist_ok=True)
    report_output.parent.mkdir(parents=True, exist_ok=True)
    partials[0].write_text(payload, encoding="utf-8")
    partials[1].write_text(report, encoding="utf-8")
    partials[0].replace(output)
    partials[1].replace(report_output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--phase1-manifest", action="append")
    parser.add_argument("--feature-manifest", action="append")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report-output", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    output = _rooted(root, args.output or DEFAULT_OUTPUT)
    report_output = _rooted(root, args.report_output or DEFAULT_REPORT)
    partials = (
        output.with_name(output.name + ".partial"),
        report_output.with_name(report_output.name + ".partial"),
    )
    try:
        catalog_path = _rooted(root, args.catalog)
        catalog = load_phase3a_catalog(catalog_path)
        approved_dates = tuple(entry.date for entry in catalog.entries)
        phase1_paths = _parse_assignments(
            args.phase1_manifest,
            root=root,
            suffix="",
            approved_dates=approved_dates,
        )
        feature_paths = _parse_assignments(
            args.feature_manifest,
            root=root,
            suffix="_trajectory_features",
            approved_dates=approved_dates,
        )
        inputs = (
            catalog_path,
            *tuple(phase1_paths.values()),
            *tuple(feature_paths.values()),
        )
        preflight_cohort_outputs(
            (output, report_output), inputs=inputs, overwrite=args.force
        )
        lineages = [
            load_daily_lineage(
                entry,
                phase1_paths[entry.date],
                feature_paths[entry.date],
                root=root,
            )
            for entry in catalog.entries
        ]
        manifest = build_phase3a_manifest(catalog, lineages)
        payload = json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n"
        report = render_phase3a_report(manifest)
        _write_outputs(
            output,
            report_output,
            payload,
            report,
            overwrite=args.force,
        )
    except (FileExistsError, OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as error:
        for partial in partials:
            if partial.exists():
                partial.unlink()
        parser.exit(1, f"error: {error}\n")

    print(f"cohort manifest: {output}")
    print(f"cohort report: {report_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
