"""Download the public sanctions list used for real-outcome labels (OFAC SDN, US Treasury).

    python scripts/fetch_watchlists.py

The list changes constantly: record the download date next to any result. Only vessels (matched on IMO / MMSI) are used.
"""

from __future__ import annotations

import urllib.request
from datetime import date
from pathlib import Path

URL = "https://www.treasury.gov/ofac/downloads/sdn.csv"


def main() -> None:
    out = Path("data/labels")
    out.mkdir(parents=True, exist_ok=True)
    dst = out / "ofac_sdn.csv"
    urllib.request.urlretrieve(URL, dst)
    (out / "ofac_sdn.downloaded").write_text(date.today().isoformat(), encoding="utf-8")
    print(f"saved {dst} ({dst.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
