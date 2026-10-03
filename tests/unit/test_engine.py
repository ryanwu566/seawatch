"""Integration entry point: capability gating and a smoke run."""

from __future__ import annotations

import numpy as np

from apps.api.seawatch.detection import engine
from apps.api.seawatch.detection.models import Track
from apps.api.seawatch.detection.simulator import normal_traffic


def test_sparse_track_is_insufficient_not_analysed():
    t = Track("412000001", "ONE POINT", "cargo", "CN", np.array([1.7e9, 1.7e9 + 600]), np.array([24.0, 24.01]), np.array([121.0, 121.0]),
              np.array([5.0, 5.0]), np.array([0.0, 0.0]))
    el = engine.eligibility(t, "message_level")
    assert el["loitering"] == "insufficient_data" and el["ais_gap"] == "insufficient_data"


def test_density_gates_detectors_that_need_status():
    t = Track("412000002", "HOURLY", "cargo", "CN", 1.7e9 + np.arange(30) * 3600.0, np.full(30, 24.0), np.full(30, 121.0), np.full(30, np.nan), np.full(30, np.nan))
    el = engine.eligibility(t, "hourly_presence")
    assert el["status_mismatch"] == "not_applicable" and el["identity_conflict"] == "not_applicable"


def test_analyze_runs_and_reports_skips():
    hist = normal_traffic(101, 30).tracks
    live = normal_traffic(102, 30).tracks
    ctx = engine.build_context(hist, "message_level", taiwan=False)
    r = engine.analyze(live, ctx, density="message_level")
    assert r.n_tracks == len(live) and r.n_analyzed <= r.n_tracks
    assert all(a.reasons for a in r.alerts)
