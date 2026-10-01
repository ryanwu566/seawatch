// Resolves a vessel's display orientation from AIS fields, rejecting the
// well-known "not available" sentinel values so we never rotate a marker to a
// meaningless angle.
//
//   Heading (HDG): 511 = not available (valid 0..359).
//   Course over ground (COG): 360.0 = not available (valid 0..359.9).
//
// Priority: true heading -> COG -> null (caller falls back to 0, i.e. north).

const HEADING_UNAVAILABLE = 511;
const COG_UNAVAILABLE = 360;

function isValidAngle(value: number | null | undefined): value is number {
  return value !== null && value !== undefined && Number.isFinite(value) && value >= 0 && value < 360;
}

/**
 * Return a usable orientation in [0, 360) from heading, then COG. Returns null
 * when neither is a valid bearing (sentinel values are treated as unavailable).
 */
export function normalizeOrientation(
  headingDeg: number | null | undefined,
  cogDeg: number | null | undefined,
): number | null {
  if (headingDeg !== HEADING_UNAVAILABLE && isValidAngle(headingDeg)) {
    return headingDeg;
  }
  if (cogDeg !== COG_UNAVAILABLE && isValidAngle(cogDeg)) {
    return cogDeg;
  }
  return null;
}
