import type { LiveVesselFeature } from "../api/live";

export const VESSEL_CATEGORIES = [
  "Cargo",
  "Tanker",
  "Fishing",
  "Passenger",
  "Tug / Service",
  "Research / Survey",
  "Government / Law Enforcement",
  "Pleasure / Sailing",
  "Other",
  "Unknown",
] as const;

export type VesselCategory = (typeof VESSEL_CATEGORIES)[number];

export const VESSEL_CATEGORY_COLORS: Record<VesselCategory, string> = {
  Cargo: "#38bdf8",
  Tanker: "#818cf8",
  Fishing: "#2dd4bf",
  Passenger: "#fbbf24",
  "Tug / Service": "#a3e635",
  "Research / Survey": "#c084fc",
  "Government / Law Enforcement": "#94a3b8",
  "Pleasure / Sailing": "#f9a8d4",
  Other: "#cbd5e1",
  Unknown: "#94a3b8",
};

interface VesselCategoryInput {
  vesselType: number | null | undefined;
  providerVesselType?: string | null;
  providerVesselTypeSpecific?: string | null;
}

function providerCategory(value: string): VesselCategory | null {
  const normalized = value.trim().toLowerCase();
  if (!normalized) return null;
  if (/research|survey|oceanographic|scientific/.test(normalized)) return "Research / Survey";
  if (/law enforcement|coast guard|government|military|naval|patrol/.test(normalized)) {
    return "Government / Law Enforcement";
  }
  if (/pleasure|sailing|yacht/.test(normalized)) return "Pleasure / Sailing";
  if (/fishing|trawler/.test(normalized)) return "Fishing";
  if (/tanker/.test(normalized)) return "Tanker";
  if (/passenger|ferry|cruise/.test(normalized)) return "Passenger";
  if (/tug|towing|pilot|dredg|service|supply|tender|search and rescue|\bsar\b/.test(normalized)) {
    return "Tug / Service";
  }
  if (/cargo|container|bulk carrier|freighter/.test(normalized)) return "Cargo";
  if (normalized === "other") return "Other";
  return null;
}

export function normalizeVesselCategory({
  vesselType,
  providerVesselType,
  providerVesselTypeSpecific,
}: VesselCategoryInput): VesselCategory {
  const specific = providerVesselTypeSpecific
    ? providerCategory(providerVesselTypeSpecific)
    : null;
  if (specific && specific !== "Other") return specific;
  const provider = providerVesselType ? providerCategory(providerVesselType) : null;
  if (provider) return provider;

  if (!Number.isInteger(vesselType) || vesselType === null || vesselType === undefined) {
    return "Unknown";
  }
  if (vesselType === 30) return "Fishing";
  if ([31, 32, 33, 34, 50, 51, 52, 53, 54, 58, 59].includes(vesselType)) {
    return "Tug / Service";
  }
  if ([35, 55].includes(vesselType)) return "Government / Law Enforcement";
  if ([36, 37].includes(vesselType)) return "Pleasure / Sailing";
  if (vesselType >= 60 && vesselType <= 69) return "Passenger";
  if (vesselType >= 70 && vesselType <= 79) return "Cargo";
  if (vesselType >= 80 && vesselType <= 89) return "Tanker";
  if (vesselType >= 90 && vesselType <= 99) return "Other";
  return "Unknown";
}

export function categoryForVessel(vessel: LiveVesselFeature): VesselCategory {
  return normalizeVesselCategory({
    vesselType: vessel.properties.vessel_type,
    providerVesselType: vessel.properties.provider_vessel_type,
    providerVesselTypeSpecific: vessel.properties.provider_vessel_type_specific,
  });
}

export function countVesselCategories(
  vessels: LiveVesselFeature[],
): Array<{ category: VesselCategory; count: number }> {
  const counts = new Map<VesselCategory, number>();
  for (const vessel of vessels) {
    const category = categoryForVessel(vessel);
    counts.set(category, (counts.get(category) ?? 0) + 1);
  }
  return VESSEL_CATEGORIES.flatMap((category) => {
    const count = counts.get(category) ?? 0;
    return count > 0 ? [{ category, count }] : [];
  });
}
