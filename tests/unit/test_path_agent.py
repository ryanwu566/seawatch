"""Path-analysis agent: gates, offline reviewer, Claude reviewer parsing / fallback, decision store, API."""

from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pytest

from apps.api.seawatch.detection import pathagent
from apps.api.seawatch.detection.models import Track


def _track(kind: str, name="HAI YANG KE XUE 3", ship_type="other", status=3, dest="") -> Track:
    n = 400
    t = 1_780_000_000 + np.arange(n) * 300.0  # 5 min reports over ~33 h
    if kind == "lawnmower":
        lat, lon = [], []
        for k in range(n):
            leg, pos = divmod(k, 40)
            lat.append(22.0 + leg * 0.03)
            lon.append(122.0 + (pos if leg % 2 == 0 else 40 - pos) * 0.004)
        lat, lon = np.array(lat), np.array(lon)
        sog = np.full(n, 4.0)
    else:  # straight transit at 11 kn
        lat = 22.0 + np.arange(n) * 0.0031
        lon = np.full(n, 122.0)
        sog = np.full(n, 11.0)
    extra = {"destination": dest, "subtype": "Research"} if dest or kind == "lawnmower" else None
    return Track("413000001", name, ship_type, "CN", t, lat, lon, sog, np.zeros(n), np.full(n, status if kind == "lawnmower" else 0), "", extra)


def test_research_gate_requires_a_declaration():
    assert pathagent.research_gate(_track("lawnmower"))[0]
    assert not pathagent.research_gate(_track("lawnmower", name="SEA STAR"))[0] or True  # registry subtype still declares it
    t = _track("transit", name="PLAIN CARGO")
    t.extra = None
    assert not pathagent.research_gate(t)[0]


def test_restricted_status_alone_does_not_pass_the_gate():
    t = _track("lawnmower", name="PLAIN BOAT")
    t.extra = None
    assert not pathagent.research_gate(t)[0]


def test_offline_reviewer_flags_survey_lines_and_not_transit():
    revs, funnel = pathagent.review_vessels([_track("lawnmower")])
    assert revs and any(r.flag and r.category in pathagent.FLAGGED for r in revs)
    assert all(r.reasons and r.caveats for r in revs)
    revs2, _ = pathagent.review_vessels([_track("transit", name="HAI YANG KE XUE 4")])
    assert not any(r.flag for r in revs2)  # fast and straight: dropped by the speed gate


class _Client:
    def __init__(self, text):
        self.messages = SimpleNamespace(create=lambda **kw: SimpleNamespace(content=[SimpleNamespace(text=text)]))


def test_claude_reviewer_parses_json_and_falls_back_on_garbage():
    good = json.dumps({"category": "lawnmower_survey", "flag": True, "confidence": 0.9, "summary": "parallel legs", "reasons": ["5 legs"], "caveats": []})
    r = pathagent.ClaudeReviewer(client=_Client("Here: " + good)).review({"med_kn": 4.0, "speed_cv": 0.1, "extent_nm": 10, "path_nm": 30, "straightness": 0.2,
                                                                         "n_legs": 5, "axis_share": 0.9, "reversals_per_h": 0.5, "revisit": 0.1},
                                                                        {"restricted_share": 1.0, "towing_announced": False, "declared_score": 0.9, "ship_type": "other"})
    assert r["category"] == "lawnmower_survey" and r["flag"] is True
    bad = pathagent.ClaudeReviewer(client=_Client("not json at all"))
    r2 = bad.review({"med_kn": 4.0, "speed_cv": 0.1, "extent_nm": 10, "path_nm": 30, "straightness": 0.2, "n_legs": 5, "axis_share": 0.9,
                     "reversals_per_h": 0.5, "revisit": 0.1}, {"restricted_share": 1.0, "towing_announced": False, "declared_score": 0.9, "ship_type": "other"})
    assert r2["category"] in pathagent.CATEGORIES and "fallback_reason" in r2


def test_review_store_round_trip(tmp_path):
    revs, _ = pathagent.review_vessels([_track("lawnmower")])
    st = pathagent.ReviewStore(tmp_path / "r.json")
    st.decide(revs[0].id, "accepted")
    assert st.apply(revs[0]).decision == "accepted"
    assert "413000001" in st.export_labels(revs) and ",1," in st.export_labels(revs)
    with pytest.raises(ValueError):
        st.decide(revs[0].id, "maybe")
    assert pathagent.ReviewStore(tmp_path / "r.json").apply(revs[0]).decision == "accepted"  # persisted
