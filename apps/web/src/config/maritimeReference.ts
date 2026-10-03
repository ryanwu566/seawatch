import { getBaseUrl } from "../api/client";

export const MARITIME_REFERENCE_SOURCES = [
  {
    id: "seawatch-eez-reference",
    route: "/context/maritime-reference/eez-reference.geojson",
    attribution:
      'EEZ reference: <a href="https://www.marineregions.org/">Marine Regions / VLIZ, World EEZ v12</a> (CC BY 4.0)',
  },
  {
    id: "seawatch-territorial-sea-12nm",
    route: "/context/maritime-reference/territorial-sea-12nm-reference.geojson",
    attribution:
      '12 NM reference: <a href="https://data.gov.tw/dataset/155452">Taiwan Ministry of the Interior</a> (OGDL 1.0; derived polygon)',
  },
  {
    id: "seawatch-contiguous-zone-24nm",
    route: "/context/maritime-reference/contiguous-zone-24nm-reference.geojson",
    attribution:
      '24 NM reference: <a href="https://data.gov.tw/dataset/163012">Taiwan Ministry of the Interior</a> (OGDL 1.0; derived band)',
  },
] as const;

export const MARITIME_REFERENCE_LAYER_IDS = {
  eez: {
    fill: "seawatch-eez-reference-fill",
    line: "seawatch-eez-reference-line",
  },
  territorialSea12Nm: {
    fill: "seawatch-territorial-sea-12nm-fill",
    line: "seawatch-territorial-sea-12nm-line",
  },
  contiguousZone24Nm: {
    fill: "seawatch-contiguous-zone-24nm-fill",
    line: "seawatch-contiguous-zone-24nm-line",
  },
} as const;

const MARITIME_REFERENCE_SOURCE_ID_SET = new Set<string>(
  MARITIME_REFERENCE_SOURCES.map(({ id }) => id),
);

export function maritimeReferenceUrl(route: string): string {
  return `${getBaseUrl()}${route}`;
}

export function isMaritimeReferenceSourceId(sourceId: unknown): boolean {
  return typeof sourceId === "string" && MARITIME_REFERENCE_SOURCE_ID_SET.has(sourceId);
}
