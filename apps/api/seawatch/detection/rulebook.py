"""The rulebook: every rule that can make activity look suspicious, in plain language, with the LIVE threshold values.

``build(cfg, hourly)`` feeds the /detection/rulebook endpoint and ``render_markdown`` writes docs/rulebook.md, so the
document, the API and the UI cannot drift apart from the thresholds the detectors actually use.
"""

from __future__ import annotations

from typing import Any

from .config import DetectionConfig
from .territory import CZ_NM, EEZ_NM, TS_NM

PRINCIPLE = (
    "An alert is a CANDIDATE FOR HUMAN REVIEW, never a finding of intent. Each rule states what was observed, why that is unusual, "
    "and the innocent explanations. Several independent weak signals raise risk together (noisy-OR); one weak signal alone stays low."
)


def _detectors(c: DetectionConfig, hourly: bool) -> list[dict[str, Any]]:
    res = "hourly ~11 km cells" if hourly else "minute-level AIS"
    return [
        dict(id="ais_gap", name="Reporting gap (going dark)",
             sees=f"A vessel stops being heard for at least {c.gap_min_minutes:g} min inside the covered area and reappears (or never does).",
             why="Switching AIS off is how vessels hide meetings, transfers and survey work.",
             thresholds={"minimum silence (min)": c.gap_min_minutes, "max implied speed across gap (kn)": c.gap_max_implied_knots,
                         "'stayed put' radius (nm)": c.stationary_nm, "area-edge margin (nm)": c.edge_margin_nm},
             discards=["left or re-entered the monitored area", "in port or at anchor", "short silence in sparse reception",
                       "this vessel's own routine (its p95 silence)", "ordinary for its ship type (peer percentile)"],
             benign=["poor satellite or shore reception", "equipment fault", "vessel left the covered area", "port or anchorage shadowing"],
             data="Needs reception coverage; hourly feeds can only say 'not seen'."),
        dict(id="loitering", name="Loitering / unusual stopping",
             sees=f"Slow (<= {c.loiter_max_speed_kn:g} kn) inside a {c.loiter_radius_nm:g} nm circle for {c.loiter_min_minutes:g}+ min, away from port.",
             why="Stopping in open water is where transfers, retrievals and equipment work happen.",
             thresholds={"minimum dwell (min)": c.loiter_min_minutes, "radius (nm)": c.loiter_radius_nm, "max speed (kn)": c.loiter_max_speed_kn},
             discards=["moored for the whole observation", "waiting at port or anchorage", "fishing on a fishing ground", "this vessel's habitual dwell cell"],
             benign=["fishing", "waiting for a berth or weather", "drifting engine trouble", "legitimate survey or cable work"],
             data="Learns stop areas from history so ports and anchorages are not alarms."),
        dict(id="rendezvous", name="Rendezvous / dark transfer",
             sees=f"Two vessels slow and within {c.proximity_distance_nm:g} nm for {c.rendezvous_min_minutes:g}+ min; stronger when one or both went dark around it.",
             why="Ship-to-ship transfer of cargo, fuel or people; sanctions evasion and smuggling.",
             thresholds={"meeting distance (nm)": c.proximity_distance_nm, "minimum meeting time (min)": c.rendezvous_min_minutes,
                         "max speed (kn)": c.rendezvous_max_speed_kn},
             discards=["both in port or anchorage", "fishing-fleet gatherings (risk reduced)"],
             benign=["fishing pairs", "bunkering at an anchorage", "tow or escort", "crew transfer"],
             data=f"Position accuracy matters: at {res} the distance test is loosened."),
        dict(id="cluster", name="Clustering",
             sees=f"{c.cluster_min_vessels}+ vessels within {c.cluster_distance_nm:g} nm for {c.cluster_min_minutes:g}+ min away from ports.",
             why="Coordinated gatherings (maritime militia, blockade rehearsal, fleet at a cable site).",
             thresholds={"vessels": c.cluster_min_vessels, "distance (nm)": c.cluster_distance_nm, "minutes": c.cluster_min_minutes},
             discards=["inside a learned stop area", "alerts larger than 6 vessels are split by lead vessel to stay reviewable"],
             benign=["fishing grounds", "weather shelter", "regatta or exercise"], data="Needs traffic density context."),
        dict(id="zone_entry", name="Restricted-zone entry",
             sees="A vessel enters a protected zone (cable corridor, restricted waters, port area).",
             why="Anchoring or dragging near cables and sensitive areas is the classic sabotage and survey pre-condition.",
             thresholds={"minimum dwell (min)": c.zone_min_dwell_minutes},
             discards=["routine visitor to this zone (learned from history)", "transit discount (-18 risk) when only crossing"],
             benign=["licensed local traffic", "fishing boats on a normal route", "operator allow-listed vessels"],
             data="Zones are illustrative; replace with official polygons."),
        dict(id="position_jump", name="Position jump / identity conflict",
             sees=f"A position change implying > {c.jump_min_implied_knots:g} kn and > {c.jump_min_distance_nm:g} nm, or the same identity alternating between places {c.identity_min_alternations}+ times.",
             why="Spoofed or cloned AIS identities.", thresholds={"implied speed (kn)": c.jump_min_implied_knots, "distance (nm)": c.jump_min_distance_nm,
                                                               "alternations": c.identity_min_alternations},
             discards=["device-range and placeholder MMSIs"], benign=["GPS glitch", "two ships sharing a mis-set MMSI", "receiver timing error"],
             data="Weak on hourly data (cell positions are +/- 5 km)."),
        dict(id="status_mismatch", name="Status / behaviour mismatch",
             sees="Declared navigational status contradicts movement (e.g. 'at anchor' while making 12 kn).",
             why="Inconsistent self-reports suggest manipulated or careless AIS.", thresholds={},
             discards=[], benign=["crew forgot to update status"], data="Message-level AIS only."),
        dict(id="route_deviation", name="Route deviation",
             sees=f"{c.deviation_min_minutes:g}+ min at >= {c.deviation_min_speed_kn:g} kn through water that historic traffic rarely uses (< {c.deviation_familiarity:g} vessels per cell).",
             why="Off-lane transit can mean avoiding observation or surveying new ground.",
             thresholds={"minutes": c.deviation_min_minutes, "familiar-water cut-off": c.deviation_familiarity},
             discards=["cells busy in the learned baseline"], benign=["weather routing", "fishing", "new routes"], data="Needs a baseline of normal traffic."),
        dict(id="survey_pattern", name="Survey-shaped track (zig-zag / lawnmower)",
             sees=f"{c.survey_min_legs}+ long legs (>= {c.survey_min_leg_nm:g} nm), each turned back on the last, similar length, stepped sideways, slow, within {c.survey_window_h:g} h.",
             why="Scanning the seabed (cables, resources) requires systematic parallel passes; ordinary transit never looks like this.",
             thresholds={"legs": c.survey_min_legs, "leg length (nm)": c.survey_min_leg_nm, "window (h)": c.survey_window_h},
             discards=["fishing, ferry, tug, pilot, SAR, service and dredger types are exempt", "turn points mostly in benign (port) areas"],
             benign=["genuine research and cable-route surveys by licensed parties", "search-and-rescue patterns", "trawling runs"],
             data="Measured recall on synthetic shapes: lawnmower 69%, zig-zag 67%, race-track 82%."),
    ]


