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


@dataclass
class Declared:
    score: float = 0.0  # 0..1 how strongly the vessel declares itself a survey / research vessel
    state_class: str | None = None  # coast_guard | maritime_safety | fisheries_enforcement
    reasons: list[str] = field(default_factory=list)


def assess(tr: Track) -> Declared:
    d = Declared()
    parts: list[float] = []
    if tr.ship_type == "seismic":
        parts.append(0.5)  # a class derived by the feed provider (noisy: tankers and support ships carry it); not a broadcast self-description
        d.reasons.append("the feed classes it as a 'seismic survey vessel' (a derived class, not something the vessel broadcast)")
    dest = (tr.extra or {}).get("destination", "") if getattr(tr, "extra", None) else ""
    if dest and _RESEARCH_DEST.search(dest.upper()):
        parts.append(0.9)
        d.reasons.append(f"its AIS destination field reads '{dest.strip()}'")
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
