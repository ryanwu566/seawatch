import { addProtocol, type StyleSpecification } from "maplibre-gl";
import { Protocol } from "pmtiles";
import emergencyGeographyRaw from "../assets/taiwan-emergency.geojson?raw";
import type { OperatingMode } from "../api/live";

export const PMTILES_ARCHIVE_URL = "/offline/taiwan.pmtiles";

export type BasemapStage = "nlsc" | "pmtiles" | "emergency";
export type OnlineFailureState = "healthy" | "nlsc_failed" | "pmtiles_failed";

let protocolRegistered = false;
const emergencyGeography = JSON.parse(emergencyGeographyRaw) as GeoJSON.FeatureCollection;

export function registerPmtilesProtocol(): void {
  if (protocolRegistered) return;
  const protocol = new Protocol();
  addProtocol("pmtiles", protocol.tile);
  protocolRegistered = true;
}

export function pmtilesStyle(): StyleSpecification {
  return {
    version: 8,
    sources: {
      "offline-vector": {
        type: "vector",
        url: `pmtiles://${PMTILES_ARCHIVE_URL}`,
        attribution: "Local operator-provided PMTiles",
      },
    },
    layers: [
      {
        id: "offline-background",
        type: "background",
        paint: { "background-color": "#071927" },
      },
      {
        id: "offline-water",
        type: "fill",
        source: "offline-vector",
        "source-layer": "water",
        paint: { "fill-color": "#0b3047" },
      },
      {
        id: "offline-land",
        type: "fill",
        source: "offline-vector",
        "source-layer": "landcover",
        paint: { "fill-color": "#173c42", "fill-opacity": 0.9 },
      },
      {
        id: "offline-roads",
        type: "line",
        source: "offline-vector",
        "source-layer": "transportation",
        paint: { "line-color": "#547078", "line-width": 0.6 },
      },
    ],
  };
}

export function emergencyStyle(): StyleSpecification {
  return {
    version: 8,
    sources: {
      "emergency-geography": {
        type: "geojson",
        data: emergencyGeography,
        attribution: "Natural Earth public domain (simplified)",
      },
    },
    layers: [
      {
        id: "emergency-sea",
        type: "background",
        paint: { "background-color": "#071927" },
      },
      {
        id: "emergency-land",
        type: "fill",
        source: "emergency-geography",
        paint: { "fill-color": "#27545a", "fill-opacity": 0.92 },
      },
      {
        id: "emergency-coast",
        type: "line",
        source: "emergency-geography",
        paint: { "line-color": "#8ac6c9", "line-width": 1.5 },
      },
    ],
  };
}

export function selectOfflineBasemap(
  mode: OperatingMode,
  onlineFailureState: OnlineFailureState,
): BasemapStage {
  if (mode === "CLOUD_LIVE") return "nlsc";
  if (onlineFailureState === "pmtiles_failed") return "emergency";
  if (onlineFailureState === "nlsc_failed") return "pmtiles";
  if (mode === "EDGE_LIVE" || mode === "EDGE_REPLAY" || mode === "NO_LIVE_SOURCE") {
    return "pmtiles";
  }
  return "nlsc";
}
