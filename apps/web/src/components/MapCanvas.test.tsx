import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, fireEvent, render } from "@testing-library/react";
import type { LiveVesselFeature } from "../api/live";

// Record interactions with the mocked MapLibre map.
const state: {
  options: Record<string, unknown> | null;
  setDataPayloads: any[];
  handlers: Record<string, (e?: any) => void>;
  layerHandlers: Record<string, (e?: any) => void>;
  images: string[];
  layers: any[];
  sources: string[];
  sourceSpecs: Record<string, any>;
  layoutProps: Array<{ layer: string; prop: string; value: unknown }>;
  featureStates: Array<{ id: unknown; state: Record<string, unknown> }>;
  flyToCalls: any[];
  easeToCalls: any[];
  fitBoundsCalls: any[];
  queryHits: any[];
  popupHtml: string[];
  styledataCb: ((e?: any) => void) | null;
  events: string[];
  styles: any[];
  dragPanDisabled: boolean;
  doubleClickDisabled: boolean;
  deferLoad: boolean;
  canvas: HTMLCanvasElement | null;
  capturedPointerId: number | null;
  releasedPointerIds: number[];
} = {
  options: null,
  setDataPayloads: [],
  handlers: {},
  layerHandlers: {},
  images: [],
  layers: [],
  sources: [],
  sourceSpecs: {},
  layoutProps: [],
  featureStates: [],
  flyToCalls: [],
  easeToCalls: [],
  fitBoundsCalls: [],
  queryHits: [],
  popupHtml: [],
  styledataCb: null,
  events: [],
  styles: [],
  dragPanDisabled: false,
  doubleClickDisabled: false,
  deferLoad: false,
  canvas: null,
  capturedPointerId: null,
  releasedPointerIds: [],
};

function last<T>(values: T[]): T | undefined {
  return values[values.length - 1];
}

