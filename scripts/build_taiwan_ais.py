"""Build the cached tracks for the real April 2026 Taiwan regions.

    python scripts/build_taiwan_ais.py DAY.csv RESEARCH_01.csv RESEARCH_02.csv
"""
import pickle
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
from seawatch.detection import mentor  # noqa: E402

day, r1, r2 = sys.argv[1:4]
day_t, _ = mentor.load([day])
res_t, _ = mentor.load([r1, r2])
out = Path("data/processed/taiwan_ais_apr2026.pkl")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_bytes(pickle.dumps((day_t, res_t)))
print(len(day_t), "day tracks,", len(res_t), "research-file tracks ->", out)
