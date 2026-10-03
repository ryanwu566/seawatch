// Pure GeoJSON overlay builders for the Resilience Logistics map.
//
// These functions own ALL logistics-specific map knowledge; MapCanvas stays
// logistics-agnostic. They produce a generic MapOverlays payload (named GeoJSON
// sources + MapLibre layer specs) that is fed into the reused Phase 8 MapCanvas
// overlay seam. No map engine, no basemap, no second MapLibre instance is
// created here — the overlays inherit the Phase 8 NLSC → PMTiles → emergency
// offline behavior automatically.

import type { LayerSpecification } from "maplibre-gl";
import type { MapOverlays } from "../../components/MapCanvas";
import type { Allocation, ScenarioContext } from "./logisticsTypes";

export const LOGISTICS_SCHEMATIC_LABEL = "SCHEMATIC CONNECTOR / 示意連線";

export const SOURCE_DISRUPTED = "logistics-disrupted-ports";
export const SOURCE_ALTERNATIVES = "logistics-alternative-ports";
export const SOURCE_DEMAND = "logistics-demand-nodes";
export const SOURCE_ROUTES = "logistics-selected-routes";

export const LAYER_DISRUPTED = "logistics-disrupted-ports-layer";
export const LAYER_ALTERNATIVES = "logistics-alternative-ports-layer";
export const LAYER_DEMAND = "logistics-demand-nodes-layer";
export const LAYER_ROUTES = "logistics-selected-routes-layer";
export const LAYER_ROUTES_LABEL = "logistics-selected-routes-label";

// Commodity colors (civilian logistics only).
const COMMODITY_COLORS: Record<string, string> = {
  medical: "#ef4444",
  food: "#22c55e",
  fuel: "#eab308",
};

// Public civilian port coordinates (WGS84), aligned with the backend dataset.
// Only public civilian ports appear here; no military/sensitive locations.
const PORT_COORDS: Record<string, [number, number]> = {
  kaohsiung: [120.3, 22.6],
  taichung: [120.52, 24.29],
  keelung: [121.74, 25.14],
};
const DEMAND_NODE_COORDS: Record<string, [number, number]> = {
  "south-node": [120.31, 22.63],
  "central-node": [120.6, 24.15],
  "north-node": [121.55, 25.05],
};

function emptyFC(): GeoJSON.FeatureCollection {
  return { type: "FeatureCollection", features: [] };
}

function pointFeature(
  coords: [number, number],
  properties: Record<string, unknown>,
): GeoJSON.Feature {
  return { type: "Feature", geometry: { type: "Point", coordinates: coords }, properties };
}

export function buildDisruptedPorts(context: ScenarioContext | null): GeoJSON.FeatureCollection {
  if (!context) return emptyFC();
  return {
    type: "FeatureCollection",
    features: context.scenario.disrupted_ports
      .filter((id) => PORT_COORDS[id])
      .map((id) =>
        pointFeature(PORT_COORDS[id], { port_id: id, status: "disrupted", label: "中斷 / Disrupted" }),
      ),
  };
}

export function buildAlternativePorts(context: ScenarioContext | null): GeoJSON.FeatureCollection {
  if (!context) return emptyFC();
  const disrupted = new Set(context.scenario.disrupted_ports);
  return {
    type: "FeatureCollection",
    features: context.candidate_ports
      .filter((id) => PORT_COORDS[id] && !disrupted.has(id))
      .map((id) => pointFeature(PORT_COORDS[id], { port_id: id, status: "alternative" })),
  };
}

export function buildDemandNodes(context: ScenarioContext | null): GeoJSON.FeatureCollection {
  if (!context) return emptyFC();
  const seen = new Set<string>();
  const features: GeoJSON.Feature[] = [];
  for (const demand of context.affected_demands) {
    const node = demand.origin_demand_node;
    if (seen.has(node) || !DEMAND_NODE_COORDS[node]) continue;
    seen.add(node);
    features.push(
      pointFeature(DEMAND_NODE_COORDS[node], {
        node,
        priority: demand.priority,
        commodity: demand.commodity,
      }),
    );
  }
  return { type: "FeatureCollection", features };
}

