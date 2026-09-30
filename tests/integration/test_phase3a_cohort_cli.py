from __future__ import annotations

import json
from pathlib import Path
import sys
import urllib.request

import pytest

from scripts import build_phase3a_cohort


def _inputs(tmp_path: Path) -> tuple[list[Path], list[Path]]:
    phase1 = []
    features = []
    for source_date in ("2024-01-01", "2024-01-02", "2024-01-03"):
        first = tmp_path / f"{source_date}-phase1.json"
        second = tmp_path / f"{source_date}-features.json"
        first.write_text("{}", encoding="utf-8")
        second.write_text("{}", encoding="utf-8")
        phase1.append(first)
        features.append(second)
    return phase1, features


def _argv(
    tmp_path: Path,
    phase1: list[Path],
    features: list[Path],
    *,
    output: Path | None = None,
    report: Path | None = None,
) -> list[str]:
    values = [
        "build_phase3a_cohort.py",
        "--root", str(tmp_path),
        "--catalog", str(Path("config/noaa_ais_phase3a_dates.json").resolve()),
        "--output", str(output or tmp_path / "cohort.json"),
        "--report-output", str(report or tmp_path / "cohort.md"),
    ]
    dates = ("2024-01-01", "2024-01-02", "2024-01-03")
    for source_date, path in zip(dates, phase1, strict=True):
        values.extend(["--phase1-manifest", f"{source_date}={path}"])
    for source_date, path in zip(dates, features, strict=True):
        values.extend(["--feature-manifest", f"{source_date}={path}"])
    return values


def test_cli_writes_aggregate_outputs_atomically_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    phase1, features = _inputs(tmp_path)
    output = tmp_path / "cohort.json"
    report = tmp_path / "cohort.md"
    calls: list[tuple[str, Path, Path]] = []

    def fake_load(entry, phase1_path, feature_path, *, root):
        calls.append((entry.date.isoformat(), phase1_path, feature_path))
        return entry.date.isoformat()

    payload = {
        "schema_version": "phase3a-multiday-v1",
        "dates": ["train", "calibration", "test"],
    }
    monkeypatch.setattr(build_phase3a_cohort, "load_daily_lineage", fake_load)
    monkeypatch.setattr(build_phase3a_cohort, "build_phase3a_manifest", lambda catalog, lineages: payload)
    monkeypatch.setattr(build_phase3a_cohort, "render_phase3a_report", lambda manifest: "measured report\n")
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network forbidden")),
    )
    monkeypatch.setattr(sys, "argv", _argv(tmp_path, phase1, features, output=output, report=report))

    assert build_phase3a_cohort.main() == 0
    assert json.loads(output.read_text(encoding="utf-8")) == payload
    assert report.read_text(encoding="utf-8") == "measured report\n"
    assert [value[0] for value in calls] == ["2024-01-01", "2024-01-02", "2024-01-03"]
    assert not output.with_name(output.name + ".partial").exists()
    assert not report.with_name(report.name + ".partial").exists()


@pytest.mark.parametrize("collision", ["final", "partial", "alias"])
def test_cli_preflights_all_output_collisions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, collision: str
) -> None:
    phase1, features = _inputs(tmp_path)
    output = tmp_path / "cohort.json"
    report = tmp_path / "cohort.md"
    if collision == "final":
        output.write_text("keep", encoding="utf-8")
    elif collision == "partial":
        report.with_name(report.name + ".partial").write_text("keep", encoding="utf-8")
    else:
        output = phase1[0]
    monkeypatch.setattr(sys, "argv", _argv(tmp_path, phase1, features, output=output, report=report))

    with pytest.raises(SystemExit) as error:
        build_phase3a_cohort.main()

    assert error.value.code == 1
    if collision != "alias":
        assert not report.exists()


def test_cli_malformed_daily_json_leaves_no_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    phase1, features = _inputs(tmp_path)
    phase1[2].write_text("not-json", encoding="utf-8")
    output = tmp_path / "cohort.json"
    report = tmp_path / "cohort.md"
    monkeypatch.setattr(sys, "argv", _argv(tmp_path, phase1, features, output=output, report=report))

    with pytest.raises(SystemExit) as error:
        build_phase3a_cohort.main()

    assert error.value.code == 1
    for path in (output, report, output.with_name(output.name + ".partial"), report.with_name(report.name + ".partial")):
        assert not path.exists()
