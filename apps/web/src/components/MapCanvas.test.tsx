import { describe, expect, it, vi, beforeEach } from "vitest";
import { render } from "@testing-library/react";
import type { LiveVesselFeature } from "../api/live";

// Record interactions with the mocked MapLibre map.
const state: {
  options: Record<string, unknown> | null;
  setDataPayloads: any[];
  handlers: Record<string, (e?: any) => void>;
  layerHandlers: Record<string, (e?: any) => void>;
  images: string[];
  layoutProps: Array<{ layer: string; prop: string; value: unknown }>;
} = {
  options: null,
  setDataPayloads: [],
  handlers: {},
  layerHandlers: {},
  images: [],
  layoutProps: [],
};

vi.mock("maplibre-gl", () => {
  class FakeMap {
    constructor(options: Record<string, unknown>) {
      state.options = options;
    }
    addControl() {}
    on(event: string, layerOrCb: any, cb?: any) {
      if (typeof layerOrCb === "function") {
        state.handlers[event] = layerOrCb;
        if (event === "load") layerOrCb();
      } else {
        state.layerHandlers[`${event}:${layerOrCb}`] = cb;
      }
    }
    once() {}
    hasImage(id: string) {
      return state.images.includes(id);
    }
    addImage(id: string) {
      state.images.push(id);
    }
    getSource(id: string) {
      return {
        setData: (data: any) => {
          state.setDataPayloads.push({ id, data });
        },
      };
    }
    addSource() {}
    getLayer() {
      return true;
    }
    addLayer() {}
    setLayoutProperty(layer: string, prop: string, value: unknown) {
      state.layoutProps.push({ layer, prop, value });
    }
    setStyle() {}
    getBounds() {
      return {
        getSouth: () => 21.5,
        getWest: () => 118.0,
        getNorth: () => 26.5,
        getEast: () => 123.5,
      };
    }
    getCanvas() {
      return { style: {} };
    }
    remove() {}
  }
  return {
    default: { Map: FakeMap, NavigationControl: class {} },
  };
});
vi.mock("maplibre-gl/dist/maplibre-gl.css", () => ({}));
// jsdom has no canvas 2d; return null icon so addImage is skipped gracefully.
vi.mock("../lib/shipIcon", () => ({ makeShipIcon: () => null }));

import { MapCanvas } from "./MapCanvas";
import { DEFAULT_LAYER_STATE } from "../lib/layerState";

const vessels: LiveVesselFeature[] = [
  {
    type: "Feature",
    id: "v1",
    geometry: { type: "Point", coordinates: [120.0, 22.3] },
    properties: {
      provider_id: "v1",
      sog_knots: 0, // zero speed => no visual advance; stays at measured pos
      cog_deg: 200,
      heading_deg: 319,
      nav_status: 0,
      vessel_type: 83,
      name: "A",
      destination: null,
      observed_at: "2026-10-01T00:00:00Z",
      source: "aishub",
      synthesized: false,
      data_age_seconds: 5,
    },
  },
  {
    type: "Feature",
    id: "v2",
    geometry: { type: "Point", coordinates: [121.0, 23.0] },
    properties: {
      provider_id: "v2",
      sog_knots: 0,
      cog_deg: 90, // no heading -> orientation falls back to COG
      heading_deg: null,
      nav_status: 0,
      vessel_type: 70,
      name: "B",
      destination: null,
      observed_at: "2026-10-01T00:00:00Z",
      source: "aisstream",
      synthesized: true,
      data_age_seconds: 5,
    },
  },
];

describe("MapCanvas", () => {
  beforeEach(() => {
    state.options = null;
    state.setDataPayloads = [];
    state.handlers = {};
    state.layerHandlers = {};
    state.images = [];
    state.layoutProps = [];
  });

  it("initializes centered on Taiwan", () => {
    render(
      <MapCanvas
        vessels={vessels}
        layers={DEFAULT_LAYER_STATE}
        selectedTrack={null}
        onSelectVessel={() => {}}
        onViewportChange={() => {}}
      />,
    );
    const center = state.options?.center as [number, number];
    expect(center[0]).toBeGreaterThan(119);
    expect(center[0]).toBeLessThan(123);
    expect(center[1]).toBeGreaterThan(21);
    expect(center[1]).toBeLessThan(26);
  });

  it("pushes all vessels onto a single GeoJSON source with orientation", () => {
    render(
      <MapCanvas
        vessels={vessels}
        layers={DEFAULT_LAYER_STATE}
        selectedTrack={null}
        onSelectVessel={() => {}}
        onViewportChange={() => {}}
      />,
    );
    const vesselPush = state.setDataPayloads.find((p) => p.id === "live-vessels");
    expect(vesselPush).toBeTruthy();
    expect(vesselPush.data.features).toHaveLength(2);
    // v1: orientation from heading (319); v2: falls back to COG (90).
    expect(vesselPush.data.features[0].properties.orientation).toBe(319);
    expect(vesselPush.data.features[1].properties.orientation).toBe(90);
    // v2 is provider-synthesized => flagged interpolated.
    expect(vesselPush.data.features[1].properties.isInterpolated).toBe(true);
  });

  it("emits the viewport bbox on load", () => {
    const onViewportChange = vi.fn();
    render(
      <MapCanvas
        vessels={vessels}
        layers={DEFAULT_LAYER_STATE}
        selectedTrack={null}
        onSelectVessel={() => {}}
        onViewportChange={onViewportChange}
      />,
    );
    expect(onViewportChange).toHaveBeenCalledWith({
      minLat: 21.5,
      minLon: 118.0,
      maxLat: 26.5,
      maxLon: 123.5,
    });
  });

  it("opens the vessel panel when a vessel symbol is clicked", () => {
    const onSelectVessel = vi.fn();
    render(
      <MapCanvas
        vessels={vessels}
        layers={DEFAULT_LAYER_STATE}
        selectedTrack={null}
        onSelectVessel={onSelectVessel}
        onViewportChange={() => {}}
      />,
    );
    const clickHandler = state.layerHandlers["click:live-vessels-symbols"];
    expect(clickHandler).toBeTruthy();
    clickHandler({ features: [{ id: "v1" }] });
    expect(onSelectVessel).toHaveBeenCalledWith(expect.objectContaining({ id: "v1" }));
  });
});
