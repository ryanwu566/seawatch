"""Learned classifier for survey-like track shapes (lawnmower, zig-zag, race-track).

The rule in :mod:`survey` finds regular parallel legs. Real surveys are messier (irregular line lengths, loops at the
turns, partial coverage), so a model is trained on shape features to generalise across variants.

Training data, honestly described:
  negatives - real windows from non-exempt vessels (almost all of them are ordinary transits / drifting / port work);
  positives - SYNTHETIC survey shapes sampled at the timestamps and reporting gaps of real vessels (so cadence cannot
              give them away). No confirmed real PRC survey occurrence exists in the September data, so real positives
              are not available for training; any real hit must be confirmed from open sources.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, roc_auc_score

from .geo import NM_M, project_xy_m
from .models import Track
from .survey import SURVEY_EXEMPT, zigzag

# Deliberately excludes window length, report density and cell-revisit rate: they let a model tell synthetic from real
# windows without looking at the leg structure that defines a survey.
FEATURES = [
    "speed_kn", "path_over_major", "aspect", "rev8", "rev14", "rev22", "amp_cv14", "mean_leg14", "lateral_ratio",
    "turn_per_h", "reversal_frac", "lateral_corr", "major_nm", "minor_nm",
]
WINDOW_H = 96.0


def shape_features(t: np.ndarray, lat: np.ndarray, lon: np.ndarray) -> dict[str, float] | None:
    n = len(t)
    if n < 10:
        return None
    x, y = project_xy_m(lat, lon)
    x, y = x / NM_M, y / NM_M
    c = np.c_[x - x.mean(), y - y.mean()]
    _, sv, vt = np.linalg.svd(c, full_matrices=False)
    s_ax, s_pe = c @ vt[0], c @ vt[1]
    major, minor = float(np.ptp(s_ax)), float(np.ptp(s_pe))
    seg = np.hypot(np.diff(x), np.diff(y))
    path = float(seg.sum())
    hours = float((t[-1] - t[0]) / 3600.0)
    f: dict[str, float] = {
        "hours": hours, "fill": float(n / max(hours, 1.0)), "speed_kn": path / max(hours, 1e-6),
        "path_over_major": path / max(major, 1.0), "aspect": minor / max(major, 1e-6), "major_nm": major, "minor_nm": minor,
    }
    for thr in (8, 14, 22):
        f[f"rev{thr}"] = float(len(zigzag(s_ax, thr)))
    tp = zigzag(s_ax, 14)
    if len(tp) >= 2:
        amps = np.abs(np.diff(s_ax[tp]))
        f["amp_cv14"] = float(np.std(amps) / max(np.mean(amps), 1e-6))
        f["mean_leg14"] = float(np.mean(amps))
        pe = s_pe[tp]
        f["lateral_ratio"] = float(np.ptp(pe) / max(np.mean(amps), 1e-6))
        f["lateral_corr"] = float(abs(np.corrcoef(np.arange(len(pe)), pe)[0, 1])) if len(pe) > 2 and np.std(pe) > 0 else 0.0
    else:
        f["amp_cv14"], f["mean_leg14"], f["lateral_ratio"], f["lateral_corr"] = 1.0, 0.0, 0.0, 0.0
    # heading behaviour on 3-fix smoothed displacement
    k = 3
    if n > k + 2:
        dx, dy = x[k:] - x[:-k], y[k:] - y[:-k]
        ok = np.hypot(dx, dy) > 1.0
        h = np.arctan2(dy, dx)[ok]
        if len(h) > 3:
            d = np.abs((np.diff(h) + math.pi) % (2 * math.pi) - math.pi)
            f["turn_per_h"] = float(np.degrees(d).sum() / max(hours, 1.0))
            f["reversal_frac"] = float((d > math.radians(120)).mean())
        else:
            f["turn_per_h"], f["reversal_frac"] = 0.0, 0.0
    else:
        f["turn_per_h"], f["reversal_frac"] = 0.0, 0.0
    f["revisit"] = float(1.0 - len(set(zip(np.round(lat, 1), np.round(lon, 1)))) / n)
    return f


def real_windows(tracks: list[Track], window_h: float = WINDOW_H, step_h: float = 48.0, exclude: tuple[str, ...] = SURVEY_EXEMPT):
    """(track index, i0, i1) index ranges of 96 h windows in non-exempt vessels."""

    out = []
    w = window_h * 3600.0
    for ti, tr in enumerate(tracks):
        if tr.ship_type in exclude or len(tr) < 10 or tr.t[-1] - tr.t[0] < w * 0.5:
            continue
        start = tr.t[0]
        while start < tr.t[-1] - w * 0.5:
            i0, i1 = int(np.searchsorted(tr.t, start)), int(np.searchsorted(tr.t, start + w))
            start += step_h * 3600.0
            if i1 - i0 >= 10:
                out.append((ti, i0, i1))
    return out


def synth_polyline(rng: np.random.Generator, shape: str, hours: float) -> tuple[np.ndarray, float] | None:
    """Waypoints (nm) of a survey-like path with >= 4 complete legs, and the speed that traverses it in ``hours``."""

    L = float(rng.uniform(24.0, 60.0))
    ratio = float(rng.uniform(0.1, 0.5))  # line spacing relative to line length: real survey lines are close-packed
    S = L * ratio
    speed = float(rng.uniform(3.5, 7.0))
    n_legs = int(speed * hours // (L + S))
    if n_legs < 4:
        return None
    n_legs = min(n_legs, 12)
    pts = [np.array([0.0, 0.0])]
    sign = 1.0
    if shape == "lawnmower":
        for _ in range(n_legs):
            pts.append(pts[-1] + np.array([sign * L * rng.uniform(0.85, 1.15), 0.0]))
            pts.append(pts[-1] + np.array([0.0, S * rng.uniform(0.8, 1.2)]))
            sign = -sign
    elif shape == "zigzag":
        adv = L * rng.uniform(0.15, 0.6)
        for _ in range(n_legs):
            pts.append(pts[-1] + np.array([adv, sign * L * rng.uniform(0.8, 1.2)]))
            sign = -sign
    else:  # racetrack: lines joined by round turns
        for _ in range(n_legs):
            end = pts[-1] + np.array([sign * L, 0.0])
            pts.append(end)
            r = S / 2
            for a_ in np.linspace(0, math.pi, 5)[1:]:
                pts.append(end + np.array([sign * r * math.sin(a_), r * (1 - math.cos(a_))]))
            sign = -sign
    rot = rng.uniform(0, math.pi)
    R = np.array([[math.cos(rot), -math.sin(rot)], [math.sin(rot), math.cos(rot)]])
    poly = np.array(pts) @ R.T
    seg = float(np.sum(np.hypot(*np.diff(poly, axis=0).T)))
    return poly, seg / max(hours, 1e-6)  # speed that completes the whole pattern inside the window


def sample_polyline(poly: np.ndarray, speed_kn: float, tt: np.ndarray) -> np.ndarray:
    seglen = np.hypot(*np.diff(poly, axis=0).T)
    cum = np.concatenate([[0.0], np.cumsum(seglen)])
    d = np.clip(speed_kn * (tt - tt[0]) / 3600.0, 0, cum[-1])
    return np.c_[np.interp(d, cum, poly[:, 0]), np.interp(d, cum, poly[:, 1])]


def make_positive(rng: np.random.Generator, template: Track, i0: int, i1: int, centre: tuple[float, float], cell: float = 0.1):
    """Survey path sampled at the timestamps (and gaps) of a real window, snapped to the feed's grid. None if the window is too short."""

    tt = template.t[i0:i1]
    hours = (tt[-1] - tt[0]) / 3600.0
    if hours < 36.0:
        return None
    for _ in range(8):
        shape = str(rng.choice(["lawnmower", "zigzag", "racetrack"]))
        made = synth_polyline(rng, shape, hours)
        if made is not None and 2.5 <= made[1] <= 8.5:
            poly, speed = made
            xy = sample_polyline(poly, speed, tt)
            lat = centre[0] + xy[:, 1] / 60.0
            lon = centre[1] + xy[:, 0] / 60.0 / max(0.2, math.cos(math.radians(centre[0])))
            return tt, np.round(lat / cell) * cell, np.round(lon / cell) * cell, shape
    return None


