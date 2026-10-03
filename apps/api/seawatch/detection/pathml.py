"""Path model: does the SHAPE of a slow vessel's track look like survey work?

Two stages, as an analyst would do it:

1. Filter: drop windows where the vessel is fast (transit) or not moving (moored / anchored). Only slow, moving stretches are looked at.
2. Shape model: describe each slow window by path-only features (turning, legs, re-traversal, parallelism, dwell, speed variability) and
   score how much it resembles windows in which vessels *announced* survey work (towing text in the destination, or sustained
   'restricted in ability to manoeuvre').

The labels come from what the vessels broadcast, the features from the path alone. So the model can be trained on self-declared
survey runs and then used on vessels that declare nothing. Positive examples are few (a handful of vessels) and the 'negative'
class contains any undeclared survey that exists, so results are indicative, not a validation. Names, destination, status, zone and
cable proximity are NOT features; they are used only to make labels and, separately, as extra evidence in the survey-threat rules.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .models import Track

STEP_S = 600.0  # resampling step
WINDOW_S = 6 * 3600.0
HOP_S = 3 * 3600.0
MAX_MEDIAN_KN = 7.0  # stage-1 speed filter: faster than this is transit
MIN_MEDIAN_KN = 1.5  # ... and slower than this is parked / drifting, not working a line
MIN_PATH_NM = 8.0

FEATURES = [
    "med_kn", "p90_kn", "speed_cv", "path_nm", "straightness", "turn_per_nm", "mean_abs_turn", "reversals_per_h", "n_legs", "mean_leg_nm",
    "leg_cv", "revisit", "axis_share", "extent_nm", "hull_ratio", "gyration_ratio", "dwell",
]


def _xy(lat, lon):
    k = 60.0
    x = (lon - lon[0]) * k * np.cos(np.radians(np.mean(lat)))
    y = (lat - lat[0]) * k
    return x, y


def _headings(x, y):
    dx, dy = np.diff(x), np.diff(y)
    d = np.hypot(dx, dy)
    return np.degrees(np.arctan2(dx, dy)) % 360.0, d


def _angdiff(a):
    d = (np.diff(a) + 180.0) % 360.0 - 180.0
    return d


def window_features(lat, lon, speed, t, min_path: float = MIN_PATH_NM, min_moving: int = 8) -> dict[str, float] | None:
    """Path-only features for one resampled window (arrays on the STEP_S grid)."""

    x, y = _xy(lat, lon)
    hd, d = _headings(x, y)
    path = float(d.sum())
    if path < min_path:
        return None
    moving = d > 0.05  # > 0.3 kn
    if moving.sum() < min_moving:
        return None
    hdm = hd[moving]
    turns = np.abs(_angdiff(hdm))
    disp = float(np.hypot(x[-1] - x[0], y[-1] - y[0]))
    # legs: split where the heading moves more than 45 degrees from the running leg heading
    legs, cur = [], 0.0
    ref = hdm[0]
    for h, dd in zip(hdm, d[moving]):
        if abs((h - ref + 180.0) % 360.0 - 180.0) > 45.0:
            if cur > 0.5:
                legs.append(cur)
            cur, ref = 0.0, h
        cur += dd
    if cur > 0.5:
        legs.append(cur)
    legs_a = np.array(legs) if legs else np.array([path])
    # re-traversal: how much of the area covered is visited on more than one separate pass
    cell = 0.4
    ci = np.floor(x / cell).astype(int)
    cj = np.floor(y / cell).astype(int)
    visits: dict[tuple[int, int], int] = {}
    last = None
    for a, b in zip(ci, cj):
        if (a, b) != last:
            visits[(a, b)] = visits.get((a, b), 0) + 1
            last = (a, b)
    revisit = float(np.mean([v >= 2 for v in visits.values()])) if visits else 0.0
    # axis share: headings along the principal axis or its reverse (parallel survey lines)
    rad = np.radians(hdm)
    c2, s2 = np.cos(2 * rad).mean(), np.sin(2 * rad).mean()
    axis = (np.degrees(np.arctan2(s2, c2)) / 2.0) % 180.0
    off = np.abs(((hdm % 180.0) - axis + 90.0) % 180.0 - 90.0)
    axis_share = float(np.mean(off < 20.0))
    pts = np.c_[x, y]
    try:
        from scipy.spatial import ConvexHull

        area = float(ConvexHull(pts).volume)
    except Exception:  # noqa: BLE001 - degenerate (collinear) windows
        area = 0.0
    r = float(np.sqrt(np.mean((x - x.mean()) ** 2 + (y - y.mean()) ** 2)))
    sp = speed[np.isfinite(speed)]
    hours = (t[-1] - t[0]) / 3600.0
    return {
        "med_kn": float(np.median(sp)) if len(sp) else float("nan"), "p90_kn": float(np.percentile(sp, 90)) if len(sp) else float("nan"),
        "speed_cv": float(np.std(sp) / max(np.mean(sp), 0.1)) if len(sp) else float("nan"), "path_nm": path, "straightness": disp / path,
        "turn_per_nm": float(turns.sum() / path), "mean_abs_turn": float(turns.mean()) if len(turns) else 0.0,
        "reversals_per_h": float(np.sum(turns > 120.0) / max(hours, 1e-6)), "n_legs": float(len(legs_a)), "mean_leg_nm": float(legs_a.mean()),
        "leg_cv": float(legs_a.std() / max(legs_a.mean(), 1e-6)), "revisit": revisit, "axis_share": axis_share,
        "extent_nm": float(np.hypot(np.ptp(x), np.ptp(y))), "hull_ratio": area / max(path ** 2, 1e-6), "gyration_ratio": r / max(path, 1e-6),
        "dwell": float(np.mean(~moving)),
    }


@dataclass
class Window:
    mmsi: str
    t0: float
    t1: float
    lat: float
    lon: float
    feats: dict[str, float]
    label: int  # 1 = vessel announced survey work during the window, else 0
    declared_by: str


def windows_for(tr: Track, window_s: float = WINDOW_S, hop_s: float = HOP_S, min_kn: float = MIN_MEDIAN_KN, max_kn: float = MAX_MEDIAN_KN,
                min_path: float = MIN_PATH_NM, min_moving: int = 8, max_gap_s: float = 2400.0, min_pts: int = 12) -> list[Window]:
    """All slow, moving windows of one track (stage 1 + feature extraction), with weak labels from what the vessel broadcast."""

    out: list[Window] = []
    if len(tr) < min(20, 2 * min_pts):
        return out
    t = tr.t
    tw = (tr.extra or {}).get("tow_t")
    start = t[0]
    while start + window_s <= t[-1]:
        i, j = np.searchsorted(t, start, "left"), np.searchsorted(t, start + window_s, "right")
        start += hop_s
        if j - i < min_pts:
            continue
        tt = t[i:j]
        if np.max(np.diff(tt)) > max_gap_s or (tt[-1] - tt[0]) < 0.9 * window_s:
            continue
        grid = np.arange(tt[0], tt[0] + window_s, STEP_S)
        lat = np.interp(grid, tt, tr.lat[i:j])
        lon = np.interp(grid, tt, tr.lon[i:j])
        raw_sp = tr.sog[i:j]
        sp = np.interp(grid, tt, np.where(np.isfinite(raw_sp), raw_sp, 0.0))
        if not (min_kn <= np.median(sp) <= max_kn):  # stage 1: transit is too fast, moored / anchored too slow
            continue
        f = window_features(lat, lon, sp, grid, min_path, min_moving)
        if f is None:
            continue
        label, by = 0, ""
        if tw is not None and np.any((tw >= tt[0]) & (tw <= tt[-1])):
            label, by = 1, "towing text"
        elif tr.status is not None and np.mean(np.asarray(tr.status[i:j]) == 3) >= 0.5 and np.median(raw_sp[np.isfinite(raw_sp)] if np.isfinite(raw_sp).any() else [0]) <= max_kn:
            label, by = 1, "restricted manoeuvre"
        out.append(Window(tr.mmsi, float(tt[0]), float(tt[-1]), float(lat.mean()), float(lon.mean()), f, label, by))
    return out


def matrix(ws: list[Window]):
    X = np.array([[w.feats[k] for k in FEATURES] for w in ws], float)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    return X, np.array([w.label for w in ws]), np.array([w.mmsi for w in ws])


def fit(X, y):
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression

    gb = GradientBoostingClassifier(n_estimators=120, max_depth=2, learning_rate=0.08, subsample=0.8, random_state=0).fit(X, y)
    lr = make_pipeline(StandardScaler(), LogisticRegression(C=0.3, class_weight="balanced", max_iter=2000)).fit(X, y)
    return gb, lr


def score(models, X) -> np.ndarray:
    gb, lr = models
    return 0.5 * gb.predict_proba(X)[:, 1] + 0.5 * lr.predict_proba(X)[:, 1]
