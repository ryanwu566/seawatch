"""Route Deviation demo runner (backend-only, no ML, no UI).

Produces a full ``route-deviation-1`` Evidence JSON for three scenarios so the
feature can be shown end-to-end:

  A. Normal route           → small deviation, within the historical corridor.
  B. Route deviation         → large derived deviation off the corridor.
  C. Insufficient baseline   → Unknown (baseline never fabricated).

Data source precedence (honest, labelled in the output ``data_source`` field):

  1. ``--segmented PATH`` or the default prepared NOAA segmented Parquet, if it
     exists. Historical corridor tracks and the "normal"/"deviation" probes are
     derived from the real prepared pipeline output.
  2. Otherwise, a committed deterministic SYNTHETIC corridor fixture, so the demo
     always runs offline without requiring the (gitignored) bulk AIS download.

This script reuses ``trajectories/route_deviation.py`` and the existing Phase 1
Parquet reader. It touches no frontend, live/edge/resilience, or logistics code,
and adds no model.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.api.seawatch.trajectories.route_deviation import (  # noqa: E402
    Point,
    build_route_baseline,
    compute_route_deviation,
)

DEFAULT_SEGMENTED = Path(
    "data/processed/features/noaa_ais_2024-01-01_sf_bay_segmented.parquet"
)

ROUTE_KEY = "demo_corridor:west->east"


# --------------------------------------------------------------------------- #
# Synthetic corridor fixture (deterministic; used only when no prepared Parquet)
# --------------------------------------------------------------------------- #


def _straight(lon0: float, lat: float, lon1: float, n: int = 24) -> list[Point]:
    return [(lon0 + (lon1 - lon0) * i / (n - 1), lat) for i in range(n)]


def synthetic_corridor() -> dict:
    """A reproducible west→east corridor with tiny lateral jitter.

    Returns historical tracks (enough for a baseline), an on-corridor probe, a
    clearly-deviating probe, and a too-small history for the Unknown case.
    """

    base_lat = 22.6  # near Kaohsiung approaches (public civilian waters)
    history = [
        _straight(120.0, base_lat + (0.0006 if k % 2 == 0 else -0.0006), 121.2)
        for k in range(12)
    ]
    normal = _straight(120.0, base_lat, 121.2)
    deviating = _straight(120.0, base_lat + 0.12, 121.2)  # ~13 km north detour
    sparse_history = history[:2]  # below MIN_BASELINE_TRACKS
    return {
        "history": history,
        "normal": normal,
        "deviating": deviating,
        "sparse_history": sparse_history,
    }


# --------------------------------------------------------------------------- #
# Prepared NOAA tracks (used when the segmented Parquet exists)
# --------------------------------------------------------------------------- #


def _tracks_from_segmented(path: Path) -> list[tuple[str, list[Point]]]:
    """Load per-segment ordered (lon, lat) tracks from prepared Parquet.

    The segmented artifact carries extra pipeline columns (``segment_id`` etc.)
    beyond the strict Phase 1 public schema, so it is read directly with pandas
    and only the public positional columns are used. Returns tracks sorted by id
    for determinism. No identity columns are read.
    """

    import pandas as pd

    frame = pd.read_parquet(path)
    needed = {"base_date_time", "longitude", "latitude"}
    missing = sorted(needed.difference(frame.columns))
    if missing:
        raise ValueError(f"segmented Parquet missing columns: {', '.join(missing)}")
    key = "segment_id" if "segment_id" in frame.columns else "track_id"
    if key not in frame.columns:
        raise ValueError("segmented Parquet has no segment_id/track_id column")
    frame = frame.sort_values([key, "base_date_time"], kind="mergesort")
    tracks: list[tuple[str, list[Point]]] = []
    for seg_id, seg in frame.groupby(key, sort=True):
        pts = [
            (float(lon), float(lat))
            for lon, lat in zip(seg["longitude"], seg["latitude"], strict=True)
        ]
        if len(pts) >= 2:
            tracks.append((str(seg_id), pts))
    return tracks


def prepared_corridor(path: Path) -> dict | None:
    """Build demo inputs from prepared NOAA tracks, or None if unusable.

    The longest track is used as the "normal" probe and also contributes to the
    historical corridor; a laterally-shifted copy of it provides a deterministic
    "deviating" probe (a reproducible synthetic offset of real geometry, clearly
    labelled as such). Returns None when there are too few tracks to be useful.
    """

    tracks = _tracks_from_segmented(path)
    if len(tracks) < 6:
        return None
    tracks.sort(key=lambda item: len(item[1]), reverse=True)
    probe_id, normal = tracks[0]
    history = [pts for _, pts in tracks[: max(6, len(tracks))]]
    # Deterministic lateral offset (~0.1° latitude ≈ 11 km) of the real probe.
    deviating = [(lon, lat + 0.1) for lon, lat in normal]
    return {
        "history": history,
        "normal": normal,
        "deviating": deviating,
        "sparse_history": history[:2],
        "probe_id": probe_id,
    }


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #


def run_demo(segmented: Path | None = None) -> dict:
    """Produce the three-scenario demo payload. Pure/deterministic."""

    source_path = segmented or DEFAULT_SEGMENTED
    corridor = None
    data_source = "synthetic_demo_corridor"
    if source_path.exists():
        corridor = prepared_corridor(source_path)
        if corridor is not None:
            data_source = "prepared_noaa_segmented"
    if corridor is None:
        corridor = synthetic_corridor()

    baseline = build_route_baseline(
        ROUTE_KEY,
        corridor["history"],
        observed_time_range="2024-01-01/2024-01-03",
    )
    sparse_baseline = build_route_baseline(ROUTE_KEY, corridor["sparse_history"])

    scenario_a = compute_route_deviation("demo-A-normal", corridor["normal"], baseline)
    scenario_b = compute_route_deviation(
        "demo-B-deviation", corridor["deviating"], baseline
    )
    scenario_c = compute_route_deviation(
        "demo-C-insufficient", corridor["normal"], sparse_baseline
    )

    return {
        "demo": "route-deviation-1",
        "data_source": data_source,
        "data_source_note": (
            "Derived from prepared NOAA segmented AIS; the 'deviating' probe is a "
            "deterministic lateral offset of a real track for demonstration."
            if data_source == "prepared_noaa_segmented"
            else "Committed deterministic synthetic corridor fixture; no bulk AIS "
            "download required. Figures are illustrative, not operational data."
        ),
        "disclaimer": (
            "Decision support for human review only; derived geometric deviations, "
            "not a judgement about any vessel."
        ),
        "scenarios": {
            "A_normal_route": scenario_a.to_dict(),
            "B_route_deviation": scenario_b.to_dict(),
            "C_insufficient_baseline": scenario_c.to_dict(),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--segmented",
        type=Path,
        default=None,
        help="Prepared NOAA segmented Parquet (defaults to the Phase 2 output path).",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help="Optional path to write the demo JSON (otherwise printed to stdout).",
    )
    args = parser.parse_args()

    payload = run_demo(args.segmented)
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if args.json_output is not None:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(text, encoding="utf-8")
        print(f"wrote {args.json_output} (data_source={payload['data_source']})")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
