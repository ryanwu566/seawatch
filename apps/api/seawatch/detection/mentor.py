"""Drop-in ingestion for any AIS export of Taiwan waters (e.g. the data the hackathon mentor will provide).

``load(paths)`` accepts CSV / parquet files (or folders of them), guesses the column names, decides whether the feed is
message-level AIS (reports every few minutes) or hourly presence, and returns Tracks. ``analyse(tracks)`` then learns
what is normal from the earlier part of the data and runs the full rule stack, including the territory / velocity /
declaration / pattern threat model, on the later part. ``scripts/ingest_mentor_ais.py`` is the command-line wrapper.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .alerts import build_alerts
from .config import DetectionConfig
from .context import DetectionContext, TrafficBaseline
from .detectors import run_all
from .history import ship_category
from .declared import is_towing_text
from .identity import is_real_ship
from .survey import _FISHING_NAME
from .learned import LearnedContext, VesselHabits
from .models import Track
from .territory import Territory

# canonical name -> accepted column names (lower-cased)
ALIASES = {
    "mmsi": ["mmsi", "ship_id", "vessel_id", "userid", "user_id", "id"],
    "t": ["t", "position_time_utc", "time", "timestamp", "datetime", "date_time", "base_date_time", "basedatetime", "position_timestamp", "ts"],
    "lat": ["lat", "latitude", "y"],
    "lon": ["lon", "lng", "longitude", "long", "x"],
    "sog": ["sog", "speed_knots", "speed", "speed_knots", "speedoverground", "speed_over_ground"],
    "cog": ["cog", "course_deg", "course", "courseoverground", "course_over_ground", "heading"],
    "name": ["name", "vessel_name", "shipname", "ship_name", "vessel_name", "vesselname"],
    "type": ["type", "vessel_type", "shiptype", "ship_type", "vessel_type", "vesseltype", "ship_and_cargo_type"],
    "imo": ["imo", "imo_number"],
    "status": ["status", "nav_status", "navstatus", "navigationalstatus", "navigational_status"],
    "dest": ["dest", "destination"],
    "subtype": ["vessel_subtype", "subtype"],
    "flag": ["flag", "flag_state", "country"],
}


NAV_CODES = {"UNDER_WAY_USING_ENGINE": 0, "AT_ANCHOR": 1, "NOT_UNDER_COMMAND": 2, "RESTRICTED_MANEUVERABILITY": 3, "CONSTRAINED_BY_DRAUGHT": 4,
             "MOORED": 5, "AGROUND": 6, "ENGAGED_IN_FISHING": 7, "UNDER_WAY_SAILING": 8}


def _read(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in (".parquet", ".pq"):
        return pd.read_parquet(path)
    return pd.read_csv(path, low_memory=False)


def files_in(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for p in map(Path, paths):
        out += sorted(x for x in p.rglob("*") if x.suffix.lower() in (".csv", ".parquet", ".pq", ".gz")) if p.is_dir() else [p]
    return out


def normalise(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str]]:
    low = {c.lower().strip(): c for c in df.columns}
    mapping = {}
    for canon, names in ALIASES.items():
        for n in names:
            if n in low:
                mapping[canon] = low[n]
                break
    missing = [k for k in ("mmsi", "t", "lat", "lon") if k not in mapping]
    if missing:
        raise ValueError(f"cannot find columns for {missing}; columns present: {list(df.columns)[:30]}")
    out = pd.DataFrame({k: df[v] for k, v in mapping.items()})
    if "status" in out and not pd.api.types.is_numeric_dtype(out["status"]):
        out["status"] = out["status"].astype(str).str.upper().map(NAV_CODES).fillna(-1)
    out["mmsi"] = out["mmsi"].astype(str).str.replace(r"\.0$", "", regex=True)
    if pd.api.types.is_numeric_dtype(out["t"]):
        x = out["t"].astype(float)
        out["t"] = x / 1000.0 if x.median() > 1e11 else x
    else:
        out["t"] = (pd.to_datetime(out["t"], utc=True, errors="coerce") - pd.Timestamp("1970-01-01", tz="UTC")) / pd.Timedelta(seconds=1)
    for c in ("lat", "lon", "sog", "cog"):
        if c in out:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.dropna(subset=["t", "lat", "lon"])
    out = out[out["lat"].between(-90, 90) & out["lon"].between(-180, 180)]
    return out.drop_duplicates(["mmsi", "t"]), mapping


def resolution(df: pd.DataFrame) -> dict[str, Any]:
    """Median seconds between a vessel's consecutive reports decides which detector preset applies."""

    d = df.sort_values(["mmsi", "t"]).groupby("mmsi")["t"].diff().dropna()
    med = float(d.median()) if len(d) else float("nan")
    return {"median_interval_s": med, "hourly": bool(med >= 1800), "has_speed": "sog" in df and bool(df["sog"].notna().mean() > 0.5)}


