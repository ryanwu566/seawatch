"""Write Taiwan's modelled maritime limits (12 nm, 24 nm, EEZ-approximation) as lines for the map.

    python scripts/build_zone_lines.py
Reference geometry only (see territory.py); not legal baselines.
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
from seawatch.detection.territory import Territory  # noqa: E402

t = Territory.default()
fig, ax = plt.subplots()
feats = []
for level, name in ((2.5, "territorial sea (12 nm)"), (1.5, "contiguous zone (24 nm)"), (0.5, "EEZ (approx. 200 nm / median line)")):
    cs = ax.contour(t._lons, t._lats, t.zone.astype(float), levels=[level])
    segs = cs.allsegs[0]
    lines = [[[round(float(x), 3), round(float(y), 3)] for x, y in s[::3]] for s in segs if len(s) > 6]
    feats.append({"type": "Feature", "properties": {"name": name, "level": {2.5: "ts", 1.5: "cz", 0.5: "eez"}[level]},
                  "geometry": {"type": "MultiLineString", "coordinates": lines}})
out = Path("data/geo/taiwan_zone_lines.geojson")
out.write_text(json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf8")
print(out, round(out.stat().st_size / 1e3), "kB", [len(f["geometry"]["coordinates"]) for f in feats])
