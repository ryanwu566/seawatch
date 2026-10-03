"""Build the compact coastline files used for the TERRITORY factor.

    python scripts/build_taiwan_geo.py

Inputs (public domain, Natural Earth 1:10m, downloaded to data/geo/ by the setup notes in docs/rulebook.md):
    ne_10m_admin_0_countries.geojson
Outputs:
    data/geo/taiwan_land.geojson   Taiwan-administered land (main island, Kinmen, Penghu, Lanyu, Green Island, ...) plus
                                   small APPROXIMATE stand-ins for Matsu and Wuqiu, which Natural Earth does not include
    data/geo/neighbour_land.geojson  mainland China, Japan, Philippines (clipped, simplified) - used only for the equidistance
                                   approximation of the exclusive economic zone

These are reference geometries, not official legal baselines. Replace them with the official limits when available.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
GEO = ROOT / "data" / "geo"

# (name, lat, lon, radius_km) approximate stand-ins for Taiwan-administered islands missing from Natural Earth
EXTRA_ISLANDS = [
    ("Nangan (Matsu)", 26.160, 119.951, 3.0), ("Beigan (Matsu)", 26.223, 119.998, 2.5), ("Dongyin (Matsu)", 26.369, 120.496, 2.0),
    ("Juguang (Matsu)", 26.370, 120.250, 2.5), ("Wuqiu", 24.994, 119.444, 1.5),
]


def circle(lat: float, lon: float, r_km: float):
    dlat = r_km / 111.0
    dlon = r_km / (111.0 * math.cos(math.radians(lat)))
    ring = [(lon + dlon * math.cos(a), lat + dlat * math.sin(a)) for a in [i * math.pi / 12 for i in range(25)]]
    return shape({"type": "Polygon", "coordinates": [ring]})


def main() -> None:
    src = GEO / "ne_10m_admin_0_countries.geojson"
    if not src.exists():
        raise SystemExit(f"missing {src}: download Natural Earth ne_10m_admin_0_countries.geojson into data/geo/")
    data = json.loads(src.read_text(encoding="utf8"))
    tw, other = [], []
    window = box(112, 16, 130, 32)
    for f in data["features"]:
        admin = f["properties"].get("ADMIN")
        geom = shape(f["geometry"])
        if admin == "Taiwan":
            tw += list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        elif admin in ("China", "Japan", "Philippines", "South Korea", "Vietnam"):
            clipped = geom.intersection(window)
            if not clipped.is_empty:
                other.append(clipped.simplify(0.01))
    tw = [g.simplify(0.002) for g in tw] + [circle(la, lo, r) for _, la, lo, r in EXTRA_ISLANDS]
    feats = [{"type": "Feature", "properties": {"name": "Taiwan-administered land"}, "geometry": mapping(unary_union(tw))}]
    (GEO / "taiwan_land.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats,
                                                       "note": "Natural Earth (public domain) + approximate Matsu/Wuqiu stand-ins; not legal baselines"}), encoding="utf8")
    feats = [{"type": "Feature", "properties": {"name": "neighbour land"}, "geometry": mapping(unary_union(other))}]
    (GEO / "neighbour_land.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf8")
    for n in ("taiwan_land.geojson", "neighbour_land.geojson"):
        print(n, round((GEO / n).stat().st_size / 1e6, 2), "MB")


if __name__ == "__main__":
    main()
