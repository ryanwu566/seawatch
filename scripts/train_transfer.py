"""Train on real San Francisco Bay AIS, test on the Taiwan simulation.

    python scripts/extract_noaa_region.py data/raw/ais-2024-01-0N.parquet data/processed/sfbay_2024-01-0N.parquet   (N=1..3)
    python scripts/train_transfer.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from seawatch.detection import ml, transfer  # noqa: E402


def main() -> None:
    files = sorted(Path("data/processed").glob("sfbay_2024-01-0*.parquet"))
    if not files:
        raise SystemExit("No data/processed/sfbay_*.parquet - run scripts/extract_noaa_region.py first.")
    t = time.time()
    days = transfer.load_days(files)
    print(f"loaded {len(days)} days, {sum(len(d) for d in days)} vessel-days in {time.time() - t:.0f}s", flush=True)
    models, report = transfer.run_transfer(days)
    Path("data/models").mkdir(parents=True, exist_ok=True)
    Path("data/models/transfer_benchmark.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    import joblib

    joblib.dump({"models": models, "report": report}, "data/models/transfer_models.joblib")
    print(json.dumps(report, indent=1))
    print(f"done in {time.time() - t:.0f}s")


if __name__ == "__main__":
    main()
