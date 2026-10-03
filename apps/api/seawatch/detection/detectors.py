"""Rule-based behaviour detectors.

Each detector turns raw AIS positions into :class:`Event` objects that carry
(a) a severity, (b) a confidence reflecting data quality, (c) plain-language
evidence, (d) the benign explanations that should be considered, and (e) what we
cannot know from AIS alone. Detectors never assert intent.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Callable

import numpy as np
from scipy.spatial import cKDTree

from .config import DetectionConfig
from .context import BENIGN_AREA_KINDS, SENSITIVE_KINDS, DetectionContext, TrafficBaseline
from .geo import NM_M, haversine_m, project_xy_m
from .models import Event, Track

KN_MS = 0.514444
STATIC_STATUS = (1, 5, 6)  # AIS navigational status: at anchor, moored, aground
SERVICE_TYPES = ("tug", "pilot", "sar", "service", "dredger")  # waiting about is part of their job


def is_berthed(tr: Track) -> bool:
    """Stationary for (essentially) the whole observation: tied up or at anchor, not 'loitering'."""

    if len(tr) < 6 or tr.t[-1] - tr.t[0] < 6 * 3600:
        return False
    x, y = project_xy_m(tr.lat, tr.lon)
    return bool((x.max() - x.min()) <= 1.5 * NM_M and (y.max() - y.min()) <= 1.5 * NM_M)


def static_fraction(tr: Track, i0: int, i1: int) -> float:
    """Share of reports in [i0, i1] where the vessel declares itself anchored / moored / aground."""

    if tr.status is None or i1 < i0:
        return 0.0
    return float(np.isin(tr.status[i0:i1 + 1], STATIC_STATUS).mean())


def fmt_dur(seconds: float) -> str:
    m = int(round(seconds / 60))
    return f"{m // 60}h {m % 60:02d}m" if m >= 60 else f"{m} min"


def fmt_pos(lat: float, lon: float) -> str:
    return f"{abs(lat):.2f}°{'N' if lat >= 0 else 'S'} {abs(lon):.2f}°{'E' if lon >= 0 else 'W'}"


def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return float(max(lo, min(hi, x)))


def _typical_interval_s(track: Track, ctx: DetectionContext) -> float:
    if len(track) < 3:
        return 600.0
    dt = np.diff(track.t)
    cov = ctx.covered(track.lat[:-1], track.lon[:-1])
    pool = dt[cov] if cov.sum() >= 3 else dt
    return float(np.median(pool))


def _data_quality(track: Track, i0: int, i1: int, ctx: DetectionContext) -> float:
    """0..1 quality of the evidence window: density of fixes and valid speed."""

    n = i1 - i0 + 1
    if n < 2:
        return 0.3
    span = max(track.t[i1] - track.t[i0], 1.0)
    interval = span / (n - 1)
    dens = 1.0 if interval <= 400 else 0.75 if interval <= 900 else 0.5
    valid = float(np.mean(~np.isnan(track.sog[i0:i1 + 1])))
    return _clip(dens * (0.6 + 0.4 * valid), 0.1, 1.0)


# --------------------------------------------------------------------------- #
# AIS reporting gaps ("dark activity")
# --------------------------------------------------------------------------- #
def detect_gaps(tracks: list[Track], ctx: DetectionContext, cfg: DetectionConfig) -> list[Event]:
    out: list[Event] = []
    for tr in tracks:
        if len(tr) < 3 or is_berthed(tr):
            continue
        dt = np.diff(tr.t)
        typical = _typical_interval_s(tr, ctx)
        for i in np.where(dt >= cfg.gap_min_minutes * 60)[0]:
            j = i + 1
            la0, lo0, la1, lo1 = tr.lat[i], tr.lon[i], tr.lat[j], tr.lon[j]
            dist_nm = float(haversine_m(la0, lo0, la1, lo1)) / NM_M
            implied = dist_nm / (dt[i] / 3600)
            mid_lat, mid_lon = (la0 + la1) / 2, (lo0 + lo1) / 2
            c0, c1 = bool(ctx.covered(la0, lo0)), bool(ctx.covered(la1, lo1))
            f = np.linspace(0, 1, 9)
            cov_frac = float(ctx.covered(la0 + (la1 - la0) * f, lo0 + (lo1 - lo0) * f).mean())
            ends_la, ends_lo = np.array([la0, la1]), np.array([lo0, lo1])
            in_port = bool(ctx.in_kinds(ends_la, ends_lo, BENIGN_AREA_KINDS).any()) or (
                float(np.nan_to_num(tr.sog[i], nan=0.0)) < 2.0 and bool(ctx.benign_mask(ends_la, ends_lo).any()))
            if ctx.near_edge(la0, lo0) or ctx.near_edge(la1, lo1):
                continue  # left / re-entered the monitored area rather than going dark
            if in_port or (tr.status is not None and int(tr.status[i]) in STATIC_STATUS):
                continue  # switching off alongside / at anchor is routine
            sat_only = cov_frac < 0.6 or not (c0 and c1)
            if sat_only and dt[i] < cfg.gap_min_minutes * 60 * 2.0:
                continue  # sparse satellite-only reporting is expected here
            dur_min = dt[i] / 60
            sog_before = float(np.nan_to_num(tr.sog[i], nan=0.0))
            underway = sog_before >= 4.0
            sev = 35 + 30 * min(1.0, (dur_min - cfg.gap_min_minutes) / (cfg.gap_min_minutes * 3))
            ev: list[str] = [f"No AIS transmissions for {fmt_dur(dt[i])} (vessel normally reports every ~{fmt_dur(typical)})."]
            if c0 and c1 and cov_frac >= 0.8:
                sev += 15
                ev.append("Both the last and next fix are inside terrestrial receiver coverage, so a coverage hole is an unlikely explanation.")
            elif sat_only:
                sev -= 25
                ev.append("The gap is in an area with satellite-only reporting, where long silences are common.")
            if underway:
                sev += 8
                ev.append(f"The vessel was under way ({sog_before:.1f} kn) when it went silent.")
            near_zone, dz = ctx.nearest_zone(la0, lo0, SENSITIVE_KINDS)
            if near_zone is not None and dz <= 15:
                sev += 10
                ev.append(f"Silence began {dz:.0f} nm from {near_zone.name}.")
            implausible = implied > cfg.gap_max_implied_knots
            if implausible:
                sev += 12
                ev.append(f"Position after the gap implies {implied:.0f} kn - physically implausible for most merchant ships.")
            else:
                ev.append(f"Position after the gap is {dist_nm:.0f} nm away, consistent with continued transit (~{implied:.0f} kn implied).")
            stationary = dist_nm < 1.5
            if stationary and not (near_zone is not None and dz <= 5):
                sev = min(sev, 28.0)
                ev.append("The vessel reappeared where it vanished (under 1.5 nm away) - consistent with powering down at a berth or anchorage.")
            conf = 0.55 + (0.2 if (c0 and c1 and cov_frac >= 0.8) else 0.0) + (0.1 if i >= 5 else 0.0) - (0.2 if sat_only else 0.0)
            out.append(Event(
                "", "ais_gap", [tr.mmsi], float(tr.t[i]), float(tr.t[j]), float(mid_lat), float(mid_lon),
                _clip(sev), _clip(conf, 0.1, 0.95),
                f"{tr.name}: AIS silent for {fmt_dur(dt[i])}",
                ev,
                ["Receiver outage or local coverage shadow", "Transponder power cycled or equipment fault",
                 "Crew switching off to avoid piracy in high-risk waters"],
                ["AIS alone cannot separate deliberate switch-off from a technical fault.",
                 "A SAR or RF-emission pass over the gap area would confirm the vessel's physical presence."],
                {"gap_s": float(dt[i]), "distance_nm": round(dist_nm, 1), "implied_kn": round(implied, 1),
                 "covered_start": c0, "covered_end": c1, "stationary": bool(stationary), "coverage_fraction": round(cov_frac, 2)},
                path=[(float(la0), float(lo0)), (float(la1), float(lo1))],
            ))
    return out


# --------------------------------------------------------------------------- #
# Loitering / unusual stopping (stay-point detection)
# --------------------------------------------------------------------------- #
def detect_loitering(tracks: list[Track], ctx: DetectionContext, cfg: DetectionConfig) -> list[Event]:
    out: list[Event] = []
    r_m = cfg.loiter_radius_nm * NM_M
    for tr in tracks:
        n = len(tr)
        if n < 4:
            continue
        x, y = project_xy_m(tr.lat, tr.lon)
        t = tr.t
        i = 0
        while i < n - 2:
            xs, ys = x[i:], y[i:]
            ok = ((np.maximum.accumulate(xs) - np.minimum.accumulate(xs)) <= 2 * r_m) & \
                 ((np.maximum.accumulate(ys) - np.minimum.accumulate(ys)) <= 2 * r_m)
            # never bridge a long reporting gap: silence is its own event
            brk = np.where(np.diff(t[i:]) >= cfg.gap_min_minutes * 60)[0]
            last = len(xs) if ok.all() else int(np.argmin(ok))
            if brk.size:
                last = min(last, int(brk[0]) + 1)
            j = i + last - 1
            dur = t[j] - t[i]
            if j - i + 1 >= 4 and dur >= cfg.loiter_min_minutes * 60:
                if dur >= 0.85 * (t[-1] - t[0]) or static_fraction(tr, i, j) >= 0.6:
                    i = j + 1
                    continue  # moored / anchored for the whole observation: berthed, not loitering
                seg = slice(i, j + 1)
                med_sog = float(np.nanmedian(tr.sog[seg])) if np.isfinite(tr.sog[seg]).any() else 0.0
                if med_sog <= cfg.loiter_max_speed_kn:
                    ev = _loiter_event(tr, i, j, dur, med_sog, ctx, cfg)
                    if ev is not None:
                        out.append(ev)
                    i = j + 1
                    continue
            i += 1
    return _merge_overlaps(out)


def _loiter_event(tr: Track, i: int, j: int, dur: float, med_sog: float, ctx: DetectionContext,
                  cfg: DetectionConfig) -> Event | None:
    la, lo = float(np.mean(tr.lat[i:j + 1])), float(np.mean(tr.lon[i:j + 1]))
    in_benign = float(np.mean(ctx.benign_mask(tr.lat[i:j + 1], tr.lon[i:j + 1])))
    if in_benign > 0.6 or ctx.nearest_zone(la, lo, BENIGN_AREA_KINDS)[1] <= cfg.loiter_radius_nm or (in_benign > 0.4 and bool(ctx.benign_mask(np.array([la]), np.array([lo]))[0])):
        return None  # waiting at anchorage / alongside / in port approaches
    in_fish = ctx.in_kinds(tr.lat[i:j + 1], tr.lon[i:j + 1], ("fishing_ground",)).mean() > 0.5
    if in_fish and tr.ship_type == "fishing":
        return None  # fishing vessels working a fishing ground
    in_sensitive = ctx.in_kinds(tr.lat[i:j + 1], tr.lon[i:j + 1], SENSITIVE_KINDS).mean() > 0.5
    if in_sensitive:
        return None  # reported as zone_entry, which carries the stronger evidence
    port_nm = ctx.nearest_port_nm(la, lo)
    zone, dz = ctx.nearest_zone(la, lo, SENSITIVE_KINDS)
    sev = 40 + 30 * min(1.0, (dur / 60 - cfg.loiter_min_minutes) / (cfg.loiter_min_minutes * 2))
    ev = [f"Stayed within {cfg.loiter_radius_nm:g} nm of {fmt_pos(la, lo)} for {fmt_dur(dur)} at a median {med_sog:.1f} kn."]
    if port_nm > 15:
        sev += 10
        ev.append(f"Open water, {port_nm:.0f} nm from the nearest port or approach.")
    if zone is not None and dz <= 10:
        sev += 18
        ev.append(f"Only {dz:.0f} nm from {zone.name}.")
    if tr.ship_type in ("tanker", "cargo"):
        sev += 5
        ev.append(f"A {tr.ship_type} has no routine operational reason to idle here.")
    elif tr.ship_type == "fishing":
        sev -= 15
        ev.append("Fishing-type vessels often idle; weighting reduced.")
    elif tr.ship_type in SERVICE_TYPES and port_nm < 0.5:
        sev -= 22
        ev.append(f"A {tr.ship_type} vessel - waiting around is routine for this type; weighting reduced.")
    elif tr.ship_type in ("passenger", "ferry") and port_nm < 0.5:
        sev -= 12
        ev.append("Passenger vessels lay over at terminals between runs; weighting reduced.")
    elif tr.ship_type == "pleasure":
        sev -= 20
        ev.append("Recreational craft often drift, circle or idle; weighting reduced.")
    conf = 0.35 + 0.45 * _data_quality(tr, i, j, ctx)
    if ctx.habits is not None and ctx.habits.is_habitual(tr.mmsi, la, lo):
        sev -= 28
        ev.append("This vessel has dwelled in this same spot before in its own history - part of its usual pattern.")
    if in_fish:
        sev -= 10
    return Event("", "loitering", [tr.mmsi], float(tr.t[i]), float(tr.t[j]), la, lo, _clip(sev), _clip(conf, 0.1, 0.95),
                 f"{tr.name}: loitering for {fmt_dur(dur)}", ev,
                 ["Weather shelter / hove-to", "Waiting for a berth, pilot or cargo orders", "Engine trouble or drifting"],
                 ["AIS shows motion, not purpose - loitering is not evidence of wrongdoing."],
                 {"duration_s": float(dur), "median_sog_kn": round(med_sog, 2), "port_nm": round(port_nm, 1)},
                 path=[(float(a), float(b)) for a, b in zip(tr.lat[i:j + 1:max(1, (j - i) // 40)], tr.lon[i:j + 1:max(1, (j - i) // 40)])])


def _merge_overlaps(events: list[Event]) -> list[Event]:
    return events


# --------------------------------------------------------------------------- #
# Proximity: rendezvous (pairs) and clusters (groups)
# --------------------------------------------------------------------------- #
GRID_S = 300.0


def _resample(tracks: list[Track], t0: float, t1: float, ctx: DetectionContext):
    grid = np.arange(t0, t1 + 1, GRID_S)
    V, K = len(tracks), grid.size
    lat = np.full((V, K), np.nan)
    lon = np.full((V, K), np.nan)
    sog = np.full((V, K), np.nan)
    stat = np.zeros((V, K), bool)
    for v, tr in enumerate(tracks):
        if len(tr) < 2:
            continue
        inside = (grid >= tr.t[0]) & (grid <= tr.t[-1])
        gi = np.searchsorted(tr.t, grid[inside])
        gi = np.clip(gi, 1, len(tr) - 1)
        near = np.minimum(grid[inside] - tr.t[gi - 1], tr.t[gi] - grid[inside])
        good = near <= 1200  # only trust the grid where fixes bracket it closely
        idx = np.where(inside)[0][good]
        lat[v, idx] = np.interp(grid[idx], tr.t, tr.lat)
        lon[v, idx] = np.interp(grid[idx], tr.t, tr.lon)
        sog[v, idx] = np.interp(grid[idx], tr.t, np.nan_to_num(tr.sog, nan=0.0))
        if tr.status is not None:
            prev = np.clip(np.searchsorted(tr.t, grid[idx], side="right") - 1, 0, len(tr) - 1)
            stat[v, idx] = np.isin(tr.status[prev], STATIC_STATUS)
    return grid, lat, lon, sog, stat


def detect_proximity(tracks: list[Track], t0: float, t1: float, ctx: DetectionContext, cfg: DetectionConfig) -> list[Event]:
    if len(tracks) < 2:
        return []
    grid, LAT, LON, SOG, STAT = _resample(tracks, t0, t1, ctx)
    V, K = LAT.shape
    exempt = np.zeros((V, K), bool)  # in port / anchorage, or fishing vessel in a fishing ground
    for v, tr in enumerate(tracks):
        if is_berthed(tr):
            exempt[v, :] = True
        ok = ~np.isnan(LAT[v])
        if ok.any():
            m = ctx.benign_mask(LAT[v, ok], LON[v, ok])
            if tr.ship_type == "fishing":
                m |= ctx.in_kinds(LAT[v, ok], LON[v, ok], ("fishing_ground",))
            exempt[v, np.where(ok)[0][m]] = True
    exempt |= STAT  # declared at anchor / moored

    prox_m = cfg.proximity_distance_nm * NM_M
    clus_m = cfg.cluster_distance_nm * NM_M
    pair_run: dict[tuple[int, int], list[int]] = {}
    pair_done: list[tuple[tuple[int, int], int, int]] = []
    groups: list[dict] = []
    group_done: list[dict] = []

    for k in range(K):
        idx = np.where(~np.isnan(LAT[:, k]) & ~exempt[:, k])[0]
        pairs_now: set[tuple[int, int]] = set()
        comps: list[set[int]] = []
        if idx.size >= 2:
            x, y = project_xy_m(LAT[idx, k], LON[idx, k])
            tree = cKDTree(np.c_[x, y])
            for a, b in tree.query_pairs(prox_m):
                va, vb = int(idx[a]), int(idx[b])
                if SOG[va, k] <= cfg.rendezvous_max_speed_kn and SOG[vb, k] <= cfg.rendezvous_max_speed_kn:
                    pairs_now.add((min(va, vb), max(va, vb)))
            # connected components at cluster distance
            parent = list(range(idx.size))

            def find(a):
                while parent[a] != a:
                    parent[a] = parent[parent[a]]
                    a = parent[a]
                return a

            for a, b in tree.query_pairs(clus_m):
                parent[find(a)] = find(b)
            buckets = defaultdict(set)
            for a in range(idx.size):
                buckets[find(a)].add(int(idx[a]))
            comps = [c for c in buckets.values() if len(c) >= cfg.cluster_min_vessels]
        # rendezvous pair runs (tolerate one missing step)
        for p in pairs_now:
            if p in pair_run:
                pair_run[p][1] = k
                pair_run[p][2] += 1
            else:
                pair_run[p] = [k, k, 1]
        for p in [p for p, r in pair_run.items() if r[1] < k - 1]:
            r = pair_run.pop(p)
            pair_done.append((p, r[0], r[1], r[2]))
        # cluster group tracking by membership overlap
        used = set()
        for comp in comps:
            best, bj = None, 0.0
            for gi, g in enumerate(groups):
                if gi in used:
                    continue
                jac = len(comp & g["members"]) / len(comp | g["members"])
                if jac > bj:
                    best, bj = gi, jac
            if best is not None and bj >= 0.5:
                g = groups[best]
                used.add(best)
                g["last"] = k
                g["members"] = comp | g["members"]
                for v in comp:
                    g["count"][v] += 1
                g["steps"] += 1
                g["maxsize"] = max(g["maxsize"], len(comp))
            else:
                groups.append({"first": k, "last": k, "members": set(comp), "count": defaultdict(int, {v: 1 for v in comp}),
                               "steps": 1, "maxsize": len(comp)})
                used.add(len(groups) - 1)
        for g in [g for g in groups if g["last"] < k - 1]:
            groups.remove(g)
            group_done.append(g)
    for p, r in pair_run.items():
        pair_done.append((p, r[0], r[1], r[2]))
    group_done.extend(groups)

    out: list[Event] = []
    for (va, vb), k0, k1, steps in pair_done:
        dur = (k1 - k0 + 1) * GRID_S
        if dur < cfg.rendezvous_min_minutes * 60 or steps < 0.6 * (k1 - k0 + 1):
            continue
        a, b = tracks[va], tracks[vb]
        if a.ship_type == "pleasure" and b.ship_type == "pleasure":
            continue  # recreational boats rafting up / racing together
        la, lo = float(np.nanmean(LAT[[va, vb], k0:k1 + 1])), float(np.nanmean(LON[[va, vb], k0:k1 + 1]))
        sep = float(np.nanmean(haversine_m(LAT[va, k0:k1 + 1], LON[va, k0:k1 + 1], LAT[vb, k0:k1 + 1], LON[vb, k0:k1 + 1]))) / NM_M
        port_nm = ctx.nearest_port_nm(la, lo)
        zone, dz = ctx.nearest_zone(la, lo, SENSITIVE_KINDS)
        sev = 45 + 25 * min(1.0, (dur / 60 - cfg.rendezvous_min_minutes) / (cfg.rendezvous_min_minutes * 2))
        ev = [f"{a.name} and {b.name} stayed within {sep:.2f} nm of each other for {fmt_dur(dur)}, both below {cfg.rendezvous_max_speed_kn:g} kn."]
        if port_nm > 10:
            sev += 10
            ev.append(f"{port_nm:.0f} nm from the nearest port - no harbour reason to meet.")
        if "tanker" in (a.ship_type, b.ship_type):
            sev += 8
            ev.append("At least one vessel is a tanker - the profile of a ship-to-ship transfer.")
        if zone is not None and dz <= 15:
            sev += 8
            ev.append(f"{dz:.0f} nm from {zone.name}.")
        out.append(Event("", "rendezvous", [a.mmsi, b.mmsi], float(grid[k0]), float(grid[k1]), la, lo, _clip(sev),
                         _clip(0.45 + 0.45 * min(_data_quality(a, 0, len(a) - 1, ctx), _data_quality(b, 0, len(b) - 1, ctx)), 0.1, 0.95),
                         f"{a.name} + {b.name}: slow rendezvous at sea for {fmt_dur(dur)}", ev,
                         ["Legitimate bunkering or crew/cargo transfer", "Towage or escort", "Both waiting for the same berth or weather"],
                         ["Proximity alone does not show that cargo was exchanged."],
                         {"duration_s": dur, "separation_nm": round(sep, 2), "port_nm": round(port_nm, 1)},
                         path=[(float(LAT[va, k]), float(LON[va, k])) for k in range(k0, k1 + 1, max(1, (k1 - k0) // 20)) if not np.isnan(LAT[va, k])]))
    for g in group_done:
        k0, k1 = g["first"], g["last"]
        dur = (k1 - k0 + 1) * GRID_S
        core = [v for v, c in g["count"].items() if c >= 0.5 * g["steps"]]
        if dur < cfg.cluster_min_minutes * 60 or len(core) < cfg.cluster_min_vessels:
            continue
        med = float(np.nanmedian(SOG[core, k0:k1 + 1]))
        if med > cfg.loiter_max_speed_kn:
            continue  # a moving convoy on a lane is not an assembly
        la, lo = float(np.nanmean(LAT[core, k0:k1 + 1])), float(np.nanmean(LON[core, k0:k1 + 1]))
        port_nm = ctx.nearest_port_nm(la, lo)
        zone, dz = ctx.nearest_zone(la, lo, SENSITIVE_KINDS)
        sev = 45 + 20 * min(1.0, (len(core) - cfg.cluster_min_vessels) / 4) + 15 * min(1.0, (dur / 60 - cfg.cluster_min_minutes) / 120)
        ev = [f"{len(core)} vessels gathered within {cfg.cluster_distance_nm:g} nm for {fmt_dur(dur)}, median speed {med:.1f} kn.",
              "Outside any port, anchorage or fishing ground."]
        if zone is not None and dz <= 20:
            sev += 10
            ev.append(f"{dz:.0f} nm from {zone.name}.")
        recreational = sum(tracks[v].ship_type in SERVICE_TYPES + ("pleasure", "passenger", "ferry") for v in core)
        if recreational >= 0.5 * len(core):
            continue  # boats congregating at a marina / terminal / regatta is not an unusual assembly
        names = ", ".join(tracks[v].name for v in core[:3]) + ("…" if len(core) > 3 else "")
        out.append(Event("", "cluster", [tracks[v].mmsi for v in core], float(grid[k0]), float(grid[k1]), la, lo, _clip(sev), 0.7,
                         f"Cluster of {len(core)} vessels ({names}) for {fmt_dur(dur)}", ev,
                         ["Weather refuge", "Search-and-rescue or rescue-at-sea response", "Informal fishing aggregation"],
                         ["Group size is estimated from 5-minute interpolated positions."],
                         {"vessels": len(core), "duration_s": dur, "median_sog_kn": round(med, 2)}))
    return out


# --------------------------------------------------------------------------- #
# Zone entry
# --------------------------------------------------------------------------- #
def detect_zone_entries(tracks: list[Track], ctx: DetectionContext, cfg: DetectionConfig) -> list[Event]:
    out: list[Event] = []
    base = {"cable": 58, "restricted": 55, "protected": 45}
    for tr in tracks:
        if tr.mmsi in ctx.allowlist or len(tr) < 2:
            continue
        t, la, lo, sg = TrafficBaseline.densify(tr, 0.5)
        for z in ctx.zones:
            if z.kind not in SENSITIVE_KINDS or tr.mmsi in ctx.habitual.get(z.id, ()):
                continue  # routine users of a zone (seen entering it in the history) are not unusual
            inside = ctx.in_zone(z, la, lo)
            if not inside.any():
                continue
            edges = np.diff(np.concatenate([[0], inside.astype(int), [0]]))
            for s, e in zip(np.where(edges == 1)[0], np.where(edges == -1)[0] - 1):
                dwell = t[e] - t[s]
                if dwell < cfg.zone_min_dwell_minutes * 60:
                    continue
                slow = float(np.nanmin(sg[s:e + 1])) < 3.0 and dwell > 600
                sev = base[z.kind] * (0.6 + 0.4 * z.sensitivity) + 8 * min(1.0, dwell / 3600)
                ev = [f"Entered {z.name} ({z.kind}) at {fmt_pos(la[s], lo[s])} and stayed {fmt_dur(max(dwell, 60))}."]
                if slow:
                    sev += 15
                    ev.append("The vessel slowed to a stop inside the zone" + (" - consistent with anchoring over a cable." if z.kind == "cable" else "."))
                if tr.ship_type in ("cargo", "tanker") and z.kind in ("restricted", "protected"):
                    sev += 5
                    ev.append(f"A {tr.ship_type} has no listed authorisation for this zone.")
                out.append(Event("", "zone_entry", [tr.mmsi], float(t[s]), float(t[e]), float(la[s:e + 1].mean()),
                                 float(lo[s:e + 1].mean()), _clip(sev), 0.8,
                                 f"{tr.name}: entered {z.name}", ev,
                                 ["Authorised transit not on the watch-list", "Emergency diversion or weather avoidance",
                                  "Chart or navigation error"],
                                 ["The zone boundary is approximate; a crossing within ~0.5 nm of the edge may be a position error."],
                                 {"dwell_s": float(dwell), "zone": z.id, "min_sog_kn": round(float(np.nanmin(sg[s:e + 1])), 1)},
                                 zone_id=z.id,
                                 path=[(float(a), float(b)) for a, b in zip(la[s:e + 1:max(1, (e - s) // 30)], lo[s:e + 1:max(1, (e - s) // 30)])]))
    return out


def learn_zone_habits(history: list[Track], ctx: DetectionContext, cfg: DetectionConfig) -> dict[str, set[str]]:
    """Which vessels enter each sensitive zone as a matter of routine, from a stretch of past traffic."""

    saved, ctx.habitual = ctx.habitual, {}
    habits: dict[str, set[str]] = {}
    for e in detect_zone_entries(history, ctx, cfg):
        habits.setdefault(e.zone_id or "", set()).update(e.mmsis)
    ctx.habitual = saved
    return habits


# --------------------------------------------------------------------------- #
# Kinematic plausibility: position spoofing + identity conflicts
# --------------------------------------------------------------------------- #
def detect_kinematics(tracks: list[Track], ctx: DetectionContext, cfg: DetectionConfig) -> list[Event]:
    out: list[Event] = []
    for tr in tracks:
        if len(tr) < 4:
            continue
        dt = np.diff(tr.t)
        d_nm = haversine_m(tr.lat[:-1], tr.lon[:-1], tr.lat[1:], tr.lon[1:]) / NM_M
        v = np.where(dt > 0, d_nm / np.maximum(dt, 1.0) * 3600, 0.0)
        bad = np.where((v >= cfg.jump_min_implied_knots) & (d_nm >= cfg.jump_min_distance_nm))[0]
        if bad.size == 0:
            continue
        clusters: list[list[int]] = [[int(bad[0])]]
        for b in bad[1:]:
            if tr.t[b] - tr.t[clusters[-1][-1]] <= 3600:
                clusters[-1].append(int(b))
            else:
                clusters.append([int(b)])
        for cl in clusters:
            i0, i1 = cl[0], cl[-1] + 1
            jump_nm = float(np.max(d_nm[cl]))
            peak = float(np.max(v[cl]))
            rep = float(np.nanmedian(tr.sog[max(0, i0 - 3):i1 + 1]))
            path = [(float(a), float(b)) for a, b in zip(tr.lat[max(0, i0 - 1):i1 + 2], tr.lon[max(0, i0 - 1):i1 + 2])]
            la, lo = float(tr.lat[i0]), float(tr.lon[i0])
            if len(cl) >= cfg.identity_min_alternations:
                span = tr.t[i1] - tr.t[i0]
                sev = 78 + 12 * min(1.0, len(cl) / 20)
                ev = [f"Position alternated between two places ~{jump_nm:.0f} nm apart {len(cl)} times in {fmt_dur(span)}.",
                      "No vessel can be in both places - two transmitters appear to be using the same MMSI."]
                out.append(Event("", "identity_conflict", [tr.mmsi], float(tr.t[i0]), float(tr.t[i1]), la, lo, _clip(sev), 0.85,
                                 f"{tr.name}: MMSI reported from two locations", ev,
                                 ["Misconfigured duplicate transponder", "Data-feed merge error upstream"],
                                 ["Which of the two sources is genuine cannot be decided from AIS alone."],
                                 {"alternations": len(cl), "separation_nm": round(jump_nm, 1)}, path=path))
            else:
                returned = len(cl) >= 2
                sev = 60 + 20 * min(1.0, peak / (cfg.jump_min_implied_knots * 4)) + (8 if returned else 0)
                ev = [f"Reported position jumped {jump_nm:.0f} nm in {fmt_dur(tr.t[i0 + 1] - tr.t[i0])} (implies {peak:.0f} kn).",
                      f"Reported speed stayed {rep:.1f} kn - the jump is not explained by the vessel's own motion."]
                if returned:
                    ev.append("The track then returned to the original course - a displaced-position (spoofing-style) signature.")
                out.append(Event("", "position_jump", [tr.mmsi], float(tr.t[i0]), float(tr.t[i1]), la, lo, _clip(sev), 0.8,
                                 f"{tr.name}: implausible position jump of {jump_nm:.0f} nm", ev,
                                 ["GNSS multipath or receiver glitch", "Corrupted message / decoding error", "Deliberate position falsification"],
                                 ["A SAR or optical look at the reported position would show whether a vessel is really there."],
                                 {"jump_nm": round(jump_nm, 1), "implied_kn": round(peak, 0), "returned": returned}, path=path))
    return out


# --------------------------------------------------------------------------- #
# Pattern of life: travel through water normal traffic doesn't use
# --------------------------------------------------------------------------- #
def detect_route_deviation(tracks: list[Track], ctx: DetectionContext, cfg: DetectionConfig) -> list[Event]:
    if ctx.baseline is None or not ctx.baseline.counts:
        return []
    out: list[Event] = []
    for tr in tracks:
        if len(tr) < 4 or tr.ship_type in ("fishing",):
            continue
        t, la, lo, sg = TrafficBaseline.densify(tr, 1.0)
        fam = ctx.baseline.familiarity(la, lo)
        under = np.nan_to_num(sg, nan=0.0) >= cfg.deviation_min_speed_kn
        exempt = ctx.benign_mask(la, lo) | ctx.in_kinds(la, lo, ("fishing_ground",))
        odd = (fam < cfg.deviation_familiarity) & under & ~exempt
        if not odd.any():
            continue
        edges = np.diff(np.concatenate([[0], odd.astype(int), [0]]))
        for s, e in zip(np.where(edges == 1)[0], np.where(edges == -1)[0] - 1):
            dur = t[e] - t[s]
            if dur < cfg.deviation_min_minutes * 60:
                continue
            dist = float(np.sum(haversine_m(la[s:e], lo[s:e], la[s + 1:e + 1], lo[s + 1:e + 1]))) / NM_M
            share = float(np.mean(fam[s:e + 1] < 0.1))
            sev = 40 + 30 * min(1.0, (dur / 60 - cfg.deviation_min_minutes) / (cfg.deviation_min_minutes * 2)) + 12 * share
            ev = [f"Travelled {dist:.0f} nm over {fmt_dur(dur)} through water that few historic vessels have used (pattern-of-life baseline of {ctx.baseline.n_vessels} vessels).",
                  f"{share * 100:.0f}% of that stretch has no recorded historic traffic at all."]
            out.append(Event("", "route_deviation", [tr.mmsi], float(t[s]), float(t[e]), float(la[s:e + 1].mean()),
                             float(lo[s:e + 1].mean()), _clip(sev), _clip(0.4 + 0.4 * min(1.0, ctx.baseline.n_vessels / 100), 0.2, 0.85),
                             f"{tr.name}: off the usual routes for {fmt_dur(dur)}", ev,
                             ["Weather routing around a storm", "Traffic avoidance or pilot instruction", "Search-and-rescue diversion"],
                             ["The baseline only knows past traffic in this dataset; new but legitimate routes look unusual until learned."],
                             {"duration_s": float(dur), "distance_nm": round(dist, 1), "unfamiliar_share": round(share, 2)},
                             path=[(float(a), float(b)) for a, b in zip(la[s:e + 1:max(1, (e - s) // 40)], lo[s:e + 1:max(1, (e - s) // 40)])]))
    return out


def detect_status_mismatch(tracks: list[Track], ctx: DetectionContext, cfg: DetectionConfig) -> list[Event]:
    """Navigational status says anchored / moored, yet the vessel is moving - stale or falsified status."""

    out: list[Event] = []
    for tr in tracks:
        if tr.status is None or len(tr) < 5:
            continue
        bad = np.isin(tr.status, STATIC_STATUS) & (np.nan_to_num(tr.sog, nan=0.0) >= 3.0)
        if bad.sum() < 3:
            continue
        edges = np.diff(np.concatenate([[0], bad.astype(int), [0]]))
        for s_, e_ in zip(np.where(edges == 1)[0], np.where(edges == -1)[0] - 1):
            dur = tr.t[e_] - tr.t[s_]
            if e_ - s_ + 1 < 3 or dur < 15 * 60:
                continue
            speed = float(np.nanmedian(tr.sog[s_:e_ + 1]))
            dist = float(haversine_m(tr.lat[s_], tr.lon[s_], tr.lat[e_], tr.lon[e_])) / NM_M
            if dist < 0.5:
                continue
            sev = 48 + 20 * min(1.0, dur / 3600) + 8 * min(1.0, speed / 12)
            out.append(Event("", "status_mismatch", [tr.mmsi], float(tr.t[s_]), float(tr.t[e_]), float(tr.lat[s_]), float(tr.lon[s_]),
                             _clip(sev), 0.75, f"{tr.name}: declares moored/at anchor but is moving",
                             [f"Navigational status says '{'at anchor' if int(tr.status[s_]) == 1 else 'moored'}' while the vessel moved {dist:.1f} nm at ~{speed:.0f} kn over {fmt_dur(dur)}.",
                              "Status is typed in by the crew; a stale value is common, a deliberately false one hides intent."],
                             ["Crew forgot to update the status", "Dragging anchor or drifting"],
                             ["Navigational status is self-reported and often left unchanged."],
                             {"duration_s": float(dur), "distance_nm": round(dist, 1), "sog_kn": round(speed, 1)},
                             path=[(float(a), float(b)) for a, b in zip(tr.lat[s_:e_ + 1:max(1, (e_ - s_) // 20)], tr.lon[s_:e_ + 1:max(1, (e_ - s_) // 20)])]))
    return out


DETECTORS: dict[str, Callable] = {}


def _group_context(events: list[Event]) -> None:
    """A loiterer surrounded by several other *notable* loiterers is part of a gathering, not a lone dweller."""

    loit = [e for e in events if e.kind == "loitering" and e.severity >= 35 and "gathering" not in e.metrics]
    for e in list(loit):
        if any("same spot before" in z for z in e.evidence):
            continue  # already explained by the vessel's own routine
        near = [o for o in loit if o is not e and o.mmsis != e.mmsis and o.t_start <= e.t_end and o.t_end >= e.t_start
                and float(haversine_m(e.lat, e.lon, o.lat, o.lon)) <= 3 * NM_M]
        if len(near) >= 3:
            e.severity = _clip(e.severity - 18)
            e.evidence.append(f"{len(near)} other vessels were loitering within 3 nm at the same time - a gathering "
                              "(regatta, fleet activity, weather refuge) rather than a lone vessel.")
            e.metrics["gathering"] = len(near) + 1


def run_all(tracks: list[Track], t0: float, t1: float, ctx: DetectionContext, cfg: DetectionConfig) -> list[Event]:
    events: list[Event] = []
    events += detect_gaps(tracks, ctx, cfg)
    events += detect_loitering(tracks, ctx, cfg)
    events += detect_proximity(tracks, t0, t1, ctx, cfg)
    events += detect_zone_entries(tracks, ctx, cfg)
    events += detect_kinematics(tracks, ctx, cfg)
    events += detect_status_mismatch(tracks, ctx, cfg)
    events += detect_route_deviation(tracks, ctx, cfg)
    _group_context(events)
    events.sort(key=lambda e: e.t_start)
    for n, e in enumerate(events, 1):
        e.id = f"E{n:03d}"
    return events
