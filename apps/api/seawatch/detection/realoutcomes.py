"""Measure the detectors against REAL outcome labels (watch-lists and documented incidents).

What this does and does not show
--------------------------------
* Watch-list labels (sanctions etc.) say a vessel is *designated*. They support one question: do designated vessels
  look unusual more often than the rest of the traffic?  It is a weak, vessel-level signal and says nothing about
  what any vessel did on the day.
* Incident labels say a vessel was suspected of something in a time window. They support: did the system raise an
  alert on that vessel in/around the window, which behaviour was the clue, and how many other vessels were raised?
  With very few incidents this is a case study, not a statistic.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .alerts import Alert, build_alerts
from .config import DetectionConfig
from .context import DetectionContext, TrafficBaseline
from .detectors import run_all
from .labels import LabelSet
from .learned import LearnedContext, VesselHabits
from .models import Track


def _auc(pos: list[float], neg: list[float]) -> float | None:
    if not pos or not neg:
        return None
    n, m = np.array(neg), np.array(pos)
    wins = (m[:, None] > n[None, :]).sum() + 0.5 * (m[:, None] == n[None, :]).sum()
    return float(wins / (len(pos) * len(neg)))


def evaluate(day_tracks: list[list[Track]], day_bounds: list[tuple[float, float]], labels: LabelSet,
             cfg: DetectionConfig | None = None, history: list[Track] | None = None) -> dict[str, Any]:
    cfg = cfg or DetectionConfig()
    allt = [t for d in day_tracks for t in d]
    la = np.concatenate([t.lat for t in allt]); lo = np.concatenate([t.lon for t in allt])
    bounds = (float(la.min()), float(lo.min()), float(la.max()), float(lo.max()))
    ctx = DetectionContext([], [], TrafficBaseline().fit(allt), learned=LearnedContext().fit(allt), bounds=bounds)
    if history:
        ctx.habits = VesselHabits().fit(history)

    risk: dict[str, float] = {}
    kinds: dict[str, set[str]] = {}
    alerts_all: list[Alert] = []
    vessel_days = 0
    for tracks, (t0, t1) in zip(day_tracks, day_bounds):
        vessel_days += len(tracks)
        ev = run_all(tracks, t0, t1, ctx, cfg)
        al = build_alerts(ev, tracks, cfg)
        alerts_all += al
        for a in al:
            for m in a.mmsis:
                if a.risk > risk.get(m, 0):
                    risk[m] = a.risk
                kinds.setdefault(m, set()).update(a.kinds)

    by = {t.mmsi: t for t in allt}
    present = {m: t for m, t in by.items()}
    rep: dict[str, Any] = {
        "vessels": len(present), "vessel_days": vessel_days, "alerts": len(alerts_all),
        "alerts_per_100_vessel_days": round(100 * len(alerts_all) / max(1, vessel_days), 1),
        "high_alerts": sum(a.level == "HIGH" for a in alerts_all),
        "labelled": [], "watchlist": {}, "incidents": [],
    }
    flagged_all = sorted(risk.values(), reverse=True)

    wl_pos: list[float] = []
    wl_ids: set[str] = set()
    for m, tr in present.items():
        hits = labels.match(tr)
        wl = [h for h in hits if h.kind == "watchlist"]
        if wl:
            wl_ids.add(m)
            wl_pos.append(risk.get(m, 0.0))
            rep["labelled"].append({"mmsi": m, "name": tr.name, "imo": tr.imo, "labels": sorted({h.category for h in wl}),
                                    "fixes": len(tr), "max_risk": round(risk.get(m, 0.0), 1), "alert_kinds": sorted(kinds.get(m, []))})
    neg = [risk.get(m, 0.0) for m in present if m not in wl_ids]
    rep["watchlist"] = {
        "present": len(wl_ids), "flagged": int(sum(r >= cfg.alert_min_risk for r in wl_pos)),
        "base_rate_flagged": round(float(np.mean([r >= cfg.alert_min_risk for r in neg])), 3) if neg else None,
        "auc": _auc(wl_pos, neg),
        "note": "A watch-list entry is a legal designation of the vessel, not evidence of behaviour on these days.",
    }

    for inc in [lb for lb in labels.labels if lb.kind == "incident"]:
        tr = next((t for t in allt if labels.match(t) and any(h is inc for h in labels.match(t))), None)
        rec: dict[str, Any] = {"category": inc.category, "names": list(inc.names), "source": inc.source, "confidence": inc.confidence,
                               "window": [inc.t_start, inc.t_end], "present_in_data": tr is not None}
        if tr is not None:
            w0, w1 = inc.t_start or tr.t[0], inc.t_end or tr.t[-1]
            inwin = (tr.t >= w0) & (tr.t <= w1)
            rec["fixes_in_window"] = int(inwin.sum())
            rec["first_seen"], rec["last_seen"] = float(tr.t[0]), float(tr.t[-1])
            mine = [a for a in alerts_all if tr.mmsi in a.mmsis and a.t_end >= w0 - 6 * 3600 and a.t_start <= w1 + 6 * 3600]
            rec["alerts_near_window"] = [{"risk": round(a.risk, 1), "level": a.level, "kinds": a.kinds, "title": a.title,
                                          "t_start": a.t_start, "t_end": a.t_end} for a in mine]
            rec["max_risk"] = round(risk.get(tr.mmsi, 0.0), 1)
            rec["rank_among_vessels"] = int(1 + sum(r > risk.get(tr.mmsi, 0.0) for r in risk.values()))
            rec["vessels_with_any_alert"] = len(risk)
        rep["incidents"].append(rec)
    return rep
