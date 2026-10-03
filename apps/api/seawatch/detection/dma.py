"""Loader for the Danish Maritime Authority open AIS archive (aisdata.ais.dk, daily zip of one CSV).

Covers Danish waters and the south-western Baltic with IMO numbers, navigational status and ship type, which makes it
the open archive best suited to testing against real outcomes (shadow-fleet transits, documented incidents).

Works on complete zips and, for development while a download is still running, on a truncated zip: the CSV is
time-ordered, so the first hours are still readable.
"""

from __future__ import annotations

import io
import struct
import zlib
from pathlib import Path
from typing import Iterator

import numpy as np
import pandas as pd

from .history import ship_category
from .models import Track

#: South-western Baltic + Danish straits + Kattegat (min_lat, min_lon, max_lat, max_lon)
BBOX_DK = (54.3, 9.3, 57.9, 15.8)

_NAV = {"at anchor": 1, "moored": 5, "aground": 6, "under way using engine": 0, "under way sailing": 8,
        "engaged in fishing": 7, "restricted manoeuvrability": 3, "restricted maneuverability": 3, "constrained by her draught": 4, "not under command": 2}
_COLS = {0: "time", 1: "mobile", 2: "mmsi", 3: "lat", 4: "lon", 5: "nav", 7: "sog", 8: "cog", 10: "imo", 12: "name", 13: "type",
         15: "width", 16: "length", 18: "draught", 19: "dest"}


def _inflate_lines(path: Path, chunk: int = 1 << 20) -> Iterator[str]:
    """Yield CSV lines from the first member of a (possibly truncated) zip, without needing the central directory."""

    with open(path, "rb") as fh:
        head = fh.read(30)
        if head[:4] != b"PK\x03\x04":
            raise ValueError(f"{path.name}: not a zip file")
        n, m = struct.unpack("<HH", head[26:30])
        fh.seek(30 + n + m)
        d = zlib.decompressobj(-zlib.MAX_WBITS)
        tail = b""
        while True:
            raw = fh.read(chunk)
            if not raw:
                break
            try:
                buf = tail + d.decompress(raw)
            except zlib.error:
                break  # truncated mid-stream
            lines = buf.split(b"\n")
            tail = lines.pop()
            for ln in lines:
                yield ln.decode("utf8", "replace")
            if d.eof:
                break


def read_frame(path: str | Path, bbox: tuple[float, float, float, float] = BBOX_DK, max_rows: int | None = None,
               block: int = 400_000) -> pd.DataFrame:
    """Cleaned, thinned (one report per vessel per minute) positions inside ``bbox``."""

    path = Path(path)
    frames: list[pd.DataFrame] = []
    buf: list[str] = []
    seen = 0

    def flush():
        if not buf:
            return
        df = pd.read_csv(io.StringIO("\n".join(buf)), header=None, usecols=list(_COLS), names=None, dtype=str, on_bad_lines="skip")
        df = df.rename(columns=_COLS)
        df = df[df["mobile"].isin(["Class A", "Class B"])]
        for c in ("lat", "lon", "sog", "cog", "width", "length", "draught"):
            df[c] = pd.to_numeric(df[c].str.replace(",", ".", regex=False), errors="coerce")
        df = df.dropna(subset=["lat", "lon"])
        df = df[df["lat"].between(bbox[0], bbox[2]) & df["lon"].between(bbox[1], bbox[3])]
        if len(df):
            df["t"] = (pd.to_datetime(df["time"], format="%d/%m/%Y %H:%M:%S", utc=True, errors="coerce") - pd.Timestamp("1970-01-01", tz="UTC")) \
                / pd.Timedelta(seconds=1)
            df = df.dropna(subset=["t"])
            df["bucket"] = (df["t"] // 60).astype("int64")
            df = df.drop_duplicates(["mmsi", "bucket"])
            frames.append(df.drop(columns=["time", "mobile", "bucket"]))
        buf.clear()

    for i, line in enumerate(_inflate_lines(path)):
        if i == 0 and line.startswith("#"):
            continue
        buf.append(line)
        seen += 1
        if len(buf) >= block:
            flush()
        if max_rows and seen >= max_rows:
            break
    flush()
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    return out.drop_duplicates(["mmsi", "t"])


def frame_to_tracks(df: pd.DataFrame, min_fixes: int = 20) -> list[Track]:
    tracks: list[Track] = []
    df = df.sort_values(["mmsi", "t"])
    for mmsi, g in df.groupby("mmsi", sort=False):
        if len(g) < min_fixes or not (isinstance(mmsi, str) and mmsi.isdigit() and len(mmsi) == 9):
            continue
        sog = g["sog"].where(g["sog"] < 102.3)
        cog = g["cog"].where(g["cog"] < 360)
        nav = g["nav"].fillna("").str.lower().map(_NAV).fillna(-1).astype(int).to_numpy()
        imo = next((x for x in g["imo"].dropna() if x.isdigit()), "")
        name = next((x for x in g["name"].dropna() if x.strip()), mmsi)
        stype = next((x for x in g["type"].dropna() if x.strip() and x.lower() not in ("undefined", "not applicable")), "")
        tracks.append(Track(mmsi, name.strip(), ship_category(stype), "", g["t"].to_numpy(float), g["lat"].to_numpy(float),
                            g["lon"].to_numpy(float), sog.to_numpy(float), cog.to_numpy(float), nav, imo))
    return tracks


def load_tracks(paths: list[str | Path], bbox=BBOX_DK, min_fixes: int = 20, max_rows: int | None = None) -> list[Track]:
    frames = [read_frame(p, bbox, max_rows) for p in paths]
    frames = [f for f in frames if len(f)]
    return frame_to_tracks(pd.concat(frames, ignore_index=True), min_fixes) if frames else []
