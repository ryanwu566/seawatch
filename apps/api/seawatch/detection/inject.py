"""Splice labelled behaviours into REAL tracks.

Real AIS archives contain no ground truth for "interesting" behaviour. Injecting
known events into genuine tracks gives us (a) realistic background traffic and
(b) labels, so models can be trained and recall can be measured without pretending
that any real vessel did something it did not.
"""

from __future__ import annotations

import copy
import math

import numpy as np

from .geo import NM_M, destination, haversine_m
from .models import Track, TruthEvent


_SCALE = 1.0  # event-duration multiplier (4 for hourly data)
_MAXDT = 600.0  # cadence ceiling when synthesising fixes
_VETO = None  # optional callable(track, index, kind) -> True when the spot is somewhere the behaviour would be unremarkable
_BOUNDS: tuple[float, float, float, float] | None = None  # monitored-area box; events are kept clear of its edge


def _edge_ok(lat: float, lon: float, margin_nm: float = 4.0) -> bool:
    if _BOUNDS is None:
        return True
    la0, lo0, la1, lo1 = _BOUNDS
    m = margin_nm / 60.0
    return la0 + m < lat < la1 - m and lo0 + m < lon < lo1 - m


def _moving_idx(tr: Track, lo_s: float, hi_s: float, min_sog: float = 4.0, kind: str = "") -> list[int]:
    """Indices in the track's interior where the vessel is under way and has context on both sides."""

    sog = np.nan_to_num(tr.sog, nan=0.0)
    ok = (sog >= min_sog) & (tr.t >= tr.t[0] + lo_s) & (tr.t <= tr.t[-1] - hi_s)
    return [int(i) for i in np.where(ok)[0] if _edge_ok(tr.lat[i], tr.lon[i]) and not (_VETO is not None and _VETO(tr, int(i), kind))]


def _candidates(tracks: list[Track], span_h: float, min_fixes: int = 30, max_p95_dt: float | None = None,
                exclude_types: tuple[str, ...] = ()) -> list[Track]:
    """Vessels worth injecting into: long enough, moving, (optionally) regular reporters of a type for which the behaviour is odd."""

    return [t for t in tracks if len(t) > min_fixes and (t.t[-1] - t.t[0]) >= span_h * 3600
            and np.nanmedian(np.nan_to_num(t.sog, nan=0.0)) >= 0.5 and t.ship_type not in exclude_types
            and (max_p95_dt is None or np.percentile(np.diff(t.t), 95) <= max_p95_dt)]


def dark_gap(tr: Track, rng: np.random.Generator):
    idx = _moving_idx(tr, 1800 * _SCALE, 4 * 3600 * _SCALE, kind="dark_gap")
    if not idx:
        return None
    i = int(rng.choice(idx))
    dur = rng.uniform(45, 180) * 60 * _SCALE
    j = int(np.searchsorted(tr.t, tr.t[i] + dur))
    if j >= len(tr) or haversine_m(tr.lat[i], tr.lon[i], tr.lat[j], tr.lon[j]) < 3 * NM_M or not _edge_ok(tr.lat[j], tr.lon[j]):
        return None  # the vessel must really travel while dark
    keep = ~((tr.t >= tr.t[i]) & (tr.t <= tr.t[i] + dur))
    if keep.all():
        return None
    out = tr.slice(0, len(tr))
    for f in ("t", "lat", "lon", "sog", "cog"):
        setattr(out, f, getattr(tr, f)[keep])
    return out, TruthEvent("", "dark_gap", (tr.mmsi,), float(tr.t[i]), float(tr.t[i] + dur), "AIS switched off while under way")


def loitering(tr: Track, rng: np.random.Generator):
    idx = _moving_idx(tr, 1800 * _SCALE, 5 * 3600 * _SCALE, kind="loitering")
    if not idx:
        return None
    i = int(rng.choice(idx))
    dur = rng.uniform(90, 240) * 60 * _SCALE
    dt = float(np.clip(np.median(np.diff(tr.t[max(0, i - 20): i + 20])), 30, _MAXDT))
    n = max(4, int(dur / dt))
    r = rng.uniform(0.5, 1.2) * NM_M
    c_lat, c_lon = tr.lat[i], tr.lon[i]
    ang = np.radians(rng.uniform(0, 360)) + np.arange(1, n + 1) * (2.5 * 0.5144 * dt / r)
    lat = c_lat + r * np.cos(ang) / 111_320.0
    lon = c_lon + r * np.sin(ang) / (111_320.0 * math.cos(math.radians(c_lat)))
    t_new = tr.t[i] + np.arange(1, n + 1) * dt
    shift = n * dt
    out = tr.slice(0, len(tr))
    out.t = np.concatenate([tr.t[: i + 1], t_new, tr.t[i + 1:] + shift])
    out.lat = np.concatenate([tr.lat[: i + 1], lat, tr.lat[i + 1:]])
    out.lon = np.concatenate([tr.lon[: i + 1], lon, tr.lon[i + 1:]])
    out.sog = np.concatenate([tr.sog[: i + 1], np.abs(2.5 + rng.normal(0, 0.3, n)), tr.sog[i + 1:]])
    out.cog = np.concatenate([tr.cog[: i + 1], (np.degrees(ang) + 90) % 360, tr.cog[i + 1:]])
    return out, TruthEvent("", "loitering", (tr.mmsi,), float(tr.t[i]), float(tr.t[i] + shift), "Circling at slow speed in open water")


