"""Stable entry point for integrating the detection system with another data source (e.g. live provider tracks).

    result = analyze(tracks, context, cfg=..., as_of=..., density="message_level")

* ``tracks``   list of ``Track`` (models.py). Required per point: time (epoch s, ascending), lat, lon. Optional: sog, cog, status, plus
               Track-level name, ship_type, flag, imo and ``extra`` {"destination", "subtype", "tow_t"}.
* ``context``  a ``DetectionContext`` built by ``build_context`` from history (or reused across calls).
* ``density``  "message_level" (reports every few minutes), "sparse_live" (a handful of positions per vessel, minutes to hours apart) or
               "hourly_presence" (one position per hour, ~11 km cells). It selects the preset and which detectors are allowed to run.

The engine answers honestly when a detector cannot run: ``result.skipped`` lists, per detector, ``not_applicable`` (the data type can never
support it) or ``insufficient_data`` (too few points / too short a span on that track). Nothing is manufactured from one position.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .alerts import Alert, build_alerts
from .config import DetectionConfig
from .context import DetectionContext, TrafficBaseline
from .detectors import run_all
from .learned import LearnedContext, VesselHabits
from .models import Event, Track
from .territory import Territory

DENSITIES = ("message_level", "sparse_live", "hourly_presence")

#: what each detector needs. min_points / min_span_s apply per track; fields are Track attributes that must be populated.
REQUIREMENTS: dict[str, dict[str, Any]] = {
    "ais_gap": {"min_points": 6, "min_span_s": 3 * 3600, "fields": [], "densities": ["message_level", "sparse_live", "hourly_presence"]},
    "loitering": {"min_points": 8, "min_span_s": 1800, "fields": [], "densities": ["message_level", "hourly_presence"]},
    "rendezvous": {"min_points": 8, "min_span_s": 1800, "fields": [], "densities": ["message_level", "hourly_presence"]},
    "cluster": {"min_points": 8, "min_span_s": 1800, "fields": [], "densities": ["message_level", "hourly_presence"]},
    "zone_entry": {"min_points": 2, "min_span_s": 0, "fields": [], "densities": ["message_level", "sparse_live", "hourly_presence"]},
    "position_jump": {"min_points": 3, "min_span_s": 0, "fields": [], "densities": ["message_level", "sparse_live", "hourly_presence"]},
    "identity_conflict": {"min_points": 6, "min_span_s": 600, "fields": [], "densities": ["message_level"]},
    "status_mismatch": {"min_points": 5, "min_span_s": 900, "fields": ["status"], "densities": ["message_level", "sparse_live"]},
    "route_deviation": {"min_points": 8, "min_span_s": 3600, "fields": ["sog"], "densities": ["message_level", "hourly_presence"]},
    "survey_pattern": {"min_points": 24, "min_span_s": 12 * 3600, "fields": [], "densities": ["message_level", "hourly_presence"]},
    "survey_threat": {"min_points": 4, "min_span_s": 0, "fields": [], "densities": ["message_level", "sparse_live", "hourly_presence"]},
}
#: event kinds produced by each requirement entry (dark_rendezvous comes from ais_gap + loitering/rendezvous/cluster)
_KINDS = {"dark_rendezvous": ("ais_gap", "loitering")}
DEFAULT_PRESET = {"message_level": DetectionConfig.dense, "sparse_live": DetectionConfig, "hourly_presence": DetectionConfig.hourly}


@dataclass
class Skipped:
    detector: str
    reason: str  # not_applicable | insufficient_data
    tracks: int = 0  # how many tracks were affected (insufficient_data only)


@dataclass
class AnalysisResult:
    events: list[Event]
    alerts: list[Alert]
    skipped: list[Skipped] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)  # what each detector discarded as normal, and why
    n_tracks: int = 0
    n_analyzed: int = 0
    density: str = "message_level"


_LOCK = threading.RLock()  # DetectionContext holds mutable counters (ctx.stats) and the allow-list: one analysis per context at a time


def build_context(history: list[Track], density: str = "message_level", cfg: DetectionConfig | None = None,
                  bounds: tuple[float, float, float, float] | None = None, taiwan: bool = True) -> DetectionContext:
    """Learn normal behaviour from ``history`` (earlier tracks of the same area). Reuse the returned context across calls and rebuild it
    when history is refreshed (hours to days); it is the expensive part (seconds for ~10k vessels)."""

    cfg = cfg or DEFAULT_PRESET[density]()
    cell = 0.1 if density == "hourly_presence" else 0.01
    baseline = TrafficBaseline(cell_deg=cell).fit(history, max_dt_s=cfg.densify_max_dt_s)
    learned = LearnedContext(cell_deg=cfg.learn_cell_deg, min_slow_s=cfg.learn_min_slow_s, max_dt_s=cfg.learn_max_dt_s,
                             min_stop_vessels=cfg.learn_min_stop_vessels).fit(history)
    if bounds is None and history:
        bounds = (min(float(t.lat.min()) for t in history), min(float(t.lon.min()) for t in history),
                  max(float(t.lat.max()) for t in history), max(float(t.lon.max()) for t in history))
    ctx = DetectionContext([], [], baseline, learned=learned, bounds=bounds)
    ctx.habits = VesselHabits(cell_deg=cell, min_dwell_s=6 * 3600, max_dt_s=cfg.learn_max_dt_s).fit(history)
    if taiwan:
        ctx.territory = Territory.default()
    return ctx


def eligibility(tr: Track, density: str) -> dict[str, str | None]:
    """Per detector: None if it may run on this track, else 'not_applicable' / 'insufficient_data'."""

    out: dict[str, str | None] = {}
    span = float(tr.t[-1] - tr.t[0]) if len(tr) else 0.0
    for name, req in REQUIREMENTS.items():
        if density not in req["densities"]:
            out[name] = "not_applicable"
        elif any(getattr(tr, f, None) is None or (f == "sog" and not np.isfinite(tr.sog).any()) for f in req["fields"]):
            out[name] = "not_applicable"
        elif len(tr) < req["min_points"] or span < req["min_span_s"]:
            out[name] = "insufficient_data"
        else:
            out[name] = None
    return out


def analyze(tracks: list[Track], context: DetectionContext, cfg: DetectionConfig | None = None, as_of: float | None = None,
            density: str = "message_level", feedback=None, watch=None) -> AnalysisResult:
    """Run the deterministic detectors and alert fusion on ``tracks`` (reports after ``as_of`` are ignored). Safe to call repeatedly with
    updated tracks; it recomputes events for the tracks given (whole-track analysis, not incremental)."""

    if density not in DENSITIES:
        raise ValueError(f"density must be one of {DENSITIES}")
    cfg = cfg or DEFAULT_PRESET[density]()
    if as_of is not None:
        tracks = [s for t in tracks if (s := t.slice(0, int(np.searchsorted(t.t, as_of, "right")))) is not None and len(s) > 0]
    skipped: dict[tuple[str, str], int] = {}
    usable: list[Track] = []
    allowed: dict[str, set[str]] = {}
    for tr in tracks:
        el = eligibility(tr, density)
        ok = {d for d, v in el.items() if v is None}
        for d, v in el.items():
            if v is not None:
                skipped[(d, v)] = skipped.get((d, v), 0) + 1
        if ok:
            usable.append(tr)
            allowed[tr.mmsi] = ok
    if not usable:
        return AnalysisResult([], [], [Skipped(d, r, n) for (d, r), n in skipped.items()], {}, len(tracks), 0, density)
    t0 = min(float(t.t[0]) for t in usable)
    t1 = max(float(t.t[-1]) for t in usable) if as_of is None else float(as_of)
    with _LOCK:
        events = run_all(usable, t0, t1, context, cfg)
        stats = {f"{k}: {v}": int(n) for (k, v), n in context.stats.items()}
    keep = []
    for e in events:
        base = {"dark_rendezvous": "ais_gap"}.get(e.kind, e.kind)
        if all(base in allowed.get(m, set()) or m not in allowed for m in e.mmsis):
            keep.append(e)
    alerts = build_alerts(keep, usable, cfg, feedback, watch)
    sk = [Skipped(d, r, n) for (d, r), n in sorted(skipped.items())]
    return AnalysisResult(keep, alerts, sk, stats, len(tracks), len(usable), density)


def redact(obj: Any, public_id) -> Any:
    """Replace raw MMSIs in an API payload (alert summary / detail, tracks, path reviews) with ``public_id(mmsi)``.

    The detection payloads carry raw MMSIs (needed internally for watch-lists and historical joins). The handoff requires that raw MMSI /
    IMO / provider UUIDs are not serialised to the public frontend: wrap every outgoing payload with this using the identity registry, e.g.
    ``redact(alert.detail(), registry.public_id_for)``. Path-review ids (``P-<mmsi>-<t>``) are rewritten too.
    """

    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k == "mmsi" and isinstance(v, str):
                out[k] = public_id(v)
            elif k == "mmsis" and isinstance(v, list):
                out[k] = [public_id(x) if isinstance(x, str) else x for x in v]
            elif k in ("id", "windows") and isinstance(v, (str, list)) and "P-" in str(v):
                out[k] = _redact_review_id(v, public_id)
            else:
                out[k] = redact(v, public_id)
        return out
    if isinstance(obj, list):
        return [redact(x, public_id) for x in obj]
    return obj


def _redact_review_id(v, public_id):
    import re

    def one(s: str) -> str:
        m = re.match(r"^P-(\d{9})-(\d+)$", s)
        return f"P-{public_id(m.group(1))}-{m.group(2)}" if m else s

    return [one(x) for x in v] if isinstance(v, list) else one(v)
