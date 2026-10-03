"""Alert policy decisions: no flat fishing discount (area summaries instead), domestic survey work is reported, survey findings are never cut."""

from __future__ import annotations

import numpy as np

from apps.api.seawatch.detection.alerts import build_alerts
from apps.api.seawatch.detection.config import DetectionConfig
from apps.api.seawatch.detection.models import Event, Track


def _fish(mmsi, lat, lon):
    t = 1_780_000_000 + np.arange(10) * 600.0
    return Track(mmsi, f"MIN YU {mmsi[-3:]}", "fishing", "CN", t, np.full(10, lat), np.full(10, lon), np.full(10, 1.0), np.zeros(10))


def _ev(kind, mmsi, lat, lon, sev=80.0, t0=1_780_000_000.0):
    return Event("", kind, [mmsi], t0, t0 + 7200, lat, lon, sev, 0.8, f"{kind} {mmsi}", ["e"], ["b"], ["u"])


def test_fishing_fleet_is_summarised_per_area_without_a_risk_cut():
    cfg = DetectionConfig.dense()
    cfg.alert_min_risk = 10.0
    ms = [f"41200000{i}" for i in range(4)]
    tracks = [_fish(m, 25.10 + i * 0.01, 119.20) for i, m in enumerate(ms)]
    events = [_ev("loitering", m, 25.10 + i * 0.01, 119.20) for i, m in enumerate(ms)]
    single = build_alerts(events[:1], tracks, cfg)
    many = build_alerts(events, tracks, cfg)
    assert len(many) == 1 and many[0].title.startswith("Fishing-fleet activity")
    assert many[0].risk >= single[0].risk  # no 0.65 discount
    assert any("not a clearance" in u for u in many[0].uncertainty)


def test_domestic_towing_is_reported_not_hidden():
    from apps.api.seawatch.detection.config import DetectionConfig as C
    from apps.api.seawatch.detection.context import DetectionContext
    from apps.api.seawatch.detection.territory import Territory
    from apps.api.seawatch.detection.threat import detect_survey_threat

    n = 60
    t = 1_780_000_000 + np.arange(n) * 300.0
    tr = Track("416123456", "TAIWAN CABLE SHIP", "other", "TW", t, np.full(n, 23.0), 122.2 + np.arange(n) * 0.001, np.full(n, 3.5), np.zeros(n), np.full(n, 3), "",
               {"destination": "TOWING KEEP 3NM CPA", "subtype": "Research", "tow_t": t[::4]})
    ctx = DetectionContext([], [], None)
    ctx.territory = Territory.default()
    ev = detect_survey_threat([tr], ctx, C.dense())
    assert ev and ev[0].metrics["rule"] == "R0"
    al = build_alerts(ev, [tr], C.dense())
    assert al and al[0].level == "LOW"  # reported, below the cut-off, but never dropped
