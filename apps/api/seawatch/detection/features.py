"""Window-level behaviour features for machine-learning models.

A *window* is one vessel over a fixed span (default 2 h, stepped every hour). The
features describe motion, reporting quality, and spatial context, and are defined
on plain AIS fields (time, lat, lon, sog, cog) so the same code runs on simulated
tracks and on real historic AIS loaded from disk.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from .context import BENIGN_AREA_KINDS, SENSITIVE_KINDS, DetectionContext
from .detectors import GRID_S, _resample
from .geo import NM_M, haversine_m, project_xy_m
from .models import Track, TruthEvent

WINDOW_S = 2 * 3600
STEP_S = 3600

FEATURES = [
    "n_fix", "max_gap_min", "cov_frac", "sog_med", "sog_p90", "low_speed_frac", "radius_nm", "path_ratio",
    "turn_per_h", "max_implied_kn", "n_jump", "fam_mean", "unfam_frac", "sens_dist_nm", "in_sens_frac",
    "port_dist_nm", "in_benign_frac", "in_fish_frac", "slow_nbr_nm", "group_size",
    "is_tanker", "is_cargo", "is_fishing", "is_ferry",
]


def _neighbour_grids(tracks: list[Track], t0: float, t1: float, ctx: DetectionContext):
    grid, LAT, LON, SOG = _resample(tracks, t0, t1, ctx)
    V, K = LAT.shape
    nn_slow = np.full((V, K), 99.0)
    group = np.zeros((V, K))
    for k in range(K):
        idx = np.where(~np.isnan(LAT[:, k]))[0]
        if idx.size < 2:
            continue
        x, y = project_xy_m(LAT[idx, k], LON[idx, k])
        pts = np.c_[x, y]
        tree = cKDTree(pts)
        d, j = tree.query(pts, k=2)
        slow = SOG[idx, k] <= 4.0
        for a in range(idx.size):
            if slow[a]:
                cand = tree.query_ball_point(pts[a], 3000.0)
                ds = [np.hypot(*(pts[b] - pts[a])) for b in cand if b != a and slow[b]]
                if ds:
                    nn_slow[idx[a], k] = min(ds) / NM_M
            group[idx[a], k] = len(tree.query_ball_point(pts[a], 3 * NM_M))
    return grid, nn_slow, group


def window_features(tracks: list[Track], t0: float, t1: float, ctx: DetectionContext,
                    truth: list[TruthEvent] | None = None) -> pd.DataFrame:
    grid, nn_slow, group = _neighbour_grids(tracks, t0, t1, ctx)
    rows: list[dict] = []
    for v, tr in enumerate(tracks):
        if len(tr) < 2:
            continue
        starts = np.arange(max(t0, tr.t[0] - 1800), min(t1, tr.t[-1] + 1800) - WINDOW_S + 1, STEP_S)
        for ws in starts:
            we = ws + WINDOW_S
            i0 = int(np.searchsorted(tr.t, ws))
            i1 = int(np.searchsorted(tr.t, we))
            lo, hi = max(0, i0 - 1), min(len(tr), i1 + 1)  # include neighbours for gap calc
            tt = tr.t[lo:hi]
            if tt.size < 2:
                continue
            # silence measured as the portion of the window not covered by successive reports
            gaps = np.minimum(tt[1:], we) - np.maximum(tt[:-1], ws)
            max_gap = float(np.max(np.clip(gaps, 0, None))) / 60
            la, lonn, sg, cg = tr.lat[i0:i1], tr.lon[i0:i1], tr.sog[i0:i1], tr.cog[i0:i1]
            n = int(la.size)
            la_ctx, lo_ctx = tr.lat[lo:hi], tr.lon[lo:hi]
            sgv = np.nan_to_num(sg, nan=0.0)
            row = {"mmsi": tr.mmsi, "t0": float(ws), "t1": float(we), "n_fix": n, "max_gap_min": max_gap,
                   "is_tanker": float(tr.ship_type == "tanker"), "is_cargo": float(tr.ship_type == "cargo"),
                   "is_fishing": float(tr.ship_type == "fishing"), "is_ferry": float(tr.ship_type in ("ferry", "passenger"))}
            ref_la, ref_lo = (la, lonn) if n else (la_ctx[:1], lo_ctx[:1])
            row["cov_frac"] = float(np.mean(ctx.covered(ref_la, ref_lo)))
            row["sog_med"] = float(np.median(sgv)) if n else 0.0
            row["sog_p90"] = float(np.percentile(sgv, 90)) if n else 0.0
            row["low_speed_frac"] = float(np.mean(sgv < 2.0)) if n else 0.0
            if n >= 2:
                x, y = project_xy_m(la, lonn)
                cx, cy = x.mean(), y.mean()
                row["radius_nm"] = float(np.max(np.hypot(x - cx, y - cy))) / NM_M
                seg = np.hypot(np.diff(x), np.diff(y))
                disp = np.hypot(x[-1] - x[0], y[-1] - y[0])
                row["path_ratio"] = float(min(20.0, seg.sum() / max(disp, 200.0)))
                dc = np.abs((np.diff(np.nan_to_num(cg)) + 180) % 360 - 180)
                row["turn_per_h"] = float(dc.sum() / (WINDOW_S / 3600))
            else:
                row.update(radius_nm=0.0, path_ratio=1.0, turn_per_h=0.0)
            if la_ctx.size >= 2:
                d = haversine_m(la_ctx[:-1], lo_ctx[:-1], la_ctx[1:], lo_ctx[1:]) / NM_M
                dt = np.maximum(np.diff(tr.t[lo:hi]), 1.0) / 3600
                v_imp = d / dt
                row["max_implied_kn"] = float(min(500.0, v_imp.max()))
                row["n_jump"] = float(np.sum((v_imp > 60) & (d > 4)))
            else:
                row.update(max_implied_kn=0.0, n_jump=0.0)
            if ctx.baseline is not None and n:
                fam = ctx.baseline.familiarity(la, lonn)
                row["fam_mean"] = float(fam.mean())
                row["unfam_frac"] = float(np.mean((fam < 1.5) & (sgv >= 5.0)))
            else:
                row["fam_mean"], row["unfam_frac"] = 5.0, 0.0
            _, ds = ctx.nearest_zone(float(ref_la.mean()), float(ref_lo.mean()), SENSITIVE_KINDS)
            row["sens_dist_nm"] = float(min(ds, 200.0))
            row["in_sens_frac"] = float(ctx.in_kinds(ref_la, ref_lo, SENSITIVE_KINDS).mean())
            row["port_dist_nm"] = float(min(ctx.nearest_port_nm(float(ref_la.mean()), float(ref_lo.mean())), 200.0))
            row["in_benign_frac"] = float(ctx.in_kinds(ref_la, ref_lo, BENIGN_AREA_KINDS).mean())
            row["in_fish_frac"] = float(ctx.in_kinds(ref_la, ref_lo, ("fishing_ground",)).mean())
            ks = np.where((grid >= ws) & (grid <= we))[0]
            row["slow_nbr_nm"] = float(nn_slow[v, ks].min()) if ks.size else 99.0
            row["group_size"] = float(group[v, ks].max()) if ks.size else 1.0
            rows.append(row)
    df = pd.DataFrame(rows)
    if truth is not None:
        y = np.zeros(len(df), int)
        for t in truth:
            if t.benign:
                continue
            m = df["mmsi"].isin(t.mmsis) & (df["t1"] >= t.t_start) & (df["t0"] <= t.t_end)
            y[m.to_numpy()] = 1
        df["y"] = y
    return df
