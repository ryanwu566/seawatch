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

  it("uses the online vector style before local and bundled fallbacks", () => {
    expect(selectOfflineBasemap(true, "healthy")).toBe("online");
    expect(selectOfflineBasemap(true, "online_failed")).toBe("pmtiles");
    expect(selectOfflineBasemap(true, "pmtiles_failed")).toBe("emergency");
  });

  it("starts offline operation on PMTiles and retains the emergency fallback", () => {
    expect(selectOfflineBasemap(false, "healthy")).toBe("pmtiles");
    expect(selectOfflineBasemap(false, "online_failed")).toBe("pmtiles");
    expect(selectOfflineBasemap(false, "pmtiles_failed")).toBe("emergency");
  });
});
