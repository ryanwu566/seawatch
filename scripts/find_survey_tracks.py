"""Search the whole Taiwan GFW presence month for survey-like (lawnmower / zig-zag) tracks.

    python scripts/find_survey_tracks.py

Writes data/models/survey_candidates.csv (one row per detected pattern) and prints the strongest. These are *pattern matches*,
not confirmed survey operations: verify any candidate against open sources before treating it as a label.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from seawatch.detection import twworld  # noqa: E402
from seawatch.detection.config import DetectionConfig  # noqa: E402
from seawatch.detection.context import DetectionContext  # noqa: E402
from seawatch.detection.learned import LearnedContext  # noqa: E402
from seawatch.detection.survey import SURVEY_EXEMPT, survey_windows  # noqa: E402


def main() -> None:
    data = twworld.load()
    tracks = data["all"]
    cfg = DetectionConfig.hourly()
    learned = LearnedContext(cell_deg=0.1, min_slow_s=cfg.learn_min_slow_s, max_dt_s=cfg.learn_max_dt_s,
                             min_stop_vessels=cfg.learn_min_stop_vessels).fit(tracks)
    ctx = DetectionContext(twworld.zones(), [], None, learned=learned, bounds=twworld.AOI)
    rows = []
    for tr in tracks:
        if tr.ship_type in SURVEY_EXEMPT:
            continue
        for a, b, m in survey_windows(tr, cfg, ctx.benign_mask):
            rows.append({"mmsi": tr.mmsi, "name": tr.name, "flag": tr.flag, "type": tr.ship_type, "imo": tr.imo,
                         "start": pd.to_datetime(tr.t[a], unit="s", utc=True), "end": pd.to_datetime(tr.t[b], unit="s", utc=True),
                         "lat": round(float(np.mean(tr.lat[a:b + 1])), 2), "lon": round(float(np.mean(tr.lon[a:b + 1])), 2), **m})
    df = pd.DataFrame(rows)
    Path("data/models").mkdir(parents=True, exist_ok=True)
    df.to_csv("data/models/survey_candidates.csv", index=False)
    print(f"{len(df)} survey-like patterns on {df['mmsi'].nunique() if len(df) else 0} vessels (of {len(tracks)} checked)")
    if len(df):
        print(df.sort_values(["legs", "hours"], ascending=False).head(40).to_string(index=False))
        print(df.groupby(["flag", "type"]).size().sort_values(ascending=False).head(12))


if __name__ == "__main__":
    main()
