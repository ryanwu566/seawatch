"""Run SeaWatch on a new AIS export of Taiwan waters (CSV / parquet files or folders).

    python scripts/ingest_mentor_ais.py PATH [PATH ...] [--live-frac 0.2] [--save data/processed/mentor_tracks.parquet]

It prints what it understood about the file (columns, reporting interval, hourly vs message-level), then learns normal
traffic from the earlier part of the data and reports what the rules flag in the last part, with the classification and
the threat-factor evidence for every suspected unauthorised survey.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from seawatch.detection import mentor  # noqa: E402
from seawatch.detection.threat import factor_table  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--live-frac", type=float, default=0.2)
    ap.add_argument("--save", default="")
    a = ap.parse_args()

    tracks, info = mentor.load(a.paths)
    print("== what was read ==")
    for k, v in info.items():
        print(f"  {k}: {v}")
    print(f"  -> treated as {'HOURLY presence' if info['hourly'] else 'message-level AIS'}")
    if a.save:
        import pandas as pd

        rows = [(t.mmsi, t.name, t.ship_type, x, y, z, s) for t in tracks for x, y, z, s in zip(t.t, t.lat, t.lon, t.sog)]
        pd.DataFrame(rows, columns=["mmsi", "name", "type", "t", "lat", "lon", "sog"]).to_parquet(a.save)
        print("saved", a.save)

    r = mentor.analyse(tracks, info["hourly"], a.live_frac)
    print(f"\n== learned from {r['history_vessels']} vessels, monitored {r['live_vessels']} ==")
    print("events by kind:", dict(r["events_by_kind"]))
    print(f"alerts: {len(r['alerts'])}   high: {sum(1 for x in r['alerts'] if x.level == 'HIGH')}")
    print("\n== discarded as normal ==")
    for (kind, why), n in r["discards"]:
        print(f"  {n:>8}  {kind}: {why}")
    ft = factor_table(r["live"], r["ctx"], r["cfg"], r["events"])
    if ft:
        print("\n== threat factors ==", ft["single"])
        for c in ft["combinations"][:8]:
            print("  T%d V%d A%d P%d : %d vessels" % (c["territory"], c["velocity"], c["declared"], c["pattern"], c["vessels"]))
    print("\n== top alerts ==")
    for al in sorted(r["alerts"], key=lambda x: -x.risk)[:15]:
        print(f"  {al.risk:5.1f} {al.level:6} {al.title[:90]}")
    print("\nTo train models on this data: python scripts/train_tw_ml.py (set SEAWATCH_DATA_ROOT) - or ask for a custom-region trainer.")


if __name__ == "__main__":
    main()
