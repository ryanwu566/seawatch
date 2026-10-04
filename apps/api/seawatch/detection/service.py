"""Detection service: scenario + baseline + config + operator feedback behind one object."""

from __future__ import annotations

import os
import threading
from typing import Any

import numpy as np

from .alerts import Alert, build_alerts
from .config import PARAM_SPECS, PARAM_SPECS_HOURLY, DetectionConfig
from .context import DetectionContext, TrafficBaseline
from .detectors import run_all
from .evaluation import evaluate_alerts
from .models import Event, Scenario
from .simulator import build_scenario, normal_traffic
from . import ml as mlmod
from .features import PORTABLE
from .state import FeedbackStore, default_store

REGIONS: dict[str, dict[str, Any]] = {
    "sf-bay": {
        "label": "San Francisco Bay", "timezone": "America/Los_Angeles", "data_kind": "real_plus_injected",
        "note": "Real recorded AIS (NOAA, 3 Jan 2024) with labelled behaviours added. Models learned from the 1-2 Jan history.",
        "model_path": "data/models/ml_sf-bay.joblib", "features": PORTABLE,
    },
    "taiwan-gfw": {
        "label": "Taiwan waters - real AIS presence (GFW, Sep 2026)", "timezone": "Asia/Taipei", "data_kind": "real_plus_injected",
        "note": "Real hourly AIS presence (Global Fishing Watch, ~11 km cells, 1-29 Sep 2026) with labelled behaviours added. "
                "History (1-25 Sep) trains the baselines; the last 4 days are monitored. Not message-level AIS.",
        "model_path": "data/models/ml_taiwan-gfw.joblib", "features": PORTABLE, "hourly": True,
        "only": ("survey_threat", "survey_pattern", "zone_entry", "position_jump", "cable_activity"),
    },
    "taiwan-research": {
        "label": "Research vessels near Taiwan - real AIS (1-16 Apr 2026)", "timezone": "Asia/Taipei", "data_kind": "real",
        "note": "Real message-level AIS of ~80 research / survey-type vessels (hackathon-supplied). Nothing injected; normal traffic learned from the 2-3 Apr full-day file.",
        "model_path": "data/models/none.joblib", "features": None, "dense": True,
        "only": ("survey_threat", "survey_pattern", "zone_entry"),  # the fleet sits in Chinese ports outside any learned coverage: generic gap/loiter rules would be noise
    },
    "taiwan-day": {
        "label": "Taiwan waters - real AIS, one full day (3 Apr 2026)", "timezone": "Asia/Taipei", "data_kind": "real",
        "note": "Real message-level AIS of the whole area (hackathon-supplied) with research vessels included. Nothing injected; learned from 2 Apr, monitored 3 Apr.",
        "model_path": "data/models/none.joblib", "features": None, "dense": True,
        # national-threat focus: gaps, loitering, rendezvous and clusters are not reliable enough here (see docs/rules-walkthrough.md)
        "only": ("survey_threat", "survey_pattern", "zone_entry", "position_jump", "identity_conflict", "cable_activity"),
    },
    "taiwan": {
        "label": "Taiwan waters (simulated)", "timezone": "Asia/Taipei", "data_kind": "simulated",
        "note": "Fully simulated vessel tracks with labelled events - no live AIS feed connected.",
        "model_path": mlmod.MODEL_PATH, "features": None,
    },
}


def available_regions() -> list[dict[str, Any]]:
    from pathlib import Path

    out = []
    for rid, r in REGIONS.items():
        ok = True
        if rid == "sf-bay":
            ok = len(list(Path(".").glob("data/processed/sfbay_2024-01-0*.parquet"))) >= 2
        elif rid in ("taiwan-research", "taiwan-day"):
            from . import mentorworld

            ok = mentorworld.available()
        elif rid == "taiwan-gfw":
            from . import gfw

            ok = gfw.available()
        out.append({"id": rid, "label": r["label"], "data_kind": r["data_kind"], "available": ok})
    return out


