"""Suspected unauthorised survey: the three-factor model from the mentor, plus the track pattern.

Factors evaluated for every vessel:

  T  TERRITORY    where it is: inside Taiwan's territorial sea (<= 12 nm), contiguous zone (12-24 nm), or the economic zone
                  (approx.). A breach by a foreign survey vessel is the clearest signal.            -> territory.py
  V  VELOCITY     survey work is done slowly: the share of time in the 5-10 kn band the mentor gave.  (speed band is configurable)
  A  AIS DECLARED the vessel itself says it is a survey / research vessel (class, name, destination).   -> declared.py
  P  PATTERN      repeated parallel or zig-zag legs (lawnmower), the shape of mapping a seabed or cable. -> survey.py

Rules (the first that fires with the highest severity names the activity; every rule states what it needs):

  R1  declared survey vessel inside the territorial sea / contiguous zone
  R2  survey pattern inside the territorial sea / contiguous zone
  R3  survey pattern in the economic zone
  R4  declared survey vessel working at survey speed in the economic zone
  R5  survey pattern outside Taiwan's claimed waters (observed behaviour only)
  R6  foreign state vessel (coast guard etc.) inside the territorial sea
  R0  the same activity by a Taiwan-registered vessel: recorded as expected, not raised

None of this proves intent or illegality. Whether research is authorised depends on consent that AIS cannot show.
"""

from __future__ import annotations

import numpy as np

from .config import DetectionConfig
from .context import DetectionContext
from .cables import Cables
from .declared import assess
from .models import Event, Track
from .survey import is_exempt, survey_windows
from .territory import CODE, LABEL

TAIWAN_MID = "416"
DECLARED_MIN = 0.6  # a feed-derived class alone (0.5) is not enough; a name / destination self-declaration (>= 0.85) is
BENIGN_SURVEY = [
    "Consented marine scientific research (coastal-state consent cannot be seen in AIS)",
    "Commercial seismic or hydrographic survey under licence",
    "Cable laying, repair or inspection under notification",
    "Search for a lost object or a rescue operation",
]
UNCERTAIN = [
    "AIS shows the track and what the vessel says about itself, not the instrument deployed or whether the coastal state consented.",
    "Zone limits are computed from public coastlines (reference geometry, not legal baselines); hourly positions carry ~3 nm of error.",
]


def _band_share(sog: np.ndarray, lo: float, hi: float) -> tuple[float, float]:
    """(share of fixes inside [lo, hi], median speed) - NaN speeds are ignored."""

    v = sog[np.isfinite(sog)]
    if len(v) == 0:
        return 0.0, float("nan")
    return float(np.mean((v >= lo) & (v <= hi))), float(np.median(v))


def _zones(terr, tr: Track, a: int, b: int, edge: float) -> dict:
    lat, lon = tr.lat[a:b + 1], tr.lon[a:b + 1]
    code = terr.code_at(lat, lon)
    dist = terr.distance_nm(lat, lon)
    ts = code == CODE["TS"]
    cz = code == CODE["CZ"]
    eez = code == CODE["EEZ"]
    return {
        "n": int(len(code)), "ts": int(ts.sum()), "cz": int(cz.sum()), "eez": int(eez.sum()),
        "ts_clear": int((ts & (dist <= 12.0 - edge)).sum()), "nearest_nm": float(np.min(dist)) if len(dist) else float("nan"),
        "ts_mask": ts, "cz_mask": cz, "eez_mask": eez,
    }


def _fmt(x: float, nd: int = 0) -> str:
    return "n/a" if x is None or not np.isfinite(x) else f"{x:.{nd}f}"


