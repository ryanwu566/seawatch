"""Measure the detectors against REAL outcome labels using Danish open AIS.

    python scripts/evaluate_real_outcomes.py data/raw/dma/aisdk-2024-11-18.zip [more zips ...]

Labels: OFAC sanctioned vessels (data/labels/ofac_sdn.csv, matched on IMO/MMSI) and documented incidents
(data/labels/incidents.csv). Partial (still-downloading) zips are read as far as they go. Output:
data/models/real_outcomes.json. See apps/api/seawatch/detection/realoutcomes.py for what the numbers do and do not mean.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

import numpy as np  # noqa: E402

from seawatch.detection import dma, labels, realoutcomes  # noqa: E402


def main() -> None:
    paths = [Path(p) for p in sys.argv[1:]]
    if not paths:
        raise SystemExit(__doc__)
    t = time.time()
    ls = labels.LabelSet(labels.load_ofac_sdn("data/labels/ofac_sdn.csv") + labels.load_incidents("data/labels/incidents.csv"))
    days, bounds = [], []
    for p in paths:
        df = dma.read_frame(p)
        tr = dma.frame_to_tracks(df, min_fixes=20)
        t0 = float(np.floor(df["t"].min() / 86400.0) * 86400.0)
        days.append(tr)
        bounds.append((t0, t0 + 86400.0))
        print(f"{p.name}: {len(tr)} vessels, {len(df):,} reports, covers {df['t'].min():.0f}..{df['t'].max():.0f}", flush=True)
    rep = realoutcomes.evaluate(days, bounds, ls)
    Path("data/models").mkdir(parents=True, exist_ok=True)
    Path("data/models/real_outcomes.json").write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in rep.items() if k != "labelled"}, indent=1, default=str))
    print("watch-listed vessels:")
    for r in rep["labelled"]:
        print("  ", r)
    print(f"done in {time.time() - t:.0f}s")


if __name__ == "__main__":
    main()
