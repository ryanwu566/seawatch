"""Route Deviation Detection (``route-deviation-1``).

A small, deterministic, dependency-free (beyond the existing trajectory stack)
evidence generator. It builds a *historical median corridor* from several past
AIS tracks of the same origin→destination route, then measures how far a current
track departs from that corridor.

Design guarantees:

* **No ML, no classifier, no judgement.** Output is a geometric deviation plus
  explainable evidence for human review. It never emits "suspicious", "threat",
  "dangerous", or "illegal".
* **Provenance-first.** Positions/courses are ``observed``; the baseline and
  cross-track metrics are ``derived``; when there is not enough history the
  output is ``unknown`` and the baseline is never fabricated.
* **Deterministic.** Same inputs ⇒ identical output. Pure functions; no I/O.

It reuses :mod:`apps.api.seawatch.trajectories.geodesy` (WGS84 geodesic
distances) and the Phase 1 observation column contract; it adds no new
architecture and touches no live/edge/resilience/logistics code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Literal, Sequence

from .geodesy import circular_difference_degrees, geodesic_distance_m

Provenance = Literal["official", "observed", "derived", "unknown"]
Confidence = Literal["HIGH", "MEDIUM", "LOW"]

# --- Documented thresholds (deterministic constants, surfaced in assumptions) -- #
#: Minimum number of historical tracks required to build a trustworthy baseline.
MIN_BASELINE_TRACKS = 5
#: Number of equal along-track anchors each track is resampled to.
BASELINE_ANCHOR_COUNT = 50
#: Deviations below this (metres) are treated as "within the corridor".
DEVIATION_MIN_M = 500.0
#: Minimum positions a current track needs before deviation can be computed.
MIN_CURRENT_POINTS = 3
#: Floor for the historical corridor width (metres) to avoid divide-by-tiny.
MIN_CORRIDOR_WIDTH_M = 100.0


Point = tuple[float, float]  # (lon, lat), WGS84


@dataclass(frozen=True)
class Provenanced:
    """A value plus how it is known. ``value is None`` ⇒ provenance ``unknown``."""

    value: object
    provenance: Provenance
    note: str | None = None


@dataclass(frozen=True)
class EvidenceItem:
    id: str
    statement: str
    confidence: Confidence
    source: str  # "trajectory_derived"
    provenance: Provenance
    evidence: str | None = None


@dataclass(frozen=True)
class BaselineSource:
    method: str
    contributing_track_count: int
    corridor_width_p90_m: float | None
    observed_time_range: str | None = None


@dataclass(frozen=True)
class RouteBaseline:
    """A historical median corridor for one route (``derived``)."""

    route_key: str
    #: Median centre-line, one (lon, lat) per along-track anchor.
    centerline: tuple[Point, ...]
    #: Per-anchor p90 lateral spread of the contributing tracks, in metres.
    corridor_width_m: tuple[float, ...]
    contributing_track_count: int
    observed_time_range: str | None
    #: True only when there was enough history to trust the corridor.
    sufficient: bool

    def source(self) -> BaselineSource:
        width = (
            _p90(self.corridor_width_m) if self.corridor_width_m else None
        )
        return BaselineSource(
            method="historical median corridor (NOAA multi-day AIS)",
            contributing_track_count=self.contributing_track_count,
            corridor_width_p90_m=width,
            observed_time_range=self.observed_time_range,
        )


@dataclass(frozen=True)
class RouteDeviationEvidence:
    """The ``route-deviation-1`` result."""

    schema_version: str
    track_ref: str
    route_key: str
    deviation_distance_m: Provenanced
    deviation_p95_m: Provenanced
    deviation_ratio: Provenanced
    baseline_source: Provenanced
    confidence: Confidence
    evidence: tuple[EvidenceItem, ...]
    disclaimer: str = (
        "Decision support for human review only; a derived geometric deviation, "
        "not a judgement about the vessel."
    )

    def to_dict(self) -> dict:
        def prov(p: Provenanced) -> dict:
            out: dict = {"value": p.value, "provenance": p.provenance}
            if p.note is not None:
                out["note"] = p.note
            return out

        return {
            "schemaVersion": self.schema_version,
            "track_ref": self.track_ref,
            "route_key": self.route_key,
            "deviation_distance_m": prov(self.deviation_distance_m),
            "deviation_p95_m": prov(self.deviation_p95_m),
            "deviation_ratio": prov(self.deviation_ratio),
            "baseline_source": prov(self.baseline_source),
            "confidence": self.confidence,
            "evidence": [
                {
                    "id": e.id,
                    "statement": e.statement,
                    "confidence": e.confidence,
                    "source": e.source,
                    "provenance": e.provenance,
                    **({"evidence": e.evidence} if e.evidence is not None else {}),
                }
                for e in self.evidence
            ],
            "disclaimer": self.disclaimer,
        }


# --------------------------------------------------------------------------- #
# Pure geometry helpers
# --------------------------------------------------------------------------- #


def _percentile(values: Sequence[float], q: float) -> float:
    """Deterministic linear-interpolation percentile (q in [0, 1])."""

    if not values:
        raise ValueError("percentile of empty sequence")
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    pos = q * (len(ordered) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    frac = pos - lo
    return float(ordered[lo] + (ordered[hi] - ordered[lo]) * frac)


def _p90(values: Sequence[float]) -> float:
    return _percentile(values, 0.90)


def _resample_track(points: Sequence[Point], anchors: int) -> list[Point]:
    """Resample a polyline to ``anchors`` equally-spaced along-track points.

    Deterministic linear interpolation by cumulative geodesic arc length. A
    degenerate track (all-same point / <2 points) returns the first point
    repeated so downstream statistics stay defined.
    """

    if anchors < 2:
        raise ValueError("anchors must be >= 2")
    pts = [(float(lon), float(lat)) for lon, lat in points]
    if len(pts) == 1:
        return [pts[0]] * anchors
    # Cumulative arc length.
    cum = [0.0]
    for i in range(1, len(pts)):
        d = geodesic_distance_m(pts[i - 1][0], pts[i - 1][1], pts[i][0], pts[i][1])
        cum.append(cum[-1] + d)
    total = cum[-1]
    if total <= 0.0:
        return [pts[0]] * anchors
    out: list[Point] = []
    for a in range(anchors):
        target = total * a / (anchors - 1)
        # Find the segment containing target.
        j = 1
        while j < len(cum) and cum[j] < target:
            j += 1
        j = min(j, len(pts) - 1)
        seg_len = cum[j] - cum[j - 1]
        t = 0.0 if seg_len <= 0 else (target - cum[j - 1]) / seg_len
        lon = pts[j - 1][0] + (pts[j][0] - pts[j - 1][0]) * t
        lat = pts[j - 1][1] + (pts[j][1] - pts[j - 1][1]) * t
        out.append((lon, lat))
    return out


def _densify(centerline: Sequence[Point], per_segment: int = 10) -> list[Point]:
    """Insert intermediate points so nearest-vertex distance approximates the
    true perpendicular cross-track distance to the polyline."""

    if len(centerline) < 2:
        return list(centerline)
    dense: list[Point] = []
    for i in range(1, len(centerline)):
        a = centerline[i - 1]
        b = centerline[i]
        for k in range(per_segment):
            t = k / per_segment
            dense.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    dense.append(centerline[-1])
    return dense


def _cross_track_distance_m(point: Point, dense_centerline: Sequence[Point]) -> float:
    """Minimum geodesic distance from ``point`` to a densified centre-line."""

    lon, lat = point
    return min(
        geodesic_distance_m(lon, lat, c[0], c[1]) for c in dense_centerline
    )


# --------------------------------------------------------------------------- #
# Baseline builder
# --------------------------------------------------------------------------- #


def build_route_baseline(
    route_key: str,
    historical_tracks: Sequence[Sequence[Point]],
    *,
    observed_time_range: str | None = None,
    anchors: int = BASELINE_ANCHOR_COUNT,
    min_tracks: int = MIN_BASELINE_TRACKS,
) -> RouteBaseline:
    """Build a historical median corridor from several past tracks.

    Returns a :class:`RouteBaseline` with ``sufficient=False`` (empty corridor)
    when fewer than ``min_tracks`` usable historical tracks are supplied — the
    caller must then emit an ``unknown`` deviation. A baseline is never built
    from a single track.
    """

    usable = [t for t in historical_tracks if len(t) >= 2]
    track_count = len(usable)
    if track_count < min_tracks:
        return RouteBaseline(
            route_key=route_key,
            centerline=(),
            corridor_width_m=(),
            contributing_track_count=track_count,
            observed_time_range=observed_time_range,
            sufficient=False,
        )

    resampled = [_resample_track(t, anchors) for t in usable]
    centerline: list[Point] = []
    widths: list[float] = []
    for a in range(anchors):
        lons = [r[a][0] for r in resampled]
        lats = [r[a][1] for r in resampled]
        c_lon = float(median(lons))
        c_lat = float(median(lats))
        centerline.append((c_lon, c_lat))
        # Lateral spread = p90 of each track's distance from the median point.
        lateral = [
            geodesic_distance_m(c_lon, c_lat, r[a][0], r[a][1]) for r in resampled
        ]
        widths.append(max(_p90(lateral), MIN_CORRIDOR_WIDTH_M))

    return RouteBaseline(
        route_key=route_key,
        centerline=tuple(centerline),
        corridor_width_m=tuple(widths),
        contributing_track_count=track_count,
        observed_time_range=observed_time_range,
        sufficient=True,
    )


# --------------------------------------------------------------------------- #
# Deviation calculator
# --------------------------------------------------------------------------- #


def _unknown_result(
    track_ref: str,
    baseline: RouteBaseline,
    reason: str,
) -> RouteDeviationEvidence:
    return RouteDeviationEvidence(
        schema_version="route-deviation-1",
        track_ref=track_ref,
        route_key=baseline.route_key,
        deviation_distance_m=Provenanced(None, "unknown", reason),
        deviation_p95_m=Provenanced(None, "unknown"),
        deviation_ratio=Provenanced(None, "unknown"),
        baseline_source=Provenanced(
            {
                "method": "historical median corridor",
                "contributing_track_count": baseline.contributing_track_count,
                "min_required": MIN_BASELINE_TRACKS,
            },
            "unknown",
        ),
        confidence="LOW",
        evidence=(
            EvidenceItem(
                id="baseline_insufficient",
                statement=(
                    "No sufficient historical baseline is available for this "
                    "route; deviation cannot be computed."
                ),
                confidence="LOW",
                source="trajectory_derived",
                provenance="unknown",
            ),
        ),
    )


def compute_route_deviation(
    track_ref: str,
    current_points: Sequence[Point],
    baseline: RouteBaseline,
    *,
    current_cog: Sequence[float] | None = None,
    min_current_points: int = MIN_CURRENT_POINTS,
    deviation_min_m: float = DEVIATION_MIN_M,
) -> RouteDeviationEvidence:
    """Measure how far ``current_points`` depart from a historical corridor.

    Emits an ``unknown`` result (never a fabricated distance) when the baseline
    is insufficient or the current track is too short to measure.
    """

    if not baseline.sufficient or not baseline.centerline:
        return _unknown_result(track_ref, baseline, "insufficient historical tracks")

    pts = [(float(lon), float(lat)) for lon, lat in current_points]
    if len(pts) < min_current_points:
        return _unknown_result(
            track_ref, baseline, "current track too short to measure deviation"
        )

    dense = _densify(baseline.centerline)
    cross = [_cross_track_distance_m(p, dense) for p in pts]
    dev_max = max(cross)
    dev_p95 = _percentile(cross, 0.95)
    corridor_p90 = _p90(baseline.corridor_width_m)
    ratio = dev_max / corridor_p90 if corridor_p90 > 0 else None

    evidence: list[EvidenceItem] = []

    # Confidence from DATA QUALITY and threshold margin only — not "danger".
    if dev_max < deviation_min_m:
        cross_conf: Confidence = "LOW"
        statement = (
            "Current track stays within the historical corridor for this "
            "origin–destination pair."
        )
    else:
        strong_history = baseline.contributing_track_count >= 2 * MIN_BASELINE_TRACKS
        if ratio is not None and ratio >= 2.0 and strong_history:
            cross_conf = "HIGH"
        elif ratio is not None and ratio >= 1.0:
            cross_conf = "MEDIUM"
        else:
            cross_conf = "LOW"
        statement = (
            "Current track departs from the historical median corridor for this "
            "origin–destination pair."
        )
    evidence.append(
        EvidenceItem(
            id="cross_track",
            statement=statement,
            confidence=cross_conf,
            source="trajectory_derived",
            provenance="derived",
            evidence=(
                f"max {dev_max / 1000:.1f} km (p95 {dev_p95 / 1000:.1f} km) "
                f"vs ~{corridor_p90 / 1000:.1f} km corridor"
            ),
        )
    )

    # Optional supporting evidence: course offset vs the along-corridor heading.
    if current_cog is not None and len(current_cog) >= 2:
        from .geodesy import WGS84_GEOD

        # Along-corridor heading from first to last centre-line point.
        c0 = baseline.centerline[0]
        c1 = baseline.centerline[-1]
        fwd_az, _, _ = WGS84_GEOD.inv(c0[0], c0[1], c1[0], c1[1])
        corridor_heading = fwd_az % 360.0
        offsets = [
            abs(circular_difference_degrees(corridor_heading, float(c)))
            for c in current_cog
            if c is not None
        ]
        if offsets:
            med_offset = float(median(offsets))
            evidence.append(
                EvidenceItem(
                    id="course_offset",
                    statement=(
                        "Course differs from the along-corridor heading over "
                        "part of the track."
                    ),
                    confidence="MEDIUM" if med_offset >= 30 else "LOW",
                    source="trajectory_derived",
                    provenance="derived",
                    evidence=f"median |ΔCOG| ~{med_offset:.0f}°",
                )
            )

    return RouteDeviationEvidence(
        schema_version="route-deviation-1",
        track_ref=track_ref,
        route_key=baseline.route_key,
        deviation_distance_m=Provenanced(
            round(dev_max, 1),
            "derived",
            "max cross-track to historical median corridor",
        ),
        deviation_p95_m=Provenanced(round(dev_p95, 1), "derived"),
        deviation_ratio=Provenanced(
            round(ratio, 3) if ratio is not None else None,
            "derived" if ratio is not None else "unknown",
            "deviation / historical p90 corridor width",
        ),
        baseline_source=Provenanced(
            {
                "method": baseline.source().method,
                "contributing_track_count": baseline.contributing_track_count,
                "observed_time_range": baseline.observed_time_range,
                "corridor_width_p90_m": round(corridor_p90, 1),
            },
            "derived",
        ),
        confidence=cross_conf,
        evidence=tuple(evidence),
    )
