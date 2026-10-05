import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Scenario } from "./api";

const state = vi.hoisted(() => ({
  sources: new Map<string, { data: unknown; setData: ReturnType<typeof vi.fn> }>(),
  layers: [] as Array<Record<string, unknown>>,
  layout: [] as Array<{ id: string; value: string }>,
  handlers: new Map<string, (event?: any) => void>(),
  layerHandlers: new Map<string, (event?: any) => void>(),
  popupHtml: [] as string[],
  queryHits: [] as any[],
}));

vi.mock("maplibre-gl", () => {
  class FakeMap {
    constructor() {}
    addControl() {}
    addSource(id: string, specification: { data: unknown }) {
      state.sources.set(id, {
        data: specification.data,
        setData: vi.fn((data: unknown) => {
          const source = state.sources.get(id);
          if (source) source.data = data;
        }),
      });
    }
    getSource(id: string) {
      return state.sources.get(id);
    }
    addLayer(layer: Record<string, unknown>, beforeId?: string) {
      const beforeIndex = beforeId
        ? state.layers.findIndex((candidate) => candidate.id === beforeId)
        : -1;
      if (beforeIndex >= 0) state.layers.splice(beforeIndex, 0, layer);
      else state.layers.push(layer);
    }
    moveLayer(id: string, beforeId?: string) {
      const currentIndex = state.layers.findIndex((layer) => layer.id === id);
      if (currentIndex < 0) return;
      const [layer] = state.layers.splice(currentIndex, 1);
      const beforeIndex = beforeId
        ? state.layers.findIndex((candidate) => candidate.id === beforeId)
        : -1;
      if (beforeIndex >= 0) state.layers.splice(beforeIndex, 0, layer);
      else state.layers.push(layer);
    }
    getLayer(id: string) {
      return state.layers.find((layer) => layer.id === id);
    }
    setLayoutProperty(id: string, _property: string, value: string) {
      state.layout.push({ id, value });
    }
    setPaintProperty() {}
    fitBounds() {}
    queryRenderedFeatures() {
      return state.queryHits;
    }
    getCanvas() {
      return { style: { cursor: "" } };
    }
    on(event: string, layerOrHandler: string | ((event?: any) => void), handler?: (event?: any) => void) {
      if (typeof layerOrHandler === "function") {
        state.handlers.set(event, layerOrHandler);
        if (event === "load") layerOrHandler();
      } else if (handler) {
        state.layerHandlers.set(`${event}:${layerOrHandler}`, handler);
      }
    }
    remove() {}
  }
  class FakePopup {
    setLngLat() { return this; }
    setHTML(html: string) {
      state.popupHtml.push(html);
      return this;
    }
    addTo() { return this; }
    remove() {}
  }
  class FakeMarker {
    setLngLat() { return this; }
    addTo() { return this; }
    remove() {}
  }
  return {
    default: {
      Map: FakeMap,
      Popup: FakePopup,
      Marker: FakeMarker,
      NavigationControl: class {},
    },
  };
});

vi.mock("maplibre-gl/dist/maplibre-gl.css", () => ({}));
vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return {
    ...actual,
    watchApi: {
      layers: vi.fn().mockResolvedValue({
        cables: { type: "FeatureCollection", features: [] },
        landing: { type: "FeatureCollection", features: [] },
        limits: { type: "FeatureCollection", features: [] },
      }),
    },
  };
});

import { WatchMap } from "./WatchMap";
import {
  buildHistoricalTrafficGeoJson,
  HISTORICAL_TRAFFIC_FILL_LAYER_ID,
  HISTORICAL_TRAFFIC_OUTLINE_LAYER_ID,
  HISTORICAL_TRAFFIC_SOURCE_ID,
} from "../../lib/historicalTraffic";

const scenario: Scenario = {
  region: "taiwan",
  region_label: "Taiwan",
  timezone: "Asia/Taipei",
  data_kind: "real",
  note: "Live",
  bounds: [[119, 21], [123, 26]],
  name: "Taiwan",
  t0: 1,
  t1: 2,
  vessels: 0,
  fixes: 0,
  simulated: false,
  zones: [],
  receivers: [],
};

const historicalTraffic = buildHistoricalTrafficGeoJson([{
  cell_lat: 25,
  cell_lon: 121.5,
  observation_count: 1200,
  unique_vessel_count: 80,
  observed_days: 40,
  active_hour_buckets: 300,
  cell_active_hour_fraction: 0.25,
  avg_vessels_per_active_hour: 4,
}]);

function watchMap(status: "loading" | "available" | "unavailable" = "available") {
  return (
    <WatchMap
      scenario={scenario}
      tracks={[]}
      alerts={[]}
      detail={null}
      selectedId={null}
      clock={2}
      truth={[]}
      showTruth={false}
      historicalTraffic={status === "available" ? historicalTraffic : null}
      historicalTrafficStatus={status}
      onSelect={vi.fn()}
    />
  );
}

function renderMap(status: "loading" | "available" | "unavailable" = "available") {
  return render(watchMap(status));
}

