"""Train and evaluate the survey-shape model, then scan the real Taiwan month for survey-like windows the rules did not flag.

    python scripts/train_survey_ml.py
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from seawatch.detection import surveyml, twworld  # noqa: E402
from seawatch.detection.config import DetectionConfig  # noqa: E402
from seawatch.detection.context import DetectionContext  # noqa: E402
from seawatch.detection.learned import LearnedContext  # noqa: E402
from seawatch.detection.survey import survey_windows  # noqa: E402


def main() -> None:
    data = twworld.load()
    tracks = data["all"]
    df = surveyml.build_dataset(tracks)
    print(f"{len(df)} windows ({int(df['y'].sum())} synthetic survey positives)", flush=True)
    model, thr, report = surveyml.fit_and_evaluate(df)

    # rule detector on the same kind of synthetic positives (held-out comparison: how often does the rule fire?)
    cfg = DetectionConfig.hourly()
    lc = LearnedContext(cell_deg=0.1, min_slow_s=cfg.learn_min_slow_s, max_dt_s=cfg.learn_max_dt_s, min_stop_vessels=cfg.learn_min_stop_vessels).fit(tracks)
    ctx = DetectionContext(twworld.zones(), [], None, learned=lc, bounds=twworld.AOI)
    rng = np.random.default_rng(7)
    wins = surveyml.real_windows(tracks)
    hits = {"lawnmower": [0, 0], "zigzag": [0, 0], "racetrack": [0, 0]}
    from seawatch.detection.models import Track

    for _ in range(600):
        ti, i0, i1 = wins[int(rng.integers(len(wins)))]
        tr = tracks[ti]
        made = surveyml.make_positive(rng, tr, i0, i1, (float(rng.uniform(22, 26)), float(rng.uniform(118.5, 123))))
        if made is None:
            continue
        tt, la, lo, shape = made
        syn = Track(tr.mmsi, tr.name, "other", tr.flag, tt, la, lo, np.full(len(tt), np.nan), np.full(len(tt), np.nan))
        hits[shape][1] += 1
        hits[shape][0] += int(bool(survey_windows(syn, cfg, ctx.benign_mask)))
    report["rule_recall_on_same_synthetic_shapes"] = {k: round(a / max(b, 1), 3) for k, (a, b) in hits.items()}

    # scan real windows
    wins = surveyml.real_windows(tracks, step_h=24.0)
    rows = []
    for ti, i0, i1 in wins:
        tr = tracks[ti]
        f = surveyml.shape_features(tr.t[i0:i1], tr.lat[i0:i1], tr.lon[i0:i1])
        if f is not None:
            rows.append({**f, "mmsi": tr.mmsi, "name": tr.name, "flag": tr.flag, "type": tr.ship_type, "imo": tr.imo, "ti": ti, "i0": i0, "i1": i1})
    scan = pd.DataFrame(rows)
    scan["score"] = model.predict_proba(scan[surveyml.FEATURES])[:, 1]
    flagged = scan[scan["score"] >= thr].copy()
    rule_flag = []
    for r in flagged.itertuples():
        tr = tracks[r.ti]
        w = survey_windows(tr.slice(r.i0, r.i1), cfg, ctx.benign_mask)
        rule_flag.append(bool(w))
    flagged["rule_also_flags"] = rule_flag
    flagged["start"] = [pd.to_datetime(tracks[r.ti].t[r.i0], unit="s", utc=True) for r in flagged.itertuples()]
    flagged["lat"] = [round(float(np.mean(tracks[r.ti].lat[r.i0:r.i1])), 2) for r in flagged.itertuples()]
    flagged["lon"] = [round(float(np.mean(tracks[r.ti].lon[r.i0:r.i1])), 2) for r in flagged.itertuples()]
    cols = ["mmsi", "name", "flag", "type", "imo", "start", "lat", "lon", "score", "rev14", "mean_leg14", "hours", "speed_kn", "rule_also_flags"]
    flagged = flagged.sort_values("score", ascending=False)
    Path("data/models").mkdir(parents=True, exist_ok=True)
    flagged[cols].to_csv("data/models/survey_ml_candidates.csv", index=False)
    report["real_windows_scanned"] = int(len(scan))
    report["real_windows_flagged"] = int(len(flagged))
    report["real_flagged_vessels"] = int(flagged["mmsi"].nunique())
    report["real_flagged_also_by_rule"] = int(flagged["rule_also_flags"].sum())
    Path("data/models/survey_ml_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    import joblib

    joblib.dump({"model": model, "threshold": thr, "features": surveyml.FEATURES}, "data/models/survey_shape.joblib")
    print(json.dumps(report, indent=1))
    print(flagged[cols].head(30).to_string(index=False))


if __name__ == "__main__":
    main()
