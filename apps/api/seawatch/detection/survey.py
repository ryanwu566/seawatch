"""Survey-like track patterns: lawnmower / zig-zag legs.

Repeated, similar-length, laterally stepped legs in open water are what survey work looks like (seismic, seabed mapping,
cable inspection, oceanographic research). They are not what transit, fishing, or ferry shuttling look like. The detector
describes *how the ship moved*; it cannot know what instrument was deployed or why.
"""

from __future__ import annotations

import math

import numpy as np

from .config import DetectionConfig
from .context import SENSITIVE_KINDS, DetectionContext
from .geo import NM_M, project_xy_m
from .models import Event, Track

SURVEY_EXEMPT = ("fishing", "pleasure", "passenger", "ferry", "tug", "pilot", "sar", "service", "dredger")


def _fmt_dur(seconds: float) -> str:
    m = int(round(seconds / 60))
    return f"{m // 60}h {m % 60:02d}m" if m >= 60 else f"{m} min"


def zigzag(s: np.ndarray, thr: float) -> list[int]:
    """Indices of turning points of a 1-D signal; a reversal needs an excursion of at least ``thr``."""

    tp: list[int] = []
    trend, ext = 0, 0
    for i in range(1, len(s)):
        if trend == 0:
            if s[i] - s[0] >= thr:
                trend, ext = 1, i
            elif s[0] - s[i] >= thr:
                trend, ext = -1, i
        elif trend == 1:
            if s[i] > s[ext]:
                ext = i
            elif s[ext] - s[i] >= thr:
                tp.append(ext)
                trend, ext = -1, i
        else:
            if s[i] < s[ext]:
                ext = i
            elif s[i] - s[ext] >= thr:
                tp.append(ext)
                trend, ext = 1, i
    return tp


def long_legs(x: np.ndarray, y: np.ndarray, min_leg_nm: float, min_move_nm: float = 3.0, turn_deg: float = 60.0) -> list[tuple[int, int, float]]:
    """Straight runs ("legs") of a track, as (start index, end index, heading in radians). Jitter below ``min_move_nm`` is ignored;
    a leg ends when the heading turns more than ``turn_deg`` away from the leg's running mean heading. Only legs at least
    ``min_leg_nm`` long are returned."""

    keep = [0]
    for i in range(1, len(x)):
        if np.hypot(x[i] - x[keep[-1]], y[i] - y[keep[-1]]) >= min_move_nm:
            keep.append(i)
    if len(keep) < 3:
        return []
    hx = np.diff(x[keep])
    hy = np.diff(y[keep])
    head = np.arctan2(hy, hx)
    legs: list[tuple[int, int, float]] = []
    start, mx, my = 0, hx[0], hy[0]
    thr = np.radians(turn_deg)
    for j in range(1, len(head)):
        mean_h = math.atan2(my, mx)
        d = abs((head[j] - mean_h + math.pi) % (2 * math.pi) - math.pi)
        if d > thr:
            legs.append((keep[start], keep[j], mean_h))
            start, mx, my = j, hx[j], hy[j]
        else:
            mx, my = mx + hx[j], my + hy[j]
    legs.append((keep[start], keep[len(head)], math.atan2(my, mx)))
    return [(a, b, h) for a, b, h in legs if np.hypot(x[b] - x[a], y[b] - y[a]) >= min_leg_nm]


