"""Bundled, public, civilian maritime reference data for GIS context.

Only public, civilian, non-operational references are included. No military
positions, no restricted/exclusion zones, no sensitive facilities. Named areas
are descriptive civilian references (illustrative approach/anchorage extents),
NOT operational data and NOT a permission/legality classification.

Provenance of every item here is ``official`` reference data (curated public
facts), distinct from the ``derived`` geometry computed over them.
"""

from __future__ import annotations

from dataclasses import dataclass

# Reference coverage bbox. A position outside this resolves to ``unknown``.
# Mirrors apps/web/src/config/taiwanMap.ts TAIWAN_BBOX.
BBOX_MIN_LON = 118.0
BBOX_MIN_LAT = 21.5
BBOX_MAX_LON = 123.5
BBOX_MAX_LAT = 26.5


@dataclass(frozen=True)
class PortRef:
    id: str
    name_zh: str
    name_en: str
    lon: float
    lat: float


# Public civilian commercial ports. Mirror of
# apps/web/src/config/taiwanMap.ts COMMERCIAL_PORTS (kept in sync intentionally;
# the backend does not import frontend config).
PORTS: tuple[PortRef, ...] = (
    PortRef("keelung", "基隆港", "Port of Keelung", 121.74, 25.13),
    PortRef("taipei", "臺北港", "Port of Taipei", 121.38, 25.17),
    PortRef("taichung", "臺中港", "Port of Taichung", 120.52, 24.29),
    PortRef("kaohsiung", "高雄港", "Port of Kaohsiung", 120.28, 22.61),
    PortRef("hualien", "花蓮港", "Port of Hualien", 121.62, 23.99),
    PortRef("anping", "安平港", "Port of Anping", 120.16, 23.0),
)

PORTS_SOURCE = "SeaWatch public civilian port reference (NLSC-area public ports)"

# Coastline / land polygons. Same simplified Natural Earth public-domain outline
# bundled for the emergency map (apps/web/src/assets/taiwan-emergency.geojson),
# used here only as reference geometry for distance-to-coast. Rings are
# [lon, lat] closed rings.
COASTLINE_SOURCE = "Natural Earth public-domain outline, simplified (reference)"

COASTLINE_RINGS: tuple[tuple[tuple[float, float], ...], ...] = (
    # Taiwan main island.
    (
        (120.02, 21.90), (120.72, 21.88), (121.18, 22.45),
        (121.55, 23.15), (121.93, 24.32), (121.99, 25.02),
        (121.60, 25.30), (121.05, 25.18), (120.55, 24.55),
        (120.10, 23.65), (120.02, 22.70), (120.02, 21.90),
    ),
    # Penghu.
    (
        (119.48, 23.45), (119.68, 23.43), (119.72, 23.64),
        (119.50, 23.68), (119.48, 23.45),
    ),
)


@dataclass(frozen=True)
class MaritimeAreaRef:
    id: str
    name_zh: str
    name_en: str
    # Descriptive label for the reviewer, not a rule classification.
    kind: str  # "anchorage" | "approach" | "fairway" | "port_area"
    # Closed polygon ring [lon, lat][]. Illustrative civilian extent.
    ring: tuple[tuple[float, float], ...]


AREAS_SOURCE = (
    "SeaWatch civilian maritime-area reference (illustrative public "
    "approach/anchorage extents; not operational data)"
)

# Illustrative civilian anchorage / port-approach extents around two major
# commercial ports. These are rectangular reference extents on the seaward side
# of the port, following the AIRSPACE_AREAS ring precedent. They carry no
# permission semantics.
MARITIME_AREAS: tuple[MaritimeAreaRef, ...] = (
    MaritimeAreaRef(
        id="kaohsiung-approach",
        name_zh="高雄港進場區（示意）",
        name_en="Kaohsiung port approach (illustrative)",
        kind="approach",
        ring=(
            (120.18, 22.52), (120.30, 22.52),
            (120.30, 22.63), (120.18, 22.63), (120.18, 22.52),
        ),
    ),
    MaritimeAreaRef(
        id="kaohsiung-anchorage-a",
        name_zh="高雄錨地 A（示意）",
        name_en="Kaohsiung Anchorage A (illustrative)",
        kind="anchorage",
        ring=(
            (120.20, 22.55), (120.26, 22.55),
            (120.26, 22.60), (120.20, 22.60), (120.20, 22.55),
        ),
    ),
    MaritimeAreaRef(
        id="keelung-approach",
        name_zh="基隆港進場區（示意）",
        name_en="Keelung port approach (illustrative)",
        kind="approach",
        ring=(
            (121.70, 25.13), (121.80, 25.13),
            (121.80, 25.22), (121.70, 25.22), (121.70, 25.13),
        ),
    ),
)


def in_bbox(lon: float, lat: float) -> bool:
    """Whether a position is inside the reference coverage bbox."""

    return (
        BBOX_MIN_LON <= lon <= BBOX_MAX_LON
        and BBOX_MIN_LAT <= lat <= BBOX_MAX_LAT
    )
