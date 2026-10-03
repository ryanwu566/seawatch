"""Load real historic AIS (CSV / Parquet, any common column naming) into detection Tracks.

Real archives differ in column names and units. This loader auto-detects the usual
variants, cleans obvious garbage (invalid coordinates, "not available" speeds,
duplicate timestamps) and returns :class:`Track` objects the detectors and ML models
already understand.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .models import Track

ALIASES = {
    "mmsi": ["mmsi", "userid", "user_id", "vessel_id", "id"],
    "time": ["basedatetime", "base_date_time", "timestamp", "time", "datetime", "date_time", "ts", "position_time", "epoch"],
    "lat": ["lat", "latitude", "y"],
    "lon": ["lon", "lng", "long", "longitude", "x"],
    "sog": ["sog", "speed", "speed_over_ground", "speedoverground", "speed_kn", "speed_knots"],
    "cog": ["cog", "course", "course_over_ground", "courseoverground", "heading_cog"],
    "name": ["vesselname", "vessel_name", "name", "shipname", "ship_name"],
    "status": ["status", "nav_status", "navigational_status", "navstatus", "navigationstatus"],
    "type": ["vesseltype", "vessel_type", "shiptype", "ship_type", "type", "ship_and_cargo_type"],
}


def _pick(cols: Iterable[str], key: str) -> str | None:
    low = {c.lower().replace(" ", "_"): c for c in cols}
    for a in ALIASES[key]:
        if a in low:
            return low[a]
    return None


def ship_category(code) -> str:
    """AIS ship-type code (or free text) -> coarse category used by the detectors."""

    try:
        c = int(float(code))
    except (TypeError, ValueError):
        s = str(code).lower()
        for k, v in (("tank", "tanker"), ("cargo", "cargo"), ("fish", "fishing"), ("passenger", "passenger"),
                     ("ferry", "ferry"), ("tug", "tug"), ("pilot", "pilot"), ("sail", "pleasure"), ("pleasure", "pleasure")):
            if k in s:
                return v
        return "other"
    if c == 30:
        return "fishing"
    if c in (31, 32, 52):
        return "tug"
    if c == 33:
        return "dredger"
    if c in (36, 37):
        return "pleasure"
    if c == 50:
        return "pilot"
    if c == 51:
        return "sar"
    if c in (53, 54, 55, 58):
        return "service"
    if 60 <= c <= 69:
        return "passenger"
    if 70 <= c <= 79:
        return "cargo"
    if 80 <= c <= 89:
        return "tanker"
    return "other"


def _read_any(path: Path) -> pd.DataFrame:
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path, low_memory=False)


def list_files(path: str | Path) -> list[Path]:
    p = Path(path)
    if p.is_file():
        return [p]
    exts = {".csv", ".gz", ".parquet", ".zst"}
    return sorted(f for f in p.rglob("*") if f.is_file() and (f.suffix in exts))


def inspect(path: str | Path, sample_rows: int = 5) -> dict:
    """Peek at an archive: files, columns, detected mapping, time/space extent (from the first file)."""

    files = list_files(path)
    if not files:
        return {"files": 0}
    df = _read_any(files[0])
    mapping = {k: _pick(df.columns, k) for k in ALIASES}
    out = {"files": len(files), "first_file": str(files[0]), "rows_in_first_file": int(len(df)),
           "columns": list(df.columns), "detected_mapping": mapping, "sample": df.head(sample_rows).to_dict("records")}
    try:
        if mapping["lat"] and mapping["lon"]:
            out["lat_range"] = [float(df[mapping["lat"]].min()), float(df[mapping["lat"]].max())]
            out["lon_range"] = [float(df[mapping["lon"]].min()), float(df[mapping["lon"]].max())]
        if mapping["time"]:
            out["time_range"] = [str(df[mapping["time"]].min()), str(df[mapping["time"]].max())]
        if mapping["mmsi"]:
            out["distinct_vessels_in_first_file"] = int(df[mapping["mmsi"]].nunique())
    except Exception as exc:  # noqa: BLE001 - inspection is best effort
        out["inspect_error"] = str(exc)
    return out


def load_tracks(path: str | Path, bbox: tuple[float, float, float, float] | None = None, min_fixes: int = 30,
                max_vessels: int | None = None, max_files: int | None = None) -> list[Track]:
    """Load tracks. ``bbox`` = (min_lat, min_lon, max_lat, max_lon) clips to an area of interest."""

    frames = []
    for f in list_files(path)[:max_files]:
        df = _read_any(f)
        m = {k: _pick(df.columns, k) for k in ALIASES}
        missing = [k for k in ("mmsi", "time", "lat", "lon") if m[k] is None]
        if missing:
            raise ValueError(f"{f.name}: cannot find columns for {missing}; columns are {list(df.columns)}")
        part = pd.DataFrame({
            "mmsi": df[m["mmsi"]].astype(str),
            "t": df[m["time"]],
            "lat": pd.to_numeric(df[m["lat"]], errors="coerce"),
            "lon": pd.to_numeric(df[m["lon"]], errors="coerce"),
            "sog": pd.to_numeric(df[m["sog"]], errors="coerce") if m["sog"] else np.nan,
            "cog": pd.to_numeric(df[m["cog"]], errors="coerce") if m["cog"] else np.nan,
            "name": df[m["name"]] if m["name"] else "",
            "type": df[m["type"]] if m["type"] else "",
            "status": pd.to_numeric(df[m["status"]], errors="coerce") if m["status"] else np.nan,
        })
        frames.append(part)
    data = pd.concat(frames, ignore_index=True)
    if pd.api.types.is_numeric_dtype(data["t"]):
        data["t"] = data["t"].astype(float)
        data.loc[data["t"] > 1e11, "t"] /= 1000.0  # milliseconds -> seconds
    else:
        stamp = pd.to_datetime(data["t"], utc=True, errors="coerce")
        data["t"] = ((stamp - pd.Timestamp("1970-01-01", tz="UTC")) / pd.Timedelta(seconds=1)).astype(float)
    data = data.dropna(subset=["t", "lat", "lon"])
    data = data[(data["lat"].between(-90, 90)) & (data["lon"].between(-180, 180)) & ~((data["lat"] == 0) & (data["lon"] == 0))]
    data.loc[data["sog"] >= 102.3, "sog"] = np.nan  # AIS 'not available'
    data.loc[data["cog"] >= 360, "cog"] = np.nan
    if bbox:
        data = data[data["lat"].between(bbox[0], bbox[2]) & data["lon"].between(bbox[1], bbox[3])]
    data = data.drop_duplicates(subset=["mmsi", "t"]).sort_values(["mmsi", "t"])
    tracks: list[Track] = []
    for mmsi, g in data.groupby("mmsi", sort=False):
        if len(g) < min_fixes or not mmsi.isdigit() or len(mmsi) != 9:
            continue
        name = str(g["name"].dropna().iloc[0]) if g["name"].notna().any() else mmsi
        tracks.append(Track(mmsi, name or mmsi, ship_category(g["type"].dropna().iloc[0]) if g["type"].notna().any() else "other",
                            "", g["t"].to_numpy(float), g["lat"].to_numpy(float), g["lon"].to_numpy(float),
                            g["sog"].to_numpy(float), g["cog"].to_numpy(float),
                            g["status"].fillna(-1).to_numpy(int) if g["status"].notna().any() else None))
        if max_vessels and len(tracks) >= max_vessels:
            break
    return tracks
