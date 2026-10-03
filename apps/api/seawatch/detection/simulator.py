"""Synthetic Taiwan-waters AIS world with labelled events.

The simulator exists so the whole product (detectors, scoring, ML, UI, demo) can be
built and *measured* without paying for live AIS. It models:

* normal commercial traffic on realistic lanes around Taiwan,
* terrestrial receiver coverage (outside it, only sparse satellite-style fixes arrive,
  which produces natural, benign reporting gaps),
* injected behaviours of interest, each with a ground-truth label,
* deliberately benign look-alikes (fishing fleets, anchorages, storm hove-to, coverage gaps)
  so false-alarm control can be measured, not just claimed.

Every vessel name/MMSI is fictional. Same seed => identical world.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np

from .geo import NM_M, bearing_deg, circle_polygon, haversine_m
from .models import Receiver, Scenario, Track, TruthEvent, Zone

T0 = datetime(2026, 10, 3, 0, 0, tzinfo=timezone.utc).timestamp()
HOURS = 36.0
KN_MS = 0.514444

# --------------------------------------------------------------------------- #
# World definition
# --------------------------------------------------------------------------- #
PORTS = {
    "kaohsiung": (22.60, 120.27),
    "keelung": (25.15, 121.75),
    "taichung": (24.28, 120.48),
    "hualien": (23.98, 121.63),
    "magong": (23.57, 119.58),
}


def build_zones() -> list[Zone]:
    z: list[Zone] = []
    for pid, (la, lo) in PORTS.items():
        z.append(Zone(f"port-{pid}", f"Port of {pid.title()}", "port", circle_polygon(la, lo, 3.0),
                      "Commercial port approaches", 0.0))
    for zid, nm, (la, lo) in (("hongkong", "Hong Kong Approaches", (22.20, 116.60)), ("japan", "Northeast Approaches", (26.40, 123.30)),
                              ("luzon", "Luzon Strait Port", (20.90, 120.90))):
        z.append(Zone(f"port-{zid}", nm, "port", circle_polygon(la, lo, 3.0), "Port approaches outside the monitored area", 0.0))
    z.append(Zone("anch-kaohsiung", "Kaohsiung Anchorage", "anchorage", circle_polygon(22.50, 120.10, 3.5),
                  "Designated waiting anchorage", 0.0))
    z.append(Zone("anch-keelung", "Keelung Anchorage", "anchorage", circle_polygon(25.24, 121.83, 3.0),
                  "Designated waiting anchorage", 0.0))
    z.append(Zone("fish-bank", "Taiwan Bank Fishing Ground", "fishing_ground", circle_polygon(22.75, 118.75, 14.0),
                  "Traditional fishing ground", 0.0))
    z.append(Zone("cable-penghu", "Penghu Subsea Cable Corridor", "cable", circle_polygon(23.95, 119.30, 5.0),
                  "Protected submarine cable corridor - no anchoring", 1.0))
    z.append(Zone("restr-kinmen", "Kinmen Restricted Waters", "restricted", circle_polygon(24.43, 118.40, 8.0),
                  "Restricted waters - transit by authorisation only", 0.8))
    z.append(Zone("prot-windfarm", "Changhua Offshore Wind Farm", "protected", circle_polygon(24.05, 120.12, 3.0),
                  "Critical energy infrastructure", 0.7))
    return z


def build_receivers() -> list[Receiver]:
    return [
        Receiver("rx-kaohsiung", 22.62, 120.30, 50), Receiver("rx-taichung", 24.30, 120.52, 50),
        Receiver("rx-keelung", 25.12, 121.78, 55), Receiver("rx-hualien", 23.98, 121.62, 50),
        Receiver("rx-penghu", 23.55, 119.60, 45), Receiver("rx-kinmen", 24.45, 118.42, 40),
    ]


KAO = (22.60, 120.27)
LANE_NS = [KAO, (22.45, 120.05), (23.20, 119.70), (24.00, 119.70), (24.80, 120.30), (25.35, 121.20), (25.15, 121.75)]
ROUTES = {
    "kaohsiung_keelung": LANE_NS,
    "keelung_kaohsiung": LANE_NS[::-1],
    "kaohsiung_hongkong": [KAO, (22.55, 120.15), (22.30, 119.00), (22.10, 117.50), (22.20, 116.60)],
    "hongkong_kaohsiung": [(22.20, 116.60), (22.10, 117.50), (22.30, 119.00), (22.55, 120.15), KAO],
    "keelung_japan": [(25.15, 121.75), (25.80, 122.60), (26.40, 123.30)],
    "japan_keelung": [(26.40, 123.30), (25.80, 122.60), (25.15, 121.75)],
    "hualien_kaohsiung": [(23.98, 121.63), (23.00, 121.65), (22.30, 121.10), (22.00, 120.60), (22.50, 120.15), KAO],
    "kaohsiung_luzon": [KAO, (22.50, 120.15), (21.80, 120.55), (20.90, 120.90)],
    "luzon_kaohsiung": [(20.90, 120.90), (21.80, 120.55), (22.50, 120.15), KAO],
    "kaohsiung_magong": [KAO, (23.00, 119.95), (23.57, 119.58)],
    "magong_kaohsiung": [(23.57, 119.58), (23.00, 119.95), KAO],
}
ROUTE_WEIGHT = {"kaohsiung_keelung": 6, "keelung_kaohsiung": 6, "kaohsiung_hongkong": 5, "hongkong_kaohsiung": 5,
                "keelung_japan": 3, "japan_keelung": 3, "hualien_kaohsiung": 3, "kaohsiung_luzon": 3,
                "luzon_kaohsiung": 3, "kaohsiung_magong": 2, "magong_kaohsiung": 2}

_ADJ = ["PACIFIC", "ORIENT", "JADE", "FORMOSA", "SILVER", "NORTHERN", "GOLDEN", "HARBOR", "AZURE", "MERIDIAN",
        "STELLAR", "EASTERN", "CRIMSON", "OCEAN", "TIDAL", "SUMMIT", "CORAL", "IRON", "SWIFT", "LUNAR"]
_NOUN = ["CARRIER", "VOYAGER", "TRADER", "SPIRIT", "PIONEER", "HORIZON", "GLORY", "EXPRESS", "FORTUNE", "LEGEND",
         "BREEZE", "HARMONY", "STAR", "CROWN", "WAVE", "ARROW", "DAWN", "REEF", "ANCHOR", "SAILOR"]
_FLAGS = [("416", "TW"), ("412", "CN"), ("477", "HK"), ("351", "PA"), ("538", "MH"), ("636", "LR"), ("431", "JP")]
_SPEED = {"cargo": (11.5, 15.0), "tanker": (10.5, 13.0), "ferry": (17.0, 20.0), "fishing": (6.0, 8.5),
          "passenger": (16.0, 20.0), "other": (8.0, 11.0)}


# --------------------------------------------------------------------------- #
# Kinematic building blocks
# --------------------------------------------------------------------------- #
class Mover:
    """Builds a dense (60 s) 'true' trajectory from composable manoeuvres."""

    DT = 60.0

    def __init__(self, rng: np.random.Generator, lat: float, lon: float, t: float):
        self.rng, self.lat, self.lon, self.t = rng, lat, lon, t
        self.cog = 0.0
        self._c: list[tuple[np.ndarray, ...]] = []

    def _push(self, ts, lats, lons, sog, cog):
        self._c.append((np.asarray(ts, float), np.asarray(lats, float), np.asarray(lons, float),
                        np.asarray(sog, float), np.asarray(cog, float)))
        self.t, self.lat, self.lon, self.cog = float(ts[-1]), float(lats[-1]), float(lons[-1]), float(cog[-1])

    def go_to(self, lat: float, lon: float, speed_kn: float, wander: float = 0.0) -> "Mover":
        dist = float(haversine_m(self.lat, self.lon, lat, lon))
        if dist < 50:
            return self
        spd = speed_kn * KN_MS
        n = max(1, int(round(dist / (spd * self.DT))))
        step = dist / (n * spd)
        f = np.arange(1, n + 1) / n
        lats = self.lat + (lat - self.lat) * f
        lons = self.lon + (lon - self.lon) * f
        brg = float(bearing_deg(self.lat, self.lon, lat, lon))
        if wander:
            off = wander * np.sin(math.pi * f) * np.sin(self.rng.uniform(0, 6.28) + 5 * f)
            lats = lats + off * math.cos(math.radians(brg + 90))
            lons = lons + off * math.sin(math.radians(brg + 90)) / max(0.2, math.cos(math.radians(self.lat)))
        ts = self.t + np.arange(1, n + 1) * step
        sog = speed_kn + self.rng.normal(0, 0.25, n)
        cog = brg + self.rng.normal(0, 1.5, n)
        self._push(ts, lats, lons, sog, cog % 360)
        return self

    def hold(self, minutes: float, speed_kn: float = 0.2, jitter_nm: float = 0.02) -> "Mover":
        n = max(1, int(minutes * 60 / self.DT))
        ts = self.t + np.arange(1, n + 1) * self.DT
        d = jitter_nm / 60.0
        lats = self.lat + np.cumsum(self.rng.normal(0, d * 0.25, n)).clip(-d * 3, d * 3)
        lons = self.lon + np.cumsum(self.rng.normal(0, d * 0.25, n)).clip(-d * 3, d * 3)
        sog = np.abs(self.rng.normal(speed_kn, 0.1, n))
        cog = (self.cog + self.rng.normal(0, 40, n)) % 360
        self._push(ts, lats, lons, sog, cog)
        return self

    def circle(self, clat: float, clon: float, radius_nm: float, minutes: float, speed_kn: float) -> "Mover":
        n = max(2, int(minutes * 60 / self.DT))
        r = radius_nm * NM_M
        theta0 = math.radians(float(bearing_deg(clat, clon, self.lat, self.lon)))
        omega = (speed_kn * KN_MS) / r
        th = theta0 + omega * self.DT * np.arange(1, n + 1)
        lats = clat + (r * np.cos(th)) / 111_320.0
        lons = clon + (r * np.sin(th)) / (111_320.0 * math.cos(math.radians(clat)))
        ts = self.t + np.arange(1, n + 1) * self.DT
        sog = speed_kn + self.rng.normal(0, 0.2, n)
        cog = (np.degrees(th) + 90) % 360
        self._push(ts, lats, lons, sog, cog)
        return self

    def arrays(self):
        return tuple(np.concatenate([c[i] for c in self._c]) for i in range(5))


def _route_points(route, f0: float, f1: float):
    """Waypoints from fraction f0 to f1 of a polyline's length (inclusive of cut points)."""

    pts = np.array(route)
    seg = np.array([float(haversine_m(*route[i], *route[i + 1])) for i in range(len(route) - 1)])
    cum = np.concatenate([[0], np.cumsum(seg)])
    L = cum[-1]

    def at(f):
        d = min(max(f, 0), 1) * L
        i = min(int(np.searchsorted(cum, d, side="right") - 1), len(seg) - 1)
        w = (d - cum[i]) / seg[i]
        return tuple(pts[i] + (pts[i + 1] - pts[i]) * w)

    out = [at(f0)]
    for i in range(1, len(route) - 1):
        if f0 < cum[i] / L < f1:
            out.append(tuple(pts[i]))
    out.append(at(f1))
    return out, L