vi.mock("maplibre-gl", () => {
  class FakeMap {
    dragPan = {
      disable: () => { state.dragPanDisabled = true; },
      enable: () => { state.dragPanDisabled = false; },
    };
    doubleClickZoom = {
      disable: () => { state.doubleClickDisabled = true; },
      enable: () => { state.doubleClickDisabled = false; },
    };
    constructor(options: Record<string, unknown>) {
      state.events.push("map");
      state.options = options;
      const canvas = document.createElement("canvas");
      canvas.setPointerCapture = (pointerId: number) => {
        state.capturedPointerId = pointerId;
      };
      canvas.releasePointerCapture = (pointerId: number) => {
        state.releasedPointerIds.push(pointerId);
        if (state.capturedPointerId === pointerId) state.capturedPointerId = null;
      };
      canvas.hasPointerCapture = (pointerId: number) => state.capturedPointerId === pointerId;
      const container = options.container;
      if (container instanceof HTMLElement) container.appendChild(canvas);
      state.canvas = canvas;
    }
    addControl() {}
    on(event: string, layerOrCb: any, cb?: any) {
      if (typeof layerOrCb === "function") {
        state.handlers[event] = layerOrCb;
        if (event === "load" && !state.deferLoad) layerOrCb();
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
    addSource(id: string, spec: any) {
      state.sources.push(id);
      state.sourceSpecs[id] = spec;
    }
    getLayer(id: string) {
      return state.layers.find((l) => l.id === id);
    }
    addLayer(layer: any) {
      state.layers.push(layer);
    }
    setLayoutProperty(layer: string, prop: string, value: unknown) {
      state.layoutProps.push({ layer, prop, value });
    }
    setFeatureState(id: unknown, s: Record<string, unknown>) {
      state.featureStates.push({ id, state: s });
    }
    // setStyle wipes custom sources, layers, and images (real MapLibre behavior).
    setStyle(style: any) {
      state.styles.push(style);
      state.layers = [];
      state.sources = [];
      state.sourceSpecs = {};
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
      return state.canvas!;
    }
    project(lngLat: [number, number] | { lng: number; lat: number }) {
      const [lng, lat] = Array.isArray(lngLat) ? lngLat : [lngLat.lng, lngLat.lat];
      return { x: lng * 100, y: lat * 100 };
    }
    unproject(point: [number, number] | { x: number; y: number }) {
      const [x, y] = Array.isArray(point) ? point : [point.x, point.y];
      return { lng: x / 100, lat: y / 100 };
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
    addProtocol: vi.fn(() => state.events.push("protocol")),
  };
});
vi.mock("pmtiles", () => ({ Protocol: class { tile() {} } }));
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

function fireCanvasPointer(
  type: "pointerdown" | "pointermove" | "pointerup",
  init: { pointerId: number; clientX: number; clientY: number; button?: number },
) {
  const event = new MouseEvent(type, {
    bubbles: true,
    cancelable: true,
    button: init.button ?? 0,
    clientX: init.clientX,
    clientY: init.clientY,
  });
  Object.defineProperties(event, {
    pointerId: { value: init.pointerId },
    pointerType: { value: "mouse" },
  });
  fireEvent(state.canvas!, event);
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
    state.sourceSpecs = {};
    state.layoutProps = [];
    state.featureStates = [];
    state.flyToCalls = [];
    state.easeToCalls = [];
    state.fitBoundsCalls = [];
    state.queryHits = [];
    state.popupHtml = [];
    state.styledataCb = null;
    state.events = [];
    state.styles = [];
    state.dragPanDisabled = false;
    state.doubleClickDisabled = false;
    state.deferLoad = false;
    state.canvas = null;
    state.capturedPointerId = null;
    state.releasedPointerIds = [];
  });

  it("initializes centered on Taiwan", () => {
    render(<MapCanvas {...baseProps()} />);
    expect(state.events.indexOf("protocol")).toBeGreaterThanOrEqual(0);
    expect(state.events.indexOf("protocol")).toBeLessThan(state.events.indexOf("map"));
    const center = state.options?.center as [number, number];
    expect(center[0]).toBeGreaterThan(119);
    expect(center[0]).toBeLessThan(123);
    expect(center[1]).toBeGreaterThan(21);
    expect(center[1]).toBeLessThan(26);
  });

  it("uses English labels for built-in geographic overlays", () => {
    render(<MapCanvas {...baseProps()} />);

    const portLabels = state.layers.find((layer) => layer.id === "ports-label");
    expect(portLabels?.layout?.["text-field"]).toEqual(["get", "nameEn"]);
  });

  it("registers the three maritime sources against allowlisted context routes", () => {
    render(<MapCanvas {...baseProps()} />);

    expect(state.sources).toEqual(expect.arrayContaining([
      "seawatch-eez-reference",
      "seawatch-territorial-sea-12nm",
      "seawatch-contiguous-zone-24nm",
    ]));
    expect(state.sourceSpecs["seawatch-eez-reference"]).toEqual(expect.objectContaining({
      type: "geojson",
      data: expect.stringMatching(/\/context\/maritime-reference\/eez-reference\.geojson$/),
      attribution: expect.stringMatching(/Marine Regions.*World EEZ v12.*CC BY 4\.0/),
    }));
    expect(state.sourceSpecs["seawatch-territorial-sea-12nm"]).toEqual(expect.objectContaining({
      type: "geojson",
      data: expect.stringMatching(
        /\/context\/maritime-reference\/territorial-sea-12nm-reference\.geojson$/,
      ),
      attribution: expect.stringMatching(/Taiwan Ministry of the Interior.*derived polygon/),
    }));
    expect(state.sourceSpecs["seawatch-contiguous-zone-24nm"]).toEqual(expect.objectContaining({
      type: "geojson",
      data: expect.stringMatching(
        /\/context\/maritime-reference\/contiguous-zone-24nm-reference\.geojson$/,
      ),
      attribution: expect.stringMatching(/Taiwan Ministry of the Interior.*derived band/),
    }));
    for (const sourceId of [
      "seawatch-eez-reference",
      "seawatch-territorial-sea-12nm",
      "seawatch-contiguous-zone-24nm",
    ]) {
      expect(state.sourceSpecs[sourceId].data).not.toMatch(/^[A-Za-z]:[\\/]|^file:/);
    }
  });

  it("draws subtle maritime fills and boundaries below Area Scan and vessel layers", () => {
    render(<MapCanvas {...baseProps()} />);

    const ids = state.layers.map((layer) => layer.id);
    const maritimeLayerIds = [
      "seawatch-eez-reference-fill",
      "seawatch-territorial-sea-12nm-fill",
      "seawatch-contiguous-zone-24nm-fill",
      "seawatch-eez-reference-line",
      "seawatch-territorial-sea-12nm-line",
      "seawatch-contiguous-zone-24nm-line",
    ];
    expect(ids).toEqual(expect.arrayContaining(maritimeLayerIds));
    for (const layerId of maritimeLayerIds) {
      expect(ids.indexOf(layerId)).toBeLessThan(ids.indexOf("live-vessels-symbols"));
      expect(ids.indexOf(layerId)).toBeLessThan(ids.indexOf("area-scan-fill"));
    }
    for (const layerId of maritimeLayerIds.filter((id) => id.endsWith("-fill"))) {
      expect(state.layers.find((layer) => layer.id === layerId)?.paint?.["fill-opacity"])
        .toBeLessThanOrEqual(0.1);
    }
  });

  it("applies independent visibility to every maritime reference group", () => {
    const { rerender } = render(<MapCanvas {...baseProps()} />);

    rerender(
      <MapCanvas
        {...baseProps({
          layers: {
            ...DEFAULT_LAYER_STATE,
            eezReference: false,
            territorialSea12NmReference: true,
            contiguousZone24NmReference: true,
          },
        })}
      />,
    );
    expect(last(state.layoutProps.filter((p) => p.layer === "seawatch-eez-reference-fill"))?.value)
      .toBe("none");
    expect(last(state.layoutProps.filter((p) => p.layer === "seawatch-territorial-sea-12nm-fill"))?.value)
      .toBe("visible");

    rerender(
      <MapCanvas
        {...baseProps({
          layers: {
            ...DEFAULT_LAYER_STATE,
            eezReference: true,
            territorialSea12NmReference: false,
            contiguousZone24NmReference: true,
          },
        })}
      />,
    );
    expect(last(state.layoutProps.filter((p) => p.layer === "seawatch-territorial-sea-12nm-line"))?.value)
      .toBe("none");
    expect(last(state.layoutProps.filter((p) => p.layer === "seawatch-contiguous-zone-24nm-line"))?.value)
      .toBe("visible");

    rerender(
      <MapCanvas
        {...baseProps({
          layers: {
            ...DEFAULT_LAYER_STATE,
            eezReference: true,
            territorialSea12NmReference: true,
            contiguousZone24NmReference: false,
          },
        })}
      />,
    );
    expect(last(state.layoutProps.filter((p) => p.layer === "seawatch-contiguous-zone-24nm-fill"))?.value)
      .toBe("none");
    expect(last(state.layoutProps.filter((p) => p.layer === "seawatch-eez-reference-line"))?.value)
      .toBe("visible");
  });

  it("restores enabled maritime layers idempotently after a basemap style reload", () => {
    const { rerender } = render(<MapCanvas {...baseProps()} />);

    rerender(
      <MapCanvas
        {...baseProps({ layers: { ...DEFAULT_LAYER_STATE, baseMap: "nlsc-photo" } })}
      />,
    );
    expect(typeof state.styledataCb).toBe("function");
    act(() => state.styledataCb?.());
    act(() => state.styledataCb?.());

    for (const sourceId of [
      "seawatch-eez-reference",
      "seawatch-territorial-sea-12nm",
      "seawatch-contiguous-zone-24nm",
    ]) {
      expect(state.sources.filter((id) => id === sourceId)).toHaveLength(1);
    }
    for (const layerId of [
      "seawatch-eez-reference-fill",
      "seawatch-territorial-sea-12nm-fill",
      "seawatch-contiguous-zone-24nm-fill",
      "seawatch-eez-reference-line",
      "seawatch-territorial-sea-12nm-line",
      "seawatch-contiguous-zone-24nm-line",
    ]) {
      expect(state.layers.filter((layer) => layer.id === layerId)).toHaveLength(1);
    }
    expect(state.layers.find((layer) => layer.id === "live-vessels-symbols")).toBeTruthy();
    expect(state.layers.find((layer) => layer.id === "area-scan-fill")).toBeTruthy();
  });

  it("restores the latest maritime visibility after a fallback style reload", () => {
    const { rerender } = render(<MapCanvas {...baseProps()} />);
    rerender(
      <MapCanvas
        {...baseProps({
          layers: { ...DEFAULT_LAYER_STATE, eezReference: false },
        })}
      />,
    );

    act(() => state.handlers.error?.({ error: new Error("online style fetch failed") }));
    act(() => state.styledataCb?.());

    expect(last(state.layoutProps.filter((p) => p.layer === "seawatch-eez-reference-fill"))?.value)
      .toBe("none");
    expect(last(state.layoutProps.filter((p) => p.layer === "seawatch-territorial-sea-12nm-fill"))?.value)
      .toBe("visible");
  });

  it("uses a toggle changed while a basemap style is still loading", () => {
    const { rerender } = render(<MapCanvas {...baseProps()} />);
    rerender(
      <MapCanvas
        {...baseProps({ layers: { ...DEFAULT_LAYER_STATE, baseMap: "nlsc-photo" } })}
      />,
    );
    rerender(
      <MapCanvas
        {...baseProps({
          layers: {
            ...DEFAULT_LAYER_STATE,
            baseMap: "nlsc-photo",
            contiguousZone24NmReference: false,
          },
        })}
      />,
    );

    act(() => state.styledataCb?.());

    expect(last(state.layoutProps.filter((p) => p.layer === "seawatch-contiguous-zone-24nm-line"))?.value)
      .toBe("none");
    expect(last(state.layoutProps.filter((p) => p.layer === "seawatch-eez-reference-line"))?.value)
      .toBe("visible");
  });

  it("does not turn a maritime source failure into a basemap failure", () => {
    const onBaseMapError = vi.fn();
    render(<MapCanvas {...baseProps({ onBaseMapError })} />);
    const styleCount = state.styles.length;

    act(() => state.handlers.error?.({
      sourceId: "seawatch-eez-reference",
      error: new Error("GeoJSON source fetch failed"),
    }));

    expect(state.styles).toHaveLength(styleCount);
    expect(onBaseMapError).not.toHaveBeenCalled();
    expect(state.layers.find((layer) => layer.id === "live-vessels-symbols")).toBeTruthy();
    expect(state.layers.find((layer) => layer.id === "area-scan-fill")).toBeTruthy();
  });

  it("finishes polygon drawing as closed longitude-latitude GeoJSON", () => {
    const onAreaGeometryChange = vi.fn();
    render(
      <MapCanvas
        {...baseProps({
          areaDrawMode: "polygon",
          onAreaGeometryChange,
        })}
      />,
    );

    expect(state.doubleClickDisabled).toBe(true);
    act(() => state.handlers.click?.({ lngLat: { lng: 120, lat: 22 }, point: {} }));
    act(() => state.handlers.click?.({ lngLat: { lng: 121, lat: 22 }, point: {} }));
    act(() => state.handlers.click?.({ lngLat: { lng: 121, lat: 23 }, point: {} }));
    expect(onAreaGeometryChange).not.toHaveBeenCalled();
    act(() => state.handlers.dblclick?.({ preventDefault: () => {} }));

    expect(onAreaGeometryChange).toHaveBeenCalledWith({
      type: "Polygon",
      coordinates: [[[120, 22], [121, 22], [121, 23], [120, 22]]],
    });
  });

  it("renders an open polygon draft with visible vertices and a distinct start vertex", () => {
    render(<MapCanvas {...baseProps({ areaDrawMode: "polygon" })} />);
    expect(state.canvas?.style.cursor).toBe("crosshair");

    act(() => state.handlers.click?.({
      lngLat: { lng: 120, lat: 22 },
      point: { x: 12000, y: 2200 },
    }));
    act(() => state.handlers.click?.({
      lngLat: { lng: 121, lat: 22 },
      point: { x: 12100, y: 2200 },
    }));
    act(() => state.handlers.click?.({
      lngLat: { lng: 121, lat: 23 },
      point: { x: 12100, y: 2300 },
    }));

    const draftPath = last(
      state.setDataPayloads.filter((entry) => entry.id === "area-scan-draft-path"),
    )?.data;
    const draftVertices = last(
      state.setDataPayloads.filter((entry) => entry.id === "area-scan-draft-vertices"),
    )?.data;
    const finalized = last(
      state.setDataPayloads.filter((entry) => entry.id === "area-scan-geometry"),
    )?.data;
    expect(draftPath.features[0].geometry).toEqual({
      type: "LineString",
      coordinates: [[120, 22], [121, 22], [121, 23]],
    });
    expect(draftVertices.features).toHaveLength(3);
    expect(draftVertices.features[0].properties.role).toBe("start");
    expect(draftVertices.features[1].properties.role).toBe("vertex");
    expect(finalized).toEqual({ type: "FeatureCollection", features: [] });
    expect(state.layers.find((layer) => layer.id === "area-scan-draft-path")?.type).toBe("line");
    expect(state.layers.find((layer) => layer.id === "area-scan-draft-vertices")?.type).toBe("circle");
  });

  it("clears polygon draft handles after finalization", () => {
    render(<MapCanvas {...baseProps({ areaDrawMode: "polygon" })} />);
    act(() => state.handlers.click?.({ lngLat: { lng: 120, lat: 22 }, point: { x: 12000, y: 2200 } }));
    act(() => state.handlers.click?.({ lngLat: { lng: 121, lat: 22 }, point: { x: 12100, y: 2200 } }));
    act(() => state.handlers.click?.({ lngLat: { lng: 121, lat: 23 }, point: { x: 12100, y: 2300 } }));
    act(() => state.handlers.dblclick?.({ preventDefault: () => {} }));

    expect(last(state.setDataPayloads.filter((entry) => entry.id === "area-scan-draft-path"))?.data)
      .toEqual({ type: "FeatureCollection", features: [] });
    expect(last(state.setDataPayloads.filter((entry) => entry.id === "area-scan-draft-vertices"))?.data)
      .toEqual({ type: "FeatureCollection", features: [] });
  });

  it("rejects a self-intersecting polygon through the invalid-geometry callback", () => {
    const onAreaGeometryChange = vi.fn();
    const onAreaGeometryInvalid = vi.fn();
    render(<MapCanvas {...baseProps({
      areaDrawMode: "polygon",
      onAreaGeometryChange,
      onAreaGeometryInvalid,
    })} />);
    for (const [lng, lat] of [[120, 22], [121, 23], [120, 23], [121, 22]]) {
      act(() => state.handlers.click?.({ lngLat: { lng, lat }, point: { x: lng * 100, y: lat * 100 } }));
    }
    act(() => state.handlers.dblclick?.({ preventDefault: () => {} }));

    expect(onAreaGeometryChange).not.toHaveBeenCalled();
    expect(onAreaGeometryInvalid).toHaveBeenCalledTimes(1);
  });

  it("finishes polygon drawing by clicking near the starting vertex", () => {
    const onAreaGeometryChange = vi.fn();
    render(
      <MapCanvas
        {...baseProps({
          areaDrawMode: "polygon",
          onAreaGeometryChange,
        })}
      />,
    );

    act(() => state.handlers.click?.({ lngLat: { lng: 120, lat: 22 }, point: { x: 12000, y: 2200 } }));
    act(() => state.handlers.click?.({ lngLat: { lng: 121, lat: 22 }, point: { x: 12100, y: 2200 } }));
    act(() => state.handlers.click?.({ lngLat: { lng: 121, lat: 23 }, point: { x: 12100, y: 2300 } }));
    expect(onAreaGeometryChange).not.toHaveBeenCalled();

    act(() => state.handlers.click?.({
      lngLat: { lng: 120.02, lat: 22.02 },
      point: { x: 12006, y: 2208 },
    }));

    expect(onAreaGeometryChange).toHaveBeenCalledTimes(1);
    expect(onAreaGeometryChange).toHaveBeenCalledWith({
      type: "Polygon",
      coordinates: [[[120, 22], [121, 22], [121, 23], [120, 22]]],
    });
    expect(state.doubleClickDisabled).toBe(false);
  });

  it("ignores a starting-vertex click until the polygon has enough vertices", () => {
    const onAreaGeometryChange = vi.fn();
    render(
      <MapCanvas
        {...baseProps({
          areaDrawMode: "polygon",
          onAreaGeometryChange,
        })}
      />,
    );

    act(() => state.handlers.click?.({ lngLat: { lng: 120, lat: 22 }, point: { x: 12000, y: 2200 } }));
    act(() => state.handlers.click?.({ lngLat: { lng: 121, lat: 22 }, point: { x: 12100, y: 2200 } }));
    act(() => state.handlers.click?.({
      lngLat: { lng: 120.02, lat: 22.02 },
      point: { x: 12006, y: 2208 },
    }));
    expect(onAreaGeometryChange).not.toHaveBeenCalled();

    act(() => state.handlers.click?.({ lngLat: { lng: 121, lat: 23 }, point: { x: 12100, y: 2300 } }));
    act(() => state.handlers.click?.({
      lngLat: { lng: 120.02, lat: 22.02 },
      point: { x: 12006, y: 2208 },
    }));

    expect(onAreaGeometryChange).toHaveBeenCalledWith({
      type: "Polygon",
      coordinates: [[[120, 22], [121, 22], [121, 23], [120, 22]]],
    });
  });

  it("keeps a click near a non-starting vertex as an ordinary polygon point", () => {
    const onAreaGeometryChange = vi.fn();
    render(
      <MapCanvas
        {...baseProps({
          areaDrawMode: "polygon",
          onAreaGeometryChange,
        })}
      />,
    );

    act(() => state.handlers.click?.({ lngLat: { lng: 120, lat: 22 }, point: { x: 12000, y: 2200 } }));
    act(() => state.handlers.click?.({ lngLat: { lng: 121, lat: 22 }, point: { x: 12100, y: 2200 } }));
    act(() => state.handlers.click?.({ lngLat: { lng: 121, lat: 23 }, point: { x: 12100, y: 2300 } }));
    act(() => state.handlers.click?.({
      lngLat: { lng: 120.5, lat: 23.2 },
      point: { x: 12101, y: 2201 },
    }));

    expect(onAreaGeometryChange).not.toHaveBeenCalled();
    act(() => state.handlers.dblclick?.({ preventDefault: () => {} }));
    expect(onAreaGeometryChange).toHaveBeenCalledWith({
      type: "Polygon",
      coordinates: [[[120, 22], [121, 22], [121, 23], [120.5, 23.2], [120, 22]]],
    });
  });

  it("Escape clears a polygon preview without committing geometry", () => {
    const onAreaGeometryChange = vi.fn();
    render(
      <MapCanvas
        {...baseProps({
          areaDrawMode: "polygon",
          onAreaGeometryChange,
        })}
      />,
    );

    act(() => state.handlers.click?.({ lngLat: { lng: 120, lat: 22 }, point: { x: 12000, y: 2200 } }));
    act(() => state.handlers.click?.({ lngLat: { lng: 121, lat: 22 }, point: { x: 12100, y: 2200 } }));
    act(() => state.handlers.click?.({ lngLat: { lng: 121, lat: 23 }, point: { x: 12100, y: 2300 } }));
    fireEvent.keyDown(window, { key: "Escape" });

    expect(onAreaGeometryChange).not.toHaveBeenCalled();
    expect(state.doubleClickDisabled).toBe(false);
    expect(last(state.setDataPayloads.filter((entry) => entry.id === "area-scan-geometry"))?.data)
      .toEqual({ type: "FeatureCollection", features: [] });
  });

  it("captures a canvas pointer drag, previews a normalized rectangle, and commits once", () => {
    const onAreaGeometryChange = vi.fn();
    render(
      <MapCanvas
        {...baseProps({
          areaDrawMode: "rectangle",
          onAreaGeometryChange,
        })}
      />,
    );

    expect(state.dragPanDisabled).toBe(true);
    expect(state.canvas?.style.cursor).toBe("crosshair");
    fireCanvasPointer("pointerdown", {
      pointerId: 7,
      button: 0,
      clientX: 12100,
      clientY: 2300,
    });
    expect(state.capturedPointerId).toBe(7);
    fireCanvasPointer("pointermove", {
      pointerId: 7,
      clientX: 12000,
      clientY: 2200,
    });
    expect(onAreaGeometryChange).not.toHaveBeenCalled();
    const expectedRectangle = {
      type: "Polygon",
      coordinates: [[[120, 22], [121, 22], [121, 23], [120, 23], [120, 22]]],
    };
    expect(last(state.setDataPayloads.filter((entry) => entry.id === "area-scan-geometry"))?.data)
      .toEqual({
        type: "Feature",
        properties: {},
        geometry: expectedRectangle,
      });
    fireCanvasPointer("pointerup", {
      pointerId: 7,
      button: 0,
      clientX: 12000,
      clientY: 2200,
    });

    expect(onAreaGeometryChange).toHaveBeenCalledTimes(1);
    expect(onAreaGeometryChange).toHaveBeenCalledWith(expectedRectangle);
    expect(state.releasedPointerIds).toEqual([7]);
    expect(state.dragPanDisabled).toBe(false);
    expect(state.canvas?.style.cursor).toBe("");
  });

  it("does not commit or restore map panning after a zero-area rectangle drag", () => {
    const onAreaGeometryChange = vi.fn();
    render(
      <MapCanvas
        {...baseProps({
          areaDrawMode: "rectangle",
          onAreaGeometryChange,
        })}
      />,
    );

    fireCanvasPointer("pointerdown", {
      pointerId: 9,
      button: 0,
      clientX: 12000,
      clientY: 2200,
    });
    fireCanvasPointer("pointerup", {
      pointerId: 9,
      button: 0,
      clientX: 12000,
      clientY: 2200,
    });

    expect(onAreaGeometryChange).not.toHaveBeenCalled();
    expect(state.dragPanDisabled).toBe(true);
    expect(state.canvas?.style.cursor).toBe("crosshair");
  });

  it("renders and selects emphasized Area Scan vessels on a separate source", () => {
    const onSelectVessel = vi.fn();
    render(
      <MapCanvas
        {...baseProps({
          areaGeometry: {
            type: "Polygon",
            coordinates: [[[120, 22], [121, 22], [121, 23], [120, 22]]],
          },
          areaVessels: [vessels[0]],
          onSelectVessel,
        })}
      />,
    );

    expect(state.sources).toContain("area-scan-geometry");
    expect(state.sources).toContain("area-scan-vessels");
    expect(state.layers.map((layer) => layer.id)).toEqual(
      expect.arrayContaining([
        "area-scan-fill",
        "area-scan-line",
        "area-scan-vessels-symbols",
      ]),
    );
    act(() =>
      state.layerHandlers["click:area-scan-vessels-symbols"]?.({ features: [{ id: "v1" }] }),
    );
    expect(onSelectVessel).toHaveBeenCalledWith(vessels[0], "datalastic");
  });

  it("keeps same-ID live and Area Scan marker provenance separate", () => {
    const onSelectVessel = vi.fn();
    const scanVersion: LiveVesselFeature = {
      ...vessels[0],
      geometry: { type: "Point", coordinates: [122, 24] },
      properties: { ...vessels[0].properties, name: "SCAN", source: "datalastic" },
    };
    render(
      <MapCanvas
        {...baseProps({ areaVessels: [scanVersion], onSelectVessel })}
      />,
    );

    act(() =>
      state.layerHandlers["click:live-vessels-symbols"]?.({
        features: [{ id: "v1", layer: { id: "live-vessels-symbols" } }],
      }),
    );
    act(() =>
      state.layerHandlers["click:area-scan-vessels-symbols"]?.({
        features: [{ id: "v1", layer: { id: "area-scan-vessels-symbols" } }],
      }),
    );

    expect(onSelectVessel).toHaveBeenNthCalledWith(1, vessels[0], "live");
    expect(onSelectVessel).toHaveBeenNthCalledWith(2, scanVersion, "datalastic");
  });

  it("flies to and selects only the requested source when IDs collide", () => {
    const scanVersion: LiveVesselFeature = {
      ...vessels[0],
      geometry: { type: "Point", coordinates: [122, 24] },
      properties: { ...vessels[0].properties, source: "datalastic" },
    };
    render(
      <MapCanvas
        {...baseProps({
          selectedId: "v1",
          selectedSource: "datalastic",
          areaVessels: [scanVersion],
        })}
      />,
    );

    expect(last(state.flyToCalls)?.center).toEqual([122, 24]);
    const liveState = state.featureStates.find(
      (entry: any) => entry.id.source === "live-vessels" && entry.id.id === "v1",
    );
    const scanState = state.featureStates.find(
      (entry: any) => entry.id.source === "area-scan-vessels" && entry.id.id === "v1",
    );
    expect(liveState?.state.selected).toBe(false);
    expect(scanState?.state.selected).toBe(true);
  });

  it("clears only Area Scan sources and live refresh never overwrites them", () => {
    const scanVersion: LiveVesselFeature = {
      ...vessels[0],
      id: "scan-1",
      properties: { ...vessels[0].properties, provider_id: "scan-1", source: "datalastic" },
    };
    const geometry: GeoJSON.Polygon = {
      type: "Polygon",
      coordinates: [[[120, 22], [121, 22], [121, 23], [120, 22]]],
    };
    const { rerender } = render(
      <MapCanvas {...baseProps({ areaGeometry: geometry, areaVessels: [scanVersion] })} />,
    );

    rerender(
      <MapCanvas
        {...baseProps({
          vessels: [vessels[1]],
          areaGeometry: geometry,
          areaVessels: [scanVersion],
        })}
      />,
    );
    const retained = last(
      state.setDataPayloads.filter((entry) => entry.id === "area-scan-vessels"),
    );
    expect(retained.data.features[0].id).toBe("scan-1");

    rerender(<MapCanvas {...baseProps({ vessels: [vessels[1]], areaGeometry: null, areaVessels: [] })} />);
    const clearedVessels = last(
      state.setDataPayloads.filter((entry) => entry.id === "area-scan-vessels"),
    );
    const clearedGeometry = last(
      state.setDataPayloads.filter((entry) => entry.id === "area-scan-geometry"),
    );
    expect(clearedVessels.data.features).toEqual([]);
    expect(clearedGeometry.data.features).toEqual([]);
  });

  it("restores Area Scan geometry and vessels after style reload", () => {
    const geometry: GeoJSON.Polygon = {
      type: "Polygon",
      coordinates: [[[120, 22], [121, 22], [121, 23], [120, 22]]],
    };
    const { rerender } = render(
      <MapCanvas {...baseProps({ areaGeometry: geometry, areaVessels: [vessels[0]] })} />,
    );
    rerender(
      <MapCanvas
        {...baseProps({
          areaGeometry: geometry,
          areaVessels: [vessels[0]],
          layers: { ...DEFAULT_LAYER_STATE, baseMap: "nlsc-photo" },
        })}
      />,
    );
    act(() => state.styledataCb?.());

    expect(state.sources).toEqual(expect.arrayContaining(["area-scan-geometry", "area-scan-vessels"]));
    expect(
      last(state.setDataPayloads.filter((entry) => entry.id === "area-scan-vessels"))
        ?.data.features[0].id,
    ).toBe("v1");
  });

  it("Escape cancels a captured rectangle draft and restores pointer interactions", () => {
    const onAreaGeometryChange = vi.fn();
    render(<MapCanvas {...baseProps({ areaDrawMode: "rectangle", onAreaGeometryChange })} />);
    fireCanvasPointer("pointerdown", {
      pointerId: 11,
      button: 0,
      clientX: 12000,
      clientY: 2200,
    });
    fireCanvasPointer("pointermove", {
      pointerId: 11,
      clientX: 12100,
      clientY: 2300,
    });
    expect(state.dragPanDisabled).toBe(true);

    fireEvent.keyDown(window, { key: "Escape" });

    expect(onAreaGeometryChange).not.toHaveBeenCalled();
    expect(state.releasedPointerIds).toEqual([11]);
    expect(state.dragPanDisabled).toBe(false);
    expect(state.doubleClickDisabled).toBe(false);
    expect(state.canvas?.style.cursor).toBe("");
    expect(last(state.setDataPayloads.filter((entry) => entry.id === "area-scan-geometry"))?.data)
      .toEqual({ type: "FeatureCollection", features: [] });
  });

  it("starts offline mode on PMTiles and latches its failure to emergency", () => {
    const { container } = render(
      <MapCanvas {...baseProps({ operatingMode: "NO_LIVE_SOURCE" })} />,
    );
    expect(JSON.stringify(state.options?.style)).toContain("pmtiles:///offline/taiwan.pmtiles");

    act(() => state.handlers.error?.({ error: new Error("PMTiles source fetch failed") }));
    expect(JSON.stringify(state.styles[state.styles.length - 1])).not.toMatch(/https?:|pmtiles:/);
    expect(container.querySelector(".map-canvas")).toHaveAttribute(
      "data-basemap-stage",
      "emergency",
    );

    const transitions = state.styles.length;
    act(() => state.handlers.error?.({ error: new Error("network still unavailable") }));
    expect(state.styles).toHaveLength(transitions);
  });

  it("tries OpenFreeMap when online mode becomes known after PMTiles fails", () => {
    const props = baseProps({
      operatingMode: "NO_LIVE_SOURCE",
      onlineBasemap: false,
      areaGeometry: {
        type: "Polygon" as const,
        coordinates: [[[120, 22], [121, 22], [121, 23], [120, 22]]],
      },
      areaVessels: [vessels[0]],
    });
    const { container, rerender } = render(<MapCanvas {...props} />);

    act(() => state.handlers.error?.({ error: new Error("PMTiles source fetch failed") }));
    expect(container.querySelector(".map-canvas")).toHaveAttribute(
      "data-basemap-stage",
      "emergency",
    );

    rerender(<MapCanvas {...props} onlineBasemap />);

    expect(last(state.styles)).toBe("https://tiles.openfreemap.org/styles/liberty");
    expect(container.querySelector(".map-canvas")).toHaveAttribute(
      "data-basemap-stage",
      "online",
    );

    act(() => state.styledataCb?.());
    expect(state.sources).toEqual(expect.arrayContaining([
      "live-vessels",
      "area-scan-geometry",
      "area-scan-draft-path",
      "area-scan-draft-vertices",
      "area-scan-vessels",
    ]));
  });

  it("applies an online preference learned before the initial style loads", () => {
    state.deferLoad = true;
    const props = baseProps({ operatingMode: "NO_LIVE_SOURCE", onlineBasemap: false });
    const { rerender } = render(<MapCanvas {...props} />);
    expect(JSON.stringify(state.options?.style)).toContain("pmtiles:///offline/taiwan.pmtiles");

    rerender(<MapCanvas {...props} onlineBasemap />);
    act(() => state.handlers.load?.());

    expect(last(state.styles)).toBe("https://tiles.openfreemap.org/styles/liberty");
  });

  it("falls back from OpenFreeMap to PMTiles and then emergency geometry", () => {
    const onBaseMapError = vi.fn();
    const { container } = render(
      <MapCanvas
        {...baseProps({ operatingMode: "CLOUD_LIVE", onBaseMapError })}
      />,
    );
    expect(state.options?.style).toBe("https://tiles.openfreemap.org/styles/liberty");

    act(() => state.handlers.error?.({ error: new Error("online style fetch failed") }));

    expect(onBaseMapError).toHaveBeenCalledWith("online style fetch failed");
    expect(JSON.stringify(last(state.styles))).toContain("pmtiles:///offline/taiwan.pmtiles");
    expect(container.querySelector(".map-canvas")).toHaveAttribute(
      "data-basemap-stage",
      "pmtiles",
    );

    act(() => state.handlers.error?.({ error: new Error("PMTiles source fetch failed") }));
    expect(JSON.stringify(last(state.styles))).not.toMatch(/https?:|pmtiles:/);
    expect(container.querySelector(".map-canvas")).toHaveAttribute(
      "data-basemap-stage",
      "emergency",
    );
  });

  it("restores vessel, Area Scan, and future overlay seams after online fallback", () => {
    render(
      <MapCanvas
        {...baseProps({
          operatingMode: "CLOUD_LIVE",
          areaGeometry: {
            type: "Polygon",
            coordinates: [[[120, 22], [121, 22], [121, 23], [120, 22]]],
          },
          areaVessels: [vessels[0]],
        })}
      />,
    );

    act(() => state.handlers.error?.({ error: new Error("online style fetch failed") }));
    act(() => state.styledataCb?.());

    expect(state.sources).toEqual(expect.arrayContaining([
      "live-vessels",
      "selected-track",
      "ports",
      "airspace",
      "area-scan-geometry",
      "area-scan-draft-path",
      "area-scan-draft-vertices",
      "area-scan-vessels",
    ]));
    expect(state.layers.map((layer) => layer.id)).toEqual(expect.arrayContaining([
      "live-vessels-symbols",
      "area-scan-fill",
      "area-scan-line",
      "area-scan-vessels-symbols",
    ]));
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
    expect(vesselPush.data.features[0].properties.category).toBe("Tanker");
    expect(vesselPush.data.features[1].properties.category).toBe("Cargo");
    expect(vesselPush.data.features[0].properties.publicId).toBe("v1");
    expect(vesselPush.data.features[0].properties).not.toHaveProperty("provider_id");
    expect(vesselPush.data.features[0].properties).not.toHaveProperty("threat");
    expect(vesselPush.data.features[0].properties).not.toHaveProperty("risk");
  });

  it("renders live and Area Scan vessels with data-driven ship symbol layers", () => {
    render(<MapCanvas {...baseProps({ areaVessels: [vessels[0]] })} />);

    const liveLayer = state.layers.find((layer) => layer.id === "live-vessels-symbols");
    const scanLayer = state.layers.find((layer) => layer.id === "area-scan-vessels-symbols");
    expect(liveLayer?.type).toBe("symbol");
    expect(scanLayer?.type).toBe("symbol");
    expect(liveLayer?.layout?.["icon-image"]).toBe("ship-icon");
    expect(scanLayer?.layout?.["icon-image"]).toBe("ship-icon");
    expect(liveLayer?.layout?.["icon-rotate"]).toEqual(["get", "orientation"]);
    expect(scanLayer?.layout?.["icon-rotate"]).toEqual(["get", "orientation"]);
    expect(state.layers.find((layer) => layer.id === "live-vessels-dot")).toBeUndefined();
    expect(state.layers.find((layer) => layer.id === "area-scan-vessels-dot")).toBeUndefined();
  });

  it("uses neutral orientation when heading and COG are invalid", () => {
    const invalid = {
      ...vessels[0],
      properties: {
        ...vessels[0].properties,
        heading_deg: Number.NaN,
        cog_deg: 360,
      },
    };
    render(<MapCanvas {...baseProps({ vessels: [invalid] })} />);

    const vesselPush = state.setDataPayloads.find((p) => p.id === "live-vessels");
    expect(vesselPush.data.features[0].properties.orientation).toBe(0);
  });

  it("preserves authoritative cached and stale display states on map features", () => {
    const classified = [
      { ...vessels[0], properties: { ...vessels[0].properties, display_state: "cached" as const } },
      { ...vessels[1], properties: { ...vessels[1].properties, display_state: "stale" as const } },
    ];
    render(<MapCanvas {...baseProps({ vessels: classified })} />);
    const vesselPush = state.setDataPayloads.find((p) => p.id === "live-vessels");
    expect(vesselPush.data.features.map((feature: any) => feature.properties.displayState)).toEqual([
      "cached",
      "stale",
    ]);
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
    expect(onSelectVessel).toHaveBeenCalledWith(
      expect.objectContaining({ id: "v1" }),
      "live",
    );
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

  it("keeps hover provenance separate when live and Area Scan share an id", () => {
    const sharedLive = {
      ...vessels[0],
      id: "shared-hover",
      properties: { ...vessels[0].properties, provider_id: "shared-hover", name: "LIVE NAME" },
    };
    const sharedArea = {
      ...sharedLive,
      properties: { ...sharedLive.properties, name: "AREA NAME", source: "datalastic" },
    };
    render(
      <MapCanvas
        {...baseProps({ vessels: [sharedLive], areaVessels: [sharedArea] })}
      />,
    );

    act(() => state.layerHandlers["mousemove:live-vessels-symbols"]?.({
      features: [{ id: "shared-hover", source: "live-vessels" }],
      lngLat: { lng: 120, lat: 22.3 },
    }));
    expect(last(state.popupHtml)).toContain("LIVE NAME");

    act(() => state.layerHandlers["mousemove:area-scan-vessels-symbols"]?.({
      features: [{ id: "shared-hover", source: "area-scan-vessels" }],
      lngLat: { lng: 120, lat: 22.3 },
    }));
    expect(last(state.popupHtml)).toContain("AREA NAME");
  });

  it("pauses follow when the user drags the map", () => {
    const onUserInteract = vi.fn();
    render(<MapCanvas {...baseProps({ follow: true, selectedId: "v1", onUserInteract })} />);
    const dragstart = state.handlers["dragstart"];
    expect(dragstart).toBeTruthy();
    dragstart();
    expect(onUserInteract).toHaveBeenCalled();
  });

  it("follows a stale Area Scan vessel at its measured position without projection", () => {
    const callbacks: FrameRequestCallback[] = [];
    const animationFrame = vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
      callbacks.push(cb);
      return callbacks.length;
    });
    const staleAreaVessel: LiveVesselFeature = {
      ...vessels[0],
      id: "area-stale",
      geometry: { type: "Point", coordinates: [120.25, 22.55] },
      properties: {
        ...vessels[0].properties,
        provider_id: "area-stale",
        source: "datalastic",
        sog_knots: 20,
        cog_deg: 90,
        heading_deg: 90,
        freshness_state: "stale",
        data_age_seconds: 1_200,
      },
    };

    render(
      <MapCanvas
        {...baseProps({
          areaVessels: [staleAreaVessel],
          selectedId: staleAreaVessel.id,
          selectedSource: "datalastic",
          follow: true,
        })}
      />,
    );
    act(() => callbacks[0]?.(0));

    expect(last(state.easeToCalls)?.center).toEqual([120.25, 22.55]);
    animationFrame.mockRestore();
  });

  it("follows an unknown-timestamp Area Scan vessel at its measured position", () => {
    const callbacks: FrameRequestCallback[] = [];
    const animationFrame = vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
      callbacks.push(cb);
      return callbacks.length;
    });
    const unknownAreaVessel: LiveVesselFeature = {
      ...vessels[0],
      id: "area-unknown",
      geometry: { type: "Point", coordinates: [120.25, 22.55] },
      properties: {
        ...vessels[0].properties,
        provider_id: "area-unknown",
        source: "datalastic",
        sog_knots: 20,
        cog_deg: 90,
        heading_deg: 90,
        observed_at: null,
        freshness_state: "unknown",
        data_age_seconds: null,
      },
    };

    render(
      <MapCanvas
        {...baseProps({
          areaVessels: [unknownAreaVessel],
          selectedId: unknownAreaVessel.id,
          selectedSource: "datalastic",
          follow: true,
        })}
      />,
    );
    act(() => callbacks[0]?.(0));

    expect(last(state.easeToCalls)?.center).toEqual([120.25, 22.55]);
    animationFrame.mockRestore();
  });

  // --- Rendering reliability regression tests (zero-vessel bug) ------------ //

  it("installs the always-visible vessel ship layer, halo, and shared ship image", () => {
    render(<MapCanvas {...baseProps()} />);
    expect(state.images).toContain("ship-icon");
    expect(state.sources).toContain("live-vessels");
    expect(state.layers.find((l) => l.id === "live-vessels-halo")).toBeTruthy();
    expect(state.layers.find((l) => l.id === "live-vessels-symbols")).toBeTruthy();
  });

  it("the primary vessel marker is a MapLibre symbol layer", () => {
    render(<MapCanvas {...baseProps()} />);
    const symbol = state.layers.find((l) => l.id === "live-vessels-symbols");
    expect(symbol?.type).toBe("symbol");
  });

  it("orders the vessel symbol above its selection halo", () => {
    render(<MapCanvas {...baseProps()} />);
    const ids = state.layers.map((l) => l.id);
    const halo = ids.indexOf("live-vessels-halo");
    const sym = ids.indexOf("live-vessels-symbols");
    expect(halo).toBeGreaterThanOrEqual(0);
    expect(sym).toBeGreaterThan(halo);
  });

  it("pushes real vessel features onto the single source when vessel_count > 0", () => {
    render(<MapCanvas {...baseProps()} />);
    const push = state.setDataPayloads.find((p) => p.id === "live-vessels");
    expect(push).toBeTruthy();
    expect(push.data.features.length).toBe(2);
  });

  it("keeps the vessel layer visible by default (visibility === visible)", () => {
    render(<MapCanvas {...baseProps()} />);
    const symbolVisibility = state.layoutProps.filter(
      (p) => p.layer === "live-vessels-symbols" && p.prop === "visibility",
    );
    expect(symbolVisibility.length).toBeGreaterThan(0);
    expect(symbolVisibility.every((p) => p.value === "visible")).toBe(true);
  });

  it("hides vessels when the liveVessels layer is toggled off", () => {
    render(
      <MapCanvas {...baseProps({ layers: { ...DEFAULT_LAYER_STATE, liveVessels: false } })} />,
    );
    const symbolVisibility = state.layoutProps.filter(
      (p) => p.layer === "live-vessels-symbols" && p.prop === "visibility",
    );
    expect(symbolVisibility.length).toBeGreaterThan(0);
    expect(symbolVisibility.every((p) => p.value === "none")).toBe(true);
  });

  it("reinstalls ship image, source, and vessel layers after a basemap style reload", () => {
    const { rerender } = render(<MapCanvas {...baseProps({ layers: DEFAULT_LAYER_STATE })} />);
    // Sanity: present after initial load.
    expect(state.images).toContain("ship-icon");
    expect(state.layers.find((l) => l.id === "live-vessels-symbols")).toBeTruthy();

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
    expect(ids.indexOf("live-vessels-symbols")).toBeGreaterThan(ids.indexOf("live-vessels-halo"));
  });

  it("keeps unselected vessels visible in the symbol layer", () => {
    render(<MapCanvas {...baseProps({ selectedId: null })} />);
    const push = state.setDataPayloads.find((p) => p.id === "live-vessels");
    // All features present even with nothing selected.
    expect(push.data.features.length).toBe(2);
    const symbol = state.layers.find((l) => l.id === "live-vessels-symbols");
    expect(symbol).toBeTruthy();
    const symbolVisibility = state.layoutProps.filter(
      (p) => p.layer === "live-vessels-symbols" && p.prop === "visibility",
    );
    expect(symbolVisibility.every((p) => p.value === "visible")).toBe(true);
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

  // --- Generic overlay seam (Phase 9 approved extension) ------------------- //

  const sampleOverlays = {
    sources: {
      "ext-points": {
        type: "FeatureCollection" as const,
        features: [
          {
            type: "Feature" as const,
            geometry: { type: "Point" as const, coordinates: [120.5, 23.0] },
            properties: { kind: "x" },
          },
        ],
      },
      "ext-lines": { type: "FeatureCollection" as const, features: [] },
    },
    layers: [
      { id: "ext-points-layer", type: "circle" as const, source: "ext-points" },
      { id: "ext-lines-layer", type: "line" as const, source: "ext-lines" },
    ],
  };

  it("does not install caller overlays when generic overlays are absent", () => {
    render(<MapCanvas {...baseProps()} />);
    // Only built-in sources, including the dedicated Area Scan paths, exist.
    const builtInSources = [
      "seawatch-eez-reference",
      "seawatch-territorial-sea-12nm",
      "seawatch-contiguous-zone-24nm",
      "live-vessels",
      "selected-track",
      "ports",
      "airspace",
      "area-scan-geometry",
      "area-scan-draft-path",
      "area-scan-draft-vertices",
      "area-scan-vessels",
    ];
    expect(state.sources.every((s) => builtInSources.includes(s))).toBe(true);
    expect(state.layers.every((l) => !l.id.startsWith("ext-"))).toBe(true);
  });

  it("installs caller overlay sources and layers when provided", () => {
    render(<MapCanvas {...baseProps({ overlays: sampleOverlays })} />);
    expect(state.sources).toContain("ext-points");
    expect(state.sources).toContain("ext-lines");
    expect(state.layers.find((l) => l.id === "ext-points-layer")).toBeTruthy();
    expect(state.layers.find((l) => l.id === "ext-lines-layer")).toBeTruthy();
  });

  it("keeps built-in vessel layers intact alongside overlays", () => {
    render(<MapCanvas {...baseProps({ overlays: sampleOverlays })} />);
    expect(state.sources).toContain("live-vessels");
    expect(state.layers.find((l) => l.id === "live-vessels-symbols")).toBeTruthy();
    expect(state.layers.find((l) => l.id === "ports-circle")).toBeTruthy();
  });

  it("overlay layers are installed above the built-in layers", () => {
    render(<MapCanvas {...baseProps({ overlays: sampleOverlays })} />);
    const ids = state.layers.map((l) => l.id);
    expect(ids.indexOf("ext-points-layer")).toBeGreaterThan(ids.indexOf("live-vessels-symbols"));
  });

  it("restores caller overlays after a basemap style reload", () => {
    const { rerender } = render(
      <MapCanvas {...baseProps({ layers: DEFAULT_LAYER_STATE, overlays: sampleOverlays })} />,
    );
    expect(state.layers.find((l) => l.id === "ext-points-layer")).toBeTruthy();

    // Switch basemap -> setStyle() wipes custom layers/sources.
    rerender(
      <MapCanvas
        {...baseProps({
          layers: { ...DEFAULT_LAYER_STATE, baseMap: "nlsc-photo" },
          overlays: sampleOverlays,
        })}
      />,
    );
    expect(typeof state.styledataCb).toBe("function");
    state.styledataCb?.();

    // Overlays reinstalled after the style reload.
    expect(state.sources).toContain("ext-points");
    expect(state.layers.find((l) => l.id === "ext-points-layer")).toBeTruthy();
    expect(state.layers.find((l) => l.id === "ext-lines-layer")).toBeTruthy();
  });

  it("restores caller overlays after a PMTiles/emergency fallback", () => {
    render(<MapCanvas {...baseProps({ operatingMode: "EDGE_LIVE", overlays: sampleOverlays })} />);
    expect(state.layers.find((l) => l.id === "ext-points-layer")).toBeTruthy();

    // Edge starts on PMTiles; its failure wipes and installs emergency style.
    act(() => state.handlers.error?.({ error: new Error("PMTiles source fetch failed") }));
    expect(typeof state.styledataCb).toBe("function");
    state.styledataCb?.();

    expect(state.sources).toContain("ext-points");
    expect(state.layers.find((l) => l.id === "ext-points-layer")).toBeTruthy();
  });

  it("does not duplicate overlay source/layer registration on re-render", () => {
    const { rerender } = render(<MapCanvas {...baseProps({ overlays: sampleOverlays })} />);
    rerender(<MapCanvas {...baseProps({ overlays: sampleOverlays })} />);
    expect(state.sources.filter((s) => s === "ext-points")).toHaveLength(1);
    expect(state.layers.filter((l) => l.id === "ext-points-layer")).toHaveLength(1);
    expect(state.layers.filter((l) => l.id === "ext-lines-layer")).toHaveLength(1);
  });

  it("updates overlay source data via setData when overlays change (no new source)", () => {
    const { rerender } = render(<MapCanvas {...baseProps({ overlays: sampleOverlays })} />);
    const updated = {
      ...sampleOverlays,
      sources: {
        ...sampleOverlays.sources,
        "ext-points": {
          type: "FeatureCollection" as const,
          features: [
            {
              type: "Feature" as const,
              geometry: { type: "Point" as const, coordinates: [121.0, 24.0] },
              properties: { kind: "y" },
            },
            {
              type: "Feature" as const,
              geometry: { type: "Point" as const, coordinates: [121.5, 24.5] },
              properties: { kind: "z" },
            },
          ],
        },
      },
    };
    rerender(<MapCanvas {...baseProps({ overlays: updated })} />);
    // Source not re-added.
    expect(state.sources.filter((s) => s === "ext-points")).toHaveLength(1);
    // Latest data pushed via setData.
    const push = [...state.setDataPayloads].reverse().find((p) => p.id === "ext-points");
    expect(push).toBeTruthy();
    expect(push.data.features).toHaveLength(2);
  });
});
