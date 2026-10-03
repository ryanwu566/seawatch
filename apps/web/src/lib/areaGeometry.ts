type Position = [number, number];

function positionsEqual(left: Position, right: Position): boolean {
  return left[0] === right[0] && left[1] === right[1];
}

function cross(a: Position, b: Position, c: Position): number {
  return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
}

function onSegment(a: Position, b: Position, point: Position): boolean {
  return Math.abs(cross(a, b, point)) <= Number.EPSILON &&
    point[0] >= Math.min(a[0], b[0]) && point[0] <= Math.max(a[0], b[0]) &&
    point[1] >= Math.min(a[1], b[1]) && point[1] <= Math.max(a[1], b[1]);
}

function segmentsIntersect(a: Position, b: Position, c: Position, d: Position): boolean {
  const abC = cross(a, b, c);
  const abD = cross(a, b, d);
  const cdA = cross(c, d, a);
  const cdB = cross(c, d, b);
  if (((abC > 0 && abD < 0) || (abC < 0 && abD > 0)) &&
      ((cdA > 0 && cdB < 0) || (cdA < 0 && cdB > 0))) return true;
  return (abC === 0 && onSegment(a, b, c)) ||
    (abD === 0 && onSegment(a, b, d)) ||
    (cdA === 0 && onSegment(c, d, a)) ||
    (cdB === 0 && onSegment(c, d, b));
}

function selfIntersects(points: Position[]): boolean {
  const count = points.length;
  for (let left = 0; left < count; left += 1) {
    const leftNext = (left + 1) % count;
    for (let right = left + 1; right < count; right += 1) {
      const rightNext = (right + 1) % count;
      if (left === right || leftNext === right || rightNext === left) continue;
      if (segmentsIntersect(points[left], points[leftNext], points[right], points[rightNext])) {
        return true;
      }
    }
  }
  return false;
}

export function finalizePolygonPoints(
  points: ReadonlyArray<readonly [number, number]>,
): GeoJSON.Polygon | null {
  const normalized: Position[] = [];
  for (const [longitude, latitude] of points) {
    if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) return null;
    if (longitude < -180 || longitude > 180 || latitude < -90 || latitude > 90) return null;
    const position: Position = [longitude, latitude];
    if (!normalized.length || !positionsEqual(normalized[normalized.length - 1], position)) {
      normalized.push(position);
    }
  }
  while (normalized.length > 1 && positionsEqual(normalized[normalized.length - 1], normalized[0])) {
    normalized.pop();
  }
  if (new Set(normalized.map(([longitude, latitude]) => `${longitude},${latitude}`)).size < 3) {
    return null;
  }
  const twiceArea = normalized.reduce((area, point, index) => {
    const next = normalized[(index + 1) % normalized.length];
    return area + point[0] * next[1] - next[0] * point[1];
  }, 0);
  if (Math.abs(twiceArea) <= Number.EPSILON || selfIntersects(normalized)) return null;
  return {
    type: "Polygon",
    coordinates: [[...normalized, [...normalized[0]] as Position]],
  };
}
