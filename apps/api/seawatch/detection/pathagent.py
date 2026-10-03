"""Path-analysis agent: reviews the slow stretches of research-type vessels and says what the movement looks like.

Pipeline (the order matters; each stage removes most of the traffic):

    1. RESEARCH GATE   only vessels that declare research / survey work (name, registry subtype, destination text such as
                       "TOWING ... CABLE"); restricted-manoeuvre status alone is not enough (offshore-construction vessels hold it too)
    2. SPEED GATE      only windows where the vessel is slow (median <= 7 kn); fast, straight transit is dropped here
    3. SHAPE FEATURES  path-only features per 6 h window (pathml.py)
    4. REVIEW          an interpretation of the window: what the movement looks like, whether it deserves analyst attention, and why

Two reviewers share one output format (``PathReview``):

* ``OfflineReviewer``  deterministic analyst rules written from the confirmed examples; always available, no network.
* ``ClaudeReviewer``   sends the rendered track image, the feature table and the AIS context to a Claude model and parses a JSON answer.
                       Needs ANTHROPIC_API_KEY (backend only). If the call fails or returns something unparsable it falls back to the
                       offline reviewer and says so in ``reviewer``.

The agent is ADVISORY. It never creates or removes deterministic alerts; it adds an interpretation that the analyst accepts or rejects,
and those decisions are stored (``ReviewStore``) as the seed of the confirmed-path set (data/labels/confirmed_paths.csv).
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from . import pathml
from .declared import assess, restricted_share, status_toggles
from .models import Track

CATEGORIES = {
    "survey_lines_under_tow": "Steady slow runs, often parallel or back-and-forth, typical of towing a sensor array or running survey lines",
    "lawnmower_survey": "Repeated parallel legs with turns at the ends, covering an area systematically",
    "station_keeping_work": "Holding position or working a small area in restricted-manoeuvre status (equipment deployment, cable or seabed inspection)",
    "tow_then_transit": "A slow towing stretch followed by or preceded by a fast straight run",
    "fishing_or_trawl": "Typical of fishing: irregular, repeated passes by a fishing-type vessel",
    "port_or_anchorage": "Parked, moored or manoeuvring near a harbour or anchorage",
    "drift_or_idle": "Adrift or idling without working a line",
    "transit": "Straight, steady, fast movement from A to B",
    "other_unclear": "Does not fit the above or the data are too thin to say",
}
FLAGGED = {"survey_lines_under_tow", "lawnmower_survey", "station_keeping_work", "tow_then_transit"}


@dataclass
class PathReview:
    id: str
    mmsi: str
    name: str
    t0: float
    t1: float
    lat: float
    lon: float
    category: str
    flag: bool  # deserves analyst attention
    confidence: float  # 0..1
    summary: str
    reasons: list[str]
    caveats: list[str]
    features: dict[str, float]
    context: dict[str, Any]
    reviewer: str  # offline | claude:<model> | offline (claude failed: ...)
    decision: str = "pending"  # pending | accepted | rejected
    second_reader: dict[str, Any] | None = None  # language-model reading of the same window, when one is configured

    def to_dict(self, with_image: bool = False) -> dict[str, Any]:
        d = asdict(self)
        d["category_description"] = CATEGORIES.get(self.category, "")
        return d


# --------------------------------------------------------------------------- #
# Context and windows
# --------------------------------------------------------------------------- #
def _context(tr: Track, i: int, j: int, terr=None, cab=None) -> dict[str, Any]:
    lat, lon = float(np.mean(tr.lat[i:j])), float(np.mean(tr.lon[i:j]))
    sub = tr.slice(i, j)
    decl = assess(tr)
    tw = (tr.extra or {}).get("tow_t")
    towing = bool(tw is not None and np.any((tw >= tr.t[i]) & (tw <= tr.t[j - 1])))
    ctx: dict[str, Any] = {
        "ship_type": tr.ship_type, "flag": tr.flag or ("TWN" if tr.mmsi.startswith("416") else ""),
        "declared_score": round(decl.score, 2), "declared_reasons": decl.reasons[:3],
        "towing_announced": towing, "destination": (tr.extra or {}).get("destination", ""),
        "registry_subtype": (tr.extra or {}).get("subtype", ""),
        "restricted_share": round(restricted_share(sub), 2), "status_switches": status_toggles(sub), "fixes": int(j - i),
    }
    if terr is not None:
        ctx["zone"] = terr.zone_at(lat, lon)
        ctx["coast_nm"] = round(float(terr.coast_nm(np.array([lat]), np.array([lon]))[0]), 1)
        ctx["taiwan_land_nm"] = round(float(terr.distance_nm(np.array([lat]), np.array([lon]))[0]), 1)
    if cab is not None:
        d = cab.distance_nm(tr.lat[i:j], tr.lon[i:j])
        ctx["cable_nm"] = round(float(d.min()), 1)
        ctx["cable_share_10nm"] = round(float(np.mean(d <= 10.0)), 2)
        ctx["nearest_cable"] = cab.nearest_name(lat, lon)
    return ctx


def research_gate(tr: Track) -> tuple[bool, str]:
    """Stage 1: does this vessel present as a research / survey vessel at all?"""

    d = assess(tr)
    if d.towing:
        return True, "announces towing / cable work"
    if d.score >= 0.6:
        return True, "declares research / survey work (name, destination or registry class)"
    # restricted-manoeuvre status alone is NOT enough: wind-farm and offshore-construction vessels hold it for weeks (Skandi Connector, Freja,
    # Nile River ...). It counts only as supporting evidence once the vessel presents as research / survey.
    return False, ""


def candidate_windows(tr: Track, max_kn: float = pathml.MAX_MEDIAN_KN, window_s: float = pathml.WINDOW_S, hop_s: float = pathml.HOP_S):
    """Stages 2-3: slow windows (stationary ones included, they can be station-keeping work) with their path features."""

    return pathml.windows_for(tr, window_s=window_s, hop_s=hop_s, min_kn=0.0, max_kn=max_kn, min_path=0.5, min_moving=3, max_gap_s=6 * 3600.0, min_pts=6)


# --------------------------------------------------------------------------- #
# Offline reviewer (deterministic analyst rules)
# --------------------------------------------------------------------------- #
class OfflineReviewer:
    name = "offline"

    def review(self, f: dict[str, float], c: dict[str, Any], image_png: bytes | None = None) -> dict[str, Any]:
        med, cv, ext = f["med_kn"], f["speed_cv"], f["extent_nm"]
        restricted, towing = c["restricted_share"], c["towing_announced"]
        declared = c["declared_score"] >= 0.6
        coast = c.get("coast_nm", 99.0)
        reasons: list[str] = []
        caveats = ["AIS shows the track and what the vessel says about itself, not the instrument deployed or whether the coastal state consented."]

        def out(cat, conf, summary):
            return {"category": cat, "confidence": round(float(conf), 2), "summary": summary, "reasons": reasons, "caveats": caveats}

        if med > pathml.MAX_MEDIAN_KN:
            reasons.append(f"median speed {med:.1f} kn is transit speed")
            return out("transit", 0.8, "Fast, steady movement: transit.")
        if coast <= 3.0 and med < 1.5:
            reasons.append(f"within {coast:.0f} nm of the coast and nearly stopped ({med:.1f} kn)")
            return out("port_or_anchorage", 0.75, "Parked or manoeuvring in harbour waters.")
        if c["ship_type"] == "fishing" and not towing:
            reasons.append("vessel is a fishing type and nothing announces survey work")
            return out("fishing_or_trawl", 0.7, "Fishing-type vessel working a ground.")

        steady = cv <= 0.35 and 2.0 <= med <= 7.0
        axis_lines = f["n_legs"] >= 2 and f["axis_share"] >= 0.55
        lawn = f["n_legs"] >= 4 and f["axis_share"] >= 0.6 and f["path_nm"] >= 12.0 and (f["reversals_per_h"] > 0.05 or f["revisit"] >= 0.1)
        survey_lines = steady and f["path_nm"] >= 10.0 and (axis_lines or f["straightness"] >= 0.35)
        station = med < 4.5 and ext <= 10.0 and (restricted >= 0.8 or (towing and med < 2.5))
        if towing:
            reasons.append(f"destination field announces towing / cable work ('{c['destination']}')")
        if restricted >= 0.3:
            reasons.append(f"'restricted in ability to manoeuvre' for {restricted * 100:.0f}% of reports")
        if declared:
            reasons.append("the vessel declares research / survey work")
        if lawn:
            reasons.append(f"{f['n_legs']:.0f} legs, {f['axis_share'] * 100:.0f}% of headings along one axis, repeated turn-backs: a lawnmower pattern")
            conf = 0.6 + 0.15 * (towing or restricted >= 0.5) + 0.1 * declared
            return out("lawnmower_survey", min(conf, 0.95), "Systematic parallel legs: a survey pattern.")
        if survey_lines and (towing or restricted >= 0.5 or declared):
            reasons.append(f"steady speed (variation {cv:.2f}) at {med:.1f} kn over {f['path_nm']:.0f} nm in {f['n_legs']:.0f} legs, {f['axis_share'] * 100:.0f}% of headings along one axis: slow survey lines")
            conf = 0.5 + 0.2 * towing + 0.15 * (restricted >= 0.5) + 0.1 * declared
            return out("survey_lines_under_tow", min(conf, 0.95), "Slow steady lines consistent with towing a sensor array or running survey lines.")
        if station:
            reasons.append(f"working within a {ext:.1f} nm area at {med:.1f} kn, restricted-manoeuvre status in {restricted * 100:.0f}% of reports")
            conf = 0.55 + 0.2 * towing + 0.15 * (restricted >= 0.8) + 0.05 * declared
            return out("station_keeping_work", min(conf, 0.9), "Working a small area in restricted-manoeuvre status: equipment deployment or seabed / cable work.")
        if med < 1.5 and ext < 3.0:
            reasons.append("nearly stationary with no working status or declaration")
            return out("drift_or_idle", 0.5, "Adrift or idling.")
        reasons.append("shape and status do not match a known working pattern")
        return out("other_unclear", 0.3, "Unclear.")


# --------------------------------------------------------------------------- #
# Claude reviewer
# --------------------------------------------------------------------------- #
SYSTEM_PROMPT = (
    "You review ship tracks for a maritime decision-support tool. You are given a picture of one vessel's track over a few hours "
    "(colour = speed in knots, black rings = reports with navigation status 'restricted in ability to manoeuvre'), numeric shape features, "
    "and AIS context. Decide what the movement looks like. You never decide intent or legality: AIS cannot show consent, the instrument "
    "used, or purpose. Reply with ONE JSON object only, keys: category (one of the listed categories), flag (true if an analyst should "
    "look at it), confidence (0-1), summary (one sentence), reasons (list of short strings that cite the numbers or the picture), "
    "caveats (list of short strings). Be conservative: say other_unclear when unsure."
)


def render_png(tr: Track, i: int, j: int, w: "pathml.Window | None" = None) -> bytes:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 2, figsize=(8.5, 3.8), gridspec_kw={"width_ratios": [1.5, 1]})
    lat, lon, sog = tr.lat[i:j], tr.lon[i:j], np.nan_to_num(tr.sog[i:j], nan=0.0)
    ax[0].plot(lon, lat, color="#9aa", lw=0.6, zorder=1)
    sc = ax[0].scatter(lon, lat, c=np.clip(sog, 0, 14), s=9, cmap="turbo", vmin=0, vmax=14, zorder=2)
    if tr.status is not None:
        r = np.asarray(tr.status[i:j]) == 3
        ax[0].scatter(lon[r], lat[r], s=34, facecolors="none", edgecolors="k", lw=0.7, zorder=3)
    ax[0].set_aspect(1 / np.cos(np.radians(float(np.mean(lat)))))
    ax[0].set_title(f"{tr.name} track (colour = knots)", fontsize=8)
    ax[0].tick_params(labelsize=6)
    fig.colorbar(sc, ax=ax[0], fraction=0.04)
    ax[1].plot((tr.t[i:j] - tr.t[i]) / 3600.0, sog, ".-", ms=2, lw=0.6)
    ax[1].set_xlabel("hours", fontsize=7)
    ax[1].set_ylabel("speed (kn)", fontsize=7)
    ax[1].tick_params(labelsize=6)
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=90)
    plt.close(fig)
    return buf.getvalue()


class ClaudeReviewer:
    """Calls a Claude model with the image + features + context. Backend only: the key is read from the environment."""

    def __init__(self, model: str | None = None, client: Any = None):
        self.model = model or os.environ.get("SEAWATCH_AGENT_MODEL", "claude-sonnet-5-5")
        self.name = f"claude:{self.model}"
        self._client = client
        self._fallback = OfflineReviewer()

    @staticmethod
    def available() -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY"))

    def _get_client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY itself; never logged or serialised
        return self._client

    def review(self, f: dict[str, float], c: dict[str, Any], image_png: bytes | None = None) -> dict[str, Any]:
        facts = {"features": {k: round(float(v), 3) for k, v in f.items()}, "context": c, "categories": CATEGORIES}
        content: list[dict[str, Any]] = []
        if image_png:
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(image_png).decode()}})
        content.append({"type": "text", "text": "Review this window.\n" + json.dumps(facts, ensure_ascii=False)})
        try:
            msg = self._get_client().messages.create(model=self.model, max_tokens=700, system=SYSTEM_PROMPT, messages=[{"role": "user", "content": content}])
            text = "".join(getattr(b, "text", "") for b in msg.content)
            m = re.search(r"\{.*\}", text, re.S)
            data = json.loads(m.group(0)) if m else {}
            cat = data.get("category")
            if cat not in CATEGORIES:
                raise ValueError("unknown category")
            return {"category": cat, "confidence": float(min(1.0, max(0.0, data.get("confidence", 0.5)))), "summary": str(data.get("summary", ""))[:300],
                    "reasons": [str(x)[:240] for x in data.get("reasons", [])][:8], "caveats": [str(x)[:240] for x in data.get("caveats", [])][:5],
                    "flag": bool(data.get("flag", cat in FLAGGED))}
        except Exception as exc:  # noqa: BLE001 - the advisory agent must never break monitoring
            r = self._fallback.review(f, c, image_png)
            r["fallback_reason"] = type(exc).__name__
            return r


# --------------------------------------------------------------------------- #
# Running the pipeline
# --------------------------------------------------------------------------- #
def review_vessels(tracks: list[Track], reviewer=None, terr=None, cab=None, with_images: bool = False, max_windows: int = 4000) -> tuple[list[PathReview], dict[str, int]]:
    """Run the four stages on a set of tracks. Returns reviews of the windows that survived both gates plus a funnel for the UI."""

    reviewer = reviewer or OfflineReviewer()
    funnel = {"vessels": len(tracks), "research_gate": 0, "windows_total": 0, "slow_windows": 0, "flagged": 0}
    out: list[PathReview] = []
    for tr in tracks:
        ok, why = research_gate(tr)
        if not ok or len(tr) < 12:
            continue
        funnel["research_gate"] += 1
        wins = candidate_windows(tr)
        funnel["slow_windows"] += len(wins)
        for w in wins:
            if len(out) >= max_windows:
                break
            i, j = int(np.searchsorted(tr.t, w.t0, "left")), int(np.searchsorted(tr.t, w.t1, "right"))
            if j - i < 4:
                continue
            c = _context(tr, i, j, terr, cab)
            c["gate"] = why
            img = render_png(tr, i, j, w) if (with_images or isinstance(reviewer, ClaudeReviewer)) else None
            if hasattr(reviewer, 'path'):
                reviewer.path = describe_path(tr, i, j)
            r = reviewer.review(w.feats, c, img)
            rid = f"P-{tr.mmsi}-{int(w.t0)}"
            rv = PathReview(rid, tr.mmsi, tr.name, w.t0, w.t1, w.lat, w.lon, r["category"], bool(r.get("flag", r["category"] in FLAGGED)), r["confidence"],
                            r["summary"], r["reasons"], r["caveats"], {k: round(float(v), 3) for k, v in w.feats.items()}, c,
                            reviewer.name + (f" (fallback: {r['fallback_reason']})" if r.get("fallback_reason") else ""),
                            second_reader=r.get("second_reader"))
            funnel["flagged"] += int(rv.flag)
            out.append(rv)
    return out, funnel


def episodes(reviews: list[PathReview], gap_s: float = 3 * 3600.0) -> list[dict[str, Any]]:
    """Merge consecutive flagged windows of one vessel into episodes (what the analyst should see, instead of 6 h slices)."""

    by: dict[str, list[PathReview]] = {}
    for r in sorted(reviews, key=lambda r: (r.mmsi, r.t0)):
        if r.flag:
            by.setdefault(r.mmsi, []).append(r)
    out = []
    for m, rs in by.items():
        cur = [rs[0]]
        for r in rs[1:]:
            if r.t0 <= cur[-1].t1 + gap_s:
                cur.append(r)
            else:
                out.append(cur)
                cur = [r]
        out.append(cur)
    res = []
    for g in out:
        cats = [x.category for x in g]
        main = max(set(cats), key=cats.count)
        res.append({"mmsi": g[0].mmsi, "name": g[0].name, "t0": g[0].t0, "t1": g[-1].t1, "windows": [x.id for x in g], "category": main,
                    "confidence": round(float(np.mean([x.confidence for x in g])), 2), "summary": g[0].summary})
    return sorted(res, key=lambda e: -e["confidence"])


class ReviewStore:
    """Analyst decisions on agent reviews. Persisted as JSON so accepted / rejected cases can seed confirmed_paths.csv."""

    def __init__(self, path: str | Path = "data/state/path_reviews.json"):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._d: dict[str, dict[str, Any]] = {}
        try:
            self._d = json.loads(self.path.read_text(encoding="utf8"))
        except (OSError, ValueError):
            self._d = {}

    def decide(self, review_id: str, decision: str, operator: str = "analyst", note: str = "") -> None:
        if decision not in ("accepted", "rejected", "pending"):
            raise ValueError("decision must be accepted, rejected or pending")
        with self._lock:
            self._d[review_id] = {"decision": decision, "operator": operator, "note": note}
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(json.dumps(self._d, indent=1), encoding="utf8")
            except OSError:
                pass

    def apply(self, r: PathReview) -> PathReview:
        r.decision = self._d.get(r.id, {}).get("decision", "pending")
        return r

    def export_labels(self, reviews: list[PathReview]) -> str:
        """CSV rows for confirmed_paths.csv: accepted -> label 1, rejected -> label 0."""

        import datetime as dt

        rows = ["mmsi,t_start,t_end,label,source"]
        for r in reviews:
            d = self._d.get(r.id, {}).get("decision")
            if d in ("accepted", "rejected"):
                a = dt.datetime.fromtimestamp(r.t0, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                b = dt.datetime.fromtimestamp(r.t1, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                rows.append(f"{r.mmsi},{a},{b},{1 if d == 'accepted' else 0},analyst review {r.id} ({r.category})")
        return "\n".join(rows) + "\n"


# --------------------------------------------------------------------------- #
# Text-only reviewer for OpenAI-compatible hosts (Featherless.ai and similar): no image, a compact numeric description of the path
# --------------------------------------------------------------------------- #
TEXT_SYSTEM = (
    "You review one ship's track for a maritime decision-support tool. You get numbers only (no picture): shape features, AIS context and "
    "a resampled path. Decide what the movement looks like. You never decide intent or legality. Answer with ONE JSON object and nothing else, "
    "keys: category, flag, confidence, summary, reasons, caveats. 'category' must be exactly one of the listed names. 'flag' is true only for "
    "survey_lines_under_tow, lawnmower_survey, station_keeping_work or tow_then_transit. 'reasons' cites the numbers. Prefer other_unclear when unsure."
)


def describe_path(tr: Track, i: int, j: int, n: int = 16) -> list[dict[str, float]]:
    """Compact text description of the path: n points with position offsets from the start (nm), speed and heading."""

    idx = np.unique(np.linspace(i, j - 1, min(n, j - i)).astype(int))
    lat0, lon0 = float(tr.lat[idx[0]]), float(tr.lon[idx[0]])
    out = []
    for k in idx:
        dn = (float(tr.lat[k]) - lat0) * 60.0
        de = (float(tr.lon[k]) - lon0) * 60.0 * float(np.cos(np.radians(lat0)))
        out.append({"h": round((tr.t[k] - tr.t[idx[0]]) / 3600.0, 2), "north_nm": round(dn, 1), "east_nm": round(de, 1),
                    "kn": round(float(tr.sog[k]), 1) if np.isfinite(tr.sog[k]) else None})
    return out


class OpenAICompatReviewer:
    """Chat-completions reviewer for any OpenAI-compatible host. Text only. Falls back to the offline rules on any failure."""

    def __init__(self, base_url: str, model: str, key: str, name: str = "llm", timeout: float = 60.0):
        self.base_url, self.model, self._key, self.timeout = base_url.rstrip("/"), model, key, timeout
        self.name = f"{name}:{model}"
        self._fallback = OfflineReviewer()
        self.path: list[dict[str, float]] = []

    def review(self, f: dict[str, float], c: dict[str, Any], image_png: bytes | None = None) -> dict[str, Any]:
        import urllib.error
        import urllib.request

        facts = {"features": {k: round(float(v), 3) for k, v in f.items()}, "context": {k: v for k, v in c.items() if k != "declared_reasons"},
                 "path": self.path, "categories": CATEGORIES}
        body = json.dumps({"model": self.model, "max_tokens": 500, "temperature": 0.1,
                           "messages": [{"role": "system", "content": TEXT_SYSTEM}, {"role": "user", "content": "Review this window.\n" + json.dumps(facts)}]}).encode()
        req = urllib.request.Request(self.base_url + "/chat/completions", data=body,
                                     headers={"Content-Type": "application/json", "Authorization": "Bearer " + self._key, "User-Agent": "seawatch/1.0"})
        try:
            text = ""
            for attempt in range(3):  # busy host (HTTP 429 / 5xx): wait and retry, then fall back to the rules
                try:
                    with urllib.request.urlopen(req, timeout=self.timeout) as r:
                        text = json.load(r)["choices"][0]["message"]["content"]
                    break
                except urllib.error.HTTPError as he:
                    if he.code not in (429, 500, 502, 503) or attempt == 2:
                        raise
                    time.sleep(2.0 * (attempt + 1))
            m = re.search(r"\{.*\}", text, re.S)
            data = json.loads(m.group(0)) if m else {}
            cat = data.get("category")
            if cat not in CATEGORIES:
                raise ValueError("unknown category")
            return {"category": cat, "confidence": float(min(1.0, max(0.0, float(data.get("confidence", 0.5))))), "summary": str(data.get("summary", ""))[:300],
                    "reasons": [str(x)[:240] for x in data.get("reasons", [])][:8], "caveats": [str(x)[:240] for x in data.get("caveats", [])][:5],
                    "flag": cat in FLAGGED}  # the category decides; small models contradict their own flag field
        except Exception as exc:  # noqa: BLE001 - advisory only; never break monitoring
            res = self._fallback.review(f, c, image_png)
            res["fallback_reason"] = type(exc).__name__
            return res


def featherless_reviewer(model: str | None = None):
    """Reviewer backed by Featherless.ai if FEATHERLESS_API (or _KEY) is set in the environment / .env, else None."""

    from .llmenv import secret

    key = secret("FEATHERLESS_API")
    if not key:
        return None
    return OpenAICompatReviewer("https://api.featherless.ai/v1", model or os.environ.get("SEAWATCH_FEATHERLESS_MODEL", "Qwen/Qwen2.5-7B-Instruct"), key, "featherless")


class EnsembleReviewer:
    """Rules decide the flag; a language model reads the same window as a second opinion. Disagreement is shown, never hidden.

    A small hosted model is cheap but unreliable on its own, so it can neither create nor remove a flag: it adjusts confidence (+0.1 when it
    agrees on the flag, -0.15 when it does not) and adds its own reading to the reasons and caveats.
    """

    def __init__(self, primary, second):
        self.primary, self.second = primary, second
        self.name = f"{primary.name}+{second.name}"
        self.path: list[dict[str, float]] = []

    def review(self, f: dict[str, float], c: dict[str, Any], image_png: bytes | None = None) -> dict[str, Any]:
        r = self.primary.review(f, c, image_png)
        if hasattr(self.second, "path"):
            self.second.path = self.path
        s = self.second.review(f, c, image_png)
        if "fallback_reason" in s:  # the second reader failed: keep the rules' answer and say so
            r.setdefault("caveats", []).append(f"Second reader unavailable ({s['fallback_reason']}); rules only.")
            return r
        agree = bool(s["flag"]) == bool(r.get("flag", r["category"] in FLAGGED))
        r["confidence"] = round(float(min(0.99, max(0.05, r["confidence"] + (0.1 if agree else -0.15)))), 2)
        r["reasons"] = list(r["reasons"]) + [f"Second reader ({self.second.name}) says: {s['category'].replace('_', ' ')} - {s['summary']}"]
        if not agree:
            r["caveats"] = list(r["caveats"]) + [f"The language-model reader disagrees on whether this deserves attention ({s['category'].replace('_', ' ')})."]
        r["second_reader"] = {"category": s["category"], "flag": bool(s["flag"]), "agrees": agree}
        return r


def add_second_readings(reviews: list[PathReview], tracks: dict[str, Track], second, workers: int = 3, only_flagged: bool = True) -> int:
    """Ask a language-model reader about the flagged windows (in parallel) and merge its answer into each review in place. Returns how many were read.

    Same rules as ``EnsembleReviewer``: the rules keep the flag; the reader adjusts confidence and adds its reading or its disagreement.
    """

    from concurrent.futures import ThreadPoolExecutor

    todo = [r for r in reviews if (r.flag or not only_flagged) and r.second_reader is None]

    def one(r: PathReview) -> bool:
        tr = tracks.get(r.mmsi)
        if tr is None:
            return False
        i, j = int(np.searchsorted(tr.t, r.t0, "left")), int(np.searchsorted(tr.t, r.t1, "right"))
        rd = OpenAICompatReviewer(second.base_url, second.model, second._key, "featherless", second.timeout)
        rd.path = describe_path(tr, i, j)
        s = rd.review(r.features, r.context)
        if "fallback_reason" in s:
            return False
        agree = bool(s["flag"]) == r.flag
        r.confidence = round(float(min(0.99, max(0.05, r.confidence + (0.1 if agree else -0.15)))), 2)
        r.reasons = list(r.reasons) + [f"Second reader ({second.name}) says: {s['category'].replace('_', ' ')} - {s['summary']}"]
        if not agree:
            r.caveats = list(r.caveats) + [f"The language-model reader disagrees on whether this deserves attention ({s['category'].replace('_', ' ')})."]
        r.second_reader = {"category": s["category"], "flag": bool(s["flag"]), "agrees": agree}
        r.reviewer = f"{r.reviewer}+{second.name}"
        return True

    with ThreadPoolExecutor(max_workers=workers) as ex:
        return sum(ex.map(one, todo))
