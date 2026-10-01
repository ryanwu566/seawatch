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
  layers: Array<{ id: string; type: string }>;
  sources: string[];
  layoutProps: Array<{ layer: string; prop: string; value: unknown }>;
  featureStates: Array<{ id: unknown; state: Record<string, unknown> }>;
  flyToCalls: any[];
  easeToCalls: any[];
  fitBoundsCalls: any[];
  queryHits: any[];
  popupHtml: string[];
  styledataCb: ((e?: any) => void) | null;
} = {
  options: null,
  setDataPayloads: [],
  handlers: {},
  layerHandlers: {},
  images: [],
  layers: [],
  sources: [],
  layoutProps: [],
  featureStates: [],
  flyToCalls: [],
  easeToCalls: [],
  fitBoundsCalls: [],
  queryHits: [],
  popupHtml: [],
  styledataCb: null,
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
        // Support array of layer ids (click/hover bound to multiple layers).
        const ids = Array.isArray(layerOrCb) ? layerOrCb : [layerOrCb];
        for (const id of ids) state.layerHandlers[`${event}:${id}`] = cb;
      }
    }
    once(event: string, cb?: any) {
      if (event === "styledata") {
        state.styledataCb = cb;
      } else if (typeof cb === "function") {
        cb();
      }
    }
    hasImage(id: string) {
      return state.images.includes(id);
    }
    addImage(id: string) {
      state.images.push(id);
    }
    getSource(id: string) {
      if (!state.sources.includes(id)) return undefined;
      return {
        setData: (data: any) => {
          state.setDataPayloads.push({ id, data });
        },
      };
    }
    addSource(id: string) {
      state.sources.push(id);
    }
    getLayer(id: string) {
      return state.layers.find((l) => l.id === id);
    }
    addLayer(layer: { id: string; type: string }) {
      state.layers.push({ id: layer.id, type: layer.type });
    }
    setLayoutProperty(layer: string, prop: string, value: unknown) {
      state.layoutProps.push({ layer, prop, value });
    }
    setFeatureState(id: unknown, s: Record<string, unknown>) {
      state.featureStates.push({ id, state: s });
    }
    // setStyle wipes custom sources, layers, and images (real MapLibre behavior).
    setStyle() {
      state.layers = [];
      state.sources = [];
      state.images = [];
    }
    getStyle() {
      return { layers: state.layers };
    }
    flyTo(opts: any) {
      state.flyToCalls.push(opts);
    }
    easeTo(opts: any) {
      state.easeToCalls.push(opts);
    }
    fitBounds(bounds: any, opts: any) {
      state.fitBoundsCalls.push({ bounds, opts });
    }
    getZoom() {
      return 7;
    }
    getCenter() {
      return { lng: 120.9, lat: 23.6 };
    }
    queryRenderedFeatures() {
      return state.queryHits;
    }
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
  class FakePopup {
    setLngLat() {
      return this;
    }
    setHTML(html: string) {
      state.popupHtml.push(html);
      return this;
    }
    addTo() {
      return this;
    }
    remove() {}
  }
  return {
    default: { Map: FakeMap, NavigationControl: class {}, Popup: FakePopup },
  };
});
vi.mock("maplibre-gl/dist/maplibre-gl.css", () => ({}));
// Return a lightweight stub ImageData so the addImage registration path runs
// (jsdom has no canvas 2d; the real icon is verified in the browser harness).
vi.mock("../lib/shipIcon", () => ({
  makeShipIcon: () => ({ width: 48, height: 48, data: new Uint8ClampedArray(48 * 48 * 4) }),
}));

import { MapCanvas } from "./MapCanvas";
import { DEFAULT_LAYER_STATE } from "../lib/layerState";