def detect_survey_threat(tracks: list[Track], ctx: DetectionContext, cfg: DetectionConfig) -> list[Event]:
    terr = ctx.territory
    if terr is None:
        return []
    edge = cfg.threat_edge_nm
    lo, hi = cfg.threat_speed_lo_kn, cfg.threat_speed_hi_kn
    out: list[Event] = []
    for tr in tracks:
        if len(tr) < 4:
            continue
        decl = assess(tr)
        wins = [] if is_exempt(tr) else survey_windows(tr, cfg, ctx.benign_mask)
        if decl.score < DECLARED_MIN and not wins and decl.state_class is None:
            ctx.skip("survey_threat", "no declaration, no pattern, not a state vessel")
            continue
        foreign = not (tr.mmsi.startswith(TAIWAN_MID) or tr.flag in ("TWN", "TW"))
        covered = np.zeros(len(tr), bool)
        candidates: list[tuple[float, str, str, int, int, dict]] = []  # (severity, rule, label, a, b, details)

        for a, b, pat in wins:
            z = _zones(terr, tr, a, b, edge)
            share, med = _band_share(tr.sog[a:b + 1], lo, hi)
            details = {"pattern": pat, "zones": z, "v_share": share, "v_median": med}
            n_w = z["ts"] + z["cz"]
            if not foreign:
                candidates.append((30.0, "R0", "Domestic (Taiwan-registered) survey - expected activity", a, b, details))
            elif n_w >= 2 or (z["ts_clear"] >= 1):
                sev = 85 + (5 if decl.score >= DECLARED_MIN else 0) + (5 if share >= 0.5 else 0)
                candidates.append((sev, "R2", "Survey-like pattern inside Taiwan's territorial sea / contiguous zone", a, b, details))
            elif z["eez"] >= 2:
                sev = 72 + (6 if decl.score >= DECLARED_MIN else 0) + (4 if share >= 0.5 else 0)
                candidates.append((sev, "R3", "Survey-like pattern in Taiwan's exclusive economic zone", a, b, details))
            else:
                sev = 55 + (6 if decl.score >= DECLARED_MIN else 0) + (3 if share >= 0.5 else 0)
                candidates.append((sev, "R5", "Survey-like pattern outside Taiwan's claimed waters", a, b, details))
            covered[a:b + 1] = True

        if foreign and decl.score >= DECLARED_MIN:
            z = _zones(terr, tr, 0, len(tr) - 1, edge)
            idx = np.where(z["ts_mask"] | z["cz_mask"])[0]
            if len(idx) and (z["ts_clear"] >= 1 or len(idx) >= 2) and not covered[idx].all():
                a, b = int(idx[0]), int(idx[-1])
                share, med = _band_share(tr.sog[idx], lo, hi)  # speed while actually inside the zone, not the whole span
                ts_hit = z["ts_clear"] >= 1 or z["ts"] >= 1
                sev = (78 if ts_hit else 70) + (8 if share >= 0.5 else 0)
                label = "Declared survey vessel inside Taiwan's territorial sea / contiguous zone"
                transit = cfg.grid_s <= 600 and np.isfinite(med) and med > hi + 1.0 and share < 0.3
                if transit:  # measured speed well above survey speed and no pattern: steaming through, not surveying
                    sev, label = 58.0, "Declared research vessel passing through Taiwan's territorial sea / contiguous zone at transit speed"
                candidates.append((sev, "R1", label, a, b,
                                   {"pattern": None, "zones": z, "v_share": share, "v_median": med, "transit": transit}))
            else:
                eidx = np.where(z["eez_mask"])[0]
                if len(eidx) >= cfg.threat_min_eez_fixes:
                    a, b = int(eidx[0]), int(eidx[-1])
                    share, med = _band_share(tr.sog[eidx], lo, hi)
                    if share >= 0.6:
                        candidates.append((62.0, "R4", "Declared survey vessel working at survey speed in Taiwan's economic zone", a, b,
                                           {"pattern": None, "zones": z, "v_share": share, "v_median": med}))

        # R7: towing an array / cable work announced in the destination, or sustained 'restricted in ability to manoeuvre' at low speed
        if foreign:
            tw = (tr.extra or {}).get("tow_t")
            span = None
            kind7 = None
            if tw is not None and len(tw) >= 3:
                span = (int(np.searchsorted(tr.t, tw.min(), "left")), min(len(tr) - 1, int(np.searchsorted(tr.t, tw.max(), "right")) - 1))
                kind7 = "tow"
            elif tr.status is not None and decl.score >= DECLARED_MIN and decl.restricted >= 0.2:
                rs = np.where((np.asarray(tr.status) == 3) & (np.nan_to_num(tr.sog, nan=0.0) <= hi))[0]
                if len(rs) >= (10 if cfg.grid_s <= 600 else 3):
                    span, kind7 = (int(rs[0]), int(rs[-1])), "restricted"
            if span is not None and span[1] > span[0]:
                a, b = span
                z = _zones(terr, tr, a, b, edge)
                share, med = _band_share(tr.sog[a:b + 1], lo, hi)
                inside = z["ts"] + z["cz"] > 0
                base = (92 if inside else 80 if z["eez"] > 0 else 60) - (8 if kind7 == "restricted" else 0)
                lab = ("Towing a survey array / working cables" if kind7 == "tow" else "Slow manoeuvring survey work (restricted in ability to manoeuvre)")
                where = "inside Taiwan's territorial sea / contiguous zone" if inside else "in Taiwan's economic zone" if z["eez"] > 0 else "outside Taiwan's claimed waters"
                pat = next((p for wa, wb, p in wins if wa <= b and wb >= a), None)
                candidates.append((base + (10 if pat else 0), "R7", f"{lab} {where}", a, b, {"pattern": pat, "zones": z, "v_share": share, "v_median": med, "mode": kind7}))

        if foreign and decl.state_class is not None:
            z = _zones(terr, tr, 0, len(tr) - 1, edge)
            idx = np.where(z["ts_mask"])[0]
            if z["ts_clear"] >= 2 and len(idx):
                a, b = int(idx[0]), int(idx[-1])
                share, med = _band_share(tr.sog[a:b + 1], lo, hi)
                candidates.append((70.0 + (6 if share >= 0.5 else 0), "R6", "Foreign state vessel inside Taiwan's territorial sea", a, b,
                                   {"pattern": None, "zones": z, "v_share": share, "v_median": med}))

        if not candidates:
            ctx.skip("survey_threat", "declared / state vessel but not in Taiwan's waters")
            continue
        candidates.sort(key=lambda c: -c[0])
        seen: list[tuple[int, int]] = []
        for sev, rule, label, a, b, d in candidates:
            if any(a <= sb and b >= sa for sa, sb in seen):
                continue  # one named activity per stretch of track
            seen.append((a, b))
            out.append(_event(tr, decl, foreign, sev, rule, label, a, b, d, cfg, terr))
    return out


