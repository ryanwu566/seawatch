"""Vessel identity-profile screening against sanctions-list labels (Danish AIS).

    python scripts/evaluate_profile.py data/raw/dma/part-*.zip data/raw/dma/aisdk-2024-11-18.zip

Builds one row per distinct vessel (de-duplicated by IMO/MMSI across files), labels it from the OFAC list, and reports
cross-validated screening performance next to trivial baselines. Output: data/models/profile_screen.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

import pandas as pd  # noqa: E402

from seawatch.detection import dma, labels, profile  # noqa: E402


def main() -> None:
    paths = [Path(p) for p in sys.argv[1:]]
    if not paths:
        raise SystemExit(__doc__)
    ls = labels.LabelSet(labels.load_ofac_sdn("data/labels/ofac_sdn.csv"))
    tabs = []
    for p in paths:
        df = dma.read_frame(p)
        if len(df):
            tabs.append(profile.static_table(df).assign(source=p.name))
            print(f"{p.name}: {len(df):,} reports", flush=True)
    tab = pd.concat(tabs, ignore_index=True)
    # one row per vessel: keep the row with most reports
    tab["key"] = tab["imo"].where(tab["imo"] != "", "mmsi:" + tab["mmsi"])
    tab = tab.sort_values("n", ascending=False).drop_duplicates("key").reset_index(drop=True)
    y = profile.label_vector(tab, ls)
    res = {"files": [p.name for p in paths], "vessels": int(len(tab)), "listed": int(y.sum()),
           "listed_vessels": tab[y == 1][["mmsi", "name", "imo", "mid", "type"]].to_dict("records"),
           "by_flag_prefix": profile.mid_lift(tab, y), "cv": profile.cross_validate(tab, y)}
    Path("data/models").mkdir(parents=True, exist_ok=True)
    Path("data/models/profile_screen.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "listed_vessels"}, indent=1, default=str))


if __name__ == "__main__":
    main()