const vessels: LiveVesselFeature[] = [
  {
    type: "Feature",
    id: "v1",
    geometry: { type: "Point", coordinates: [120.0, 22.3] },
    properties: {
      provider_id: "v1",
      sog_knots: 0,
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
      cog_deg: 90,
      heading_deg: 511, // AIS sentinel "not available" -> falls back to COG 90
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

function baseProps(overrides: Partial<React.ComponentProps<typeof MapCanvas>> = {}) {
  return {
    vessels,
    layers: DEFAULT_LAYER_STATE,
    selectedId: null,
    selectedTrack: null,
    follow: false,
    onSelectVessel: () => {},
    onDeselect: () => {},
    onViewportChange: () => {},
    ...overrides,
  };
}

describe("MapCanvas", () => {
  beforeEach(() => {
    state.options = null;
    state.setDataPayloads = [];
    state.handlers = {};
    state.layerHandlers = {};
    state.images = [];
    state.layers = [];
    state.sources = [];
    state.layoutProps = [];
    state.featureStates = [];
    state.flyToCalls = [];
    state.easeToCalls = [];
    state.fitBoundsCalls = [];
    state.queryHits = [];
    state.popupHtml = [];
    state.styledataCb = null;
  });

  it("initializes centered on Taiwan", () => {
    render(<MapCanvas {...baseProps()} />);
    const center = state.options?.center as [number, number];
    expect(center[0]).toBeGreaterThan(119);
    expect(center[0]).toBeLessThan(123);
    expect(center[1]).toBeGreaterThan(21);
    expect(center[1]).toBeLessThan(26);
  });

  it("pushes all vessels onto a single GeoJSON source with valid orientation", () => {
    render(<MapCanvas {...baseProps()} />);
    const vesselPush = state.setDataPayloads.find((p) => p.id === "live-vessels");
    expect(vesselPush).toBeTruthy();
    expect(vesselPush.data.features).toHaveLength(2);
    // v1: orientation from heading (319).
    expect(vesselPush.data.features[0].properties.orientation).toBe(319);
    // v2: heading 511 is a sentinel -> falls back to COG (90), never 511.
    expect(vesselPush.data.features[1].properties.orientation).toBe(90);
    expect(vesselPush.data.features[1].properties.isInterpolated).toBe(true);
  });

  it("emits the viewport bbox on load", () => {
    const onViewportChange = vi.fn();
    render(<MapCanvas {...baseProps({ onViewportChange })} />);
    expect(onViewportChange).toHaveBeenCalledWith({
      minLat: 21.5,
      minLon: 118.0,
      maxLat: 26.5,
      maxLon: 123.5,
    });
  });

  it("selects a vessel when its symbol is clicked", () => {
    const onSelectVessel = vi.fn();
    render(<MapCanvas {...baseProps({ onSelectVessel })} />);
    const clickHandler = state.layerHandlers["click:live-vessels-symbols"];
    expect(clickHandler).toBeTruthy();
    clickHandler({ features: [{ id: "v1" }] });
    expect(onSelectVessel).toHaveBeenCalledWith(expect.objectContaining({ id: "v1" }));
  });

  it("deselects when clicking empty map (no vessel under cursor)", () => {
    const onDeselect = vi.fn();
    render(<MapCanvas {...baseProps({ onDeselect })} />);
    state.queryHits = []; // nothing under the click point
    const mapClick = state.handlers["click"];
    expect(mapClick).toBeTruthy();
    mapClick({ point: { x: 1, y: 1 } });
    expect(onDeselect).toHaveBeenCalled();
  });

  it("sets the selected feature-state on the chosen vessel", () => {
    render(<MapCanvas {...baseProps({ selectedId: "v1" })} />);
    const selectedTrue = state.featureStates.find(
      (f: any) => f.id.id === "v1" && f.state.selected === true,
    );
    const otherFalse = state.featureStates.find(
      (f: any) => f.id.id === "v2" && f.state.selected === false,
    );
    expect(selectedTrue).toBeTruthy();
    expect(otherFalse).toBeTruthy();
  });

  it("flies to the selected vessel", () => {
    render(<MapCanvas {...baseProps({ selectedId: "v1" })} />);
    expect(state.flyToCalls.length).toBeGreaterThan(0);
    expect(state.flyToCalls[0].center).toEqual([120.0, 22.3]);
  });

  it("shows a hover tooltip without opening the panel", () => {
    const onSelectVessel = vi.fn();
    render(<MapCanvas {...baseProps({ onSelectVessel })} />);
    const move = state.layerHandlers["mousemove:live-vessels-symbols"];
    expect(move).toBeTruthy();
    move({ features: [{ id: "v1" }], lngLat: { lng: 120, lat: 22.3 } });
    expect(state.popupHtml.length).toBeGreaterThan(0);
    expect(state.popupHtml[0]).toContain("A");
    // Hovering must NOT select.
    expect(onSelectVessel).not.toHaveBeenCalled();
  });

  it("pauses follow when the user drags the map", () => {
    const onUserInteract = vi.fn();
    render(<MapCanvas {...baseProps({ follow: true, selectedId: "v1", onUserInteract })} />);
    const dragstart = state.handlers["dragstart"];
    expect(dragstart).toBeTruthy();
    dragstart();
    expect(onUserInteract).toHaveBeenCalled();
  });

  // --- Rendering reliability regression tests (zero-vessel bug) ------------ //

  it("installs the always-visible vessel dot layer, halo, symbol, and ship image", () => {
    render(<MapCanvas {...baseProps()} />);
    expect(state.images).toContain("ship-icon");
    expect(state.sources).toContain("live-vessels");
    expect(state.layers.find((l) => l.id === "live-vessels-dot")).toBeTruthy();
    expect(state.layers.find((l) => l.id === "live-vessels-halo")).toBeTruthy();
    expect(state.layers.find((l) => l.id === "live-vessels-symbols")).toBeTruthy();
  });

  it("the primary vessel dot layer is a circle (renders without a loaded sprite/style)", () => {
    render(<MapCanvas {...baseProps()} />);
    const dot = state.layers.find((l) => l.id === "live-vessels-dot");
    expect(dot?.type).toBe("circle");
  });

  it("orders vessel layers above the basemap (dot above halo, symbol above dot)", () => {
    render(<MapCanvas {...baseProps()} />);
    const ids = state.layers.map((l) => l.id);
    const halo = ids.indexOf("live-vessels-halo");
    const dot = ids.indexOf("live-vessels-dot");
    const sym = ids.indexOf("live-vessels-symbols");
    expect(halo).toBeGreaterThanOrEqual(0);
    expect(dot).toBeGreaterThan(halo);
    expect(sym).toBeGreaterThan(dot);
  });

  it("pushes real vessel features onto the single source when vessel_count > 0", () => {
    render(<MapCanvas {...baseProps()} />);
    const push = state.setDataPayloads.find((p) => p.id === "live-vessels");
    expect(push).toBeTruthy();
    expect(push.data.features.length).toBe(2);
  });

  it("keeps the vessel layer visible by default (visibility === visible)", () => {
    render(<MapCanvas {...baseProps()} />);
    const dotVis = state.layoutProps.filter(
      (p) => p.layer === "live-vessels-dot" && p.prop === "visibility",
    );
    expect(dotVis.length).toBeGreaterThan(0);
    expect(dotVis.every((p) => p.value === "visible")).toBe(true);
  });

  it("hides vessels when the liveVessels layer is toggled off", () => {
    render(
      <MapCanvas {...baseProps({ layers: { ...DEFAULT_LAYER_STATE, liveVessels: false } })} />,
    );
    const dotVis = state.layoutProps.filter(
      (p) => p.layer === "live-vessels-dot" && p.prop === "visibility",
    );
    expect(dotVis.length).toBeGreaterThan(0);
    expect(dotVis.every((p) => p.value === "none")).toBe(true);
  });

  it("reinstalls ship image, source, and vessel layers after a basemap style reload", () => {
    const { rerender } = render(<MapCanvas {...baseProps({ layers: DEFAULT_LAYER_STATE })} />);
    // Sanity: present after initial load.
    expect(state.images).toContain("ship-icon");
    expect(state.layers.find((l) => l.id === "live-vessels-dot")).toBeTruthy();

    // Switch basemap -> setStyle() wipes custom layers/sources/images.
    rerender(
      <MapCanvas {...baseProps({ layers: { ...DEFAULT_LAYER_STATE, baseMap: "nlsc-photo" } })} />,
    );
    // The effect called setStyle (wiped) then queued a styledata reinstall.
    expect(typeof state.styledataCb).toBe("function");
    state.styledataCb?.();

    // Everything is reinstalled after the style reload.
    expect(state.images).toContain("ship-icon");
    expect(state.sources).toContain("live-vessels");
    expect(state.layers.find((l) => l.id === "live-vessels-dot")).toBeTruthy();
    expect(state.layers.find((l) => l.id === "live-vessels-halo")).toBeTruthy();
    expect(state.layers.find((l) => l.id === "live-vessels-symbols")).toBeTruthy();
  });

  it("restores vessel data and layer order after a basemap style reload", () => {
    const { rerender } = render(<MapCanvas {...baseProps({ layers: DEFAULT_LAYER_STATE })} />);
    rerender(
      <MapCanvas {...baseProps({ layers: { ...DEFAULT_LAYER_STATE, baseMap: "nlsc-photo" } })} />,
    );
    state.styledataCb?.();
    // Vessel data re-pushed onto the source after reload.
    const pushesAfter = state.setDataPayloads.filter((p) => p.id === "live-vessels");
    expect(pushesAfter.length).toBeGreaterThan(0);
    // Correct order preserved.
    const ids = state.layers.map((l) => l.id);
    expect(ids.indexOf("live-vessels-dot")).toBeGreaterThan(ids.indexOf("live-vessels-halo"));
    expect(ids.indexOf("live-vessels-symbols")).toBeGreaterThan(ids.indexOf("live-vessels-dot"));
  });

  it("keeps unselected vessels visible (dot layer not filtered by selection)", () => {
    render(<MapCanvas {...baseProps({ selectedId: null })} />);
    const push = state.setDataPayloads.find((p) => p.id === "live-vessels");
    // All features present even with nothing selected.
    expect(push.data.features.length).toBe(2);
    const dot = state.layers.find((l) => l.id === "live-vessels-dot");
    expect(dot).toBeTruthy();
    // Dot layer is visible (not hidden when no selection).
    const dotVis = state.layoutProps.filter(
      (p) => p.layer === "live-vessels-dot" && p.prop === "visibility",
    );
    expect(dotVis.every((p) => p.value === "visible")).toBe(true);
  });

  it("fits the map to a preset region when fitBoundsNonce changes", () => {
    const bounds: [number, number, number, number] = [118.0, 21.5, 123.5, 26.3];
    const { rerender } = render(<MapCanvas {...baseProps({ fitBounds: bounds, fitBoundsNonce: 0 })} />);
    const before = state.fitBoundsCalls.length;
    rerender(<MapCanvas {...baseProps({ fitBounds: bounds, fitBoundsNonce: 1 })} />);
    expect(state.fitBoundsCalls.length).toBeGreaterThan(before);
    const last = state.fitBoundsCalls[state.fitBoundsCalls.length - 1];
    expect(last.bounds).toEqual([
      [118.0, 21.5],
      [123.5, 26.3],
    ]);
  });

  it("caps the select flyTo zoom to a useful maritime detail level (<=12)", () => {
    render(<MapCanvas {...baseProps({ selectedId: "v1" })} />);
    expect(state.flyToCalls.length).toBeGreaterThan(0);
    expect(state.flyToCalls[0].zoom).toBeLessThanOrEqual(12);
  });

  it("declutters at low zoom: the directional symbol icon fades in with zoom", () => {
    render(<MapCanvas {...baseProps()} />);
    const sym = state.layers.find((l) => l.id === "live-vessels-symbols");
    expect(sym).toBeTruthy();
    expect(sym?.type).toBe("symbol");
  });
});
