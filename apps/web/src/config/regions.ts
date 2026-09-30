// Region configuration. Keeps two contexts strictly separate and never blurs
// them: the validated real-data analytical benchmark (NOAA SF Bay) and the
// Taiwan presentation layer (synthetic demo scenario in this build).

export type RegionId = "sf-bay" | "taiwan-demo";

export interface RegionConfig {
  id: RegionId;
  /** Short region label shown in the header badge. */
  region: string;
  /** Data source / provenance label shown in the header badge. */
  source: string;
  /** Whether this region's data is observed AIS or a synthetic scenario. */
  dataKind: "real" | "synthetic";
  /** MapLibre initial center [lng, lat]. */
  center: [number, number];
  /** MapLibre initial zoom. */
  zoom: number;
}

export const SF_BAY_REGION: RegionConfig = {
  id: "sf-bay",
  region: "SF Bay Benchmark",
  source: "NOAA MarineCadastre AIS",
  dataKind: "real",
  center: [-122.4, 37.75],
  zoom: 8,
};

// Taiwan and immediately surrounding civilian waters. Centered on the island;
// reference civilian ports (Keelung, Taichung, Kaohsiung) inform the extent.
// No sensitive or military locations are hard-coded.
export const TAIWAN_DEMO_REGION: RegionConfig = {
  id: "taiwan-demo",
  region: "Taiwan Demo",
  source: "Synthetic Demo Scenario",
  dataKind: "synthetic",
  center: [120.6, 23.9],
  zoom: 7,
};

/**
 * The active region depends on demo mode:
 * - Demo mode on  -> Taiwan Demo (synthetic scenario).
 * - Demo mode off -> SF Bay Benchmark (NOAA real AIS from the backend).
 */
export function activeRegion(demoMode: boolean): RegionConfig {
  return demoMode ? TAIWAN_DEMO_REGION : SF_BAY_REGION;
}
