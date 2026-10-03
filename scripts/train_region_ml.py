"""Train the ML second opinion for a region from its own history, benchmark on the held-out live day.

    python scripts/train_region_ml.py            # San Francisco Bay (real AIS)
    python scripts/train_detection_ml.py         # Taiwan simulation
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from seawatch.detection import regionml  # noqa: E402

if __name__ == "__main__":
    t = time.time()
    report = regionml.train_and_save_sf()
    Path("data/models/ml_sf-bay_benchmark.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    for name, m in report["test"]["methods"].items():
        print(f"{name:34s} precision={m['precision']:.2f} recall={m['recall']:.2f} f1={m['f1']:.2f} roc_auc={m['roc_auc']} pr_auc={m['pr_auc']}")
    print(json.dumps(report["test"]["by_kind"], indent=1))
    print(f"done in {time.time() - t:.0f}s")