def _lane_start(route, f_event: float, hours_before: float, speed: float):
    _, L = _route_points(route, 0, 1)
    f0 = max(0.0, f_event - speed * KN_MS * hours_before * 3600 / L)
    return f0


# --------------------------------------------------------------------------- #
# World builder
# --------------------------------------------------------------------------- #
class _World:
    def __init__(self, seed: int, t0: float = T0, hours: float = HOURS):
        self.rng = np.random.default_rng(seed)
        self.t0, self.t1 = t0, t0 + hours * 3600
        self.receivers = build_receivers()
        self.zones = build_zones()
        self.tracks: list[Track] = []
        self.truth: list[TruthEvent] = []
        self._mmsi_used: set[str] = set()
        self._n = 0

    # identity ---------------------------------------------------------------
    def identity(self, ship_type: str, flag_hint: str | None = None):
        while True:
            mid, flag = _FLAGS[self.rng.integers(len(_FLAGS))] if flag_hint is None else \
                next(f for f in _FLAGS if f[1] == flag_hint)
            mmsi = mid + "".join(str(self.rng.integers(10)) for _ in range(6))
            if mmsi not in self._mmsi_used:
                self._mmsi_used.add(mmsi)
                break
        name = f"{_ADJ[self.rng.integers(len(_ADJ))]} {_NOUN[self.rng.integers(len(_NOUN))]}"
        if ship_type == "fishing":
            name = f"FU YUAN YU {self.rng.integers(100, 999)}"
        return mmsi, name, flag

    def tid(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}-{self._n:03d}"

    # reporting layer --------------------------------------------------------
    def covered(self, lat, lon):
        d = np.full(np.shape(lat), 1e9)
        for r in self.receivers:
            d = np.minimum(d, haversine_m(lat, lon, r.lat, r.lon) / NM_M / r.range_nm)
        return d <= 1.0

    def report(self, mover: Mover, ship_type: str, mmsi: str, name: str, flag: str,
               dark: list[tuple[float, float]] | None = None, force_dense: bool = False) -> Track:
        t, la, lo, sog, cog = mover.arrays()
        cov = self.covered(la, lo)
        idx, i, n = [], 0, len(t)
        while i < n:
            idx.append(i)
            step = self.rng.uniform(0.8, 1.25) * (120 if (cov[i] or force_dense) else 1500 * self.rng.uniform(0.6, 1.7))
            nxt = np.searchsorted(t, t[i] + step)
            i = max(i + 1, int(nxt))
        idx = np.array(idx)
        t, la, lo, sog, cog = t[idx], la[idx], lo[idx], sog[idx], cog[idx]
        # GNSS noise (~15 m)
        la = la + self.rng.normal(0, 15 / 111_320.0, la.size)
        lo = lo + self.rng.normal(0, 15 / 111_320.0, lo.size)
        keep = (t >= self.t0) & (t <= self.t1)
        for a, b in dark or []:
            keep &= ~((t >= a) & (t <= b))
        return Track(mmsi, name, ship_type, flag, t[keep], la[keep], lo[keep],
                     np.clip(sog[keep], 0, None), cog[keep])

    def add(self, track: Track):
        if len(track) >= 2:
            self.tracks.append(track)

    def label(self, kind, mmsis, a, b, note="", benign=False):
        self.truth.append(TruthEvent(self.tid("T"), kind, tuple(mmsis), float(a), float(b), note, benign))

    # normal traffic ---------------------------------------------------------
    def normal_vessel(self):
        keys = list(ROUTES)
        w = np.array([ROUTE_WEIGHT[k] for k in keys], float)
        key = keys[self.rng.choice(len(keys), p=w / w.sum())]
        route = ROUTES[key]
        stype = "ferry" if "magong" in key else str(self.rng.choice(["cargo", "tanker", "cargo"]))
        lo_, hi_ = _SPEED[stype]
        speed = self.rng.uniform(lo_, hi_)
        start = self.t0 + self.rng.uniform(-20, 30) * 3600
        mmsi, name, flag = self.identity(stype)
        m = Mover(self.rng, route[0][0] + self.rng.normal(0, 0.01), route[0][1] + self.rng.normal(0, 0.01), start)
        m.hold(self.rng.uniform(20, 70), 0.1)
        side = self.rng.normal(0, 0.03)
        for la, lo in route[1:]:
            m.go_to(la + side, lo + side, speed, wander=0.03)
        m.hold(self.rng.uniform(30, 90), 0.1)
        self.add(self.report(m, stype, mmsi, name, flag))

    def coastal_fisher(self):
        """Fishing boat that works a ground, dwelling slowly there - routine behaviour."""

        mmsi, name, flag = self.identity("fishing", "TW")
        zone = next(z for z in self.zones if z.id == "fish-bank")
        c = (22.75, 118.75)
        start = self.t0 + self.rng.uniform(-6, 8) * 3600
        m = Mover(self.rng, c[0] + self.rng.uniform(-0.15, 0.15), c[1] + self.rng.uniform(-0.2, 0.2), start)
        for _ in range(self.rng.integers(2, 4)):
            m.circle(m.lat + self.rng.uniform(-.03, .03), m.lon + self.rng.uniform(-.03, .03),
                     self.rng.uniform(0.5, 1.5), self.rng.uniform(60, 150), self.rng.uniform(2, 3.5))
            m.go_to(c[0] + self.rng.uniform(-0.2, 0.2), c[1] + self.rng.uniform(-0.25, 0.25), 6.0)
        self.add(self.report(m, "fishing", mmsi, name, flag))
        return zone

    # event injectors --------------------------------------------------------
    def _tev(self, lo=7.0, hi=22.0):
        return self.t0 + self.rng.uniform(lo, hi) * 3600

    def ev_dark_gap(self):
        route, stype, sp = ROUTES["kaohsiung_keelung"], "tanker", 12.0
        fe = self.rng.uniform(0.35, 0.55)
        tev = self._tev(6, 20)
        pts, L = _route_points(route, _lane_start(route, fe, 3.0, sp), 1.0)
        mmsi, name, flag = self.identity(stype, str(self.rng.choice(["PA", "HK", "CN"])))
        m = Mover(self.rng, *pts[0], tev - 3 * 3600)
        for p in pts[1:]:
            m.go_to(*p, sp, wander=0.02)
        dur = self.rng.uniform(95, 150) * 60
        self.add(self.report(m, stype, mmsi, name, flag, dark=[(tev, tev + dur)]))
        self.label("dark_gap", [mmsi], tev, tev + dur, "Tanker stops transmitting for ~2h mid-strait while under way")

    def ev_dark_sts(self):
        route, sp = ROUTES["kaohsiung_keelung"], 11.5
        tev = self._tev(8, 20)
        M = (23.30, 119.20)  # rendezvous point inside receiver coverage, off the lane
        fe = 0.28
        pts, _ = _route_points(route, _lane_start(route, fe, 3.0, sp), 1.0)
        a_mmsi, a_name, a_flag = self.identity("tanker", "PA")
        b_mmsi, b_name, b_flag = self.identity("tanker", "CN")
        a = Mover(self.rng, *pts[0], tev - 3 * 3600)
        for p in pts[1:2]:
            a.go_to(*p, sp, wander=0.01)
        t_leave = a.t
        a.go_to(*M, sp)
        a.hold(105, 0.4)
        t_back = a.t
        a.go_to(*pts[1], sp)
        for p in pts[2:]:
            a.go_to(*p, sp, wander=0.02)
        dark_end = t_back + 25 * 60
        self.add(self.report(a, "tanker", a_mmsi, a_name, a_flag, dark=[(t_leave, dark_end)]))
        b = Mover(self.rng, M[0] + 0.01, M[1] - 0.01, t_leave - 40 * 60)
        b.hold((t_back - t_leave) / 60 + 70, 0.3, jitter_nm=0.05)
        b.go_to(22.9, 119.95, 9.0)
        self.add(self.report(b, "tanker", b_mmsi, b_name, b_flag))
        self.label("dark_sts", [a_mmsi, b_mmsi], t_leave, dark_end,
                   "Tanker A goes dark, meets slow tanker B off-lane, resumes transmitting")

    def ev_loiter_cable(self):
        route, stype, sp = ROUTES["kaohsiung_keelung"], "cargo", 11.0
        tev = self._tev(6, 18)
        mmsi, name, flag = self.identity(stype, str(self.rng.choice(["CN", "HK"])))
        pts, _ = _route_points(route, 0.38, 0.55)
        m = Mover(self.rng, *pts[0], tev - 2 * 3600)
        m.go_to(23.93, 119.48, sp)
        t_a = m.t
        m.circle(23.95, 119.44, 1.1, self.rng.uniform(230, 290), 2.3)
        t_b = m.t
        m.go_to(24.0, 119.7, sp)
        m.go_to(24.8, 120.3, sp)
        self.add(self.report(m, stype, mmsi, name, flag))
        self.label("loitering", [mmsi], t_a, t_b, "Cargo ship circles slowly ~5 nm from a subsea cable corridor for ~4h")

    def ev_zone_restricted(self):
        mmsi, name, flag = self.identity("other", "CN")
        tev = self._tev(8, 20)
        m = Mover(self.rng, 24.15, 119.25, tev - 70 * 60)
        m.go_to(24.43, 118.62, 9.0)
        t_in = m.t
        m.go_to(24.43, 118.42, 8.0).hold(18, 1.0)
        m.go_to(24.40, 118.62, 9.0)
        t_out = m.t
        m.go_to(24.15, 119.25, 9.0)
        self.add(self.report(m, "other", mmsi, name, flag))
        self.label("zone_entry", [mmsi], t_in, t_out, "Unauthorised vessel crosses into Kinmen restricted waters")

    def ev_anchor_cable(self):
        mmsi, name, flag = self.identity("cargo", "HK")
        tev = self._tev(8, 20)
        m = Mover(self.rng, 23.70, 119.55, tev - 80 * 60)
        m.go_to(23.95, 119.31, 9.5)
        t_in = m.t
        m.hold(75, 0.3)
        t_out = m.t
        m.go_to(24.05, 119.75, 10.5)
        m.go_to(24.80, 120.3, 12)
        self.add(self.report(m, "cargo", mmsi, name, flag))
        self.label("zone_entry", [mmsi], t_in, t_out, "Cargo ship stops inside the subsea cable corridor (anchoring-like)")

    def ev_rendezvous(self):
        tev = self._tev(8, 20)
        P = (23.62 + self.rng.uniform(-.05, .05), 119.82)
        ids = [self.identity("tanker", "CN"), self.identity("tanker", "PA")]
        legs = []
        for k, (mmsi, name, flag) in enumerate(ids):
            start = (22.9, 120.0) if k == 0 else (24.6, 120.15)
            tgt = (P[0] + k * 0.004, P[1] + k * 0.003)
            lead = float(haversine_m(*start, *tgt)) / (11 * KN_MS)
            m = Mover(self.rng, *start, tev - lead)
            m.go_to(P[0] + k * 0.004, P[1] + k * 0.003, 11)
            m.hold(95, 0.5, jitter_nm=0.04)
            t_hold = m.t
            m.go_to(*(start if k else (24.6, 120.15)), 11)
            legs.append((m, mmsi, name, flag, t_hold))
        for m, mmsi, name, flag, _ in legs:
            self.add(self.report(m, "tanker", mmsi, name, flag))
        t_end = legs[0][4]
        self.label("rendezvous", [i[0] for i in ids], t_end - 95 * 60, t_end, "Two tankers meet and drift together ~95 min at sea")

    def ev_spoof(self):
        route, stype, sp = ROUTES["kaohsiung_hongkong"], "cargo", 13.0
        mmsi, name, flag = self.identity(stype, "CN")
        tev = self._tev(8, 18)
        pts, _ = _route_points(route, 0.1, 0.9)
        m = Mover(self.rng, *pts[0], tev - 2 * 3600)
        for p in pts[1:]:
            m.go_to(*p, sp, wander=0.02)
        tr = self.report(m, stype, mmsi, name, flag)
        wins = [(tev, tev + 14 * 60), (tev + 3.2 * 3600, tev + 3.2 * 3600 + 11 * 60)]
        for a, b in wins:
            sel = (tr.t >= a) & (tr.t <= b)
            off_lat, off_lon = 0.9 * math.cos(math.radians(30)), 0.9 * math.sin(math.radians(30))
            tr.lat[sel] += off_lat
            tr.lon[sel] += off_lon
        self.add(tr)
        self.label("position_jump", [mmsi], wins[0][0], wins[1][1], "Reported position teleports ~55 nm and back (x2) while SOG stays normal")

    def ev_identity_clone(self):
        mmsi, name, flag = self.identity("cargo", "TW")
        tev = self._tev(4, 12)
        a = Mover(self.rng, 23.80, 121.62, tev)
        a.go_to(22.50, 120.15, 12.5, wander=0.02).hold(20, 0.1)
        b = Mover(self.rng, 25.20, 121.55, tev)
        b.hold(8 * 60, 0.1, jitter_nm=0.1)
        ta = self.report(a, "cargo", mmsi, name, flag, force_dense=True)
        tb = self.report(b, "cargo", mmsi, name, flag, force_dense=True)
        t = np.concatenate([ta.t, tb.t])
        order = np.argsort(t, kind="stable")
        merged = Track(mmsi, name, "cargo", flag, t[order], np.concatenate([ta.lat, tb.lat])[order],
                       np.concatenate([ta.lon, tb.lon])[order], np.concatenate([ta.sog, tb.sog])[order],
                       np.concatenate([ta.cog, tb.cog])[order])
        self.add(merged)
        self.label("identity_conflict", [mmsi], float(ta.t[0]), float(min(ta.t[-1], tb.t[-1])),
                   "Same MMSI is reported from two places ~150 nm apart at the same time")

    def ev_route_deviation(self):
        mmsi, name, flag = self.identity("cargo", "CN")
        tev = self._tev(4, 12)
        m = Mover(self.rng, 22.50, 120.12, tev)
        m.go_to(23.20, 119.70, 12.5, wander=0.01)
        m.go_to(23.50, 118.75, 12.5)
        t_a = m.t
        m.go_to(24.35, 118.95, 12.5)
        m.go_to(24.60, 119.95, 12.5)
        t_b = m.t
        m.go_to(24.80, 120.30, 12.5)
        m.go_to(25.35, 121.20, 12.5)
        self.add(self.report(m, "cargo", mmsi, name, flag))
        self.label("route_deviation", [mmsi], t_a - 25 * 60, t_b - 40 * 60, "Cargo ship leaves the normal strait lane for unused water")

    def ev_cluster(self):
        tev = self._tev(8, 20)
        C = (23.55 + self.rng.uniform(-.04, .04), 118.62)
        mm = []
        for k in range(6):
            mmsi, name, flag = self.identity("fishing", "CN")
            ang = k * 60 + self.rng.uniform(-10, 10)
            r = self.rng.uniform(14, 22)
            sl = C[0] + r / 60 * math.cos(math.radians(ang)), C[1] + r / 60 * math.sin(math.radians(ang)) / 0.92
            m = Mover(self.rng, *sl, tev - 2.2 * 3600)
            m.go_to(C[0] + self.rng.normal(0, .008), C[1] + self.rng.normal(0, .008), 7.5)
            m.hold(100, 1.2, jitter_nm=0.1)
            m.go_to(*sl, 7.5)
            mm.append(mmsi)
            self.add(self.report(m, "fishing", mmsi, name, flag))
        self.label("cluster", mm, tev, tev + 100 * 60 + 600, "Six fishing-type vessels converge and hold together outside any fishing ground")

    # benign look-alikes -----------------------------------------------------
    def benign_fishing_fleet(self, n=9):
        ids = []
        for _ in range(n):
            self.coastal_fisher()
            ids.append(self.tracks[-1].mmsi)
        self.label("fishing_ops", ids, self.t0, self.t1, "Fishing fleet working Taiwan Bank (loitering + clustering expected)", True)

    def benign_anchored(self, n=4):
        ids = []
        for k in range(n):
            st = "tanker" if k % 2 else "cargo"
            mmsi, name, flag = self.identity(st)
            m = Mover(self.rng, 22.50 + self.rng.uniform(-.02, .02), 120.10 + self.rng.uniform(-.02, .02),
                      self.t0 - 600)
            m.hold(HOURS * 60 + 30, 0.15, jitter_nm=0.2)
            self.add(self.report(m, st, mmsi, name, flag))
            ids.append(mmsi)
        self.label("anchored", ids, self.t0, self.t1, "Vessels waiting at the Kaohsiung anchorage", True)

    def benign_sat_gap(self):
        mmsi, name, flag = self.identity("cargo")
        m = Mover(self.rng, 22.50, 120.15, self.t0 + self.rng.uniform(1, 6) * 3600)
        m.go_to(21.80, 120.55, 12.5).go_to(20.90, 120.90, 12.5)
        m.hold(60, 0.1).go_to(21.80, 120.55, 12.5).go_to(22.50, 120.15, 12.5)
        self.add(self.report(m, "cargo", mmsi, name, flag))
        self.label("coverage_gap", [mmsi], self.t0, self.t1, "Sparse satellite-only reporting outside terrestrial coverage", True)

    def benign_hove_to(self):
        mmsi, name, flag = self.identity("cargo", "TW")
        tev = self._tev(8, 16)
        pts, _ = _route_points(ROUTES["keelung_kaohsiung"], 0.2, 0.9)
        m = Mover(self.rng, *pts[0], tev - 3600)
        m.go_to(24.40, 120.00, 12.0)
        t_a = m.t
        m.hold(105, 0.6, jitter_nm=0.3)
        t_b = m.t
        for p in pts[1:]:
            m.go_to(*p, 12.0)
        self.add(self.report(m, "cargo", mmsi, name, flag))
        self.label("hove_to", [mmsi], t_a, t_b, "Cargo ship stops ~105 min in heavy weather (benign, but looks like loitering)", True)


