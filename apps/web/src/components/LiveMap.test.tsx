import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import type { LiveVesselCollection } from "../api/live";

// MapLibre needs WebGL that jsdom lacks; mock it and record the init options and
// the single GeoJSON source's setData payload (proving one-source rendering).
const setDataSpy = vi.fn();

vi.mock("maplibre-gl", () => {
  class FakeMap {
    static lastOptions: Record<string, unknown> | null = null;
    private handlers: Record<string, () => void> = {};
    constructor(options: Record<string, unknown>) {
      FakeMap.lastOptions = options;
    }
    on(event: string, cb: () => void) {
      this.handlers[event] = cb;
      if (event === "load") cb(); // fire load immediately
    }
    once() {}
    addControl() {}
    addSource() {}
    addLayer() {}
    getSource() {
      return { setData: setDataSpy };
    }
    remove() {}
  }
  return {
    default: {
      Map: FakeMap,
      NavigationControl: class {},
      LngLatBounds: class {
        extend() {
          return this;
        }
      },
    },
  };
});
vi.mock("maplibre-gl/dist/maplibre-gl.css", () => ({}));

import { LiveMap } from "./LiveMap";
import maplibregl from "maplibre-gl";

const collection: LiveVesselCollection = {
  type: "FeatureCollection",
  attribution: "Open Waters AIS",
  server_timestamp: "2026-10-01T01:00:00Z",
  data_timestamp: "2026-10-01T00:59:42Z",
  vessel_count: 2,
  features: [
    {
      type: "Feature",
      id: "v1",
      geometry: { type: "Point", coordinates: [120.0, 22.3] },
      properties: {
        provider_id: "v1",
        sog_knots: 16.3,
        cog_deg: 322.2,
        heading_deg: 319,
        nav_status: 0,
        vessel_type: 83,
        name: "CLIPPER ERIS",
        destination: "TW MLI",
        observed_at: "2026-10-01T00:59:42Z",
        source: "aishub",
        synthesized: false,
        data_age_seconds: 18,
      },
    },
    {
      type: "Feature",
      id: "v2",
      geometry: { type: "Point", coordinates: [121.0, 23.0] },
      properties: {
        provider_id: "v2",
        sog_knots: null,
        cog_deg: null,
        heading_deg: null,
        nav_status: null,
        vessel_type: null,
        name: null,
        destination: null,
        observed_at: "2026-10-01T00:59:50Z",
        source: "aisstream",
        synthesized: true,
        data_age_seconds: 10,
      },
    },
  ],
};

describe("LiveMap (minimal Taiwan proof)", () => {
  beforeEach(() => {
    setDataSpy.mockClear();
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (String(url).includes("/live/vessels")) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(collection) });
        }
        if (String(url).includes("/live/health")) {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                status: "online",
                provider: "open_waters",
                connected: true,
                subscribed: true,
                last_message_at: "2026-10-01T00:59:50Z",
                message_age_seconds: 5,
                vessel_count: 2,
                reconnect_attempts: 0,
                last_error: null,
              }),
          });
        }
        return Promise.resolve({ ok: false, status: 404, statusText: "Not Found" });
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("initializes the map centered on Taiwan", () => {
    render(<LiveMap />);
    const options = (maplibregl as unknown as {
      Map: { lastOptions: Record<string, unknown> | null };
    }).Map.lastOptions;
    const center = options?.center as [number, number];
    expect(center[0]).toBeGreaterThan(119); // Taiwan longitude
    expect(center[0]).toBeLessThan(123);
    expect(center[1]).toBeGreaterThan(21); // Taiwan latitude
    expect(center[1]).toBeLessThan(26);
  });

  it("shows the LIVE indicator and freshest AIS age", async () => {
    render(<LiveMap />);
    expect(screen.getByText(/即時資料 \/ LIVE/)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/Vessels: 2/)).toBeInTheDocument();
    });
    // Freshest fix across the collection is 10s.
    await waitFor(() => {
      expect(screen.getByText(/10s ago/)).toBeInTheDocument();
    });
  });

  it("pushes vessels onto a single GeoJSON source via setData", async () => {
    render(<LiveMap />);
    await waitFor(() => {
      expect(setDataSpy).toHaveBeenCalled();
    });
    const calls = setDataSpy.mock.calls;
    const payload = calls[calls.length - 1]?.[0];
    expect(payload.type).toBe("FeatureCollection");
    expect(payload.features).toHaveLength(2);
    // Heading preferred for orientation; falls back to COG, else 0.
    expect(payload.features[0].properties.orientation).toBe(319);
    expect(payload.features[1].properties.orientation).toBe(0); // no heading/cog
  });
});