def build_dataset(tracks: list[Track], seed: int = 0, max_neg: int = 25000, pos_per_neg: float = 0.15):
    rng = np.random.default_rng(seed)
    wins = real_windows(tracks)
    rng.shuffle(wins)
    wins = wins[:max_neg]
    rows, meta = [], []
    for ti, i0, i1 in wins:
        tr = tracks[ti]
        f = shape_features(tr.t[i0:i1], tr.lat[i0:i1], tr.lon[i0:i1])
        if f is None:
            continue
        rows.append({**f, "y": 0, "mmsi": tr.mmsi, "shape": "real", "ti": ti, "i0": i0, "i1": i1})
    n_pos = int(len(rows) * pos_per_neg)
    for k in range(n_pos):
        ti, i0, i1 = wins[int(rng.integers(len(wins)))]
        tr = tracks[ti]
        centre = (float(rng.uniform(22.0, 26.0)), float(rng.uniform(118.5, 123.0)))
        made = make_positive(rng, tr, i0, i1, centre)
        if made is None:
            continue
        tt, la, lo, shape = made
        f = shape_features(tt, la, lo)
        if f is not None:
            rows.append({**f, "y": 1, "mmsi": tr.mmsi, "shape": shape, "ti": -1, "i0": -1, "i1": -1})
    return pd.DataFrame(rows)


