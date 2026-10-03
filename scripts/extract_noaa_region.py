"""Crop a NOAA MarineCadastre daily AIS parquet to a bounding box and save a small file.

    python scripts/extract_noaa_region.py data/raw/ais-2024-01-01.parquet data/processed/sfbay_2024-01-01.parquet

Default box is San Francisco Bay (west -122.65, south 37.40, east -122.0, north 38.10), a
region with dense, varied traffic (ferries, tugs, cargo, tankers, pilots, pleasure craft).
NOAA stores positions as WKB points; they are decoded here without extra dependencies.
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

BBOX = (37.40, -122.65, 38.10, -122.00)  # min_lat, min_lon, max_lat, max_lon
COLS = ["mmsi", "base_date_time", "sog", "cog", "vessel_name", "vessel_type", "geometry"]


def decode_wkb_points(blobs) -> tuple[np.ndarray, np.ndarray]:
    lon = np.empty(len(blobs))
    lat = np.empty(len(blobs))
    for i, b in enumerate(blobs):
        if b is None or len(b) < 21:
            lon[i] = lat[i] = np.nan
            continue
        fmt = "<dd" if b[0] == 1 else ">dd"
        lon[i], lat[i] = struct.unpack_from(fmt, b, 5)
    return lon, lat


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src", type=Path)
    ap.add_argument("dst", type=Path)
    ap.add_argument("--bbox", type=float, nargs=4, default=BBOX, metavar=("MIN_LAT", "MIN_LON", "MAX_LAT", "MAX_LON"))
    args = ap.parse_args()
    la0, lo0, la1, lo1 = args.bbox

    pf = pq.ParquetFile(args.src)
    keep = []
    for rg in range(pf.num_row_groups):
        tbl = pf.read_row_group(rg, columns=COLS).to_pandas()
        lon, lat = decode_wkb_points(tbl["geometry"].to_numpy())
        m = (lat >= la0) & (lat <= la1) & (lon >= lo0) & (lon <= lo1)
        if m.any():
            sub = tbl.loc[m, [c for c in COLS if c != "geometry"]].copy()
            sub["lat"], sub["lon"] = lat[m], lon[m]
            keep.append(sub)
    import pandas as pd

    out = pd.concat(keep, ignore_index=True).rename(columns={"base_date_time": "time"})
    args.dst.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(args.dst, index=False)
    print(f"{args.src.name}: kept {len(out):,} rows, {out['mmsi'].nunique():,} vessels -> {args.dst}")


if __name__ == "__main__":
    main()
