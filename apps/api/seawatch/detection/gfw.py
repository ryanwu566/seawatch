"""Loader for Global Fishing Watch "AIS vessel presence" (hourly, ~0.1 degree cells, one row per vessel-hour).

This is NOT message-level AIS: positions are the centre of a ~11 km cell for each hour a vessel was present, with no
speed, course or navigation status. We turn it into hourly :class:`Track` objects and mark them for the *hourly*
detection preset. Speeds are estimated from cell-to-cell displacement and are coarse (multiples of ~6 kn).

Fishing-gear beacons (vesselType GEAR) are not ships and are excluded.
"""

from __future__ import annotations

import glob
import os
from pathlib import Path

import numpy as np
import pandas as pd

from .geo import NM_M, haversine_m
from .models import Track

CELL_DEG = 0.1
TYPE_MAP = {"FISHING": "fishing", "CARGO": "cargo", "PASSENGER": "passenger", "CARRIER": "carrier", "BUNKER": "bunker",
            "SEISMIC_VESSEL": "seismic", "OTHER": "other", "NA": "other"}
COLS = ["date", "lat", "lon", "vesselId", "mmsi", "shipName", "flag", "vesselType", "imo"]


def data_root() -> Path:
    return Path(os.environ.get("SEAWATCH_DATA_ROOT", "D:/SeaWatch"))


def daily_files(root: Path | None = None) -> list[Path]:
    root = root or data_root()
    return sorted(Path(p) for p in glob.glob(str(root / "ais" / "historical" / "processed" / "daily" / "gfw_taiwan_*.parquet")))


def available() -> bool:
    """The raw daily files are on disk, or the processed cache built from them is (so the app runs with the SSD unplugged)."""

    return len(daily_files()) >= 3 or Path("data/processed/tw_gfw_cache.pkl").exists()


def is_vessel_mmsi(m: str) -> bool:
    """A plausible ship MMSI: 9 digits, first digit 2-7 (MID-led), not a placeholder like 416333333."""

    m = str(m)
    return len(m) == 9 and m.isdigit() and m[0] in "234567" and not any(m.count(d) >= 6 for d in set(m))


def read_presence(files: list[Path], drop_gear: bool = True) -> pd.DataFrame:
    df = pd.concat([pd.read_parquet(f, columns=COLS) for f in files], ignore_index=True)
    if drop_gear:
        df = df[df["vesselType"].fillna("") != "GEAR"]
    df = df.dropna(subset=["mmsi"])
    df = df[df["mmsi"].astype(str).map(is_vessel_mmsi)]  # drop AIS devices (SART/MOB/EPIRB/AtoN) and placeholder identities
    ts = pd.to_datetime(df["date"], utc=True)
    df = df.assign(t=((ts - pd.Timestamp("1970-01-01", tz="UTC")) / pd.Timedelta(seconds=1)).astype("float64"))
    return df.drop(columns=["date"]).sort_values(["vesselId", "t"]).drop_duplicates(["vesselId", "t"])


def estimate_sog(t: np.ndarray, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Knots from cell-to-cell displacement; NaN across gaps longer than 2 h. Coarse by construction."""

    sog = np.full(t.size, np.nan)
    if t.size < 2:
        return sog
    dt = np.diff(t) / 3600.0
    d = haversine_m(lat[:-1], lon[:-1], lat[1:], lon[1:]) / NM_M
    v = np.where(dt <= 2.0, d / np.maximum(dt, 1e-6), np.nan)
    sog[1:] = v
    sog[0] = v[0]
    return np.minimum(sog, 60.0)


def to_tracks(df: pd.DataFrame, min_fixes: int = 6) -> list[Track]:
    tracks: list[Track] = []
    for vid, g in df.groupby("vesselId", sort=False):
        if len(g) < min_fixes:
            continue
        t = g["t"].to_numpy(float)
        la, lo = g["lat"].to_numpy(float), g["lon"].to_numpy(float)
        imo = str(g["imo"].dropna().iloc[0]) if g["imo"].notna().any() else ""
        imo = imo if imo.isdigit() else ""
        name = str(g["shipName"].dropna().iloc[0]).strip() if g["shipName"].notna().any() else ""
        mmsi = str(g["mmsi"].iloc[0])
        stype = TYPE_MAP.get(str(g["vesselType"].dropna().iloc[0]), "other") if g["vesselType"].notna().any() else "other"
        flag = str(g["flag"].dropna().iloc[0]) if g["flag"].notna().any() else ""
        tracks.append(Track(mmsi, name or mmsi, stype, flag, t, la, lo, estimate_sog(t, la, lo), np.full(t.size, np.nan), None, imo))
    return tracks


def coarsen(track: Track, step_s: float = 3600.0, cell: float = CELL_DEG) -> Track | None:
    """Make a fine-resolution (simulated / injected) track look like this feed: hourly fixes snapped to cell centres."""

    if len(track) < 2:
        return None
    grid = np.arange(np.ceil(track.t[0] / step_s) * step_s, track.t[-1] + 1, step_s)
    idx = np.searchsorted(track.t, grid)
    idx = np.clip(idx, 1, len(track) - 1)
    pick = np.where(np.abs(track.t[idx] - grid) < np.abs(track.t[idx - 1] - grid), idx, idx - 1)
    ok = np.abs(track.t[pick] - grid) <= step_s / 2
    # a silent stretch stays silent: only take hours that actually have a nearby report
    grid, pick = grid[ok], pick[ok]
    if grid.size < 2:
        return None
    la = np.round(track.lat[pick] / cell) * cell
    lo = np.round(track.lon[pick] / cell) * cell
    return Track(track.mmsi, track.name, track.ship_type, track.flag, grid, la, lo, estimate_sog(grid, la, lo),
                 np.full(grid.size, np.nan), None, track.imo)