def fit_and_evaluate(df: pd.DataFrame, seed: int = 0):
    """Split BY VESSEL so no vessel's windows are in both train and test."""

    rng = np.random.default_rng(seed)
    vessels = df["mmsi"].unique()
    rng.shuffle(vessels)
    test_v = set(vessels[: len(vessels) // 4])
    te = df["mmsi"].isin(test_v).to_numpy()
    tr_df, te_df = df[~te], df[te]
    m = HistGradientBoostingClassifier(max_depth=4, learning_rate=0.06, max_iter=250, class_weight="balanced", random_state=seed)
    m.fit(tr_df[FEATURES], tr_df["y"])
    s = m.predict_proba(te_df[FEATURES])[:, 1]
    y = te_df["y"].to_numpy()
    neg = s[y == 0]
    thr = float(np.quantile(neg, 0.995))
    report = {
        "train_windows": int(len(tr_df)), "test_windows": int(len(te_df)), "test_positives": int(y.sum()),
        "roc_auc": round(float(roc_auc_score(y, s)), 4), "pr_auc": round(float(average_precision_score(y, s)), 4),
        "threshold_at_0.5pct_false_positive": round(thr, 3),
        "recall_at_that_threshold": round(float((s[y == 1] >= thr).mean()), 3),
        "recall_by_shape": {sh: round(float((s[(y == 1) & (te_df["shape"].to_numpy() == sh)] >= thr).mean()), 3)
                            for sh in ("lawnmower", "zigzag", "racetrack")},
    }
    # the rule detector on the same synthetic positives, for comparison
    importances = pd.Series(
        __import__("sklearn.inspection", fromlist=["x"]).permutation_importance(m, te_df[FEATURES], y, n_repeats=3, random_state=seed,
                                                                                scoring="average_precision").importances_mean,
        index=FEATURES).sort_values(ascending=False)
    report["top_features"] = {k: round(float(v), 4) for k, v in importances.head(6).items()}
    final = HistGradientBoostingClassifier(max_depth=4, learning_rate=0.06, max_iter=250, class_weight="balanced", random_state=seed)
    final.fit(df[FEATURES], df["y"])
    return final, thr, report
