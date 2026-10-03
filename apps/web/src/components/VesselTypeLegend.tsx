import { VESSEL_CATEGORY_COLORS, type VesselCategory } from "../lib/vesselCategory";

const LEGEND_ITEMS: Array<{ label: string; categories: VesselCategory[] }> = [
  { label: "Cargo", categories: ["Cargo"] },
  { label: "Tanker", categories: ["Tanker"] },
  { label: "Fishing", categories: ["Fishing"] },
  { label: "Passenger", categories: ["Passenger"] },
  { label: "Tug / Service", categories: ["Tug / Service"] },
  { label: "Research / Survey", categories: ["Research / Survey"] },
  {
    label: "Government / Law Enforcement",
    categories: ["Government / Law Enforcement"],
  },
  { label: "Pleasure / Sailing", categories: ["Pleasure / Sailing"] },
  { label: "Other / Unknown", categories: ["Other", "Unknown"] },
];

function swatchBackground(categories: VesselCategory[]): string {
  if (categories.length === 1) return VESSEL_CATEGORY_COLORS[categories[0]];
  const [first, second] = categories;
  return `linear-gradient(90deg, ${VESSEL_CATEGORY_COLORS[first]} 0 50%, ${VESSEL_CATEGORY_COLORS[second]} 50% 100%)`;
}

/** Vessel type only; detection or risk state remains a separate visual channel. */
export function VesselTypeLegend() {
  return (
    <aside className="vessel-type-legend" role="region" aria-label="Vessel type legend">
      <strong className="vessel-type-legend-title">Vessel Type</strong>
      <div className="vessel-type-legend-grid">
        {LEGEND_ITEMS.map(({ label, categories }) => (
          <span className="vessel-type-legend-item" key={label}>
            <i
              className="vessel-type-legend-swatch"
              style={{ background: swatchBackground(categories) }}
              aria-hidden="true"
            />
            {label}
          </span>
        ))}
      </div>
    </aside>
  );
}
