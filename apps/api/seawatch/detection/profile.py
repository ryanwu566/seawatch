"""Vessel identity-profile screening, learned from watch-list labels.

Question answered: do vessels that appear on a sanctions list share AIS-visible traits that ordinary traffic does
not (country prefix of the MMSI, ship type and size, how complete / honest the static data are, destination
conventions, reporting quality)?  Such a screen can only ever be a *prior for human attention*: it is trained on
who was designated, which reflects policy and enforcement choices as much as behaviour.

Guards against fooling ourselves: IMO / MMSI / name never enter the features (only the MMSI country prefix does);
evaluation is cross-validated; every result is compared with trivial baselines (ship type alone, flag alone).
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold

from .labels import LabelSet


def imo_valid(imo: str) -> bool:
    """IMO numbers carry a check digit; a wrong one on static data is a data-quality red flag."""

    d = re.sub(r"\D", "", imo or "")
    if len(d) != 7:
        return False
    return sum(int(c) * w for c, w in zip(d[:6], range(7, 1, -1))) % 10 == int(d[6])


def static_table(df: pd.DataFrame) -> pd.DataFrame:
    """One row per vessel from a cleaned report frame (see dma.read_frame)."""

    rows = []
    for mmsi, g in df.sort_values(["mmsi", "t"]).groupby("mmsi", sort=False):
        if not (isinstance(mmsi, str) and mmsi.isdigit() and len(mmsi) == 9):
            continue
        imo = next((x for x in g["imo"].dropna() if str(x).isdigit()), "")
        name = next((x for x in g["name"].dropna() if str(x).strip()), "")
        dest = g["dest"].dropna().astype(str).str.strip().str.upper()
        dest = dest[~dest.isin(["", "UNKNOWN", "NAN"])]
        sog = g["sog"].where(g["sog"] < 102.3)
        n = len(g)
        d = np.hypot(np.diff(g["lat"].to_numpy()), np.diff(g["lon"].to_numpy())) * 60
        dt = np.maximum(np.diff(g["t"].to_numpy()), 1) / 3600
        v = d / dt if n > 1 else np.array([0.0])
        typ = next((x for x in g["type"].dropna() if str(x).lower() not in ("undefined", "")), "Undefined")
        nav = g["nav"].fillna("").str.lower()
        rows.append({
            "mmsi": mmsi, "imo": imo, "name": name, "mid": int(mmsi[:3]), "type": typ, "n": n,
            "length": float(g["length"].max()) if g["length"].notna().any() else np.nan,
            "width": float(g["width"].max()) if g["width"].notna().any() else np.nan,
            "draught": float(g["draught"].max()) if g["draught"].notna().any() else np.nan,
            "has_imo": float(bool(imo)), "imo_valid": float(imo_valid(imo)) if imo else np.nan,
            "no_name": float(not str(name).strip()),
            "no_dest": float(len(dest) == 0), "dest_for_orders": float(dest.str.contains("ORDER").any()) if len(dest) else 0.0,
            "n_dest": float(dest.nunique()) if len(dest) else 0.0,
            "sog_med": float(sog.median()) if sog.notna().any() else np.nan,
            "sog_max": float(sog.max()) if sog.notna().any() else np.nan,
            "frac_moving": float((sog > 1).mean()) if sog.notna().any() else np.nan,
            "frac_anchor": float(nav.str.contains("anchor").mean()),
            "frac_unknown_nav": float(nav.str.contains("unknown").mean()),
            "implied_max": float(min(v.max(), 300.0)), "n_jump": float(((v > 60) & (d > 4)).sum()),
            "max_gap_h": float(np.max(np.diff(g["t"].to_numpy())) / 3600) if n > 1 else 0.0,
        })
    return pd.DataFrame(rows)


NUMERIC = ["length", "width", "draught", "has_imo", "imo_valid", "no_name", "no_dest", "dest_for_orders", "n_dest", "sog_med", "sog_max",
           "frac_moving", "frac_anchor", "frac_unknown_nav", "implied_max", "n_jump", "max_gap_h"]


def label_vector(tab: pd.DataFrame, labels: LabelSet) -> np.ndarray:
    imos = {lb.imo for lb in labels.labels if lb.kind == "watchlist" and lb.imo}
    mmsis = {lb.mmsi for lb in labels.labels if lb.kind == "watchlist" and lb.mmsi}
    return (tab["imo"].isin(imos) | tab["mmsi"].isin(mmsis)).astype(int).to_numpy()


def _design(tab: pd.DataFrame, top_mids: list[int], types: list[str]) -> pd.DataFrame:
    X = tab[NUMERIC].copy()
    for m in top_mids:
        X[f"mid_{m}"] = (tab["mid"] == m).astype(float)
    X["mid_other"] = (~tab["mid"].isin(top_mids)).astype(float)
    for t in types:
        X[f"type_{t}"] = (tab["type"] == t).astype(float)
    return X


def cross_validate(tab: pd.DataFrame, y: np.ndarray, folds: int = 5, seed: int = 0) -> dict[str, Any]:
    """Out-of-fold scores for: ship-type prior, flag prior, full profile. AUC / PR-AUC / listed vessels in the top 5%."""

    pos = int(y.sum())
    if pos < 8:
        return {"positives": pos, "negatives": int(len(y) - pos), "note": "too few listed vessels for a cross-validated estimate"}
    folds = min(folds, pos)
    tab = tab.reset_index(drop=True)
    types = list(tab["type"].value_counts().index[:8])
    oof = {k: np.zeros(len(y)) for k in ("type_prior", "flag_prior", "profile")}
    for tr, te in StratifiedKFold(folds, shuffle=True, random_state=seed).split(tab, y):
        top = [int(m) for m in tab.iloc[tr]["mid"].value_counts().index[:25]]
        rate_t = pd.Series(y[tr]).groupby(tab.iloc[tr]["type"].to_numpy()).mean()
        rate_f = pd.Series(y[tr]).groupby(tab.iloc[tr]["mid"].to_numpy()).mean()
        oof["type_prior"][te] = tab.iloc[te]["type"].map(rate_t).fillna(y[tr].mean()).to_numpy()
        oof["flag_prior"][te] = tab.iloc[te]["mid"].map(rate_f).fillna(y[tr].mean()).to_numpy()
        m = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.06, max_iter=150, class_weight="balanced", random_state=seed)
        m.fit(_design(tab.iloc[tr], top, types), y[tr])
        oof["profile"][te] = m.predict_proba(_design(tab.iloc[te], top, types))[:, 1]
    out: dict[str, Any] = {"positives": pos, "negatives": int(len(y) - pos), "folds": folds, "scores": {},
                           "base_rate": round(float(y.mean()), 4)}
    k = max(1, int(round(0.05 * len(y))))
    for name, s in oof.items():
        order = np.argsort(-s, kind="stable")
        out["scores"][name] = {"roc_auc": round(float(roc_auc_score(y, s)), 3), "pr_auc": round(float(average_precision_score(y, s)), 3),
                               "listed_in_top_5pct": int(y[order[:k]].sum()), "top_5pct_size": k}
    return out


def mid_lift(tab: pd.DataFrame, y: np.ndarray, min_n: int = 8) -> list[dict[str, Any]]:
    """Which MMSI country prefixes carry most of the listed vessels (descriptive only)."""

    df = pd.DataFrame({"mid": tab["mid"].to_numpy(), "y": y})
    g = df.groupby("mid")["y"].agg(["sum", "count"])
    g = g[g["count"] >= min_n].assign(rate=lambda x: x["sum"] / x["count"]).sort_values("rate", ascending=False)
    return [{"mid": int(m), "listed": int(r["sum"]), "vessels": int(r["count"]), "rate": round(float(r["rate"]), 3)} for m, r in g.head(10).iterrows()]
