"""Cable-area activity: a vessel of ANY type (fishing hulls included) that is slow or stopped on a charted submarine cable, away from harbours.

This is the signature of the publicly reported cable-damage cases (anchor dragged or lowered over a cable): the hull type does not matter, the
place and the behaviour do. It deliberately ignores harbours and the first few miles off any coast, where cables run to shore and boats legitimately
stop. Cable routes are an approximate public map, so the corridor is taken as 2 nm either side.

Not a finding of damage or intent. Innocent explanations: fishing close to a cable, cable maintenance, waiting for weather, mechanical trouble.
"""

from __future__ import annotations

import numpy as np

from .cables import Cables
from .config import DetectionConfig
from .context import DetectionContext
from .detectors import fmt_dur
from .models import Event, Track

CORRIDOR_NM = 2.0
MAX_KN = 3.0
MIN_COAST_NM = 3.0
MAX_HOURS = 8.0
CROWD = 6


def detect_cable_activity(tracks: list[Track], ctx: DetectionContext, cfg: DetectionConfig) -> list[Event]:
    cab, terr = Cables.default(), getattr(ctx, "territory", None)
    if cab is None or terr is None:
        return []
    min_s = max(2700.0, cfg.loiter_min_minutes * 60.0 * 0.5) if cfg.grid_s <= 600 else 3 * 3600.0
    out: list[Event] = []
    # who else is slow nearby, hour by hour: a crowd of slow boats is a fishing ground or an anchorage, a LONE boat stopped on a cable is the signal
    crowd: dict[tuple[int, int, int], set[str]] = {}
    for tr in tracks:
        sl = np.nan_to_num(tr.sog, nan=0.0) <= MAX_KN
        for i in np.where(sl)[0][::3]:
            crowd.setdefault((int(tr.lat[i] / 0.05), int(tr.lon[i] / 0.05), int(tr.t[i] // 3600)), set()).add(tr.mmsi)

    def crowd_size(lat: float, lon: float, t0: float, t1: float) -> int:
        ci, cj = int(lat / 0.05), int(lon / 0.05)
        best = 0
        for h in range(int(t0 // 3600), int(t1 // 3600) + 1):
            s_: set[str] = set()
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    s_ |= crowd.get((ci + di, cj + dj, h), set())
            best = max(best, len(s_))
        return best

    for tr in tracks:
        if len(tr) < 6:
            continue
        near = cab.distance_nm(tr.lat, tr.lon) <= CORRIDOR_NM
        if not near.any():
            continue
        sp = tr.sog[np.isfinite(tr.sog)]
        if len(sp) < 6 or float(np.percentile(sp, 95)) < 4.0:
            ctx.skip("cable_activity", "never moves at ship speed (fish farm, buoy or other fixed object)")
            continue
        slow = np.nan_to_num(tr.sog, nan=0.0) <= MAX_KN
        offshore = terr.coast_nm(tr.lat, tr.lon) >= MIN_COAST_NM
        in_area = terr.distance_nm(tr.lat, tr.lon) <= 250.0
        m = near & slow & offshore & in_area & ~ctx.benign_mask(tr.lat, tr.lon)
        idx = np.where(m)[0]
        if len(idx) < 3:
            continue
        # split into runs separated by more than an hour
        runs = np.split(idx, np.where(np.diff(tr.t[idx]) > 3600.0)[0] + 1)
        for run in runs:
            a, b = int(run[0]), int(run[-1])
            dur = float(tr.t[b] - tr.t[a])
            if dur < min_s or len(run) < 3:
                continue
            if dur > MAX_HOURS * 3600.0 and float(np.ptp(tr.lat[run]) * 60.0) < 0.5 and float(np.ptp(tr.lon[run]) * 55.0) < 0.5:
                ctx.skip("cable_activity", "fixed for many hours on one spot (installation or mooring)")
                continue
            lat, lon = float(np.mean(tr.lat[run])), float(np.mean(tr.lon[run]))
            n_near = crowd_size(lat, lon, float(tr.t[a]), float(tr.t[b]))
            if n_near >= CROWD:
                ctx.skip("cable_activity", f"{CROWD}+ vessels slow in the same area (fishing ground or anchorage)")
                continue
            cname = cab.nearest_name(lat, lon)
            dmin = float(cab.distance_nm(tr.lat[run], tr.lon[run]).min())
            med = float(np.median(np.nan_to_num(tr.sog[run], nan=0.0)))
            cover = float(len(run)) / max(1.0, float(b - a + 1))
            sev = 62.0 + min(18.0, dur / 3600.0 * 3.0) + (6.0 if med < 1.0 else 0.0)
            if tr.status is not None and int(np.median(np.asarray(tr.status)[run])) not in (1, 5):
                sev += 4.0  # not declaring itself anchored / moored while stopped on the cable
            ev = [f"CABLE AREA: {fmt_dur(dur)} slow (median {med:.1f} kn) within {CORRIDOR_NM:g} nm of the charted cable '{cname}' (closest {dmin:.1f} nm), "
                  f"{float(np.median(terr.coast_nm(tr.lat[run], tr.lon[run]))):.0f} nm from the nearest coast, outside any harbour or learned stopping area, with only {n_near - 1} other slow vessel(s) within about 6 km.",
                  f"VESSEL: {tr.name} ({tr.ship_type}{', flag ' + tr.flag if tr.flag else ''}); the hull type does not clear it, fishing vessels are among the "
                  f"publicly reported cases of cable damage.",
                  "The cable route is an approximate public map; the vessel may be a few miles from the real cable."]
            out.append(Event("", "cable_activity", [tr.mmsi], float(tr.t[a]), float(tr.t[b]), lat, lon, float(min(sev, 92.0)), 0.7, f"{tr.name}: slow on cable {cname}", ev,
                             ["Fishing close to a cable", "Cable maintenance or inspection", "Waiting for weather or a berth", "Engine trouble"],
                             ["AIS cannot show whether an anchor or gear was lowered, nor any damage."],
                             {"cable": cname, "cable_nm": round(dmin, 1), "median_kn": round(med, 1), "minutes": round(dur / 60.0), "coverage": round(cover, 2)},
                             path=[(float(p), float(q)) for p, q in zip(tr.lat[a:b + 1:max(1, (b - a) // 40)], tr.lon[a:b + 1:max(1, (b - a) // 40)])]))
    return out
