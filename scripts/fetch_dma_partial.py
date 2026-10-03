"""Download only the FIRST part of several Danish AIS daily files (the archive is time-ordered).

    python scripts/fetch_dma_partial.py --days 2024-11-01 2024-11-05 ... --mb 60

A 60 MB slice is roughly the first 3 hours of a day: enough static data (name, IMO, type, size, destination) for
~1,500 vessels. The link to the archive is slow (~0.3 MB/s), so this is meant to run in the background.
"""

from __future__ import annotations

import argparse
import urllib.request
from pathlib import Path

BASE = "http://aisdata.ais.dk.s3.eu-central-1.amazonaws.com/{year}/aisdk-{day}.zip"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", nargs="+", required=True)
    ap.add_argument("--mb", type=int, default=60)
    ap.add_argument("--out", default="data/raw/dma")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for day in args.days:
        dst = out / f"part-{day}.zip"
        if dst.exists() and dst.stat().st_size >= args.mb * 1_000_000 * 0.98:
            print(f"{dst.name} already present", flush=True)
            continue
        req = urllib.request.Request(BASE.format(year=day[:4], day=day), headers={"Range": f"bytes=0-{args.mb * 1_000_000 - 1}"})
        with urllib.request.urlopen(req, timeout=120) as r, open(dst, "wb") as fh:
            while chunk := r.read(1 << 20):
                fh.write(chunk)
        print(f"{dst.name}: {dst.stat().st_size / 1e6:.0f} MB", flush=True)


if __name__ == "__main__":
    main()
