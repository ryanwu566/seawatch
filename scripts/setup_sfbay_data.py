"""One-time data setup: download NOAA public AIS for 1-3 Jan 2024 and crop it to San Francisco Bay.

    python scripts/setup_sfbay_data.py          # ~700 MB download, ~5 min; leaves ~10 MB in data/processed/
    python scripts/train_region_ml.py           # optional: ML second opinion for the region (~2 min)

Source: NOAA Office for Coastal Management / MarineCadastre AIS broadcast points (CC0 1.0).
"""

from __future__ import annotations

import subprocess
import sys
import urllib.request
from pathlib import Path

URL = "https://ocmgeodatastor1.blob.core.windows.net/marinecadastre/ais2024/ais-2024-01-{d:02d}.parquet"


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    raw, out = root / "data" / "raw", root / "data" / "processed"
    raw.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    for d in (1, 2, 3):
        dst = out / f"sfbay_2024-01-{d:02d}.parquet"
        if dst.exists():
            print(f"{dst.name} already present")
            continue
        src = raw / f"ais-2024-01-{d:02d}.parquet"
        if not src.exists():
            print(f"downloading {src.name} ...", flush=True)
            urllib.request.urlretrieve(URL.format(d=d), src)
        subprocess.run([sys.executable, str(root / "scripts" / "extract_noaa_region.py"), str(src), str(dst)], check=True)
    print("done - start the app with scripts/run_demo.ps1")


if __name__ == "__main__":
    main()