def position_jump(tr: Track, rng: np.random.Generator):
    idx = _moving_idx(tr, 1800 * _SCALE, 3600 * _SCALE, kind="position_jump")
    if not idx:
        return None
    i = int(rng.choice(idx))
    k = int(rng.integers(3, 7)) if _SCALE <= 1 else int(rng.integers(2, 4))
    if i + k >= len(tr):
        return None
    brg, dist = rng.uniform(0, 360), rng.uniform(40, 90) * NM_M
    out = tr.slice(0, len(tr))
    out.lat, out.lon = tr.lat.copy(), tr.lon.copy()
    for j in range(i, i + k):
        out.lat[j], out.lon[j] = destination(tr.lat[j], tr.lon[j], brg, dist)
    return out, TruthEvent("", "position_jump", (tr.mmsi,), float(tr.t[i]), float(tr.t[i + k]), "Position displaced while speed stays normal")


def identity_conflict(tr: Track, rng: np.random.Generator, pool: list[Track]):
    others = [o for o in pool if o.mmsi != tr.mmsi]
    rng.shuffle(others)
    for o in others[:40]:
        lo, hi = max(tr.t[0], o.t[0]), min(tr.t[-1], o.t[-1])
        if hi - lo < 4 * 3600 * _SCALE:
            continue
        a = rng.uniform(lo, hi - 3 * 3600 * _SCALE)
        b = a + rng.uniform(3, 6) * 3600 * _SCALE
        m = (o.t >= a) & (o.t <= b)
        if m.sum() < 8:
            continue
        # skip pairs that are naturally close together (not a conflict)
        if np.hypot(o.lat[m].mean() - tr.lat.mean(), o.lon[m].mean() - tr.lon.mean()) < 0.1:
            continue
        t = np.concatenate([tr.t, o.t[m]])
        order = np.argsort(t, kind="stable")
        out = tr.slice(0, len(tr))
        out.t = t[order]
        out.lat = np.concatenate([tr.lat, o.lat[m]])[order]
        out.lon = np.concatenate([tr.lon, o.lon[m]])[order]
        out.sog = np.concatenate([tr.sog, o.sog[m]])[order]
        out.cog = np.concatenate([tr.cog, o.cog[m]])[order]
        return out, TruthEvent("", "identity_conflict", (tr.mmsi,), float(a), float(b), "Same MMSI reported from two places")
    return None


def route_deviation(tr: Track, rng: np.random.Generator):
    idx = _moving_idx(tr, 3600, 4 * 3600, min_sog=5.0)
    if not idx:
        return None
    i = int(rng.choice(idx))
    dur = rng.uniform(1.5, 3.5) * 3600
    m = (tr.t >= tr.t[i]) & (tr.t <= tr.t[i] + dur)
    if m.sum() < 6:
        return None
    off_nm = rng.uniform(6, 15) * rng.choice([-1, 1])
    ramp = np.sin(np.pi * (tr.t[m] - tr.t[i]) / dur)
    out = tr.slice(0, len(tr))
    out.lat, out.lon = tr.lat.copy(), tr.lon.copy()
    # one smooth lateral shift, perpendicular to the segment's overall direction
    idx = np.where(m)[0]
    dy, dx = tr.lat[idx[-1]] - tr.lat[idx[0]], (tr.lon[idx[-1]] - tr.lon[idx[0]]) * math.cos(math.radians(tr.lat[i]))
    if math.hypot(dx, dy) * 60 < 1.0:
        return None  # not really travelling anywhere
    perp = math.atan2(dx, dy) + math.pi / 2
    out.lat[m] += off_nm / 60.0 * ramp * math.cos(perp)
    out.lon[m] += off_nm / 60.0 * ramp * math.sin(perp) / max(0.2, math.cos(math.radians(tr.lat[i])))
    return out, TruthEvent("", "route_deviation", (tr.mmsi,), float(tr.t[i]), float(tr.t[i] + dur), "Leaves its usual path for open water")


