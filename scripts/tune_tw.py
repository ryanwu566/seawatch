"""Multi-seed tuning harness for the Taiwan (GFW presence) world.

    python scripts/tune_tw.py [--seeds 21 22 23]

For each seed the scripted and injected behaviours move; real background traffic is identical. Prints per-behaviour recall and the
number of alerts on untouched real vessels at several alert thresholds (the operator's alert budget).
"""

from __future__ import annotations

import argparse
import sys
import warnings
from collections import Counter
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from seawatch.detection import twworld  # noqa: E402
from seawatch.detection.alerts import build_alerts  # noqa: E402
from seawatch.detection.detectors import run_all  # noqa: E402
from seawatch.detection.evaluation import evaluate_alerts  # noqa: E402

THRESHOLDS = (30, 40, 50, 55, 60, 70)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[21, 22, 23])
    args = ap.parse_args()
    data = twworld.load()
    rec = {t: Counter() for t in THRESHOLDS}
    n_truth = Counter()
    unver = {t: 0 for t in THRESHOLDS}
    true_n = {t: 0 for t in THRESHOLDS}
    for sd in args.seeds:
        scn, parts = twworld.build_tw_scenario(data, sd)
        ctx = twworld.make_context(scn, parts)
        cfg = parts["cfg"]
        ev = run_all(scn.tracks, scn.t0, scn.t1, ctx, cfg)
        base = build_alerts(ev, scn.tracks, cfg)
        for thr in THRESHOLDS:
            al = [a for a in base if a.risk >= thr]
            r = evaluate_alerts(al, scn)
            for k, v in r["per_kind"].items():
                rec[thr][k] += v["detected"]
                if thr == THRESHOLDS[0]:
                    n_truth[k] += v["truth"]
            unver[thr] += r["false_alarms"]
            true_n[thr] += r["true_alerts"]
    days = 4 * len(args.seeds)
    for thr in THRESHOLDS:
        print(f"risk >= {thr}: recall " + ", ".join(f"{k} {rec[thr][k]}/{n_truth[k]}" for k in sorted(n_truth)) +
              f" | alerts on added events {true_n[thr]} | unverified on real vessels {unver[thr] / days:.0f} per day")


if __name__ == "__main__":
    main()
