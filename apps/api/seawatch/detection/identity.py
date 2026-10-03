"""Identity hygiene for message-level AIS: drop things that broadcast like ships but are not.

In dense Chinese / Taiwanese fishing grounds a large share of 'vessels' are drift-net and trap beacons, AIS test devices and
placeholder identities. They sit still next to their tending boat, so unfiltered they produce thousands of fake rendezvous,
clusters and loiters. Real ships (including ones with no static data) are kept.
"""

from __future__ import annotations

import re

# battery / signal suffix in the name ("MJY06010-15-57%", "TIELONG61968-55-60%"), or net-marker serials ("CT2-5322---8-71%")
_BEACON_NAME = re.compile(r"%|^[A-Z]{1,4}\d*-+\d|-{2,}|^(.)\1{5,}$|^[^A-Z0-9]{3,}$|^\W*[0-9 ]{5,}\W*$")


def valid_mmsi(m: str) -> bool:
    """9 digits, maritime identification digits 201-775, not a repeated-digit placeholder."""

    m = str(m)
    if len(m) != 9 or not m.isdigit() or not (201 <= int(m[:3]) <= 775):
        return False
    return not any(m.count(d) >= 6 for d in set(m))


def looks_like_gear(name: str, mmsi: str = "") -> bool:
    n = (name or "").strip().upper()
    if n == str(mmsi):  # name is just the MMSI: static data never received; keep, it may be a real boat
        return False
    return bool(n) and bool(_BEACON_NAME.search(n))


def is_real_ship(name: str, mmsi: str) -> bool:
    return valid_mmsi(mmsi) and not looks_like_gear(name, mmsi)
