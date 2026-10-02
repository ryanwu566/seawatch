import { describe, expect, it } from "vitest";
import {
  LAYER_DISRUPTED,
  LOGISTICS_SCHEMATIC_LABEL,
  SOURCE_ROUTES,
  buildAlternativePorts,
  buildDemandNodes,
  buildDisruptedPorts,
  buildLogisticsOverlays,
  buildSelectedRoutes,
} from "./logisticsLayers";
import type { Allocation, ScenarioContext } from "./logisticsTypes";

const context: ScenarioContext = {
  scenario: {
    id: "kaohsiung-disruption",
    name_zh: "高雄港中斷情境",
    name_en: "Kaohsiung Port Disruption",
    disrupted_ports: ["kaohsiung"],
    description_zh: "x",
    description_en: "x",
    source_type: "scenario",
  },
  affected_demands: [
    { id: "medical-south", commodity: "medical", priority: 1, quantity_units: 30, origin_demand_node: "south-node", source_type: "scenario" },
    { id: "food-south", commodity: "food", priority: 2, quantity_units: 50, origin_demand_node: "south-node", source_type: "scenario" },
  ],
  candidate_ports: ["taichung", "keelung"],
  candidate_routes: [],
  provenance_summary: {},
};

const allocations: Allocation[] = [
  {
    demand_id: "medical-south",
    assignments: [
      { port_id: "taichung", route_id: "taichung->south-node", units: 30, eta_hours: 9.5, cost: 2.2, risk: 0.21 },
    ],
    satisfied_units: 30,
    unmet_units: 0,
    score: 0.1,
  },
  {
    demand_id: "food-south",
    assignments: [
      { port_id: "taichung", route_id: "taichung->south-node", units: 30, eta_hours: 9.5, cost: 2.2, risk: 0.21 },
      { port_id: "keelung", route_id: "keelung->south-node", units: 20, eta_hours: 15, cost: 2.6, risk: 0.28 },
    ],
    satisfied_units: 50,
    unmet_units: 0,
    score: 0.4,
  },
];

describe("logisticsLayers builders", () => {
  it("marks the disrupted port distinctly", () => {
    const fc = buildDisruptedPorts(context);
    expect(fc.features).toHaveLength(1);
    expect(fc.features[0].properties?.port_id).toBe("kaohsiung");
    expect(fc.features[0].properties?.status).toBe("disrupted");
  });

  it("renders alternative ports and excludes the disrupted one", () => {
    const fc = buildAlternativePorts(context);
    const ids = fc.features.map((f) => f.properties?.port_id);
    expect(ids).toEqual(expect.arrayContaining(["taichung", "keelung"]));
    expect(ids).not.toContain("kaohsiung");
  });

  it("renders demand nodes sized by priority", () => {
    const fc = buildDemandNodes(context);
    expect(fc.features).toHaveLength(1); // both demands share south-node
    expect(fc.features[0].properties?.priority).toBe(1);
  });

  it("colors selected routes by commodity and flags schematic connectors", () => {
    const fc = buildSelectedRoutes(context, allocations);
    expect(fc.features.length).toBe(3); // 1 medical + 2 food split
    const medical = fc.features.find((f) => f.properties?.commodity === "medical");
    const food = fc.features.filter((f) => f.properties?.commodity === "food");
    expect(medical?.properties?.color).toBe("#ef4444");
    expect(food).toHaveLength(2);
    for (const f of fc.features) {
      expect(f.properties?.schematic).toBe(true);
      expect(f.properties?.schematic_label).toBe(LOGISTICS_SCHEMATIC_LABEL);
      expect(f.geometry.type).toBe("LineString");
    }
  });

  it("only civilian ports appear (no sensitive locations)", () => {
    const overlays = buildLogisticsOverlays(context, allocations);
    const allPortIds = [
      ...overlays.sources["logistics-disrupted-ports"].features,
      ...overlays.sources["logistics-alternative-ports"].features,
    ].map((f) => f.properties?.port_id);
    expect(new Set(allPortIds)).toEqual(new Set(["kaohsiung", "taichung", "keelung"]));
  });

  it("assembles a generic MapOverlays payload (pure, no engine)", () => {
    const overlays = buildLogisticsOverlays(context, allocations);
    expect(Object.keys(overlays.sources)).toContain(SOURCE_ROUTES);
    expect(overlays.layers.some((l) => l.id === LAYER_DISRUPTED)).toBe(true);
    // Every layer references a provided source.
    const sourceIds = new Set(Object.keys(overlays.sources));
    for (const layer of overlays.layers) {
      expect(sourceIds.has((layer as { source: string }).source)).toBe(true);
    }
  });

  it("returns empty collections when context is null", () => {
    expect(buildDisruptedPorts(null).features).toHaveLength(0);
    expect(buildSelectedRoutes(null, allocations).features).toHaveLength(0);
  });
});
