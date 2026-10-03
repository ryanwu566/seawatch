"""Multi-seed tuning harness for the San Francisco Bay world.

    python scripts/tune_sf.py [--seeds 11 12 13 14 15] [--set loiter_min_minutes=60 ...]

Builds the SF world for several seeds (each moves the scripted events and injected vessels), runs the
detectors and reports per-behaviour recall, benign look-alike alerts and unverified alerts on real traffic.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from seawatch.detection import sfworld  # noqa: E402
from seawatch.detection.alerts import build_alerts  # noqa: E402
from seawatch.detection.config import DetectionConfig  # noqa: E402
from seawatch.detection.detectors import run_all  # noqa: E402
from seawatch.detection.evaluation import evaluate_alerts  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[11, 12, 13, 14, 15])
    ap.add_argument("--set", nargs="*", default=[], help="threshold overrides, e.g. loiter_min_minutes=60")
    args = ap.parse_args()
    over = {k: float(v) for k, v in (x.split("=") for x in args.set)}
    cfg = DetectionConfig.from_dict({**DetectionConfig().to_dict(), **over})
    days = sfworld.load_days(".")
    per_kind: dict[str, list[int]] = {}
    tot = Counter()
    unverified_kinds: Counter = Counter()
    for sd in args.seeds:
        scn, parts = sfworld.build_sf_scenario(days, seed=sd)
        ctx = sfworld.make_context(scn, parts)
        ev = run_all(scn.tracks, scn.t0, scn.t1, ctx, cfg)
        al = build_alerts(ev, scn.tracks, cfg)
        r = evaluate_alerts(al, scn)
        for k, v in r["per_kind"].items():
            a = per_kind.setdefault(k, [0, 0]); a[0] += v["detected"]; a[1] += v["truth"]
        tot["alerts"] += r["alerts"]; tot["true"] += r["true_alerts"]; tot["benign"] += r["false_alarms_on_benign_lookalikes"]
        tot["unverified"] += r["false_alarms"] - r["false_alarms_on_benign_lookalikes"]
        for a in al:
            if a.id in r["false_alarm_ids"]:
                unverified_kinds.update(a.kinds)
    print("recall:", {k: f"{a}/{b}" for k, (a, b) in sorted(per_kind.items())})
    n = len(args.seeds)
    print(f"per scenario: alerts={tot['alerts']/n:.1f} true={tot['true']/n:.1f} benign-lookalike alerts={tot['benign']/n:.1f} "
          f"unverified real={tot['unverified']/n:.1f}")
    print("unverified by kind:", dict(unverified_kinds.most_common()))


if __name__ == "__main__":
    main()