def survey_windows(tr: Track, cfg: DetectionConfig, benign_mask) -> list[tuple[int, int, dict]]:
    """Index ranges of ``tr`` that look like a survey pattern, with their descriptors.

    A pattern is a run of at least ``survey_min_legs`` long legs, each turned back on the previous one (U-turn or sharp zig-zag, >= 105 degrees),
    of similar length, stepped sideways from one another (not the same line retraced), at towing speed, away from ports.
    """

    win = cfg.survey_window_h * 3600.0
    if len(tr) < 10 or tr.t[-1] - tr.t[0] < win * 0.5:
        return []
    x, y = project_xy_m(tr.lat, tr.lon)
    x, y = x / NM_M, y / NM_M
    min_leg = cfg.survey_min_leg_nm
    found: list[tuple[int, int, dict]] = []
    start = tr.t[0]
    while start < tr.t[-1] - win * 0.5:
        i0, i1 = int(np.searchsorted(tr.t, start)), int(np.searchsorted(tr.t, start + win))
        start += win / 2
        if i1 - i0 < 10:
            continue
        legs = long_legs(x[i0:i1], y[i0:i1], min_leg, min_move_nm=max(2.0, min_leg * 0.2))
        best: list[tuple[int, int, float]] = []
        # strategy A keeps legs parallel / anti-parallel to the longest leg (lawnmower, race-track, saw-tooth) and so drops
        # perpendicular connectors; strategy B keeps every long leg (zig-zag). Take whichever gives the longer U-turn run.
        variants = [legs]
        if legs:
            lens_all = [np.hypot(x[i0 + b] - x[i0 + a], y[i0 + b] - y[i0 + a]) for a, b, _ in legs]
            axis = legs[int(np.argmax(lens_all))][2]
            variants.append([lg for lg in legs if min(abs((lg[2] - axis) % math.pi), math.pi - abs((lg[2] - axis) % math.pi)) <= math.radians(35)])
        for cand in variants:
            run = [cand[0]] if cand else []
            for k in range(1, len(cand)):
                dh = abs((cand[k][2] - cand[k - 1][2] + math.pi) % (2 * math.pi) - math.pi)
                if math.radians(105) <= dh:
                    run.append(cand[k])
                else:
                    best = run if len(run) > len(best) else best
                    run = [cand[k]]
            best = run if len(run) > len(best) else best
        if len(best) < cfg.survey_min_legs:
            continue
        sel = best
        lens = np.array([np.hypot(x[i0 + b] - x[i0 + a], y[i0 + b] - y[i0 + a]) for a, b, _ in sel])
        if float(np.std(lens) / max(np.mean(lens), 1e-6)) > 0.6:
            continue
        mids = np.array([[(x[i0 + a] + x[i0 + b]) / 2, (y[i0 + a] + y[i0 + b]) / 2] for a, b, _ in sel])
        dirs = np.array([[math.cos(h), math.sin(h)] for _, _, h in sel])
        lateral = []
        for k in range(1, len(sel)):
            d = mids[k] - mids[k - 1]
            lateral.append(abs(d[0] * -dirs[k - 1][1] + d[1] * dirs[k - 1][0]))
        lateral_arr = np.array(lateral)
        if float(np.mean(lateral_arr)) < 0.08 * float(np.mean(lens)):
            continue  # the same line retraced (a shuttle), not stepped survey lines
        a0, b0 = i0 + sel[0][0], i0 + sel[-1][1]
        seg_len = float(np.sum(np.hypot(np.diff(x[a0:b0 + 1]), np.diff(y[a0:b0 + 1]))))
        span_h = (tr.t[b0] - tr.t[a0]) / 3600.0
        if span_h <= 0 or seg_len / span_h > 9.0:
            continue  # too fast for towing survey gear
        turn_idx = [i0 + sel[k][0] for k in range(len(sel))]
        if float(np.mean(benign_mask(tr.lat[turn_idx], tr.lon[turn_idx]))) > 0.4:
            continue  # turning around in port approaches / at stopping areas
        found.append((a0, b0, {"legs": len(sel), "mean_leg_nm": float(np.mean(lens)), "spacing_nm": float(np.mean(lateral_arr)),
                                "area_nm2": float(np.ptp(x[a0:b0 + 1]) * np.ptp(y[a0:b0 + 1])), "hours": span_h, "path_nm": seg_len}))
    merged: list[list] = []
    for a, b, m in sorted(found):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
            if m["legs"] > merged[-1][2]["legs"]:
                merged[-1][2] = m
        else:
            merged.append([a, b, m])
    return [(a, b, m) for a, b, m in merged]


def detect_survey_pattern(tracks: list[Track], ctx: DetectionContext, cfg: DetectionConfig) -> list[Event]:
    out: list[Event] = []
    for tr in tracks:
        if tr.ship_type in SURVEY_EXEMPT:
            continue
        for a, b, m in survey_windows(tr, cfg, ctx.benign_mask):
            la, lo = float(np.mean(tr.lat[a:b + 1])), float(np.mean(tr.lon[a:b + 1]))
            zone, dz = ctx.nearest_zone(la, lo, SENSITIVE_KINDS)
            sev = 78 + 4 * min(m["legs"] - cfg.survey_min_legs, 5)
            ev = [f"Ran {m['legs']} roughly parallel legs of ~{m['mean_leg_nm']:.0f} nm each, stepping ~{m['spacing_nm']:.0f} nm sideways, over "
                  f"{_fmt_dur(m['hours'] * 3600)} - a lawnmower / zig-zag survey pattern covering ~{m['area_nm2']:.0f} nm²."]
            if zone is not None and dz <= 40:
                sev += 12
                ev.append(f"The survey area is {dz:.0f} nm from {zone.name}.")
            if tr.ship_type == "seismic":
                sev -= 25
                ev.append("Registered as a seismic survey vessel - this pattern is its normal work; weighting reduced.")
            step = max(1, (b - a) // 60)
            out.append(Event(
                "", "survey_pattern", [tr.mmsi], float(tr.t[a]), float(tr.t[b]), la, lo, float(max(0.0, min(100.0, sev))), 0.8,
                f"{tr.name}: survey-like track pattern ({m['legs']} legs)", ev,
                ["Commercial seismic or hydrographic survey", "Oceanographic or fisheries research cruise",
                 "Cable laying / repair or pipeline inspection", "Search for a lost object"],
                ["AIS shows the track, not the instrument - it cannot show whether sensors are deployed or what is being mapped."],
                {k: round(float(v), 1) for k, v in m.items()},
                path=[(float(p), float(q)) for p, q in zip(tr.lat[a:b + 1:step], tr.lon[a:b + 1:step])]))
    return out