describe("WatchMap historical traffic", () => {
  beforeEach(() => {
    state.sources.clear();
    state.layers.length = 0;
    state.layout.length = 0;
    state.handlers.clear();
    state.layerHandlers.clear();
    state.popupHtml.length = 0;
    state.queryHits.length = 0;
    vi.stubGlobal("requestAnimationFrame", vi.fn(() => 1));
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
  });

  it("installs historical context below maritime, vessels, and detection overlays and defaults off", async () => {
    renderMap();

    await waitFor(() => expect(state.sources.has(HISTORICAL_TRAFFIC_SOURCE_ID)).toBe(true));
    const ids = state.layers.map((layer) => layer.id);
    expect(ids.indexOf(HISTORICAL_TRAFFIC_FILL_LAYER_ID)).toBeLessThan(ids.indexOf("limits-line"));
    expect(ids.indexOf(HISTORICAL_TRAFFIC_OUTLINE_LAYER_ID)).toBeLessThan(ids.indexOf("vessels"));
    expect(ids.indexOf(HISTORICAL_TRAFFIC_FILL_LAYER_ID)).toBeLessThan(ids.indexOf("rings"));
    expect(screen.getByRole("button", { name: "Historical Traffic Density" })).toHaveAttribute("aria-pressed", "false");
    expect(state.layout).toContainEqual({ id: HISTORICAL_TRAFFIC_FILL_LAYER_ID, value: "none" });
    expect(screen.queryByLabelText("Historical presence legend")).not.toBeInTheDocument();
  });

  it("keeps vessels below detection alerts and selection overlays", () => {
    renderMap();

    const ids = state.layers.map((layer) => layer.id);
    expect(ids.indexOf("vessels")).toBeLessThan(ids.indexOf("ev-lines"));
    expect(ids.indexOf("vessels")).toBeLessThan(ids.indexOf("pulse"));
    expect(ids.indexOf("vessels")).toBeLessThan(ids.indexOf("rings"));
  });

  it("keeps delayed historical data below maritime and operational overlays", async () => {
    const view = renderMap("loading");

    view.rerender(watchMap("available"));

    await waitFor(() => expect(state.sources.has(HISTORICAL_TRAFFIC_SOURCE_ID)).toBe(true));
    const ids = state.layers.map((layer) => layer.id);
    expect(ids.indexOf(HISTORICAL_TRAFFIC_FILL_LAYER_ID)).toBeLessThan(ids.indexOf("limits-line"));
    expect(ids.indexOf(HISTORICAL_TRAFFIC_OUTLINE_LAYER_ID)).toBeLessThan(ids.indexOf("vessels"));
    expect(ids.indexOf(HISTORICAL_TRAFFIC_FILL_LAYER_ID)).toBeLessThan(ids.indexOf("rings"));
  });

  it("owns an independent toggle and displays the shared historical legend", async () => {
    renderMap();
    const toggle = await screen.findByRole("button", { name: "Historical Traffic Density" });
    fireEvent.click(toggle);

    expect(toggle).toHaveAttribute("aria-pressed", "true");
    expect(state.layout).toContainEqual({ id: HISTORICAL_TRAFFIC_FILL_LAYER_ID, value: "visible" });
    expect(screen.getByLabelText("Historical presence legend")).toHaveTextContent("standardized hourly vessel presence");
    expect(screen.getByLabelText("Historical presence legend")).toHaveTextContent("not raw/message-level AIS");
  });

  it("keeps the live map usable when historical context is unavailable", () => {
    renderMap("unavailable");
    expect(screen.getByRole("button", { name: "Historical Traffic Density" })).toBeDisabled();
    expect(state.layers.some((layer) => layer.id === "vessels")).toBe(true);
  });

  it("restores the source and layers idempotently after a style event", async () => {
    renderMap();
    await waitFor(() => expect(state.handlers.has("styledata")).toBe(true));
    state.sources.delete(HISTORICAL_TRAFFIC_SOURCE_ID);
    state.layers = state.layers.filter((layer) => ![
      HISTORICAL_TRAFFIC_FILL_LAYER_ID,
      HISTORICAL_TRAFFIC_OUTLINE_LAYER_ID,
    ].includes(String(layer.id) as any));

    act(() => state.handlers.get("styledata")?.());
    act(() => state.handlers.get("styledata")?.());

    expect(state.sources.has(HISTORICAL_TRAFFIC_SOURCE_ID)).toBe(true);
    expect(state.layers.filter((layer) => layer.id === HISTORICAL_TRAFFIC_FILL_LAYER_ID)).toHaveLength(1);
    expect(state.layers.filter((layer) => layer.id === HISTORICAL_TRAFFIC_OUTLINE_LAYER_ID)).toHaveLength(1);
  });

  it("uses the aggregate-only shared popup formatter", async () => {
    renderMap();
    await waitFor(() => expect(state.layerHandlers.has(`mousemove:${HISTORICAL_TRAFFIC_FILL_LAYER_ID}`)).toBe(true));
    act(() => state.layerHandlers.get(`mousemove:${HISTORICAL_TRAFFIC_FILL_LAYER_ID}`)?.({
      features: [{ properties: historicalTraffic.features[0].properties }],
      lngLat: { lng: 121.5, lat: 25 },
    }));

    const popup = state.popupHtml[state.popupHtml.length - 1];
    expect(popup).toContain("Presence observations");
    expect(popup).toContain("standardized hourly vessel presence");
    expect(popup).not.toMatch(/MMSI|raw_mmsi|timestamp/i);
  });

  it("does not let historical hover cover vessels or detection rings", async () => {
    renderMap();
    await waitFor(() => expect(state.layerHandlers.has(`mousemove:${HISTORICAL_TRAFFIC_FILL_LAYER_ID}`)).toBe(true));
    state.queryHits.push({ layer: { id: "vessels" } });

    act(() => state.layerHandlers.get(`mousemove:${HISTORICAL_TRAFFIC_FILL_LAYER_ID}`)?.({
      features: [{ properties: historicalTraffic.features[0].properties }],
      lngLat: { lng: 121.5, lat: 25 },
      point: { x: 100, y: 100 },
    }));

    expect(state.popupHtml).toHaveLength(0);
  });
});