def default_region() -> str:
    import os

    want = os.environ.get("SEAWATCH_REGION")
    avail = {r["id"]: r["available"] for r in available_regions()}
    if want in avail and avail[want]:
        return want
    for rid in ("taiwan-research", "taiwan-gfw", "sf-bay"):
        if avail.get(rid):
            return rid
    return "taiwan"

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
    "status_mismatch": lambda e, c: e.t_start + 900,
    "survey_pattern": lambda e, c: e.t_start + 0.6 * (e.t_end - e.t_start),
    "survey_threat": lambda e, c: e.t_start + 0.5 * (e.t_end - e.t_start),
    "cable_activity": lambda e, c: e.t_start + 0.6 * (e.t_end - e.t_start),
}


class DetectionService:
    def __init__(self, seed: int = 7, store: FeedbackStore | None = None, region: str = "taiwan"):
        self.lock = threading.RLock()
        self.seed = seed
        self.region = region
        self.info = REGIONS[region]
        self.hourly = bool(self.info.get("hourly"))
        self.dense = bool(self.info.get("dense"))
        self.cfg = DetectionConfig.hourly() if self.hourly else DetectionConfig.dense() if self.dense else DetectionConfig()
        self.store = store or default_store()
        self.watch = self._load_watchlists()
        self._events: list[Event] | None = None
        self._windows = None
        self._evt_cfg: dict | None = None
        self.parts: dict[str, Any] = {}
        if region == "taiwan-gfw":
            from . import twworld

            data = twworld.load()
            self.scenario, self.parts = twworld.build_tw_scenario(data)
            self.baseline = self.parts["baseline"]
            self._base_ctx = twworld.make_context(self.scenario, self.parts)
            self.learned = self.parts["learned"]
        elif region in ("taiwan-research", "taiwan-day"):
            from . import mentorworld

            self.scenario, self.parts = mentorworld.load(region)
            self.baseline = self.parts["baseline"]
            self._base_ctx = mentorworld.make_context(self.scenario, self.parts)
            self.learned = self.parts["learned"]
        elif region == "sf-bay":
            from . import sfworld

            days = sfworld.load_days(".")
            self.scenario, self.parts = sfworld.build_sf_scenario(days)
            self.baseline = self.parts["baseline"]
            self._base_ctx = sfworld.make_context(self.scenario, self.parts)
            self.learned = self.parts["learned"]
        else:
            self.scenario = build_scenario(seed)
            hist = [t for sd in (101, 102, 103) for t in normal_traffic(sd).tracks]
            self.baseline = TrafficBaseline().fit(hist)
            self._base_ctx = None
            self.learned = mlmod.make_learned(False)
        loaded = mlmod.load(self.info["model_path"], self.info["features"])
        self.ml_models, self.ml_report = loaded if loaded else (None, None)
        if self.ml_models is not None:  # scoring every window of a big feed takes minutes: do it off the request path
            threading.Thread(target=self._warm_windows, daemon=True).start()

    @staticmethod
    def _load_watchlists():
        """Reported research vessels (OSINT, cited) and the sanctions list, if present locally. Matched on IMO / MMSI only."""

        from pathlib import Path

        from . import labels

        items = []
        for loader, path in ((labels.load_osint, "data/labels/osint_vessels.csv"), (labels.load_ofac_sdn, "data/labels/ofac_sdn.csv")):
            if Path(path).exists():
                try:
                    items += loader(path)
                except Exception:  # noqa: BLE001 - a malformed list must never stop monitoring
                    pass
        return labels.LabelSet(items)

    # -- pipeline ---------------------------------------------------------- #
    def _context(self) -> DetectionContext:
        if self._base_ctx is not None:
            self._base_ctx.allowlist = set(self.store.allowlist)
            return self._base_ctx
        ctx = DetectionContext(self.scenario.zones, self.scenario.receivers, self.baseline, set(self.store.allowlist))
        if self.region == "taiwan":
            from .territory import Territory

            ctx.territory = Territory.default()
        return ctx

    def events(self) -> list[Event]:
        with self.lock:
            key = (self.cfg.to_dict(), tuple(sorted(self.store.allowlist)))
            if self._events is None or self._evt_cfg != key:
                ev = run_all(self.scenario.tracks, self.scenario.t0, self.scenario.t1, self._context(), self.cfg)
                only = self.info.get("only")
                if only:
                    ev = [e for e in ev if e.kind in only]
                for e in ev:
                    e.metrics["detected_at"] = float(_DETECT_LAG[e.kind](e, self.cfg))
                self._events, self._evt_cfg = ev, key
            return self._events

    def _warm_windows(self) -> None:
        try:
            from .features import window_features

            df = window_features(self.scenario.tracks, self.scenario.t0, self.scenario.t1, self._context(),
                                 learned=self.learned, cfg=self.cfg if self.hourly else None)
            df["gb"] = self.ml_models.gb_score(df)
            df["if"] = self.ml_models.if_score(df)
            self._windows = df
        except Exception:  # noqa: BLE001 - the ML second opinion is optional; never block monitoring
            self._windows = None

    def ml_windows(self):
        """ML window scores for the live scenario; None until the background scoring has finished (or if no model exists)."""

        return self._windows if self.ml_models is not None else None

    def alerts(self, as_of: float | None = None, include_dismissed: bool = False) -> list[Alert]:
        evs = self.events()
        if as_of is not None:
            evs = [e for e in evs if e.metrics.get("detected_at", e.t_end) <= as_of]
        al = build_alerts(evs, self.scenario.tracks, self.cfg, self.store, self.watch)
        for a in al:
            self.store.apply(a)
            a.raised_at = min(e.metrics.get("detected_at", e.t_end) for e in a.events if e.kind != "dark_rendezvous") \
                if any(e.kind != "dark_rendezvous" for e in a.events) else a.t_end
            w = self.ml_windows()
            if w is not None:
                a.ml = mlmod.score_alert(self.ml_models, w, a.mmsis, a.t_start, a.t_end, a.risk)
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
            "simulated": self.info["data_kind"] == "simulated",
            "hourly": self.hourly, "tracks_sampled": len(self.scenario.tracks) > 2500,
            "region": self.region, "region_label": self.info["label"], "timezone": self.info["timezone"],
            "data_kind": self.info["data_kind"], "note": self.info["note"], "bounds": self.bounds(),
        }

    def bounds(self) -> list[list[float]]:
        la = np.concatenate([t.lat for t in self.scenario.tracks]); lo = np.concatenate([t.lon for t in self.scenario.tracks])
        return [[float(lo.min()) - 0.05, float(la.min()) - 0.05], [float(lo.max()) + 0.05, float(la.max()) + 0.05]]

    def tracks(self, max_tracks: int = 2500) -> list[dict[str, Any]]:
        """Tracks for the map. Big feeds are sampled: every vessel in an alert or a known event, plus the longest others."""

        out = []
        tracks = self.scenario.tracks
        if len(tracks) > max_tracks:
            keep = {m for a in self.alerts(include_dismissed=True) for m in a.mmsis} | {m for t in self.scenario.truth for m in t.mmsis}
            rest = sorted((t for t in tracks if t.mmsi not in keep), key=lambda t: -len(t))[: max(0, max_tracks - len(keep))]
            tracks = [t for t in tracks if t.mmsi in keep] + rest
        for t in tracks:
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
        if not self.scenario.truth:  # real data without labels: there is nothing to score against, say so rather than report 0%
            return {"alerts": len(al), "true_alerts": 0, "false_alarms": 0, "false_alarms_on_benign_lookalikes": 0, "precision": 0.0, "recall": 0.0,
                    "f1": 0.0, "alerts_per_100_vessel_days": 0.0, "false_alarms_per_100_vessel_days": 0.0, "real_background": True,
                    "per_kind": {}, "missed": [], "false_alarm_ids": [], "unlabelled": True}
        scn = self.scenario
        only = self.info.get("only")
        if only:  # score only the behaviours this region reports
            from dataclasses import replace

            from .evaluation import ACCEPT

            scn = replace(scn, truth=[t for t in scn.truth if ACCEPT.get(t.kind, {t.kind}) & set(only)])
        out = evaluate_alerts(al, scn)
        out["real_background"] = self.info["data_kind"] == "real_plus_injected"
        return out


    # -- compact historical runtime ---------------------------------------- #

    def historical_summary(self) -> dict[str, Any]:
        """Metadata for the compact historical runtime, when available."""

        from . import historical_runtime

        if not historical_runtime.available():
            return {
                "available": False,
                "reason": "historical_runtime_not_available",
            }

        return historical_runtime.summary()

    def historical_context(
        self,
        mmsi: str,
        lat: float | None = None,
        lon: float | None = None,
    ) -> dict[str, Any]:
        """Historical baseline and coarse traffic context for a live vessel.

        MMSI joins are conservative: only Runtime rows marked
        unique_9digit_candidate are returned.
        """

        from . import historical_runtime

        if not historical_runtime.available():
            return {
                "available": False,
                "joined": False,
                "reason": "historical_runtime_not_available",
                "baseline": None,
                "traffic": None,
            }

        baseline = historical_runtime.lookup_mmsi(mmsi)

        traffic = None

        if lat is not None and lon is not None:
            traffic = historical_runtime.traffic_at(
                lat,
                lon,
            )

        return {
            "available": True,
            "joined": baseline is not None,
            "join_status": (
                baseline.get("mmsi_join_status")
                if baseline is not None
                else "not_joinable_or_not_found"
            ),
            "baseline": baseline,
            "traffic": traffic,
        }


    def historical_for_alert(
        self,
        alert: Alert,
    ) -> dict[str, Any]:
        """Safe historical context for an alert.

        Raw MMSI and GFW vesselId are used internally for lookup only and are
        intentionally not added to this historical-context payload.
        """

        from . import historical_runtime

        if not historical_runtime.available():
            return {
                "available": False,
                "matched_vessels": 0,
                "total_vessels": len(alert.mmsis),
                "vessels": [],
                "traffic": None,
            }

        vessels = []

        for index, mmsi in enumerate(alert.mmsis):
            baseline = historical_runtime.lookup_mmsi(mmsi)

            if baseline is None:
                vessels.append({
                    "live_index": index,
                    "joined": False,
                    "join_status": "not_joinable_or_not_found",
                })
                continue

            vessels.append({
                "live_index": index,
                "joined": True,
                "join_status": baseline.get("mmsi_join_status"),
                "observed_days": baseline.get("observed_days"),
                "observation_count": baseline.get("observation_count"),
                "coverage_band": baseline.get("coverage_band"),
                "dataset_day_fraction": baseline.get("dataset_day_fraction"),
                "dominant_cell": [
                    baseline.get("dominant_cell_lat"),
                    baseline.get("dominant_cell_lon"),
                ],
                "dominant_cell_observation_share":
                    baseline.get("dominant_cell_observation_share"),
            })

        traffic = historical_runtime.traffic_at(
            alert.lat,
            alert.lon,
        )

        if traffic is not None:
            traffic = {
                "cell_lat": traffic.get("cell_lat"),
                "cell_lon": traffic.get("cell_lon"),
                "observation_count": traffic.get("observation_count"),
                "unique_vessel_count": traffic.get("unique_vessel_count"),
                "observed_days": traffic.get("observed_days"),
                "active_hour_buckets": traffic.get("active_hour_buckets"),
                "cell_active_hour_fraction":
                    traffic.get("cell_active_hour_fraction"),
                "avg_vessels_per_active_hour":
                    traffic.get("avg_vessels_per_active_hour"),
                "context_warning": traffic.get("context_warning"),
            }

        return {
            "available": True,
            "matched_vessels": sum(
                1 for item in vessels
                if item["joined"]
            ),
            "total_vessels": len(vessels),
            "vessels": vessels,
            "traffic": traffic,
            "source_note": (
                "GFW standardized hourly presence; "
                "coarse historical context, not raw AIS."
            ),
        }

    # -- path-analysis agent (advisory) ---------------------------------------- #
    def path_reviews(self):
        """Research-gate -> speed-gate -> shape features -> reviewer, for message-level regions. Cached; decisions come from the ReviewStore."""

        from . import pathagent
        from .cables import Cables
        from .territory import Territory

        if self.hourly:
            return [], {"note": "Hourly presence data has no speed or status: the path agent needs message-level AIS."}, "none"
        with self.lock:
            if getattr(self, "_path", None) is None:
                mode = os.environ.get("SEAWATCH_PATH_AGENT", "offline")
                reviewer = pathagent.OfflineReviewer()
                if mode == "claude" and pathagent.ClaudeReviewer.available():
                    reviewer = pathagent.ClaudeReviewer()
                second = pathagent.featherless_reviewer() if mode == "featherless" else None
                revs, funnel = pathagent.review_vessels(self.scenario.tracks, reviewer, Territory.default(), Cables.default())
                self._path = (revs, funnel, reviewer.name)
                if second is not None:  # rules answer immediately; the language-model second reading fills in from a background thread
                    by_id = {t.mmsi: t for t in self.scenario.tracks}
                    threading.Thread(target=lambda: pathagent.add_second_readings(revs, by_id, second), daemon=True).start()
            if getattr(self, "_review_store", None) is None:
                self._review_store = pathagent.ReviewStore()
            revs, funnel, rn = self._path
            for r in revs:
                self._review_store.apply(r)
            return revs, funnel, rn

    def review_store(self):
        self.path_reviews()
        return self._review_store

    def assessment(self) -> dict[str, Any]:
        """How well activity is identified and how signal is separated from noise: funnel, per-detector discards, factor table, recall."""

        from collections import Counter

        from .threat import factor_table

        evs = self.events()
        ctx = self._context()
        al = self.alerts(include_dismissed=True)
        tracks = self.scenario.tracks
        kinds = Counter(e.kind for e in evs)
        ml_on = any(a.ml and a.ml.get("available") for a in al)
        confirmed = [a for a in al if a.ml and a.ml.get("agreement") == "agree"]
        funnel = [
            {"stage": "vessels observed", "count": len(tracks)},
            {"stage": "vessels with at least one rule event", "count": len({m for e in evs for m in e.mmsis})},
            {"stage": "rule events", "count": len(evs)},
            {"stage": f"alerts (risk >= {self.cfg.alert_min_risk:g})", "count": len(al)},
        ]
        if ml_on:
            funnel.append({"stage": "alerts the statistical model also finds unusual", "count": len(confirmed)})
        funnel.append({"stage": f"high priority (risk >= {self.cfg.high_risk:g})", "count": sum(1 for a in al if a.level == "HIGH")})
        discards = sorted(({"detector": k[0], "reason": k[1], "count": int(v)}
                           for k, v in getattr(ctx, "stats", {}).items()), key=lambda r: -r["count"])
        threat = [e for e in evs if e.kind == "survey_threat"]
        classes = Counter(e.metrics.get("classification", "?") for e in threat)
        top = sorted(threat, key=lambda e: -e.severity)[:12]
        threat_rows = [{"mmsi": e.mmsis[0], "name": next((t.name for t in tracks if t.mmsi == e.mmsis[0]), ""), "rule": e.metrics.get("rule"),
                        "classification": e.metrics.get("classification"), "severity": round(float(e.severity), 1),
                        "factors": e.metrics.get("factors"), "evidence": e.evidence[:6]} for e in top]
        ev = self.evaluation()
        return {
            "region": self.region, "data_kind": self.info["data_kind"], "hourly": self.hourly, "funnel": funnel,
            "events_by_kind": dict(kinds), "discards": discards[:40],
            "factors": factor_table(tracks, ctx, self.cfg, evs) if ctx.territory is not None else None,
            "threat_classes": dict(classes), "threat_top": threat_rows,
            "evaluation": ev, "ml": self.ml_report,
            "ml_agreement": {"agree": len(confirmed), "rules_only": sum(1 for a in al if a.ml and a.ml.get("agreement") == "rules_only"),
                             "pending": not ml_on and self.ml_models is not None},
        }

    def config(self) -> dict[str, Any]:
        defaults = DetectionConfig.hourly() if self.hourly else DetectionConfig.dense() if self.dense else DetectionConfig()
        return {"values": self.cfg.to_dict(), "specs": PARAM_SPECS_HOURLY if self.hourly else PARAM_SPECS, "defaults": defaults.to_dict()}

    def set_config(self, values: dict[str, Any]) -> None:
        with self.lock:
            merged = self.cfg.to_dict()
            merged.update({k: v for k, v in values.items() if k in merged})
            self.cfg = DetectionConfig.from_dict(merged)

    def reset_config(self) -> None:
        with self.lock:
            self.cfg = DetectionConfig.hourly() if self.hourly else DetectionConfig.dense() if self.dense else DetectionConfig()


_service: DetectionService | None = None
_cache: dict[str, DetectionService] = {}
_lock = threading.Lock()


def get_service() -> DetectionService:
    global _service
    with _lock:
        if _service is None:
            rid = default_region()
            _service = _cache.setdefault(rid, DetectionService(region=rid))
        return _service


def set_region(region: str) -> DetectionService:
    global _service
    if region not in REGIONS:
        raise KeyError(region)
    with _lock:
        if region not in _cache:
            _cache[region] = DetectionService(region=region)
        _service = _cache[region]
        return _service
