"""Alert fusion: group events per incident, correlate across vessels, score risk, explain.

An *alert* is what an operator sees: one incident that may combine several
behavioural events (e.g. a vessel that goes dark, then a second vessel loiters
where the first could have reached). The risk score is a transparent
noisy-OR over per-event evidence - never a black box, never a threat verdict.
"""

from __future__ import annotations

import numpy as np

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
    "route_deviation": "Off-route", "status_mismatch": "Status mismatch", "survey_pattern": "Survey-like track", "survey_threat": "Suspected unauthorised survey", "dark_rendezvous": "Possible dark transfer",
}
KIND_WEIGHT = {
    "ais_gap": 0.90, "loitering": 0.80, "rendezvous": 1.00, "cluster": 0.90, "zone_entry": 1.00,
    "position_jump": 0.90, "identity_conflict": 1.00, "route_deviation": 0.70, "status_mismatch": 0.60, "survey_pattern": 1.00, "survey_threat": 1.00, "dark_rendezvous": 1.00,
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
    watch: list[dict[str, Any]] = field(default_factory=list)
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
            "ml_agreement": (self.ml or {}).get("agreement"), "watched": bool(self.watch), "suppressed_by_feedback": self.suppressed_by_feedback, "n_notes": len(self.notes),
            "top_reason": self.reasons[0] if self.reasons else "",
        }

    def detail(self) -> dict[str, Any]:
        d = self.summary()
        d.update({
            "reasons": self.reasons, "breakdown": self.breakdown,
            "benign_explanations": self.benign_explanations, "uncertainty": self.uncertainty,
            "recommended_action": self.recommended_action, "notes": self.notes, "ml": self.ml, "watch": self.watch,
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


def _correlate_dark_rendezvous(events: list[Event], meta: dict[str, Track] | None = None) -> list[Event]:
    """Gap + another vessel stopping somewhere the dark vessel could have reached in time."""

    extra: list[Event] = []
    pairs: dict[int, tuple[Event, list]] = {}  # partner event -> the gaps that point at it
    gaps = [e for e in events if e.kind == "ais_gap"]
    others = [e for e in events if e.kind in ("loitering", "rendezvous", "cluster")]
    for g in gaps:
        if g.metrics.get("stationary"):
            continue
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
            d_each = [float(haversine_m(o.lat, o.lon, a, b)) / NM_M for a, b in ends]
            dist = min(d_each)
            # the dark vessel must be able to go out to the other vessel, stay for the overlap, and come back
            slack_nm = 15.0 * max(0.0, (g.t_end - g.t_start) - overlap) / 3600.0
            if dist > reach_nm or sum(d_each) > 0.7 * slack_nm + 1.0:
                continue
            frac = overlap / max(o.t_end - o.t_start, 1.0)
            cover = overlap / max(g.t_end - g.t_start, 1.0)
            if frac < 0.6 or cover < 0.5 or o.severity < 50:
                continue  # the other vessel must be stopped for most of the time the first one is dark, and for much of the silence
            score = frac - dist / 200.0
            if best is None or score > best[0]:
                best = (score, o, dist, overlap)
        if best is None:
            continue
        pairs.setdefault(id(best[1]), (best[1], []))[1].append((g, best[2], best[3], reach_nm))
    for o, group in pairs.values():
        gs = [x[0] for x in group]
        mm = sorted(set(o.mmsis) | {m for g in gs for m in g.mmsis})
        n = len(gs)
        g0, dist, overlap, reach_nm = max(group, key=lambda x: x[0].severity)
        det = max(max(g.metrics.get("detected_at", g.t_end) for g in gs), o.metrics.get("detected_at", o.t_end))
        if n == 1:
            ev = [f"One vessel went silent for {fmt_dur(g0.t_end - g0.t_start)} while another vessel stopped {dist:.0f} nm from where it vanished "
                  f"({fmt_dur(overlap)} of overlap).",
                  f"The silent vessel could physically have reached that spot (reach ~ {reach_nm:.0f} nm in the time available).",
                  "This is the classic signature of a hidden ship-to-ship transfer: one party stays visible, the other is dark."]
            summary, sev = "Possible dark ship-to-ship transfer", 82.0
        else:
            ev = [f"{n} vessels went silent while the same vessel stayed stopped nearby, each within reach of it "
                  f"(longest silence {fmt_dur(max(g.t_end - g.t_start for g in gs))}).",
                  "A single stopped vessel with a succession of boats vanishing around it is the pattern of an at-sea gathering or transshipment point.",
                  "Each boat's silence alone may be ordinary for its type; the shared meeting point is what makes the group notable."]
            summary, sev = f"Possible at-sea gathering: {n} vessels dark around one stopped vessel", min(95.0, 80.0 + 2.0 * n)
        fishing = sum(1 for g in gs if meta and g.mmsis[0] in meta and meta[g.mmsis[0]].ship_type == "fishing")
        if fishing >= 0.6 * n:
            sev -= 22
            ev.append("Most of the silent boats are fishing vessels: handing catch to a carrier or support ship is routine, so the weighting is reduced.")
        extra.append(Event(
            "", "dark_rendezvous", mm, min(min(g.t_start for g in gs), o.t_start), max(max(g.t_end for g in gs), o.t_end),
            o.lat, o.lon, sev, min(min(g.confidence for g in gs), o.confidence), summary, ev,
            ["Two unrelated events can overlap by coincidence in dense traffic", "Vessels may simply have lost power or coverage",
             "Legitimate fleet support (supply, bunkering, collection of catch)"],
            ["Without SAR, optical or RF data the dark vessels' real positions are unknown - this link is an inference."],
            {"distance_nm": round(dist, 1), "reach_nm": round(reach_nm, 1), "dark_vessels": n, "detected_at": det}, path=[(o.lat, o.lon)]))
    return extra


def build_alerts(events: list[Event], tracks: list[Track], cfg: DetectionConfig, feedback=None, watch=None) -> list[Alert]:
    meta = {t.mmsi: t for t in tracks}
    events = list(events) + _correlate_dark_rendezvous(events, meta)
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
        if len(e.mmsis) > 8:
            continue  # a big gathering must not chain unrelated vessels into one alert
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
    # A busy area can chain many unrelated vessels through meeting / "dark transfer" links. Cap an alert at 6 vessels: a bigger
    # group is rebuilt without its multi-vessel events as bridges; each of those events then belongs to its lead vessel's alert.
    if any(len({m for e in g for m in e.mmsis}) > 6 for g in groups.values()):
        parent = list(range(len(events)))
        by_lead: dict[str, list[int]] = {}
        for i, e in enumerate(events):
            by_lead.setdefault(e.mmsis[0], []).append(i)  # partners are named in the lead's alert but never bridge two alerts
        for idxs in by_lead.values():
            idxs.sort(key=lambda i: events[i].t_start)
            for a, b in zip(idxs, idxs[1:]):
                if events[b].t_start - events[a].t_end <= link_s:
                    parent[find(a)] = find(b)
        groups = {}
        for i, e in enumerate(events):
            groups.setdefault(find(i), []).append(e)

    meta = {t.mmsi: t for t in tracks}
    alerts: list[Alert] = []
    for evs in groups.values():
        alerts.append(_make_alert(evs, meta, cfg, feedback, watch))
    alerts = [a for a in alerts if a.risk >= cfg.alert_min_risk or a.suppressed_by_feedback
              or (feedback is not None and a.id in feedback.records)]
    alerts.sort(key=lambda a: -a.risk)
    return alerts


def _make_alert(evs: list[Event], meta: dict[str, Track], cfg: DetectionConfig, feedback, watch=None) -> Alert:
    mmsis = sorted({m for e in evs for m in e.mmsis})
    items = [(e.kind, e.severity, e.confidence) for e in evs]
    risk = _noisy_or(items)
    kinds = sorted({e.kind for e in evs}, key=lambda k: -max(e.severity for e in evs if e.kind == k))
    if len(kinds) >= 3:
        risk = min(99.0, risk + 6)
    # A survey breach of Taiwan's own 24 nm (rules R1 / R2) is the case the mentor model says must be raised as a threat: floor it at HIGH.
    # Operator feedback below can still lower it.
    if any(e.kind == "survey_threat" and e.metrics.get("rule") in ("R1", "R2") and not e.metrics.get("transit") for e in evs):
        risk = max(risk, cfg.high_risk)
    # Fishing fleets silence, loiter, meet and gather as a matter of routine: behaviour that is only 'ordinary work' for them is discounted.
    # Zone entries, spoofing and survey patterns are NOT discounted.
    routine = {"ais_gap", "loitering", "rendezvous", "cluster", "dark_rendezvous", "route_deviation"}
    if kinds and set(kinds) <= routine and mmsis:
        fish = sum(getattr(meta.get(m), "ship_type", "") == "fishing" for m in mmsis) / len(mmsis)
        if fish >= 0.7:
            risk *= 0.65
            from .territory import Territory

            terr = Territory.default()
            if terr is not None and float(terr.coast_nm(np.array([np.mean([e.lat for e in evs])]), np.array([np.mean([e.lon for e in evs])]))[0]) <= 6.0:
                risk *= 0.7  # a fishing fleet inside harbour / bay waters: moorage, not a meeting
    suppressed = None
    if feedback is not None:
        factor, why = feedback.risk_modifier(mmsis, kinds, evs)
        if factor != 1.0:
            risk *= factor
            suppressed = why
    watched: list[dict[str, Any]] = []
    if watch is not None:
        for m in mmsis:
            tr = meta.get(m)
            for lb in (watch.match(tr) if tr is not None else []):
                watched.append({"mmsi": m, "name": tr.name, "category": lb.category, "source": lb.source, "note": lb.note,
                                "confidence": lb.confidence})
        if watched:
            risk = min(99.0, risk + 8.0)  # a modest prior: the behaviour matters more than the listing
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
    for w_ in watched:
        reasons.append(f"{w_['name']} is on a watch-list ({w_['category'].replace('_', ' ')}; {w_['confidence']}): {w_['note'] or w_['source']}. A listing is not evidence of what this vessel is doing now.")
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
    weights = [max(e.confidence, 0.05) * max(e.severity, 1.0) for e in evs]
    conf = sum(e.confidence * w for e, w in zip(evs, weights)) / sum(weights)
    title = "Possible dark ship-to-ship transfer" if "dark_rendezvous" in kinds else " + ".join(KIND_LABEL.get(k, k) for k in kinds[:3])
    threat = next((e for e in sorted(evs, key=lambda e: -e.severity) if e.kind == "survey_threat"), None)
    if threat is not None:
        title = threat.metrics.get("classification", title)
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
                 breakdown, ben[:6], unc, ACTIONS[level], suppressed, watched)
