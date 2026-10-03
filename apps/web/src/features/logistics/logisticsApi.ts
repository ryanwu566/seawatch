// Typed client for the Phase 9 /logistics endpoints.
//
// It is built on the SHARED getBaseUrl() API-base policy (apps/web/src/api/client.ts)
// and defines NO independent URL policy: it hardcodes no Render/Vercel/localhost/
// 127.0.0.1 host. Public Cloud (explicit VITE_API_BASE_URL) targets Render; an
// Edge production build without an override stays exact same-origin ("").

import { ApiError, getBaseUrl } from "../../api/client";
import type {
  DecisionBrief,
  ScenarioContext,
  ScenarioListResponse,
  WeightsInput,
} from "./logisticsTypes";

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${getBaseUrl()}${path}`, {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      // Non-JSON error body; keep the status text.
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

async function postJson<T>(path: string, payload: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${getBaseUrl()}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      // keep status text
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

export function fetchScenarios(signal?: AbortSignal): Promise<ScenarioListResponse> {
  return getJson<ScenarioListResponse>("/logistics/scenarios", signal);
}

export function fetchScenarioContext(
  scenarioId: string,
  signal?: AbortSignal,
): Promise<ScenarioContext> {
  return getJson<ScenarioContext>(
    `/logistics/scenarios/${encodeURIComponent(scenarioId)}`,
    signal,
  );
}

export function runSimulation(
  scenarioId: string,
  weights?: WeightsInput,
  signal?: AbortSignal,
): Promise<DecisionBrief> {
  return postJson<DecisionBrief>(
    "/logistics/simulate",
    { scenario_id: scenarioId, weights: weights ?? null },
    signal,
  );
}
