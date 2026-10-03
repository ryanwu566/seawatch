import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { DICTIONARIES } from "../i18n/dictionaries";

const mapState: {
  handlers: Record<string, (event?: any) => void>;
  layerHandlers: Record<string, (event?: any) => void>;
  layers: Array<{ id: string; type: string }>;
  sources: string[];
  doubleClickDisabled: boolean;
  dragPanDisabled: boolean;
  canvas: HTMLCanvasElement | null;
  capturedPointerId: number | null;
} = {
  handlers: {},
  layerHandlers: {},
  layers: [],
  sources: [],
  doubleClickDisabled: false,
  dragPanDisabled: false,
  canvas: null,
  capturedPointerId: null,
};

vi.mock("maplibre-gl", () => {
  class FakeMap {
    dragPan = {
      disable: () => { mapState.dragPanDisabled = true; },
      enable: () => { mapState.dragPanDisabled = false; },
    };
    doubleClickZoom = {
      disable: () => { mapState.doubleClickDisabled = true; },
      enable: () => { mapState.doubleClickDisabled = false; },
    };

    constructor(options: Record<string, unknown>) {
      const canvas = document.createElement("canvas");
      canvas.setPointerCapture = (pointerId: number) => {
        mapState.capturedPointerId = pointerId;
      };
      canvas.releasePointerCapture = (pointerId: number) => {
        if (mapState.capturedPointerId === pointerId) mapState.capturedPointerId = null;
      };
      canvas.hasPointerCapture = (pointerId: number) => mapState.capturedPointerId === pointerId;
      const container = options.container;
      if (container instanceof HTMLElement) container.appendChild(canvas);
      mapState.canvas = canvas;
    }

    on(event: string, layerOrCallback: any, callback?: any) {
      if (typeof layerOrCallback === "function") {
        mapState.handlers[event] = layerOrCallback;
        if (event === "load") layerOrCallback();
        return;
      }
      const layerIds = Array.isArray(layerOrCallback) ? layerOrCallback : [layerOrCallback];
      for (const layerId of layerIds) mapState.layerHandlers[`${event}:${layerId}`] = callback;
    }
    once(_event: string, callback?: any) {
      callback?.();
    }
    addControl() {}
    hasImage() { return false; }
    addImage() {}
    addSource(id: string) { mapState.sources.push(id); }
    getSource(id: string) {
      return mapState.sources.includes(id) ? { setData: () => {} } : undefined;
    }
    addLayer(layer: { id: string; type: string }) {
      mapState.layers.push({ id: layer.id, type: layer.type });
    }
    getLayer(id: string) { return mapState.layers.find((layer) => layer.id === id); }
    getStyle() { return { layers: mapState.layers }; }
    setStyle() {
      mapState.layers = [];
      mapState.sources = [];
    }
    setLayoutProperty() {}
    setFeatureState() {}
    flyTo() {}
    easeTo() {}
    fitBounds() {}
    getZoom() { return 7; }
    getCenter() { return { lng: 120.9, lat: 23.6 }; }
    getBounds() {
      return {
        getSouth: () => 21.5,
        getWest: () => 118,
        getNorth: () => 26.5,
        getEast: () => 123.5,
      };
    }
    getCanvas() { return mapState.canvas!; }
    queryRenderedFeatures() { return []; }
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
    setLngLat() { return this; }
    setHTML() { return this; }
    addTo() { return this; }
    remove() {}
  }

  return {
    default: { Map: FakeMap, NavigationControl: class {}, Popup: FakePopup },
    addProtocol: vi.fn(),
  };
});
vi.mock("pmtiles", () => ({ Protocol: class { tile() {} } }));
vi.mock("maplibre-gl/dist/maplibre-gl.css", () => ({}));
vi.mock("../lib/shipIcon", () => ({
  makeShipIcon: () => ({ width: 48, height: 48, data: new Uint8ClampedArray(48 * 48 * 4) }),
}));

import { I18nProvider } from "../i18n/I18nContext";
import { LiveDashboard } from "./LiveDashboard";

const expectedPolygon: GeoJSON.Polygon = {
  type: "Polygon",
  coordinates: [[[120, 22], [121, 22], [121, 23], [120, 22]]],
};

const expectedRectangle: GeoJSON.Polygon = {
  type: "Polygon",
  coordinates: [[[120, 22], [121, 22], [121, 23], [120, 23], [120, 22]]],
};

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function requestPath(input: RequestInfo | URL): string {
  const raw = input instanceof Request ? input.url : String(input);
  return new URL(raw, "http://localhost").pathname;
}

