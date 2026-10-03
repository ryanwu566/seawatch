"""Detection service: scenario + baseline + config + operator feedback behind one object."""

from __future__ import annotations

import threading
from typing import Any

import numpy as np

from .alerts import Alert, build_alerts
from .config import PARAM_SPECS, DetectionConfig
from .context import DetectionContext, TrafficBaseline
from .detectors import run_all
from .evaluation import evaluate_alerts
from .models import Event, Scenario
from .simulator import build_scenario, normal_traffic
from .state import FeedbackStore, default_store

# When an event becomes *actionable* (earliest moment a live system could raise it).
_DETECT_LAG = {
    "ais_gap": lambda e, c: e.t_start + c.gap_min_minutes * 60,
    "loitering": lambda e, c: e.t_start + c.loiter_min_minutes * 60,
    "rendezvous": lambda e, c: e.t_start + c.rendezvous_min_minutes * 60,
    "cluster": lambda e, c: e.t_start + c.cluster_min_minutes * 60,
    "route_deviation": lambda e, c: e.t_start + c.deviation_min_minutes * 60,
    "zone_entry": lambda e, c: e.t_start,
    "position_jump": lambda e, c: e.t_end,
    "identity_conflict": lambda e, c: min(e.t_end, e.t_start + 1800),
}


class DetectionService:
    def __init__(self, seed: int = 7, store: FeedbackStore | None = None):
        self.lock = threading.RLock()
        self.seed = seed
        self.scenario: Scenario = build_scenario(seed)
        hist = [t for sd in (101, 102, 103) for t in normal_traffic(sd).tracks]
        self.baseline = TrafficBaseline().fit(hist)
        self.cfg = DetectionConfig()
        self.store = store or default_store()
        self._events: list[Event] | None = None
        self._evt_cfg: dict | None = None

    # -- pipeline ---------------------------------------------------------- #
    def _context(self) -> DetectionContext:
        return DetectionContext(self.scenario.zones, self.scenario.receivers, self.baseline, set(self.store.allowlist))

    def events(self) -> list[Event]:
        with self.lock:
            key = (self.cfg.to_dict(), tuple(sorted(self.store.allowlist)))
            if self._events is None or self._evt_cfg != key:
                ev = run_all(self.scenario.tracks, self.scenario.t0, self.scenario.t1, self._context(), self.cfg)
                for e in ev:
                    e.metrics["detected_at"] = float(_DETECT_LAG[e.kind](e, self.cfg))
                self._events, self._evt_cfg = ev, key
            return self._events

    def alerts(self, as_of: float | None = None, include_dismissed: bool = False) -> list[Alert]:
        evs = self.events()
        if as_of is not None:
            evs = [e for e in evs if e.metrics.get("detected_at", e.t_end) <= as_of]
        al = build_alerts(evs, self.scenario.tracks, self.cfg, self.store)
        for a in al:
            self.store.apply(a)
            a.raised_at = min(e.metrics.get("detected_at", e.t_end) for e in a.events if e.kind != "dark_rendezvous") \
                if any(e.kind != "dark_rendezvous" for e in a.events) else a.t_end
        if not include_dismissed:
            al = [a for a in al if a.status != "false_alarm"]
        return al

    def alert(self, alert_id: str) -> Alert | None:
        return next((a for a in self.alerts(include_dismissed=True) if a.id == alert_id), None)

    # -- payloads ----------------------------------------------------------- #
    def meta(self) -> dict[str, Any]:
        s = self.scenario
        return {
            "name": s.name, "t0": s.t0, "t1": s.t1, "vessels": len(s.tracks),
            "fixes": int(sum(len(t) for t in s.tracks)),
            "zones": [{"id": z.id, "name": z.name, "kind": z.kind, "description": z.description,
                       "polygon": [[round(a, 4), round(b, 4)] for a, b in z.polygon]} for z in s.zones],
            "receivers": [{"id": r.id, "lat": r.lat, "lon": r.lon, "range_nm": r.range_nm} for r in s.receivers],
            "simulated": True,
        }

    def tracks(self) -> list[dict[str, Any]]:
        out = []
        for t in self.scenario.tracks:
            out.append({
                "mmsi": t.mmsi, "name": t.name, "type": t.ship_type, "flag": t.flag,
                "t": [int(x) for x in t.t],
                "lat": [round(float(x), 4) for x in t.lat], "lon": [round(float(x), 4) for x in t.lon],
                "sog": [round(float(x), 1) if np.isfinite(x) else None for x in t.sog],
            })
        return out

    def truth(self) -> list[dict[str, Any]]:
        return [{"id": t.id, "kind": t.kind, "mmsis": list(t.mmsis), "t_start": t.t_start, "t_end": t.t_end,
                 "note": t.note, "benign": t.benign} for t in self.scenario.truth]

    def evaluation(self) -> dict[str, Any]:
        al = self.alerts(include_dismissed=True)
        return evaluate_alerts(al, self.scenario)

    def config(self) -> dict[str, Any]:
        return {"values": self.cfg.to_dict(), "specs": PARAM_SPECS, "defaults": DetectionConfig().to_dict()}

    def set_config(self, values: dict[str, Any]) -> None:
        with self.lock:
            merged = self.cfg.to_dict()
            merged.update({k: v for k, v in values.items() if k in merged})
            self.cfg = DetectionConfig.from_dict(merged)

    def reset_config(self) -> None:
        with self.lock:
            self.cfg = DetectionConfig()


_service: DetectionService | None = None
_lock = threading.Lock()


def get_service() -> DetectionService:
    global _service
    with _lock:
        if _service is None:
            _service = DetectionService()
        return _service