# plans ----------------------------------------------------------------------- #
EVENT_KINDS = {
    "dark_gap": "ev_dark_gap", "dark_sts": "ev_dark_sts", "loitering": "ev_loiter_cable",
    "zone_entry_restricted": "ev_zone_restricted", "zone_entry_cable": "ev_anchor_cable",
    "rendezvous": "ev_rendezvous", "position_jump": "ev_spoof", "identity_conflict": "ev_identity_clone",
    "route_deviation": "ev_route_deviation", "cluster": "ev_cluster",
}
DEMO_PLAN = list(EVENT_KINDS)


def normal_traffic(seed: int, n: int = 55) -> Scenario:
    """Event-free traffic for pattern-of-life baselines ('historic' data)."""

    w = _World(seed)
    for _ in range(n):
        w.normal_vessel()
    return Scenario(f"history-{seed}", w.t0, w.t1, w.tracks, w.zones, w.receivers, [], seed)


def build_scenario(seed: int = 7, plan: list[str] | None = None, n_normal: int = 55, benign: bool = True,
                   name: str | None = None) -> Scenario:
    w = _World(seed)
    for _ in range(n_normal):
        w.normal_vessel()
    for kind in (DEMO_PLAN if plan is None else plan):
        getattr(w, EVENT_KINDS[kind])()
    if benign:
        w.benign_fishing_fleet(9)
        w.benign_anchored(4)
        w.benign_sat_gap()
        w.benign_hove_to()
    return Scenario(name or f"taiwan-demo-{seed}", w.t0, w.t1, w.tracks, w.zones, w.receivers, w.truth, seed)


def random_plan(rng: np.random.Generator, n: int = 8) -> list[str]:
    return list(rng.choice(list(EVENT_KINDS), size=n, replace=True))
