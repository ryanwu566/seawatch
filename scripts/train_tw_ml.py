"""Train the ML second opinion for the real Taiwan (GFW presence) region and benchmark it on the held-out live days.

    python scripts/train_tw_ml.py
"""

from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from seawatch.detection import regionml  # noqa: E402

if __name__ == "__main__":
    t = time.time()
    report = regionml.train_and_save_tw()
    Path("data/models").mkdir(parents=True, exist_ok=True)
    Path("data/models/ml_taiwan-gfw_benchmark.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    for name, m in report["test"]["methods"].items():
        print(f"{name:34s} precision={m['precision']:.2f} recall={m['recall']:.2f} f1={m['f1']:.2f} roc_auc={m['roc_auc']} pr_auc={m['pr_auc']}")
    print(json.dumps(report["test"]["by_kind"], indent=1))
    print(f"done in {time.time() - t:.0f}s")
