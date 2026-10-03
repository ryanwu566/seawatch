"""Run the rule detectors on REAL San Francisco Bay AIS - clean, with injected events, and a threshold sweep.

    python scripts/evaluate_rules_on_real.py

Context (ports/anchorages, receiver coverage, normal traffic) is learned from the same archive, so no
hand-drawn zones are needed. Reports: alerts per 100 vessel-days on untouched real tracks, recall of
injected behaviours, and how the alert rate responds to each threshold (false-alarm budgeting).
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from seawatch.detection import transfer  # noqa: E402
from seawatch.detection.alerts import build_alerts  # noqa: E402
from seawatch.detection.config import DetectionConfig  # noqa: E402
from seawatch.detection.context import DetectionContext, TrafficBaseline  # noqa: E402
from seawatch.detection.detectors import run_all  # noqa: E402
from seawatch.detection.evaluation import evaluate_alerts  # noqa: E402
from seawatch.detection.inject import inject  # noqa: E402
from seawatch.detection.learned import LearnedContext  # noqa: E402
from seawatch.detection.models import Scenario  # noqa: E402


def main() -> None:
    files = sorted(Path("data/processed").glob("sfbay_2024-01-0*.parquet"))
    days = transfer.load_days(files)
    allt = [t for d in days for t in d]
    ctx = DetectionContext([], [], TrafficBaseline().fit(allt), learned=LearnedContext().fit(allt))
    cfg = DetectionConfig()
    report: dict = {"vessel_days": sum(len(d) for d in days), "clean": {}, "injected": {}, "sweep": {}}

    # 1) untouched real tracks
    kinds: Counter = Counter()
    n_alerts = 0
    for d in days:
        t0, t1 = transfer._day_bounds(d)
        ev = run_all(d, t0, t1, ctx, cfg)
        al = build_alerts(ev, d, cfg)
        kinds.update(e.kind for e in ev)
        n_alerts += len(al)
    vd = report["vessel_days"]
    report["clean"] = {"events_by_kind": dict(kinds), "alerts": n_alerts, "alerts_per_100_vessel_days": round(100 * n_alerts / vd, 1)}

    # 2) injected behaviours on real tracks
    tot = {"alerts": 0, "true": 0, "false": 0, "truth": 0, "det": 0}
    per_kind: dict = {}
    for i, d in enumerate(days):
        tracks, truth = inject(d, 100 + i, 8)
        t0, t1 = transfer._day_bounds(tracks)
        ev = run_all(tracks, t0, t1, ctx, cfg)
        al = build_alerts(ev, tracks, cfg)
        r = evaluate_alerts(al, Scenario("sf", t0, t1, tracks, [], [], truth, 0))
        tot["alerts"] += r["alerts"]; tot["true"] += r["true_alerts"]; tot["false"] += r["false_alarms"]
        tot["truth"] += sum(v["truth"] for v in r["per_kind"].values()); tot["det"] += sum(v["detected"] for v in r["per_kind"].values())
        for k, v in r["per_kind"].items():
            a = per_kind.setdefault(k, [0, 0]); a[0] += v["detected"]; a[1] += v["truth"]
    report["injected"] = {**tot, "recall": round(tot["det"] / max(1, tot["truth"]), 3),
                          "alert_precision": round(tot["true"] / max(1, tot["alerts"]), 3),
                          "recall_by_kind": {k: f"{a}/{b}" for k, (a, b) in per_kind.items()}}

    # 3) threshold sweep on clean real data (events per 100 vessel-days)
    sweeps = {"gap_min_minutes": [20, 30, 40, 60, 90, 120], "loiter_min_minutes": [45, 60, 90, 120, 180, 240],
              "rendezvous_min_minutes": [20, 30, 45, 60, 90], "deviation_min_minutes": [30, 60, 90, 120]}
    kind_of = {"gap_min_minutes": "ais_gap", "loiter_min_minutes": "loitering", "rendezvous_min_minutes": "rendezvous",
               "deviation_min_minutes": "route_deviation"}
    for name, values in sweeps.items():
        row = {}
        for v in values:
            c = DetectionConfig.from_dict({**cfg.to_dict(), name: v})
            n = 0
            for d in days:
                t0, t1 = transfer._day_bounds(d)
                n += sum(e.kind == kind_of[name] for e in run_all(d, t0, t1, ctx, c))
            row[str(v)] = round(100 * n / vd, 1)
        report["sweep"][name] = row
    Path("data/models").mkdir(parents=True, exist_ok=True)
    Path("data/models/rules_on_real_sfbay.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
