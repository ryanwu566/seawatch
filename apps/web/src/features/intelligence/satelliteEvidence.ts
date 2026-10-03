export type SatelliteEvidenceValue = string | number | boolean;

export type SatelliteEvidenceProvenance = "Observed" | "Derived" | "Unknown";

export interface SatelliteEvidence {
  provider?: SatelliteEvidenceValue;
  scene_id?: SatelliteEvidenceValue;
  platform?: SatelliteEvidenceValue;
  datetime?: SatelliteEvidenceValue;
  orbit?: SatelliteEvidenceValue;
  availability?: SatelliteEvidenceValue;
  provenance?: Partial<
    Record<
      "scene_id" | "platform" | "datetime" | "orbit" | "availability",
      SatelliteEvidenceProvenance
    >
  >;
}
