import { describe, expect, it } from "vitest";
import type { LiveVesselFeature } from "../api/live";
import {
  countVesselCategories,
  normalizeVesselCategory,
} from "./vesselCategory";

function vessel(
  id: string,
  vesselType: number | null,
  providerVesselType?: string | null,
  providerVesselTypeSpecific?: string | null,
): LiveVesselFeature {
  return {
    type: "Feature",
    id,
    geometry: { type: "Point", coordinates: [120, 22] },
    properties: {
      provider_id: id,
      sog_knots: null,
      cog_deg: null,
      heading_deg: null,
      nav_status: null,
      vessel_type: vesselType,
      provider_vessel_type: providerVesselType,
      provider_vessel_type_specific: providerVesselTypeSpecific,
      name: null,
      destination: null,
      observed_at: null,
      source: "test",
      synthesized: false,
      data_age_seconds: null,
    },
  };
}

describe("vessel category normalization", () => {
  it.each([
    [70, "Cargo"],
    [83, "Tanker"],
    [30, "Fishing"],
    [62, "Passenger"],
    [52, "Tug / Service"],
    [35, "Government / Law Enforcement"],
    [36, "Pleasure / Sailing"],
    [95, "Other"],
  ] as const)("maps AIS type %i to %s", (vesselType, expected) => {
    expect(normalizeVesselCategory({ vesselType })).toBe(expected);
  });

  it.each([
    ["Cargo", null, "Cargo"],
    ["Tanker", "Oil Products Tanker", "Tanker"],
    ["Fishing", null, "Fishing"],
    ["Passenger", "Ro-Ro Passenger Ship", "Passenger"],
    ["Tug", "Harbour Tug", "Tug / Service"],
    ["Other", "Research Vessel", "Research / Survey"],
    ["Government", "Law Enforcement", "Government / Law Enforcement"],
    ["Pleasure Craft", "Sailing Vessel", "Pleasure / Sailing"],
  ] as const)(
    "maps provider type %s / %s to %s",
    (providerVesselType, providerVesselTypeSpecific, expected) => {
      expect(normalizeVesselCategory({
        vesselType: null,
        providerVesselType,
        providerVesselTypeSpecific,
      })).toBe(expected);
    },
  );

  it("uses Unknown for absent or unrecognized type data", () => {
    expect(normalizeVesselCategory({ vesselType: null })).toBe("Unknown");
    expect(normalizeVesselCategory({
      vesselType: null,
      providerVesselType: "Unmapped experimental craft",
    })).toBe("Unknown");
  });

  it("counts only categories present in the returned vessels", () => {
    expect(countVesselCategories([
      vessel("cargo-1", 70),
      vessel("cargo-2", null, "Cargo"),
      vessel("fish-1", 30),
      vessel("unknown-1", null),
    ])).toEqual([
      { category: "Cargo", count: 2 },
      { category: "Fishing", count: 1 },
      { category: "Unknown", count: 1 },
    ]);
  });
});
