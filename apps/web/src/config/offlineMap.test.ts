import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ addProtocol: vi.fn(), tile: vi.fn() }));

vi.mock("maplibre-gl", () => ({ addProtocol: mocks.addProtocol }));
vi.mock("pmtiles", () => ({ Protocol: class { tile = mocks.tile; } }));

import {
  PMTILES_ARCHIVE_URL,
  emergencyStyle,
  pmtilesStyle,
  registerPmtilesProtocol,
  selectOfflineBasemap,
} from "./offlineMap";

describe("offline map configuration", () => {
  beforeEach(() => mocks.addProtocol.mockClear());

  it("registers the PMTiles protocol once and uses one fixed relative archive", () => {
    registerPmtilesProtocol();
    registerPmtilesProtocol();
    expect(mocks.addProtocol).toHaveBeenCalledTimes(1);
    expect(mocks.addProtocol).toHaveBeenCalledWith("pmtiles", expect.any(Function));
    expect(PMTILES_ARCHIVE_URL).toBe("/offline/taiwan.pmtiles");
    expect(JSON.stringify(pmtilesStyle())).toContain("pmtiles:///offline/taiwan.pmtiles");
  });

  it("contains a guaranteed emergency style with no remote dependency", () => {
    const serialized = JSON.stringify(emergencyStyle());
    expect(serialized).toContain("FeatureCollection");
    expect(serialized).toContain("Taiwan");
    expect(serialized).not.toMatch(/https?:|glyphs|sprite|remote|cdn/i);
  });

  it("keeps Cloud Live on NLSC after online basemap failures", () => {
    expect(selectOfflineBasemap("CLOUD_LIVE", "healthy")).toBe("nlsc");
    expect(selectOfflineBasemap("CLOUD_LIVE", "nlsc_failed")).toBe("nlsc");
    expect(selectOfflineBasemap("CLOUD_LIVE", "pmtiles_failed")).toBe("nlsc");
  });

  it.each(["EDGE_LIVE", "EDGE_REPLAY", "NO_LIVE_SOURCE"] as const)(
    "keeps %s on the PMTiles then emergency fallback chain",
    (mode) => {
      expect(selectOfflineBasemap(mode, "healthy")).toBe("pmtiles");
      expect(selectOfflineBasemap(mode, "nlsc_failed")).toBe("pmtiles");
      expect(selectOfflineBasemap(mode, "pmtiles_failed")).toBe("emergency");
    },
  );

  it("preserves the existing NLSC then offline fallback chain for Offline Demo", () => {
    expect(selectOfflineBasemap("OFFLINE_DEMO", "healthy")).toBe("nlsc");
    expect(selectOfflineBasemap("OFFLINE_DEMO", "nlsc_failed")).toBe("pmtiles");
    expect(selectOfflineBasemap("OFFLINE_DEMO", "pmtiles_failed")).toBe("emergency");
  });
});
