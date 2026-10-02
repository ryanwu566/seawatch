import { expect, test } from "@playwright/test";
import path from "node:path";

test("records bounded MapLibre GeoJSON update timing", async ({ page }, testInfo) => {
  await page.setContent(
    '<div id="map" style="position:fixed;inset:0;width:1024px;height:768px"></div>',
  );
  await page.addScriptTag({
    path: path.resolve(process.cwd(), "node_modules/maplibre-gl/dist/maplibre-gl.js"),
  });

  const result = await page.evaluate(async () => {
    const maplibre = (window as any).maplibregl;
    const map = new maplibre.Map({
      container: "map",
      style: {
        version: 8,
        sources: {},
        layers: [
          { id: "background", type: "background", paint: { "background-color": "#071927" } },
        ],
      },
      center: [120.9, 23.6],
      zoom: 6,
      attributionControl: false,
    });
    await new Promise<void>((resolve) => map.once("load", resolve));
    map.addSource("generated-vessels", {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
    });
    map.addLayer({
      id: "generated-vessels-dot",
      type: "circle",
      source: "generated-vessels",
      paint: { "circle-radius": 2, "circle-color": "#38bdf8" },
    });
    const source = map.getSource("generated-vessels");
    const makeData = (offset: number) => ({
      type: "FeatureCollection",
      features: Array.from({ length: 1_000 }, (_, index) => ({
        type: "Feature",
        id: `anonymous-${index}`,
        geometry: {
          type: "Point",
          coordinates: [119 + ((index * 17) % 400) / 100 + offset, 21.8 + ((index * 13) % 350) / 100],
        },
        properties: { displayState: "live" },
      })),
    });
    const samples: number[] = [];
    for (let index = 0; index < 33; index += 1) {
      performance.mark("map-update-start");
      source.setData(makeData(index / 100_000));
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
      performance.mark("map-update-end");
      performance.measure("map-update", "map-update-start", "map-update-end");
      const duration = performance.getEntriesByName("map-update").at(-1)?.duration ?? 0;
      if (index >= 3) samples.push(duration);
      performance.clearMarks();
      performance.clearMeasures();
    }
    map.remove();
    const sorted = [...samples].sort((a, b) => a - b);
    const nearest = (percent: number) =>
      sorted[Math.max(0, Math.ceil((percent / 100) * sorted.length) - 1)];
    return {
      metric: "GeoJSON setData call through next animation frame",
      unit: "ms",
      feature_count: 1_000,
      warmup_samples: 3,
      sample_count: samples.length,
      median: nearest(50),
      p95: nearest(95),
      max: Math.max(...samples),
      caveat: "Browser Performance API timing; not a network latency or completed render metric.",
      user_agent: navigator.userAgent,
    };
  });

  expect(result.sample_count).toBe(30);
  expect(result.max).toBeGreaterThan(0);
  await testInfo.attach("map-performance.json", {
    body: JSON.stringify(result, null, 2),
    contentType: "application/json",
  });
  console.log(`MAP_PERFORMANCE ${JSON.stringify(result)}`);
});
