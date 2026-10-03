// Taiwan map configuration: official NLSC basemaps, public commercial ports, and
// public airspace context. Only public, civilian, non-operational information is
// included. No military positions, deployments, or sensitive facilities.

import type { StyleSpecification } from "maplibre-gl";

export const TAIWAN_CENTER: [number, number] = [120.9, 23.6];
export const TAIWAN_ZOOM = 6.6;
export const TAIWAN_BBOX = { minLat: 21.5, minLon: 118.0, maxLat: 26.5, maxLon: 123.5 };
export const OPENFREEMAP_LIBERTY_STYLE_URL =
  "https://tiles.openfreemap.org/styles/liberty";

// Quick-navigation presets. Bounds are intentionally centered on WATER (ports
// are approached from their seaward side) so a preset never centers inland.
export interface LocationPreset {
  id: "taiwan" | "keelung" | "strait" | "kaohsiung";
  labelKey: "presetTaiwanWaters" | "presetKeelung" | "presetTaiwanStrait" | "presetKaohsiung";
  /** [west, south, east, north] */
  bounds: [number, number, number, number];
}

export const LOCATION_PRESETS: LocationPreset[] = [
  { id: "taiwan", labelKey: "presetTaiwanWaters", bounds: [118.0, 21.5, 123.5, 26.3] },
  // Keelung approaches: north coast waters.
  { id: "keelung", labelKey: "presetKeelung", bounds: [121.5, 25.05, 122.1, 25.45] },
  // Taiwan Strait: the water channel west of the island.
  { id: "strait", labelKey: "presetTaiwanStrait", bounds: [118.6, 23.0, 120.4, 25.2] },
  // Kaohsiung approaches: south-west harbour waters.
  { id: "kaohsiung", labelKey: "presetKaohsiung", bounds: [120.1, 22.3, 120.5, 22.75] },
];


// --- Official Taiwan NLSC basemaps (public WMTS, EPSG:3857 / Web Mercator) --- //
// NLSC (National Land Surveying and Mapping Center) publishes public web tiles.
// We reference them as raster sources; tiles are fetched on demand (no bulk
// caching) and attribution is kept visible. If a browser blocks these via CORS,
// the UI surfaces a note rather than faking success (see MapCanvas error state).
export const NLSC_EMAP_TILES =
  "https://wmts.nlsc.gov.tw/wmts/EMAP/default/GoogleMapsCompatible/{z}/{y}/{x}";
export const NLSC_PHOTO_TILES =
  "https://wmts.nlsc.gov.tw/wmts/PHOTO2/default/GoogleMapsCompatible/{z}/{y}/{x}";
export const NLSC_ATTRIBUTION =
  "© 內政部國土測繪中心 NLSC Taiwan";

export type BaseMapId = "nlsc-emap" | "nlsc-photo";

/** Build a MapLibre style for an NLSC raster basemap. */
export function nlscStyle(base: BaseMapId): StyleSpecification {
  const tiles = base === "nlsc-photo" ? NLSC_PHOTO_TILES : NLSC_EMAP_TILES;
  return {
    version: 8,
    sources: {
      "nlsc-base": {
        type: "raster",
        tiles: [tiles],
        tileSize: 256,
        attribution: NLSC_ATTRIBUTION,
        maxzoom: 18,
      },
    },
    layers: [
      {
        id: "nlsc-base-layer",
        type: "raster",
        source: "nlsc-base",
      },
    ],
  };
}

/** Primary online vector style; the existing orthophoto remains selectable. */
export function onlineStyle(base: BaseMapId): StyleSpecification | string {
  return base === "nlsc-photo" ? nlscStyle(base) : OPENFREEMAP_LIBERTY_STYLE_URL;
}

// --- Public commercial ports (civilian) ------------------------------------ //
export interface Port {
  id: string;
  nameZh: string;
  nameEn: string;
  lon: number;
  lat: number;
}

export const COMMERCIAL_PORTS: Port[] = [
  { id: "keelung", nameZh: "基隆港", nameEn: "Port of Keelung", lon: 121.74, lat: 25.13 },
  { id: "taipei", nameZh: "臺北港", nameEn: "Port of Taipei", lon: 121.38, lat: 25.17 },
  { id: "taichung", nameZh: "臺中港", nameEn: "Port of Taichung", lon: 120.52, lat: 24.29 },
  { id: "kaohsiung", nameZh: "高雄港", nameEn: "Port of Kaohsiung", lon: 120.28, lat: 22.61 },
  { id: "hualien", nameZh: "花蓮港", nameEn: "Port of Hualien", lon: 121.62, lat: 23.99 },
  { id: "anping", nameZh: "安平港", nameEn: "Port of Anping", lon: 120.16, lat: 23.0 },
];

export function portsGeoJson(): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: COMMERCIAL_PORTS.map((p) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [p.lon, p.lat] },
      properties: { id: p.id, nameZh: p.nameZh, nameEn: p.nameEn },
    })),
  };
}

// --- Public airspace context (contextual only) ----------------------------- //
// Illustrative public FIR / airspace reference polygons. These are contextual
// civilian references, NOT live radar tracks and NOT operational military data.
export interface AirspaceArea {
  id: string;
  nameZh: string;
  nameEn: string;
  kind: "restricted" | "fir";
  /** Simple polygon ring [lon, lat][]. */
  ring: [number, number][];
}

export const AIRSPACE_AREAS: AirspaceArea[] = [
  {
    id: "taipei-fir",
    nameZh: "臺北飛航情報區（示意邊界）",
    nameEn: "Taipei FIR (illustrative boundary)",
    kind: "fir",
    ring: [
      [117.5, 21.0],
      [124.5, 21.0],
      [124.5, 29.0],
      [117.5, 29.0],
      [117.5, 21.0],
    ],
  },
];

export function airspaceGeoJson(): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: AIRSPACE_AREAS.map((a) => ({
      type: "Feature",
      geometry: { type: "Polygon", coordinates: [a.ring] },
      properties: { id: a.id, nameZh: a.nameZh, nameEn: a.nameEn, kind: a.kind },
    })),
  };
}
