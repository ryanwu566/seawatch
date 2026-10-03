"""Train and benchmark the detection ML models, then save them for the API.

    python scripts/train_detection_ml.py

Trains on simulated seeds 1-10 and tests on held-out seeds 31-38. Replace/augment the
training set with real historic AIS via ``seawatch.detection.history`` when available.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from seawatch.detection import ml  # noqa: E402


def main() -> None:
    models, report = ml.run_benchmark()
    ml.save(models, report)
    Path("data/models").mkdir(parents=True, exist_ok=True)
    Path("data/models/detection_ml_benchmark.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    for name, m in report["methods"].items():
        print(f"{name:34s} precision={m['precision']:.2f} recall={m['recall']:.2f} f1={m['f1']:.2f} false={m['false']}")


if __name__ == "__main__":
    main()
