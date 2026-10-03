// Read-only maritime GIS context client.
//
// Calls the EXISTING backend route only — GET /context/geographic?lon=&lat= —
// which returns a `gis-context-1` payload. No new endpoint is added. The
// frontend performs no geometry; it renders the finished, provenance-labeled
// facts the backend computes (distance to coast, nearest port + distance, named
// maritime area containment).

import { getBaseUrl } from "../../api/client";
import type { GeographicContext } from "./geographicTypes";

/**
 * Fetch geographic context facts for a WGS84 position.
 *
 * Returns the backend `gis-context-1` payload. A position outside reference
 * coverage (or a null position) yields a fully-`unknown` result from the
 * backend — never a guessed value. The caller renders Unknown accordingly.
 */
export async function fetchGeographicContext(
  lon: number,
  lat: number,
  signal?: AbortSignal,
): Promise<GeographicContext> {
  const params = new URLSearchParams({ lon: String(lon), lat: String(lat) });
  const response = await fetch(`${getBaseUrl()}/context/geographic?${params.toString()}`, {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return (await response.json()) as GeographicContext;
}
