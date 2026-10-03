import { describe, expect, it } from "vitest";
import {
  nlscStyle,
  OPENFREEMAP_LIBERTY_STYLE_URL,
  NLSC_ATTRIBUTION,
  COMMERCIAL_PORTS,
  portsGeoJson,
  airspaceGeoJson,
  TAIWAN_BBOX,
} from "./taiwanMap";

describe("Taiwan NLSC basemap config", () => {
  it("uses OpenFreeMap Liberty as the primary online vector basemap", () => {
    expect(OPENFREEMAP_LIBERTY_STYLE_URL).toBe(
      "https://tiles.openfreemap.org/styles/liberty",
    );
  });

  it("builds an e-Map raster style with NLSC attribution", () => {
    const style = nlscStyle("nlsc-emap");
    expect(style.version).toBe(8);
    const source = (style.sources as any)["nlsc-base"];
    expect(source.type).toBe("raster");
    expect(source.tiles[0]).toContain("wmts.nlsc.gov.tw");
    expect(source.tiles[0]).toContain("EMAP");
    expect(source.attribution).toBe(NLSC_ATTRIBUTION);
  });

  it("builds an orthophoto raster style", () => {
    const style = nlscStyle("nlsc-photo");
    const source = (style.sources as any)["nlsc-base"];
    expect(source.tiles[0]).toContain("PHOTO2");
  });
});

describe("public maritime ports", () => {
  it("includes Keelung, Taichung, Kaohsiung", () => {
    const ids = COMMERCIAL_PORTS.map((p) => p.id);
    expect(ids).toContain("keelung");
    expect(ids).toContain("taichung");
    expect(ids).toContain("kaohsiung");
  });

  it("emits valid GeoJSON points within the Taiwan bbox", () => {
    const fc = portsGeoJson();
    expect(fc.type).toBe("FeatureCollection");
    for (const f of fc.features) {
      const [lon, lat] = (f.geometry as GeoJSON.Point).coordinates;
      expect(lon).toBeGreaterThanOrEqual(TAIWAN_BBOX.minLon);
      expect(lon).toBeLessThanOrEqual(TAIWAN_BBOX.maxLon);
      expect(lat).toBeGreaterThanOrEqual(TAIWAN_BBOX.minLat);
      expect(lat).toBeLessThanOrEqual(TAIWAN_BBOX.maxLat);
    }
  });
});

describe("public airspace context", () => {
  it("provides polygon context only (no live tracks)", () => {
    const fc = airspaceGeoJson();
    expect(fc.features.length).toBeGreaterThan(0);
    for (const f of fc.features) {
      expect(f.geometry.type).toBe("Polygon");
      // Context layers are labeled; they never carry live/position data.
      expect(f.properties).not.toHaveProperty("sog");
      expect(f.properties).not.toHaveProperty("mmsi");
    }
  });
});
