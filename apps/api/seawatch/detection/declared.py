"""AIS-DECLARED factor: does the vessel itself say it does survey / research work (or that it is a state vessel)?

What a vessel broadcasts about itself is cheap to read and cheap to fake, so a hit is strong evidence and a miss proves nothing.
Sources used, strongest first:

* a feed-derived vessel class that says "seismic survey" (e.g. Global Fishing Watch ``SEISMIC_VESSEL``) - weak, because it is derived and noisy;
* destination text such as "SURVEY" / "RESEARCH" (message-level AIS only);
* the ship name (English words and the common Chinese-ship pinyin: Xiang Yang Hong, Kexue, Haiyang Dizhi, ...);
* navigational status "restricted in ability to manoeuvre" held for most of the time (message-level AIS only) - weak, because
  cable-layers, dredgers and pilots use it too.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np

from .models import Track

# strong self-descriptions (matched on the upper-cased name with spaces / punctuation removed)
_RESEARCH_NAME = re.compile(
    r"RESEARCH|SURVEY|SEISMIC|OCEANOGRAPH|HYDROGRAPH|GEOPHYS|SCIENTIFIC|OCEANRESEARCHER|"
    r"KEXUE|KEYAN|TANSUO|XIANGYANGHONG|DONGFANGHONG|HAIYANGDIZHI|ZHANGJIAN|SHENHAIYIHAO|JIAGENG|SHIYAN(?![A-Z])"
)
_RESEARCH_DEST = re.compile(r"SURVEY|RESEARCH|SCIENTIF|SEISMIC|HYDROGRAPH|OCEANOGRAPH|CABLE.?(LAY|REPAIR|INSPECT)")
# state vessels by declared name
_STATE_NAME = [
    ("coast_guard", re.compile(r"COASTGUARD|CHINACOASTGUARD|HAIJINGCHUAN|^CG\d{3,5}$")),
    ("maritime_safety", re.compile(r"ZHONGGUOHAIJIAN|HAIJIAN\d|HAIXUN")),
    ("fisheries_enforcement", re.compile(r"ZHONGGUOYUZHENG|YUZHENG\d")),
]


def _norm(name: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (name or "").upper())


# destination text that announces a towed array or cable work ("TOWING 5NM CABLE", "TOWING KEEP 3NM CPA", "KEEP 2CPA PASSING")
_TOWING = re.compile(r"\bTOW(?:ING|ED|AGE)?\b|CPA\b|KEEP\s*\d|STREAMER|\bARRAYS?\b|\bCABLES?\b")


def is_towing_text(dest: str) -> bool:
    return bool(dest) and bool(_TOWING.search(dest.upper()))


def restricted_share(tr: Track) -> float:
    return float(np.mean(np.asarray(tr.status) == 3)) if tr.status is not None and len(tr.status) else 0.0


def status_toggles(tr: Track, max_dur_s: float = 1800.0, min_base_s: float = 3600.0) -> int:
    """Brief departures from a steady navigation status while under way (e.g. UNDER_WAY_USING_ENGINE -> NOT_DEFINED -> back).

    Rare among ordinary traffic (about 0.6% of non-fishing vessels in a full day), which is why it is informative.
    """

    if tr.status is None or len(tr) < 8:
        return 0
    s = np.asarray(tr.status)
    idx = np.r_[0, np.where(s[1:] != s[:-1])[0] + 1, len(s)]
    n = 0
    for k in range(1, len(idx) - 2):
        a, b = idx[k], idx[k + 1]
        prev0, prev1, nxt0, nxt1 = idx[k - 1], a, b, idx[k + 2]
        if s[prev0] != s[nxt0] or s[prev0] == s[a]:
            continue
        if tr.t[min(b, len(tr) - 1)] - tr.t[a] > max_dur_s:
            continue
        if tr.t[prev1 - 1] - tr.t[prev0] < min_base_s or tr.t[nxt1 - 1] - tr.t[nxt0] < min_base_s:
            continue
        sp = tr.sog[max(0, a - 3):b + 3]
        if np.isfinite(sp).any() and np.nanmedian(sp) > 3.0:
            n += 1
    return n


@dataclass
class Declared:
    score: float = 0.0  # 0..1 how strongly the vessel declares itself a survey / research vessel
    state_class: str | None = None  # coast_guard | maritime_safety | fisheries_enforcement
    reasons: list[str] = field(default_factory=list)
    towing: bool = False  # destination text says it is towing an array / working cables
    restricted: float = 0.0  # share of reports with status 'restricted in ability to manoeuvre'
    toggles: int = 0  # brief status departures while under way


def assess(tr: Track) -> Declared:
    d = Declared()
    parts: list[float] = []
    if tr.ship_type == "seismic":
        parts.append(0.5)  # a class derived by the feed provider (noisy: tankers and support ships carry it); not a broadcast self-description
        d.reasons.append("the feed classes it as a 'seismic survey vessel' (a derived class, not something the vessel broadcast)")
    sub = ((tr.extra or {}).get("subtype") or "").lower()
    if sub in ("research", "seismic surveyor", "fishery research", "survey", "hydrographic"):
        parts.append(0.7)
        d.reasons.append(f"the vessel register behind the feed lists it as '{(tr.extra or {}).get('subtype')}' (a registry class, not a live broadcast)")
    dest = (tr.extra or {}).get("destination", "") if getattr(tr, "extra", None) else ""
    if dest and _RESEARCH_DEST.search(dest.upper()):
        parts.append(0.9)
        d.reasons.append(f"its AIS destination field reads '{dest.strip()}'")
    tow_t = (tr.extra or {}).get("tow_t")
    if tow_t is not None and len(tow_t) >= 3 or is_towing_text(dest):
        d.towing = True
        parts.append(0.95)
        d.reasons.append(f"its AIS destination field announces towing / cable work ('{(dest or '').strip()}')")
    d.restricted = restricted_share(tr)
    d.toggles = status_toggles(tr)
    nm = _norm(tr.name)
    if nm and _RESEARCH_NAME.search(nm):
        parts.append(0.85)
        d.reasons.append(f"its AIS name '{tr.name}' contains a survey / research designation")
    if tr.status is not None and len(tr.status) and float(np.mean(np.asarray(tr.status) == 3)) >= 0.5:
        parts.append(0.4)
        d.reasons.append("it reports 'restricted in ability to manoeuvre' for most of the track (also used by cable-layers and dredgers)")
    if parts:
        d.score = float(1.0 - np.prod([1.0 - p for p in parts]))
    for cls, rx in _STATE_NAME:
        if rx.search(nm):
            d.state_class = cls
            d.reasons.append(f"its AIS name '{tr.name}' marks it as a state vessel ({cls.replace('_', ' ')})")
            break
    return d
