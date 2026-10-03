"""Scoring a detector against the simulator's ground truth."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from .alerts import Alert
from .models import Event, Scenario, TruthEvent

# Which detector event kinds count as a hit for each truth kind.
ACCEPT = {
    "dark_gap": {"ais_gap", "dark_rendezvous"},
    "dark_sts": {"ais_gap", "loitering", "dark_rendezvous", "rendezvous"},
    "loitering": {"loitering"},
    "zone_entry": {"zone_entry"},
    "rendezvous": {"rendezvous", "dark_rendezvous"},
    "position_jump": {"position_jump", "identity_conflict"},
    "identity_conflict": {"identity_conflict", "position_jump"},
    "route_deviation": {"route_deviation"},
    "cluster": {"cluster", "rendezvous"},
    "survey_pattern": {"survey_pattern", "survey_threat"},
    "survey_threat": {"survey_threat", "survey_pattern"},
}
TOL_S = 3600.0


def _overlaps(e: Event, tr: TruthEvent) -> bool:
    return e.t_end >= tr.t_start - TOL_S and e.t_start <= tr.t_end + TOL_S


def _matches(e: Event, tr: TruthEvent) -> bool:
    return bool(set(e.mmsis) & set(tr.mmsis)) and _overlaps(e, tr)


def evaluate_events(events: Iterable[Event], scenario: Scenario) -> dict[str, Any]:
    events = list(events)
    positives = [t for t in scenario.truth if not t.benign]
    per_kind: dict[str, dict[str, int]] = defaultdict(lambda: {"truth": 0, "detected": 0})
    detected = []
    for tr in positives:
        hit = any(_matches(e, tr) and e.kind in ACCEPT.get(tr.kind, set()) for e in events)
        per_kind[tr.kind]["truth"] += 1
        per_kind[tr.kind]["detected"] += int(hit)
        detected.append((tr, hit))
    return {"per_kind": dict(per_kind), "recall": sum(h for _, h in detected) / max(1, len(detected))}


def evaluate_alerts(alerts: list[Alert], scenario: Scenario, vessel_days: float | None = None) -> dict[str, Any]:
    """Alert-level precision / recall / false alarms against labelled truth."""

    positives = [t for t in scenario.truth if not t.benign]
    benign = [t for t in scenario.truth if t.benign]
    tp_alerts, fp_alerts, benign_alerts = [], [], []
    for a in alerts:
        hit = any(
            any(_matches(e, t) and e.kind in ACCEPT.get(t.kind, set()) for e in a.events) for t in positives
        )
        if hit:
            tp_alerts.append(a)
        else:
            fp_alerts.append(a)
            if any(any(_matches(e, t) for e in a.events) for t in benign):
                benign_alerts.append(a)
    per_kind: dict[str, dict[str, int]] = defaultdict(lambda: {"truth": 0, "detected": 0})
    missed = []
    for t in positives:
        hit = any(any(_matches(e, t) and e.kind in ACCEPT.get(t.kind, set()) for e in a.events) for a in alerts)
        per_kind[t.kind]["truth"] += 1
        per_kind[t.kind]["detected"] += int(hit)
        if not hit:
            missed.append(t.kind)
    vd = vessel_days if vessel_days is not None else len(scenario.tracks) * (scenario.t1 - scenario.t0) / 86400
    n = len(alerts)
    recall = sum(v["detected"] for v in per_kind.values()) / max(1, len(positives))
    precision = len(tp_alerts) / n if n else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "alerts": n, "true_alerts": len(tp_alerts), "false_alarms": len(fp_alerts),
        "false_alarms_on_benign_lookalikes": len(benign_alerts),
        "precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3),
        "alerts_per_100_vessel_days": round(100 * n / max(vd, 1e-9), 1),
        "false_alarms_per_100_vessel_days": round(100 * len(fp_alerts) / max(vd, 1e-9), 1),
        "per_kind": dict(per_kind), "missed": missed,
        "false_alarm_ids": [a.id for a in fp_alerts],
    }