def _event(tr: Track, decl, foreign: bool, sev: float, rule: str, label: str, a: int, b: int, d: dict, cfg: DetectionConfig, terr) -> Event:
    z, pat = d["zones"], d["pattern"]
    lat, lon = float(np.mean(tr.lat[a:b + 1])), float(np.mean(tr.lon[a:b + 1]))
    near_line = z["nearest_nm"] is not None and np.isfinite(z["nearest_nm"]) and abs(z["nearest_nm"] - 12.0) < cfg.threat_edge_nm
    hours = (tr.t[b] - tr.t[a]) / 3600.0

    # --- one line per factor, with the numbers ---------------------------------------------------------------------
    n = max(z["n"], 1)
    terr_txt = (f"TERRITORY: {z['ts']} of {n} fixes inside the territorial sea, {z['cz']} in the contiguous zone, {z['eez']} in the economic zone; "
                f"closest approach to Taiwan-administered land {_fmt(z['nearest_nm'])} nm.")
    if near_line:
        terr_txt += " The closest approach is within a few nm of the 12 nm limit, which is inside the position error of this feed."
    vel_txt = (f"VELOCITY: {d['v_share'] * 100:.0f}% of the track was within the {cfg.threat_speed_lo_kn:g}-{cfg.threat_speed_hi_kn:g} kn survey-speed band "
               f"(median {_fmt(d['v_median'], 1)} kn).")
    ais_txt = ("AIS DECLARATION: " + "; ".join(decl.reasons[:3]) + ".") if decl.reasons else "AIS DECLARATION: nothing in its broadcast identifies it as a survey or research vessel (absence proves nothing)."
    pat_txt = (f"PATTERN: {pat['legs']} parallel / zig-zag legs of ~{pat['mean_leg_nm']:.0f} nm, stepping ~{pat['spacing_nm']:.0f} nm sideways, "
               f"over {pat['hours']:.0f} h covering ~{pat['area_nm2']:.0f} nm².") if pat else "PATTERN: no repeated-leg survey pattern."
    flag_txt = ("FLAG: not Taiwan-registered (MMSI prefix " + tr.mmsi[:3] + ").") if foreign else "FLAG: Taiwan-registered (MMSI prefix 416) - own-waters activity is expected."
    why = {
        "R1": "A vessel that declares itself a survey vessel is inside waters where foreign research needs Taiwan's consent.",
        "R2": "Survey-shaped movement inside waters where foreign research needs Taiwan's consent.",
        "R3": "Survey-shaped movement in the economic zone, where research needs the coastal state's consent.",
        "R4": "A self-declared survey vessel moving at survey speed in the economic zone.",
        "R5": "Survey-shaped movement; outside Taiwan's claimed waters, so reported as behaviour only.",
        "R6": "A foreign state vessel inside the territorial sea.",
        "R0": "Taiwan-registered vessel doing survey work: recorded for completeness, not raised.",
        "R7": "The vessel itself announces towing / cable work, or holds 'restricted in ability to manoeuvre' while moving slowly: the signature of towing sensors or inspecting a cable.",
    }[rule]
    cab = Cables.default()
    cab_f = None
    if cab is not None:
        dn = cab.distance_nm(tr.lat[a:b + 1], tr.lon[a:b + 1])
        j = int(np.argmin(dn))
        cab_f = {"nearest_nm": round(float(dn[j]), 1), "cable": cab.nearest_name(float(tr.lat[a + j]), float(tr.lon[a + j])),
                 "share_within_10nm": round(float(np.mean(dn <= 10.0)), 2), "met": bool(np.mean(dn <= 10.0) >= 0.2)}
    status_txt = (f"NAV STATUS: 'restricted in ability to manoeuvre' for {decl.restricted * 100:.0f}% of reports"
                  + (f"; status briefly switched away and back {decl.toggles} time(s) while under way" if decl.toggles else "") + ".")         if (decl.restricted > 0 or decl.toggles) else "NAV STATUS: nothing unusual (no restricted-manoeuvre or status switching)."
    cable_txt = (f"CABLES: closest charted submarine cable ({cab_f['cable']}) {cab_f['nearest_nm']:.0f} nm away; {cab_f['share_within_10nm'] * 100:.0f}% of the stretch "
                 f"was within 10 nm of a cable.") if cab_f else "CABLES: no cable map loaded."
    evidence = [f"CLASSIFIED AS: {label} (rule {rule}). {why}", terr_txt, vel_txt, ais_txt, status_txt, pat_txt, cable_txt, flag_txt]
    if cab_f and cab_f["met"] and rule in ("R1", "R2", "R3", "R4", "R7"):
        sev = min(100.0, sev + 4)
    factors = {
        "territory": {"ts_fixes": z["ts"], "cz_fixes": z["cz"], "eez_fixes": z["eez"], "fixes": z["n"], "nearest_nm": round(float(z["nearest_nm"]), 1),
                      "met": bool(z["ts"] + z["cz"] > 0), "on_the_line": bool(near_line)},
        "velocity": {"share_in_band": round(float(d["v_share"]), 2), "median_kn": None if not np.isfinite(d["v_median"]) else round(float(d["v_median"]), 1),
                     "band_kn": [cfg.threat_speed_lo_kn, cfg.threat_speed_hi_kn], "met": bool(d["v_share"] >= 0.5)},
        "declared": {"score": round(float(decl.score), 2), "reasons": decl.reasons, "met": bool(decl.score >= DECLARED_MIN)},
        "pattern": {"legs": None if not pat else int(pat["legs"]), "met": bool(pat)},
        "status": {"restricted_share": round(float(decl.restricted), 2), "toggles": int(decl.toggles),
                   "met": bool(decl.restricted >= 0.2 or decl.toggles >= 1)},
        "towing": {"met": bool(decl.towing), "destination": (tr.extra or {}).get("destination", "")},
        "cable": cab_f or {"met": False},
        "foreign": foreign, "state_class": decl.state_class,
    }
    conf = 0.75 - (0.15 if near_line else 0.0) - (0.1 if cfg.grid_s > 600 else 0.0)
    return Event(
        "", "survey_threat", [tr.mmsi], float(tr.t[a]), float(tr.t[b]), lat, lon, float(max(0.0, min(100.0, sev))), float(max(0.2, conf)),
        f"{tr.name}: {label}", evidence, BENIGN_SURVEY, UNCERTAIN,
        {"classification": label, "rule": rule, "factors": factors, "hours": round(float(hours), 1), "transit": bool(d.get("transit", False)), "mode": d.get("mode")},
        path=[(float(p), float(q)) for p, q in zip(tr.lat[a:b + 1:max(1, (b - a) // 60)], tr.lon[a:b + 1:max(1, (b - a) // 60)])])


# --------------------------------------------------------------------------- #
# How the four factors separate signal from noise (used by the Assessment view)
# --------------------------------------------------------------------------- #
def factor_table(tracks: list[Track], ctx: DetectionContext, cfg: DetectionConfig, events: list[Event]) -> dict:
    """For every foreign vessel: which of T / V / A / P hold, and how often combinations occur.

    A single factor is common and means little (many foreign ships cross Taiwan's waters; many move at 5-10 kn). The combinations are
    rare, and that rarity is what turns the factors into a usable signal.
    """

    terr = ctx.territory
    if terr is None:
        return {}
    pattern_ids = {e.mmsis[0] for e in events if e.kind == "survey_threat" and e.metrics.get("factors", {}).get("pattern", {}).get("met")}
    classified = {e.mmsis[0]: e.metrics.get("rule") for e in events if e.kind == "survey_threat"}
    lo, hi = cfg.threat_speed_lo_kn, cfg.threat_speed_hi_kn
    combos: dict[tuple[bool, bool, bool, bool], int] = {}
    single = {"foreign": 0, "T": 0, "V": 0, "A": 0, "P": 0}
    for tr in tracks:
        if tr.mmsi.startswith(TAIWAN_MID) or tr.flag in ("TWN", "TW") or len(tr) < 4:
            continue
        single["foreign"] += 1
        code = terr.code_at(tr.lat, tr.lon)
        t = bool(np.any((code == CODE["TS"]) | (code == CODE["CZ"])))
        share, _ = _band_share(tr.sog, lo, hi)
        v = share >= 0.5 and len(tr) >= 6
        a = assess(tr).score >= DECLARED_MIN
        p = tr.mmsi in pattern_ids
        single["T"] += t
        single["V"] += v
        single["A"] += a
        single["P"] += p
        combos[(t, v, a, p)] = combos.get((t, v, a, p), 0) + 1
    rows = [{"territory": k[0], "velocity": k[1], "declared": k[2], "pattern": k[3], "vessels": n,
             "factors_met": int(sum(k))} for k, n in sorted(combos.items(), key=lambda kv: (-sum(kv[0]), -kv[1]))]
    return {"single": {k: int(v) for k, v in single.items()}, "combinations": rows,
            "classified": {r: sum(1 for x in classified.values() if x == r) for r in sorted(set(classified.values()))}}
