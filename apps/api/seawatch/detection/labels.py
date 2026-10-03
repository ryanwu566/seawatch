"""Real-world outcome labels: watch-lists and documented incidents.

Two label kinds, deliberately kept apart because they answer different questions:

* **watch-list** entries say a *vessel* is on a sanctions / IUU / detention list. They carry no information about
  what the vessel did on any given day, so they support vessel-level questions only ("do listed vessels look
  unusual more often than other vessels?").
* **incident** entries say a *vessel did / was suspected of something in a time window* (e.g. cable damage), with a
  public source. They support event-level questions ("was an alert raised on that vessel in that window, and which
  behaviour was the clue?").

Neither is ground truth about intent. Incidents are reported as *suspected* and may be accidents; lists are legal
designations, not behaviour. Every label records its source and how sure we are.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .models import Track


@dataclass(frozen=True)
class VesselLabel:
    kind: str  # "watchlist" | "incident"
    imo: str = ""
    mmsi: str = ""
    names: tuple[str, ...] = ()
    category: str = ""  # e.g. sanctions:IRAN-EO13902, cable_damage_suspected
    source: str = ""
    t_start: float | None = None  # epoch s (incidents only)
    t_end: float | None = None
    note: str = ""
    confidence: str = "documented"  # documented | reported | weak


def _ts(s: str) -> float | None:
    s = (s or "").strip()
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()


def load_ofac_sdn(path: str | Path) -> list[VesselLabel]:
    """Vessels from the public OFAC SDN list (sdn.csv), keyed on IMO / MMSI found in the remarks column."""

    out: list[VesselLabel] = []
    with open(path, encoding="utf8", errors="replace", newline="") as fh:
        for r in csv.reader(fh):
            if len(r) < 12 or r[2].strip().lower() != "vessel":
                continue
            remarks = r[-1]
            imo = re.findall(r"IMO\s*(\d{7})", remarks)
            mmsi = re.findall(r"MMSI\s*(\d{9})", remarks)
            names = tuple({r[1].strip(), *re.findall(r"[fa]\.k\.a\. '([^']+)'", remarks)})
            for i in imo or [""]:
                for m in mmsi or [""]:
                    if i or m:
                        out.append(VesselLabel("watchlist", i, m, names, f"sanctions:{r[3].strip()}", "OFAC SDN (US Treasury)",
                                               note="Listed hull; says nothing about behaviour on a given day"))
    return out


def load_incidents(path: str | Path) -> list[VesselLabel]:
    out: list[VesselLabel] = []
    with open(path, encoding="utf8", newline="") as fh:
        for r in csv.DictReader(row for row in fh if not row.startswith("#")):
            out.append(VesselLabel("incident", r["imo"].strip(), r["mmsi"].strip(), tuple(n for n in r["names"].split("|") if n),
                                   r["category"], r["source"], _ts(r["t_start_utc"]), _ts(r["t_end_utc"]), r["note"],
                                   r.get("confidence", "documented")))
    return out


def load_osint(path: str | Path) -> list[VesselLabel]:
    """OSINT-reported vessels (data/labels/osint_vessels.csv): matched on IMO, each row cites its source."""

    out: list[VesselLabel] = []
    with open(path, encoding="utf8", newline="") as fh:
        for r in csv.DictReader(row for row in fh if not row.startswith("#")):
            out.append(VesselLabel("watchlist", r["imo"].strip(), r.get("mmsi", "").strip(), tuple(n for n in r["names"].split("|") if n),
                                   r["category"], r["source_note"], note=r["observed"], confidence="reported"))
    return out


@dataclass
class LabelSet:
    labels: list[VesselLabel] = field(default_factory=list)

    def match(self, tr: Track) -> list[VesselLabel]:
        """Labels that refer to this track: MMSI or IMO equal (names are NOT used - they are trivially spoofed/duplicated)."""

        hits = []
        for lb in self.labels:
            if (lb.mmsi and lb.mmsi == tr.mmsi) or (lb.imo and tr.imo and lb.imo == re.sub(r"\D", "", tr.imo)[-7:]):
                hits.append(lb)
        return hits