def survey_pattern(tr: Track, rng: np.random.Generator):
    """Hourly-feed only: insert a lawnmower / zig-zag / race-track survey (>= 4 legs of 24-60 nm) into an under-way vessel."""

    if _SCALE <= 1:
        return None
    from .surveyml import sample_polyline, synth_polyline

    idx = _moving_idx(tr, 1800 * _SCALE, 12 * 3600 * _SCALE, kind="survey_pattern")
    if not idx:
        return None
    i = int(rng.choice(idx))
    dt = float(np.clip(np.median(np.diff(tr.t[max(0, i - 20): i + 20])), 600, _MAXDT))
    for _ in range(10):
        hours = float(rng.uniform(40, 90))
        made = synth_polyline(rng, str(rng.choice(["lawnmower", "zigzag", "racetrack"])), hours)
        if made is not None and 2.5 <= made[1] <= 8.5:
            break
    else:
        return None
    poly, speed = made
    n = max(8, int(hours * 3600 / dt))
    tt = tr.t[i] + np.arange(1, n + 1) * dt
    xy = sample_polyline(poly, speed, tt)
    lat = tr.lat[i] + xy[:, 1] / 60.0
    lon = tr.lon[i] + xy[:, 0] / 60.0 / max(0.2, math.cos(math.radians(tr.lat[i])))
    shift = n * dt
    out = tr.slice(0, len(tr))
    out.t = np.concatenate([tr.t[: i + 1], tt, tr.t[i + 1:] + shift])
    out.lat = np.concatenate([tr.lat[: i + 1], lat, tr.lat[i + 1:]])
    out.lon = np.concatenate([tr.lon[: i + 1], lon, tr.lon[i + 1:]])
    out.sog = np.concatenate([tr.sog[: i + 1], np.full(n, speed), tr.sog[i + 1:]])
    out.cog = np.concatenate([tr.cog[: i + 1], np.full(n, np.nan), tr.cog[i + 1:]])
    return out, TruthEvent("", "survey_pattern", (tr.mmsi,), float(tr.t[i]), float(tr.t[i] + shift), "Runs a survey-like lawnmower / zig-zag pattern")


INJECTORS = ["dark_gap", "loitering", "position_jump", "identity_conflict", "route_deviation"]


def inject(tracks: list[Track], seed: int, per_kind: int = 6,
           bounds: tuple[float, float, float, float] | None = None, kinds: list[str] | None = None,
           time_scale: float = 1.0, max_dt: float = 600.0, snap_cell: float | None = None, min_fixes: int = 30,
           max_p95_dt: float | None = None, exclude_types: tuple[str, ...] = (), veto=None) -> tuple[list[Track], list[TruthEvent]]:
    """Return (tracks-with-injections, truth). Each injection uses a distinct vessel; originals are untouched."""

    global _BOUNDS, _SCALE, _MAXDT, _VETO
    _BOUNDS, _SCALE, _MAXDT, _VETO = bounds, time_scale, max_dt, veto
    rng = np.random.default_rng(seed)
    pool = _candidates(tracks, 6 * time_scale if time_scale > 1 else 6, min_fixes, max_p95_dt, exclude_types)
    order = [int(i) for i in rng.permutation(len(pool))]
    out = {t.mmsi: t for t in tracks}
    truth: list[TruthEvent] = []
    used: set[str] = set()
    n = 0
    for kind in (kinds or INJECTORS):
        done = 0
        for pi in order:
            if done >= per_kind:
                break
            tr = pool[pi]
            if tr.mmsi in used:
                continue
            fn = globals()[kind]
            res = fn(tr, rng, pool) if kind == "identity_conflict" else fn(tr, rng)
            if res is None:
                continue
            new, tev = res
            if new.status is not None and len(new.status) != len(new.t):
                new.status = None  # array lengths changed; status unknown for this injected vessel
            if snap_cell:
                new.lat = np.round(new.lat / snap_cell) * snap_cell
                new.lon = np.round(new.lon / snap_cell) * snap_cell
            out[tr.mmsi] = new
            used.add(tr.mmsi)
            n += 1
            truth.append(TruthEvent(f"I{n:03d}", tev.kind, tev.mmsis, tev.t_start, tev.t_end, tev.note))
            done += 1
    return list(out.values()), truth