function installBackendFetchMock() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const path = requestPath(input);
    if (path === "/live/vessels") {
      return jsonResponse({
        type: "FeatureCollection",
        attribution: "Open Waters AIS",
        server_timestamp: "2026-10-03T00:00:00Z",
        data_timestamp: "2026-10-03T00:00:00Z",
        vessel_count: 0,
        features: [],
      });
    }
    if (path === "/live/health") {
      return jsonResponse({
        status: "online",
        provider: "datalastic",
        connected: true,
        subscribed: false,
        last_message_at: null,
        message_age_seconds: null,
        vessel_count: 0,
        reconnect_attempts: 0,
        last_error: null,
        live_ingest_enabled: false,
        area_scan_autoauth_loopback_enabled: true,
        provider_status: {
          provider: "datalastic",
          configured: true,
          reachable: true,
          key_status: "valid",
          addons: true,
          requests_remaining: 100,
          rate_limit_remaining: 10,
          last_success_at: "2026-10-03T00:00:00Z",
          last_error_category: null,
        },
      });
    }
    if (path === "/resilience/status") {
      return jsonResponse({
        mode: "NO_LIVE_SOURCE",
        coverage: "none",
        simulated: false,
        internet_available: true,
        power_mode: "external",
        cloud: {
          source: "open_waters",
          fresh: false,
          message_age_seconds: null,
          vessel_count: 0,
          connected: false,
          input_kind: null,
        },
        edge: {
          source: "edge_ais",
          fresh: false,
          message_age_seconds: null,
          vessel_count: 0,
          connected: false,
          input_kind: "disabled",
        },
      });
    }
    if (path === "/live/area-scan/session") {
      return jsonResponse({ authenticated: true, expires_in_seconds: 900 });
    }
    if (path === "/live/area-scan/plan") {
      return jsonResponse({
        area_square_km: 123.45,
        provider_queries: 1,
        max_provider_queries: 16,
        can_scan: true,
        reason: null,
      });
    }
    if (path === "/live/area-scan") {
      return jsonResponse({
        source: "datalastic",
        scanned_at: "2026-10-03T02:00:00Z",
        cached: false,
        scan: { geometry_type: "Polygon", provider_queries: 1 },
        total: 0,
        vessels: [],
      });
    }
    throw new Error(`Unexpected request: ${path}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderDashboard() {
  return render(
    <I18nProvider>
      <LiveDashboard />
    </I18nProvider>,
  );
}

function clickMap(lng: number, lat: number, x = lng * 100, y = lat * 100) {
  act(() => mapState.handlers.click?.({ lngLat: { lng, lat }, point: { x, y } }));
}

async function openAuthenticatedPolygonMode() {
  const t = DICTIONARIES.en;
  fireEvent.click(screen.getByRole("button", { name: t.areaScan }));
  expect(await screen.findByText(t.areaScanAuthenticated)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: t.areaScanPolygon }));
  await waitFor(() => expect(mapState.doubleClickDisabled).toBe(true));
  return t;
}

async function openAuthenticatedRectangleMode() {
  const t = DICTIONARIES.en;
  fireEvent.click(screen.getByRole("button", { name: t.areaScan }));
  expect(await screen.findByText(t.areaScanAuthenticated)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: t.areaScanRectangle }));
  await waitFor(() => expect(mapState.dragPanDisabled).toBe(true));
  return t;
}

function dragRectangle(
  start: [number, number],
  end: [number, number],
  pointerId = 17,
) {
  fireCanvasPointer("pointerdown", {
    pointerId,
    button: 0,
    clientX: start[0] * 100,
    clientY: start[1] * 100,
  });
  fireCanvasPointer("pointermove", {
    pointerId,
    clientX: end[0] * 100,
    clientY: end[1] * 100,
  });
  fireCanvasPointer("pointerup", {
    pointerId,
    button: 0,
    clientX: end[0] * 100,
    clientY: end[1] * 100,
  });
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
  fireEvent(mapState.canvas!, event);
}

function areaScanPosts(fetchMock: ReturnType<typeof vi.fn>) {
  return fetchMock.mock.calls.filter(([input, init]) =>
    requestPath(input as RequestInfo | URL) === "/live/area-scan" &&
    (init as RequestInit | undefined)?.method === "POST",
  );
}

describe("LiveDashboard Area Scan drawing flow", () => {
  beforeEach(() => {
    mapState.handlers = {};
    mapState.layerHandlers = {};
    mapState.layers = [];
    mapState.sources = [];
    mapState.doubleClickDisabled = false;
    mapState.dragPanDisabled = false;
    mapState.canvas = null;
    mapState.capturedPointerId = null;
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it.each([
    ["double-click", () => act(() => mapState.handlers.dblclick?.({ preventDefault: vi.fn() }))],
    ["starting-vertex click", () => clickMap(120.02, 22.02, 12006, 2208)],
  ])("commits a polygon on %s and sends one backend scan", async (_label, finish) => {
    const fetchMock = installBackendFetchMock();
    renderDashboard();
    const t = await openAuthenticatedPolygonMode();

    clickMap(120, 22);
    clickMap(121, 22);
    clickMap(121, 23);
    expect(screen.getByRole("button", { name: t.scanArea })).toBeDisabled();
    expect(areaScanPosts(fetchMock)).toHaveLength(0);

    finish();
    await waitFor(() => expect(screen.getByRole("button", { name: t.scanArea })).toBeEnabled());
    expect(mapState.doubleClickDisabled).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: t.scanArea }));

    await waitFor(() => expect(areaScanPosts(fetchMock)).toHaveLength(1));
    const [, request] = areaScanPosts(fetchMock)[0];
    expect(JSON.parse(String((request as RequestInit).body))).toEqual({ geometry: expectedPolygon });
    expect(fetchMock.mock.calls.every(([input]) => !String(input).includes("api.datalastic.com")))
      .toBe(true);

    fireEvent.click(screen.getByRole("button", { name: t.clearAreaScan }));
    expect(screen.getByRole("button", { name: t.scanArea })).toBeDisabled();
    expect(areaScanPosts(fetchMock)).toHaveLength(1);
  });

  it("keeps a preview and Escape cancellation from enabling Scan Area", async () => {
    const fetchMock = installBackendFetchMock();
    renderDashboard();
    const t = await openAuthenticatedPolygonMode();

    clickMap(120, 22);
    clickMap(121, 22);
    clickMap(121, 23);
    expect(screen.getByRole("button", { name: t.scanArea })).toBeDisabled();

    fireEvent.keyDown(window, { key: "Escape" });

    expect(screen.getByRole("button", { name: t.scanArea })).toBeDisabled();
    expect(mapState.doubleClickDisabled).toBe(false);
    expect(areaScanPosts(fetchMock)).toHaveLength(0);
  });

  it("commits a canvas rectangle drag and sends exactly one same-origin scan", async () => {
    const fetchMock = installBackendFetchMock();
    renderDashboard();
    const t = await openAuthenticatedRectangleMode();

    expect(mapState.canvas?.style.cursor).toBe("crosshair");
    dragRectangle([121, 23], [120, 22]);

    await waitFor(() => expect(screen.getByRole("button", { name: t.scanArea })).toBeEnabled());
    expect(mapState.dragPanDisabled).toBe(false);
    expect(mapState.capturedPointerId).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: t.scanArea }));

    await waitFor(() => expect(areaScanPosts(fetchMock)).toHaveLength(1));
    const [, request] = areaScanPosts(fetchMock)[0];
    expect(JSON.parse(String((request as RequestInit).body))).toEqual({
      geometry: expectedRectangle,
    });
    expect(fetchMock.mock.calls.every(([input]) => !String(input).includes("api.datalastic.com")))
      .toBe(true);

    fireEvent.click(screen.getByRole("button", { name: t.clearAreaScan }));
    expect(screen.getByRole("button", { name: t.scanArea })).toBeDisabled();
    expect(areaScanPosts(fetchMock)).toHaveLength(1);
  });

  it("cancels a rectangle draft on Escape and restores map panning", async () => {
    const fetchMock = installBackendFetchMock();
    renderDashboard();
    const t = await openAuthenticatedRectangleMode();

    fireCanvasPointer("pointerdown", {
      pointerId: 23,
      button: 0,
      clientX: 12000,
      clientY: 2200,
    });
    fireCanvasPointer("pointermove", {
      pointerId: 23,
      clientX: 12100,
      clientY: 2300,
    });
    fireEvent.keyDown(window, { key: "Escape" });

    expect(screen.getByRole("button", { name: t.scanArea })).toBeDisabled();
    expect(mapState.dragPanDisabled).toBe(false);
    expect(mapState.capturedPointerId).toBeNull();
    expect(areaScanPosts(fetchMock)).toHaveLength(0);
  });

  it("does not enable Scan Area for a zero-area rectangle drag", async () => {
    const fetchMock = installBackendFetchMock();
    renderDashboard();
    const t = await openAuthenticatedRectangleMode();

    dragRectangle([120, 22], [120, 22], 29);

    expect(screen.getByRole("button", { name: t.scanArea })).toBeDisabled();
    expect(mapState.dragPanDisabled).toBe(true);
    expect(areaScanPosts(fetchMock)).toHaveLength(0);
  });
});