/**
 * Selected-solution routes colored by commodity. Routes without authoritative
 * geometry are drawn as straight port→node connectors and flagged schematic so
 * the UI/label can show SCHEMATIC CONNECTOR / 示意連線 — never presented as a
 * measured road or shipping route.
 */
export function buildSelectedRoutes(
  context: ScenarioContext | null,
  allocations: Allocation[],
): GeoJSON.FeatureCollection {
  if (!context) return emptyFC();
  const commodityByDemand = new Map(
    context.affected_demands.map((d) => [d.id, { commodity: d.commodity, node: d.origin_demand_node }]),
  );
  const features: GeoJSON.Feature[] = [];
  for (const alloc of allocations) {
    const meta = commodityByDemand.get(alloc.demand_id);
    if (!meta) continue;
    const nodeCoord = DEMAND_NODE_COORDS[meta.node];
    if (!nodeCoord) continue;
    for (const assignment of alloc.assignments) {
      const portCoord = PORT_COORDS[assignment.port_id];
      if (!portCoord) continue;
      features.push({
        type: "Feature",
        geometry: { type: "LineString", coordinates: [portCoord, nodeCoord] },
        properties: {
          demand_id: alloc.demand_id,
          commodity: meta.commodity,
          color: COMMODITY_COLORS[meta.commodity] ?? "#94a3b8",
          units: assignment.units,
          port_id: assignment.port_id,
          // No authoritative geometry in V1 → always a schematic connector.
          schematic: true,
          schematic_label: LOGISTICS_SCHEMATIC_LABEL,
        },
      });
    }
  }
  return { type: "FeatureCollection", features };
}

function layerSpecs(): LayerSpecification[] {
  return [
    {
      id: LAYER_ROUTES,
      type: "line",
      source: SOURCE_ROUTES,
      layout: { "line-join": "round", "line-cap": "round" },
      paint: {
        "line-color": ["get", "color"],
        "line-width": 2.5,
        "line-dasharray": [2, 2], // dashed = schematic, not a measured route
      },
    },
    {
      id: LAYER_ROUTES_LABEL,
      type: "symbol",
      source: SOURCE_ROUTES,
      layout: {
        "symbol-placement": "line-center",
        "text-field": ["get", "schematic_label"],
        "text-size": 10,
      },
      paint: { "text-color": "#e2e8f0", "text-halo-color": "#04121f", "text-halo-width": 1.2 },
    },
    {
      id: LAYER_DEMAND,
      type: "circle",
      source: SOURCE_DEMAND,
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["get", "priority"], 1, 9, 3, 5],
        "circle-color": "#38bdf8",
        "circle-stroke-color": "#04121f",
        "circle-stroke-width": 2,
      },
    },
    {
      id: LAYER_ALTERNATIVES,
      type: "circle",
      source: SOURCE_ALTERNATIVES,
      paint: {
        "circle-radius": 7,
        "circle-color": "#22d3ee",
        "circle-stroke-color": "#04121f",
        "circle-stroke-width": 2,
      },
    },
    {
      id: LAYER_DISRUPTED,
      type: "circle",
      source: SOURCE_DISRUPTED,
      paint: {
        "circle-radius": 9,
        "circle-color": "#64748b",
        "circle-stroke-color": "#ef4444",
        "circle-stroke-width": 3,
      },
    },
  ];
}

/** Assemble the generic MapOverlays payload for the MapCanvas seam. */
export function buildLogisticsOverlays(
  context: ScenarioContext | null,
  allocations: Allocation[],
): MapOverlays {
  return {
    sources: {
      [SOURCE_DISRUPTED]: buildDisruptedPorts(context),
      [SOURCE_ALTERNATIVES]: buildAlternativePorts(context),
      [SOURCE_DEMAND]: buildDemandNodes(context),
      [SOURCE_ROUTES]: buildSelectedRoutes(context, allocations),
    },
    layers: layerSpecs(),
  };
}

export { PORT_COORDS as LOGISTICS_PORT_COORDS };
