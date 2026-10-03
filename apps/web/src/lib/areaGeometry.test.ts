import { describe, expect, it } from "vitest";
import { finalizePolygonPoints } from "./areaGeometry";

describe("Area Scan polygon finalization", () => {
  it("creates one exactly closed GeoJSON ring", () => {
    expect(finalizePolygonPoints([[120, 22], [121, 22], [121, 23]])).toEqual({
      type: "Polygon",
      coordinates: [[[120, 22], [121, 22], [121, 23], [120, 22]]],
    });
  });

  it("removes duplicate closing coordinates before closing once", () => {
    expect(finalizePolygonPoints([
      [120, 22], [121, 22], [121, 23], [120, 22], [120, 22],
    ])?.coordinates[0]).toEqual([[120, 22], [121, 22], [121, 23], [120, 22]]);
  });

  it.each([
    ["fewer than three unique vertices", [[120, 22], [121, 22], [120, 22]]],
    ["zero area", [[120, 22], [121, 22], [122, 22]]],
    ["non-finite coordinates", [[120, 22], [121, 22], [Number.NaN, 23]]],
    ["self-intersection", [[120, 22], [121, 23], [120, 23], [121, 22]]],
  ] as const)("rejects %s", (_label, points) => {
    expect(finalizePolygonPoints(points)).toBeNull();
  });
});