def _threat(c: DetectionConfig, hourly: bool) -> dict[str, Any]:
    lo, hi = c.threat_speed_lo_kn, c.threat_speed_hi_kn
    return {
        "title": "Suspected unauthorised survey (the mentor's three factors, plus pattern)",
        "premise": ("Foreign research or survey ships operating in Taiwan's waters are treated as a potential threat to subsea cables. "
                    "Three factors identify them; the zig-zag pattern is a fourth, independent confirmation."),
        "legal": ("Reference only: UNCLOS Art. 19(2)(j) makes research or survey in the territorial sea non-innocent passage; Arts. 245-246 "
                  "require coastal-state consent for research in the territorial sea and EEZ. Taiwan is not a UNCLOS party and its legal "
                  "status is for lawyers. AIS cannot show whether consent exists, so every result is a candidate for review."),
        "factors": [
            dict(code="T", name="Territory", rule=f"Positions inside Taiwan's territorial sea (<= {TS_NM:g} nm), contiguous zone ({TS_NM:g}-{CZ_NM:g} nm) or EEZ (<= {EEZ_NM:g} nm, nearer to Taiwan than to the mainland, Japan or the Philippines).",
                 note=f"Reference geometry from Natural Earth coastlines, not legal baselines. A fix within {c.threat_edge_nm:g} nm of a limit counts as 'on the line' (position error)."),
            dict(code="V", name="Velocity", rule=f"Typical speed within {lo:g}-{hi:g} kn for at least half of the track's fixes.",
                 note="The mentor said '5 to 10 miles per hour or so'; we read it as knots (nautical miles per hour). Adjustable in the Tuning lab. Hourly data estimates speed from cell steps."),
            dict(code="A", name="AIS declaration", rule="The vessel itself signals survey or research: name containing a survey/research designation (RESEARCH, SURVEY, KEXUE, XIANG YANG HONG, HAIYANG DIZHI ...), a survey destination, or a feed class of seismic vessel (weak).",
                 note="Strong evidence when present (score >= 0.6) but proves little when absent; names are cheap to change."),
            dict(code="P", name="Pattern", rule="Survey-shaped zig-zag / lawnmower track (see the survey detector above).",
                 note="Independent of what the vessel claims; a ship that hides its role still has to sail the lines."),
        ],
        "rules": [
            dict(id="R2", name="Pattern in territorial sea / contiguous zone", severity="85 (+5 if declared, +5 if survey speed)", needs="T + P",
                 meaning="Foreign vessel sailing survey lines inside Taiwan's 24 nm: highest-confidence rule."),
            dict(id="R3", name="Pattern in the EEZ", severity="72", needs="EEZ + P",
                 meaning="Survey lines in the EEZ. Consent may exist; review."),
            dict(id="R5", name="Pattern outside Taiwan's claimed waters", severity="55", needs="P",
                 meaning="Survey lines near Taiwan but outside claimed waters; informational context."),
            dict(id="R1", name="Declared survey vessel in territorial sea / contiguous zone", severity="78 in TS, 70 in CZ (+8 survey speed)", needs="T + A",
                 meaning="The ship says it is a research vessel and is inside Taiwan's 24 nm; easy case."),
            dict(id="R4", name="Declared survey vessel working at survey speed in the EEZ", severity="62", needs=f"A + V (>= 60% of fixes) + {c.threat_min_eez_fixes} EEZ fixes",
                 meaning="Declared and slow for a long time in the EEZ, without a clear pattern."),
            dict(id="R6", name="Foreign state vessel in the territorial sea", severity="70 (+6 survey speed)", needs=">= 2 clear TS fixes + state-vessel name",
                 meaning="Coast guard, maritime safety or fisheries enforcement ship of another state inside the 12 nm. Not survey, but a sovereignty matter."),
            dict(id="R0", name="Taiwan-registered survey vessel", severity="30 (not raised)", needs="MMSI 416xxxxxx",
                 meaning="Domestic research is expected; recorded, never alerted."),
        ],
        "noise": ("Single factors are common (many foreign ships cross these waters; many move at 5-10 kn). The combination is rare. "
                  "The Assessment view shows how many vessels meet each combination."),
    }


