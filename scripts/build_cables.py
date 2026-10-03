"""Clip the public TeleGeography submarine-cable map to the Taiwan region.

    curl -L -o data/geo/cable-geo.json https://www.submarinecablemap.com/api/v3/cable/cable-geo.json
    curl -L -o data/geo/landing-point-geo.json https://www.submarinecablemap.com/api/v3/landing-point/landing-point-geo.json
    python scripts/build_cables.py

Source: TeleGeography Submarine Cable Map (CC BY-NC-SA 4.0, https://www.submarinecablemap.com). Routes are approximate public
depictions, not survey-grade positions.
"""
import json
from pathlib import Path

from shapely.geometry import box, mapping, shape

GEO = Path(__file__).resolve().parents[1] / "data" / "geo"
W = box(112, 16, 130, 32)
feats = []
for f in json.loads((GEO / "cable-geo.json").read_text(encoding="utf8"))["features"]:
    g = shape(f["geometry"]).intersection(W)
    if g.is_empty:
        continue
    feats.append({"type": "Feature", "properties": {"id": f["properties"]["id"], "name": f["properties"]["name"]}, "geometry": mapping(g.simplify(0.003))})
(GEO / "taiwan_cables.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats,
    "attribution": "TeleGeography Submarine Cable Map, CC BY-NC-SA 4.0"}), encoding="utf8")
lp = []
for f in json.loads((GEO / "landing-point-geo.json").read_text(encoding="utf8"))["features"]:
    x, y = f["geometry"]["coordinates"][:2]
    if 112 <= x <= 130 and 16 <= y <= 32:
        lp.append({"type": "Feature", "properties": {"name": f["properties"]["name"]}, "geometry": f["geometry"]})
(GEO / "taiwan_landing_points.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": lp}), encoding="utf8")
print(len(feats), "cables,", len(lp), "landing points;", sorted(f["properties"]["name"] for f in feats))
