"""Detection stack: simulator determinism, detectors vs ground truth, operator feedback, API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.api.seawatch.detection.alerts import build_alerts
from apps.api.seawatch.detection.config import DetectionConfig
from apps.api.seawatch.detection.context import DetectionContext, TrafficBaseline
from apps.api.seawatch.detection.detectors import run_all
from apps.api.seawatch.detection.evaluation import evaluate_alerts
from apps.api.seawatch.detection.service import DetectionService
from apps.api.seawatch.detection.simulator import build_scenario, normal_traffic
from apps.api.seawatch.detection.state import FeedbackStore


@pytest.fixture(scope="module")
def world():
    s = build_scenario(7)
    base = TrafficBaseline().fit([t for sd in (101, 102) for t in normal_traffic(sd, 40).tracks])
    return s, base


def test_simulator_is_deterministic():
    a, b = build_scenario(3), build_scenario(3)
    assert [t.mmsi for t in a.tracks] == [t.mmsi for t in b.tracks]
    assert a.tracks[5].lat.tolist() == b.tracks[5].lat.tolist()
    assert [e.kind for e in a.truth] == [e.kind for e in b.truth]


def test_every_injected_behaviour_is_detected_and_explained(world):
    s, base = world
    cfg = DetectionConfig()
    events = run_all(s.tracks, s.t0, s.t1, DetectionContext(s.zones, s.receivers, base), cfg)
    alerts = build_alerts(events, s.tracks, cfg)
    r = evaluate_alerts(alerts, s)
    assert r["missed"] == []
    assert r["precision"] >= 0.8
    for a in alerts:
        assert a.reasons and a.uncertainty and a.benign_explanations
        assert 0 <= a.risk <= 99 and a.level in ("HIGH", "MEDIUM", "LOW")


def test_benign_lookalikes_do_not_alert(world):
    s, base = world
    cfg = DetectionConfig()
    events = run_all(s.tracks, s.t0, s.t1, DetectionContext(s.zones, s.receivers, base), cfg)
    quiet = {m for t in s.truth if t.benign and t.kind in ("fishing_ops", "anchored", "coverage_gap") for m in t.mmsis}
    assert not [e for e in events if set(e.mmsis) <= quiet]


def test_raising_gap_threshold_removes_gap_alert(world):
    s, base = world
    ctx = DetectionContext(s.zones, s.receivers, base)
    n_default = sum(e.kind == "ais_gap" for e in run_all(s.tracks, s.t0, s.t1, ctx, DetectionConfig()))
    n_strict = sum(e.kind == "ais_gap" for e in run_all(s.tracks, s.t0, s.t1, ctx, DetectionConfig(gap_min_minutes=400)))
    assert n_default >= 1 and n_strict == 0


def test_false_alarm_feedback_downweights_repeat():
    svc = DetectionService(7, FeedbackStore(None))
    top = svc.alerts()[-1]
    before = top.risk
    svc.store.set_status(top, "false_alarm")
    again = svc.alert(top.id)
    assert again.status == "false_alarm" and again.suppressed_by_feedback and again.risk < before
    assert top.id not in [a.id for a in svc.alerts()]


def test_replay_clock_hides_future_alerts():
    svc = DetectionService(7, FeedbackStore(None))
    early = svc.alerts(as_of=svc.scenario.t0 + 3600)
    late = svc.alerts()
    assert len(early) < len(late)


def test_detection_api_round_trip():
    from apps.api.seawatch.detection import service as svc_mod
    from apps.api.seawatch.main import create_app

    svc_mod._service = DetectionService(7, FeedbackStore(None))
    c = TestClient(create_app())
    al = c.get("/detection/alerts").json()["alerts"]
    assert al and al[0]["risk"] >= al[-1]["risk"]
    detail = c.get(f"/detection/alerts/{al[0]['id']}").json()
    assert detail["timeline"] and detail["reasons"] and detail["recommended_action"]
    assert c.post(f"/detection/alerts/{al[0]['id']}/notes", json={"text": "checking"}).status_code == 200
    r = c.post(f"/detection/alerts/{al[0]['id']}/status", json={"status": "false_alarm"})
    assert r.json()["status"] == "false_alarm"
    assert c.post(f"/detection/alerts/{al[1]['id']}/status", json={"status": "bogus"}).status_code == 422
    cfg = c.put("/detection/config", json={"alert_min_risk": 70}).json()
    assert cfg["values"]["alert_min_risk"] == 70
    assert all(a["risk"] >= 70 for a in c.get("/detection/alerts").json()["alerts"])
    assert c.get("/detection/evaluation").json()["alerts"] >= 0
    svc_mod._service = None


# --- San Francisco Bay world (real AIS) - only runs where the data has been set up ---------------
_SF_FILES = list(__import__("pathlib").Path("data/processed").glob("sfbay_2024-01-0*.parquet"))


@pytest.mark.skipif(len(_SF_FILES) < 2, reason="run scripts/setup_sfbay_data.py first")
def test_sf_world_labels_are_found_and_background_is_real():
    from apps.api.seawatch.detection import sfworld

    days = sfworld.load_days(".")
    scn, parts = sfworld.build_sf_scenario(days)
    ctx = sfworld.make_context(scn, parts)
    cfg = DetectionConfig()
    alerts = build_alerts(run_all(scn.tracks, scn.t0, scn.t1, ctx, cfg), scn.tracks, cfg)
    r = evaluate_alerts(alerts, scn)
    assert r["recall"] >= 0.8
    assert len(scn.tracks) > 300  # genuine recorded traffic, not a handful of scripted vessels
    # scripted/injected events are the only labelled ones; the rest of the traffic is untouched
    assert {t.kind for t in scn.truth} >= {"rendezvous", "dark_sts", "cluster", "zone_entry", "dark_gap"}


def test_berthed_vessels_are_not_loitering_or_dark():
    import numpy as np

    from apps.api.seawatch.detection.detectors import detect_gaps, detect_loitering
    from apps.api.seawatch.detection.models import Track

    t = np.arange(0, 12 * 3600, 180.0)
    berthed = Track("366000001", "ALONGSIDE", "cargo", "US", t, np.full(t.size, 37.8), np.full(t.size, -122.4),
                    np.full(t.size, 0.1), np.zeros(t.size), np.full(t.size, 5))
    ctx = DetectionContext([], [], None)
    assert detect_loitering([berthed], ctx, DetectionConfig()) == []
    assert detect_gaps([berthed], ctx, DetectionConfig()) == []
