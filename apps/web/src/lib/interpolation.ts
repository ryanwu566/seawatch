// Frontend visual interpolation ("dead reckoning") for smooth ship motion
// between real AIS fixes. This NEVER changes the measured data: it only advances
// a VISUAL marker position based on the last measured position, speed over
// ground, and course, then reconciles to each new real fix when it arrives.
//
// The UI must always distinguish a measured AIS fix from this visual position.

export interface MeasuredFix {
  /** Measured longitude/latitude of the last real AIS fix (EPSG:4326). */
  lon: number;
  lat: number;
  /** Speed over ground in knots (null when unknown -> no visual advance). */
  sogKnots: number | null;
  /** Course over ground / heading in degrees used for projection direction. */
  courseDeg: number | null;
  /** Epoch ms when this fix was observed upstream. */
  observedAtMs: number;
}

const EARTH_RADIUS_M = 6_371_000;
const KNOTS_TO_M_PER_S = 0.514444;
// Cap how far we visually dead-reckon past the last fix, so a lost vessel does
// not drift forever. After this, the marker holds at its last projected point.
const MAX_PROJECTION_SECONDS = 120;

function toRad(deg: number): number {
  return (deg * Math.PI) / 180;
}
function toDeg(rad: number): number {
  return (rad * 180) / Math.PI;
}

/**
 * Project a measured fix forward by `elapsedSeconds` along its course at its
 * speed, returning the visual [lon, lat]. Returns the measured position
 * unchanged when speed or course is unknown or speed is ~0.
 */
export function projectPosition(
  fix: MeasuredFix,
  nowMs: number,
): { lon: number; lat: number; interpolated: boolean } {
  if (!Number.isFinite(fix.observedAtMs)) {
    return { lon: fix.lon, lat: fix.lat, interpolated: false };
  }
  const sog = fix.sogKnots ?? 0;
  const course = fix.courseDeg;
  const elapsed = Math.min(
    MAX_PROJECTION_SECONDS,
    Math.max(0, (nowMs - fix.observedAtMs) / 1000),
  );
  if (sog <= 0.1 || course === null || elapsed <= 0) {
    return { lon: fix.lon, lat: fix.lat, interpolated: false };
  }
  const distanceM = sog * KNOTS_TO_M_PER_S * elapsed;
  const angular = distanceM / EARTH_RADIUS_M; // angular distance in radians
  const bearing = toRad(course);
  const lat1 = toRad(fix.lat);
  const lon1 = toRad(fix.lon);

  const lat2 = Math.asin(
    Math.sin(lat1) * Math.cos(angular) +
      Math.cos(lat1) * Math.sin(angular) * Math.cos(bearing),
  );
  const lon2 =
    lon1 +
    Math.atan2(
      Math.sin(bearing) * Math.sin(angular) * Math.cos(lat1),
      Math.cos(angular) - Math.sin(lat1) * Math.sin(lat2),
    );

  return { lon: toDeg(lon2), lat: toDeg(lat2), interpolated: true };
}

/**
 * Smoothly reconcile a currently-displayed visual position toward a target
 * (used when a fresh real fix arrives) by linear interpolation. `alpha` is the
 * fraction to move this frame (0..1). Small alpha => smooth glide, avoids
 * teleporting the marker.
 */
export function reconcile(
  current: { lon: number; lat: number },
  target: { lon: number; lat: number },
  alpha: number,
): { lon: number; lat: number } {
  const a = Math.max(0, Math.min(1, alpha));
  return {
    lon: current.lon + (target.lon - current.lon) * a,
    lat: current.lat + (target.lat - current.lat) * a,
  };
}
