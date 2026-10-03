"""Map provider text (Datalastic navigation status / vessel type) to the numeric AIS codes the Detection stack understands.

Detection reads navigation status (3 = restricted in ability to manoeuvre is a survey signal) and ship type (fishing, tug, ... are handled
differently) from numbers. Unknown or unmapped text returns ``None``; nothing is guessed.
"""

from __future__ import annotations

import re


def _norm(text: str | None) -> str:
    return re.sub(r"[^a-z]", "", (text or "").lower())


def nav_status_code(text: str | None) -> int | None:
    """AIS navigational status code (0-8) from provider text, or None."""

    t = _norm(text)
    if not t:
        return None
    for needle, code in (
        ("notundercommand", 2), ("restricted", 3), ("constrainedbyher", 4), ("constrained", 4), ("draught", 4), ("draft", 4),
        ("moored", 5), ("aground", 6), ("engagedinfishing", 7), ("sailing", 8), ("atanchor", 1), ("anchor", 1), ("underwayusingengine", 0),
        ("underwayengine", 0), ("engine", 0),
    ):
        if needle in t:
            return code
    return None


def vessel_type_code(type_text: str | None, specific_text: str | None = None) -> int | None:
    """ITU-R M.1371 ship-and-cargo type code (representative value of the class) from provider text, or None."""

    t = _norm(type_text) + "|" + _norm(specific_text)
    for needle, code in (
        ("fishing", 30), ("trawler", 30), ("towing", 31), ("dredg", 33), ("diving", 34), ("military", 35), ("sailing", 36), ("pleasure", 37), ("yacht", 37),
        ("highspeed", 40), ("pilot", 50), ("searchandrescue", 51), ("sar", 51), ("tug", 52), ("portTender".lower(), 53), ("lawenforcement", 55),
        ("passenger", 60), ("ferry", 60), ("cruise", 60), ("tanker", 80), ("cargo", 70), ("container", 70), ("bulk", 70), ("carrier", 70), ("freighter", 70),
    ):
        if needle in t:
            return code
    if re.search(r"research|survey|seismic|hydrograph|oceanograph|offshore|supply|other|unknown|special", t):
        return 90
    return None
