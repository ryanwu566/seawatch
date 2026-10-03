// TypeScript mirrors of the Phase 9 logistics API schemas.
// These are plain data shapes; the client in logisticsApi.ts fetches them.

export interface ScenarioSummary {
  id: string;
  name_zh: string;
  name_en: string;
  disrupted_ports: string[];
  source_type: string;
}

export interface ScenarioListResponse {
  count: number;
  scenarios: ScenarioSummary[];
}

export interface AffectedDemand {
  id: string;
  commodity: "medical" | "food" | "fuel";
  priority: number;
  quantity_units: number;
  origin_demand_node: string;
  source_type: string;
}

export interface CandidateRoute {
  id: string;
  from_port: string;
  to_demand_node: string;
  distance_km: number;
  baseline_eta_hours: number;
  route_risk: number;
  schematic: boolean;
  source_type: string;
}

export interface ScenarioContext {
  scenario: {
    id: string;
    name_zh: string;
    name_en: string;
    disrupted_ports: string[];
    description_zh: string;
    description_en: string;
    source_type: string;
  };
  affected_demands: AffectedDemand[];
  candidate_ports: string[];
  candidate_routes: CandidateRoute[];
  provenance_summary: Record<string, number>;
}

export interface Assignment {
  port_id: string;
  route_id: string;
  units: number;
  eta_hours: number;
  cost: number;
  risk: number;
}

export interface Allocation {
  demand_id: string;
  assignments: Assignment[];
  satisfied_units: number;
  unmet_units: number;
  score: number;
}

export interface AlternativeRow {
  port_id: string;
  port_label: string;
  eta_hours: number;
  distance_km: number;
  per_unit_cost: number;
  capacity_units: number;
  capacity_utilization: number;
  risk: number;
  schematic: boolean;
  schematic_label: string | null;
  route_source_type: string;
}

export interface UnmetRow {
  demand_id: string;
  commodity: string | null;
  unmet_units: number;
}

export interface DecisionBrief {
  scenario_id: string;
  summary_zh: string;
  summary_en: string;
  recommended_allocations: Allocation[];
  alternatives: AlternativeRow[];
  trade_offs: string[];
  unmet_demand: UnmetRow[];
  provenance_note: string;
  assumptions: string[];
  provenance_summary: Record<string, number>;
}

export interface WeightsInput {
  time?: number;
  cost?: number;
  risk?: number;
  capacity?: number;
}