def to_tracks(df: pd.DataFrame, min_fixes: int = 6) -> list[Track]:
    tracks = []
    dropped = to_tracks.dropped = {}
    for mmsi, g in df.sort_values(["mmsi", "t"]).groupby("mmsi", sort=False):
        if len(g) < min_fixes:
            continue
        name = next((str(x) for x in g.get("name", pd.Series(dtype=object)).dropna() if str(x).strip()), mmsi)
        if not is_real_ship(name, mmsi):
            dropped["gear/placeholder"] = dropped.get("gear/placeholder", 0) + 1
            continue
        typ = next((x for x in g.get("type", pd.Series(dtype=object)).dropna()), "")
        imo = next((str(int(float(x))) for x in g.get("imo", pd.Series(dtype=object)).dropna() if str(x).replace(".0", "").isdigit()), "")
        sub = next((str(x) for x in g.get("subtype", pd.Series(dtype=object)).dropna() if str(x).strip()), "")
        dests = [str(x) for x in g.get("dest", pd.Series(dtype=object)).dropna() if str(x).strip() and str(x) != "0"]
        dest = dests[0] if dests else ""
        tow_mask = g["dest"].fillna("").astype(str).map(is_towing_text).to_numpy() if "dest" in g else np.zeros(len(g), bool)
        if tow_mask.any():
            dest = next(x for x in g["dest"].fillna("").astype(str) if is_towing_text(x))
        tow_t = g["t"].to_numpy(float)[tow_mask][::5] if tow_mask.any() else None
        sog = g["sog"].to_numpy(float) if "sog" in g else np.full(len(g), np.nan)
        if np.isfinite(sog).mean() < 0.5:  # derive from position steps when the feed has no speed
            from .geo import haversine_m

            dt = np.maximum(np.diff(g["t"].to_numpy(float), prepend=np.nan), 1.0)
            d = haversine_m(g["lat"].shift(1).to_numpy(float), g["lon"].shift(1).to_numpy(float), g["lat"].to_numpy(float), g["lon"].to_numpy(float))
            sog = d / dt * 1.94384
        cog = g["cog"].to_numpy(float) if "cog" in g else np.full(len(g), np.nan)
        status = pd.to_numeric(g["status"], errors="coerce").fillna(-1).astype(int).to_numpy() if "status" in g else None
        flag = str(g["flag"].dropna().iloc[0]) if "flag" in g and g["flag"].notna().any() else ("TWN" if mmsi.startswith("416") else "")
        cat = ship_category(typ)
        if cat == "other" and _FISHING_NAME.search(name.upper().replace("-", "")):
            cat = "fishing"  # unclassified boats named like Chinese / Taiwanese fishing vessels
        tracks.append(Track(mmsi, name.strip(), cat, flag, g["t"].to_numpy(float), g["lat"].to_numpy(float), g["lon"].to_numpy(float),
                            sog, cog, status, imo, {k: v for k, v in (("destination", dest if dest not in ("0", "nan") else ""), ("subtype", sub), ("tow_t", tow_t)) if v is not None and (isinstance(v, np.ndarray) or v != "")} or None))
    return tracks


def load(paths: list[str]) -> tuple[list[Track], dict[str, Any]]:
    frames, maps = [], {}
    for f in files_in(paths):
        df, maps = normalise(_read(f))
        frames.append(df)
    if not frames:
        raise ValueError("no CSV / parquet files found")
    df = pd.concat(frames, ignore_index=True).drop_duplicates(["mmsi", "t"])
    res = resolution(df)
    tracks = to_tracks(df)
    info = {"rows": int(len(df)), "vessels": int(df["mmsi"].nunique()), "tracks": len(tracks), "columns_mapped": maps, **res,
            "t0": float(df["t"].min()), "t1": float(df["t"].max()),
            "bbox": [float(df["lat"].min()), float(df["lon"].min()), float(df["lat"].max()), float(df["lon"].max())]}
    return tracks, info


def analyse(tracks: list[Track], hourly: bool, live_frac: float = 0.2) -> dict[str, Any]:
    """Learn normal behaviour from the first part of the data, then run all rules on the last ``live_frac`` of it."""

    cfg = DetectionConfig.hourly() if hourly else DetectionConfig.dense()
    t0 = min(float(t.t[0]) for t in tracks)
    t1 = max(float(t.t[-1]) for t in tracks)
    cut = t1 - live_frac * (t1 - t0)
    hist = [s for t in tracks if (s := _clip(t, t0, cut)) is not None]
    live = [s for t in tracks if (s := _clip(t, cut, t1)) is not None]
    cell = 0.1 if hourly else 0.01
    baseline = TrafficBaseline(cell_deg=cell).fit(hist, max_dt_s=cfg.densify_max_dt_s)
    learned = LearnedContext(cell_deg=cfg.learn_cell_deg, min_slow_s=cfg.learn_min_slow_s, max_dt_s=cfg.learn_max_dt_s,
                             min_stop_vessels=cfg.learn_min_stop_vessels).fit(hist)
    la = np.concatenate([t.lat for t in tracks])
    lo = np.concatenate([t.lon for t in tracks])
    bounds = (float(la.min()), float(lo.min()), float(la.max()), float(lo.max()))
    ctx = DetectionContext([], [], baseline, learned=learned, bounds=bounds)
    ctx.habits = VesselHabits(cell_deg=cell, min_dwell_s=6 * 3600, max_dt_s=cfg.learn_max_dt_s).fit(hist)
    ctx.territory = Territory.default()
    events = run_all(live, cut, t1, ctx, cfg)
    alerts = build_alerts(events, live, cfg)
    return {"cfg": cfg, "history_vessels": len(hist), "live_vessels": len(live), "t_live": cut, "t1": t1, "events": events, "alerts": alerts,
            "events_by_kind": Counter(e.kind for e in events), "discards": ctx.stats.most_common(15), "ctx": ctx, "live": live}


def _clip(tr: Track, a: float, b: float) -> Track | None:
    i = int(np.searchsorted(tr.t, a, "left"))
    j = int(np.searchsorted(tr.t, b, "right"))
    return tr.slice(i, j) if j - i >= 4 else None