def _fusion(c: DetectionConfig) -> dict[str, Any]:
    return {
        "risk": "Event severity x detector weight x confidence, combined across independent events with noisy-OR so extra evidence adds but never exceeds 100.",
        "levels": {"alert shown from": c.alert_min_risk, "medium": c.medium_risk, "high": c.high_risk},
        "grouping": "Events on the same vessel(s) within the link window are merged into one alert so a story reads as one item.",
        "ml": "A second, statistical opinion (Isolation Forest + gradient boosting) scores the same time window. 'Agree' means both consider it unusual; 'rules only' lowers trust.",
        "watch": "Vessels on a cited research-vessel or sanctions list get +8 risk and a caveat. They are matched on IMO / MMSI only; a listing is about the hull, not about this week's behaviour.",
        "feedback": "Operators mark false alarms, add notes, allow-list vessels and tune thresholds; those decisions suppress or reshape later alerts.",
    }


def build(cfg: DetectionConfig, hourly: bool = False) -> dict[str, Any]:
    return {"principle": PRINCIPLE, "detectors": _detectors(cfg, hourly), "threat_model": _threat(cfg, hourly), "fusion": _fusion(cfg),
            "resolution": "hourly ~11 km cells (thresholds scaled up accordingly)" if hourly else "minute-level AIS"}


def render_markdown(cfg: DetectionConfig | None = None, hourly: bool = True) -> str:
    cfg = cfg or (DetectionConfig.hourly() if hourly else DetectionConfig())
    b = build(cfg, hourly)
    out = ["# SeaWatch rulebook: what makes activity 'suspicious'", "", f"_Generated from the live thresholds ({b['resolution']})._", "", b["principle"], ""]
    t = b["threat_model"]
    out += [f"## 1. {t['title']}", "", t["premise"], "", f"**Legal background.** {t['legal']}", "", "### Factors", ""]
    for f in t["factors"]:
        out += [f"* **{f['code']} - {f['name']}.** {f['rule']} _{f['note']}_"]
    out += ["", "### Rules", "", "| rule | name | severity | needs | meaning |", "|---|---|---|---|---|"]
    for r in t["rules"]:
        out.append(f"| {r['id']} | {r['name']} | {r['severity']} | {r['needs']} | {r['meaning']} |")
    out += ["", t["noise"], "", "## 2. Behaviour detectors", ""]
    for d in b["detectors"]:
        out += [f"### {d['name']}", "", f"* **What it sees:** {d['sees']}", f"* **Why it matters:** {d['why']}"]
        if d["thresholds"]:
            out.append("* **Thresholds:** " + "; ".join(f"{k} = {v:g}" for k, v in d["thresholds"].items()))
        if d["discards"]:
            out.append("* **Discarded as noise:** " + "; ".join(d["discards"]))
        out += ["* **Innocent explanations:** " + "; ".join(d["benign"]), f"* **Data needs / limits:** {d['data']}", ""]
    f = b["fusion"]
    out += ["## 3. From events to alerts", ""] + [f"* **{k}:** {v}" for k, v in f.items()]
    return "\n".join(out) + "\n"
