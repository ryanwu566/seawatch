"""Alert fusion: group events per incident, correlate across vessels, score risk, explain.

An *alert* is what an operator sees: one incident that may combine several
behavioural events (e.g. a vessel that goes dark, then a second vessel loiters
where the first could have reached). The risk score is a transparent
noisy-OR over per-event evidence - never a black box, never a threat verdict.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from .config import DetectionConfig
from .detectors import fmt_dur, fmt_pos
from .geo import NM_M, haversine_m
from .models import Event, Track

KIND_LABEL = {
    "ais_gap": "AIS silence", "loitering": "Loitering", "rendezvous": "Slow rendezvous", "cluster": "Vessel cluster",
    "zone_entry": "Protected-zone entry", "position_jump": "Position anomaly", "identity_conflict": "Identity conflict",
    "route_deviation": "Off-route", "dark_rendezvous": "Possible dark transfer",
}
KIND_WEIGHT = {
    "ais_gap": 0.90, "loitering": 0.80, "rendezvous": 1.00, "cluster": 0.90, "zone_entry": 1.00,
    "position_jump": 0.90, "identity_conflict": 1.00, "route_deviation": 0.70, "dark_rendezvous": 1.00,
}
ACTIONS = {
    "HIGH": "Escalate: task an ISR/patrol asset or request SAR / RF-emission confirmation of the area now.",
    "MEDIUM": "Queue for analyst review within the shift; cross-check against SAR or RF data if available.",
    "LOW": "Keep under watch; no action unless it repeats or combines with other behaviour.",
}


@dataclass
class Alert:
    id: str
    title: str
    risk: float
    level: str
    confidence: float
    mmsis: list[str]
    vessels: list[dict[str, Any]]
    t_start: float
    t_end: float
    lat: float
    lon: float
    events: list[Event]
    kinds: list[str]
    reasons: list[str]
    breakdown: list[dict[str, Any]]
    benign_explanations: list[str]
    uncertainty: list[str]
    recommended_action: str
    suppressed_by_feedback: str | None = None
    raised_at: float = 0.0
    ml: dict[str, Any] | None = None
    status: str = "new"
    notes: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.id, "title": self.title, "risk": round(self.risk, 1), "level": self.level,
            "confidence": round(self.confidence, 2), "mmsis": self.mmsis, "vessels": self.vessels,
            "t_start": self.t_start, "t_end": self.t_end, "raised_at": self.raised_at, "lat": round(self.lat, 4), "lon": round(self.lon, 4),
            "kinds": self.kinds, "status": self.status, "n_events": len(self.events),
            "ml_agreement": (self.ml or {}).get("agreement"), "suppressed_by_feedback": self.suppressed_by_feedback, "n_notes": len(self.notes),
            "top_reason": self.reasons[0] if self.reasons else "",
        }

    def detail(self) -> dict[str, Any]:
        d = self.summary()
        d.update({
            "reasons": self.reasons, "breakdown": self.breakdown,
            "benign_explanations": self.benign_explanations, "uncertainty": self.uncertainty,
            "recommended_action": self.recommended_action, "notes": self.notes, "ml": self.ml,
            "timeline": [e.to_dict() for e in sorted(self.events, key=lambda e: e.t_start)],
        })
        return d


def _noisy_or(items: list[tuple[str, float, float]]) -> float:
    """items: (kind, severity, confidence) -> risk 0..100 (best event per kind)."""

    best: dict[str, float] = {}
    for kind, sev, conf in items:
        p = KIND_WEIGHT.get(kind, 0.8) * sev * (0.6 + 0.4 * conf) / 100.0
        best[kind] = max(best.get(kind, 0.0), p)
    prod = 1.0
    for p in best.values():
        prod *= 1.0 - 0.9 * min(p, 1.0)
    return 100.0 * (1.0 - prod)


def _correlate_dark_rendezvous(events: list[Event]) -> list[Event]:
    """Gap + another vessel stopping somewhere the dark vessel could have reached in time."""

    extra: list[Event] = []
    gaps = [e for e in events if e.kind == "ais_gap"]
    others = [e for e in events if e.kind in ("loitering", "rendezvous", "cluster")]
    for g in gaps:
        dur_h = (g.t_end - g.t_start) / 3600
        reach_nm = max(8.0, 0.5 * dur_h * 15.0)
        best = None
        for o in others:
            if set(o.mmsis) & set(g.mmsis):
                continue
            overlap = min(g.t_end, o.t_end) - max(g.t_start, o.t_start)
            if overlap < 1200:
                continue
            ends = g.path or [(g.lat, g.lon)]
            dist = min(float(haversine_m(o.lat, o.lon, a, b)) / NM_M for a, b in ends)
            if dist > reach_nm:
                continue
            frac = overlap / max(o.t_end - o.t_start, 1.0)
            score = frac - dist / 200.0
            if best is None or score > best[0]:
                best = (score, o, dist, overlap)
        if best is None:
            continue
        _, o, dist, overlap = best
        extra.append(Event(
            "", "dark_rendezvous", sorted(set(g.mmsis) | set(o.mmsis)), min(g.t_start, o.t_start), max(g.t_end, o.t_end),
            o.lat, o.lon, 82.0, min(g.confidence, o.confidence),
            "Possible dark ship-to-ship transfer",
            [f"One vessel went silent for {fmt_dur(g.t_end - g.t_start)} while another vessel stopped {dist:.0f} nm from where it vanished "
             f"({fmt_dur(overlap)} of overlap).",
             f"The silent vessel could physically have reached that spot (reach ≈ {reach_nm:.0f} nm in the time available).",
             "This is the classic signature of a hidden ship-to-ship transfer: one party stays visible, the other is dark."],
            ["Two unrelated events can overlap by coincidence in dense traffic", "Dark vessel may simply have lost power or coverage"],
            ["Without SAR, optical or RF data the dark vessel's real position is unknown - this link is an inference."],
            {"distance_nm": round(dist, 1), "reach_nm": round(reach_nm, 1),
             "detected_at": max(g.metrics.get("detected_at", g.t_end), o.metrics.get("detected_at", o.t_end))}, path=[(o.lat, o.lon)]))
    return extra


def build_alerts(events: list[Event], tracks: list[Track], cfg: DetectionConfig, feedback=None) -> list[Alert]:
    events = list(events) + _correlate_dark_rendezvous(events)
    for n, e in enumerate(events):
        if not e.id:
            e.id = f"X{n:03d}"
    # union-find: events share a vessel and fall within the linking window
    parent = list(range(len(events)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    link_s = cfg.alert_link_hours * 3600
    by_mmsi: dict[str, list[int]] = {}
    for i, e in enumerate(events):
        for m in e.mmsis:
            by_mmsi.setdefault(m, []).append(i)
    for idxs in by_mmsi.values():
        idxs.sort(key=lambda i: events[i].t_start)
        for a, b in zip(idxs, idxs[1:]):
            if events[b].t_start - events[a].t_end <= link_s:
                parent[find(a)] = find(b)
    groups: dict[int, list[Event]] = {}
    for i, e in enumerate(events):
        groups.setdefault(find(i), []).append(e)

    meta = {t.mmsi: t for t in tracks}
    alerts: list[Alert] = []
    for evs in groups.values():
        alerts.append(_make_alert(evs, meta, cfg, feedback))
    alerts = [a for a in alerts if a.risk >= cfg.alert_min_risk or a.suppressed_by_feedback
              or (feedback is not None and a.id in feedback.records)]
    alerts.sort(key=lambda a: -a.risk)
    return alerts


def _make_alert(evs: list[Event], meta: dict[str, Track], cfg: DetectionConfig, feedback) -> Alert:
    mmsis = sorted({m for e in evs for m in e.mmsis})
    items = [(e.kind, e.severity, e.confidence) for e in evs]
    risk = _noisy_or(items)
    kinds = sorted({e.kind for e in evs}, key=lambda k: -max(e.severity for e in evs if e.kind == k))
    if len(kinds) >= 3:
        risk = min(99.0, risk + 6)
    suppressed = None
    if feedback is not None:
        factor, why = feedback.risk_modifier(mmsis, kinds, evs)
        if factor != 1.0:
            risk *= factor
            suppressed = why
    risk = float(min(99.0, risk))
    level = "HIGH" if risk >= cfg.high_risk else "MEDIUM" if risk >= cfg.medium_risk else "LOW"
    # marginal contribution of each kind to the score
    breakdown = []
    for k in kinds:
        without = _noisy_or([i for i in items if i[0] != k]) if len(kinds) > 1 else 0.0
        top = max((e for e in evs if e.kind == k), key=lambda e: e.severity)
        breakdown.append({"kind": k, "label": KIND_LABEL.get(k, k), "severity": round(top.severity, 1),
                          "confidence": round(top.confidence, 2), "points": round(_noisy_or(items) - without, 1)})
    breakdown.sort(key=lambda b: -b["points"])
    reasons: list[str] = []
    for k in [b["kind"] for b in breakdown]:
        top = max((e for e in evs if e.kind == k), key=lambda e: e.severity)
        reasons.extend(top.evidence)
    seen, uniq = set(), []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            uniq.append(r)
    ben = list(dict.fromkeys(b for e in evs for b in e.benign_explanations))
    unc = list(dict.fromkeys(u for e in evs for u in e.uncertainty))
    unc.append("Assessment uses AIS only - it infers behaviour from self-reported positions that can be missing, wrong or falsified.")
    weights = [max(e.confidence, 0.05) * e.severity for e in evs]
    conf = sum(e.confidence * w for e, w in zip(evs, weights)) / sum(weights)
    title = "Possible dark ship-to-ship transfer" if "dark_rendezvous" in kinds else " + ".join(KIND_LABEL.get(k, k) for k in kinds[:3])
    lead = max(evs, key=lambda e: e.severity)
    names = [meta[m].name if m in meta else m for m in mmsis]
    key = hashlib.sha1(("|".join(mmsis) + str(int(min(e.t_start for e in evs) // 7200))).encode()).hexdigest()[:8]
    vessels = [{"mmsi": m, "name": meta[m].name if m in meta else m, "type": meta[m].ship_type if m in meta else "unknown",
                "flag": meta[m].flag if m in meta else ""} for m in mmsis]
    if len(names) <= 2:
        title = f"{title} - {' & '.join(names)}"
    else:
        title = f"{title} - {names[0]} +{len(names) - 1}"
    return Alert(f"A-{key}", title, risk, level, float(conf), mmsis, vessels, min(e.t_start for e in evs),
                 max(e.t_end for e in evs), lead.lat, lead.lon, sorted(evs, key=lambda e: e.t_start), kinds, uniq[:8],
                 breakdown, ben[:6], unc, ACTIONS[level], suppressed)
