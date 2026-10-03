"""Operator feedback: statuses, notes, and what the system learns from false alarms."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from .geo import NM_M, haversine_m

STATUSES = ("new", "under_review", "confirmed", "escalated", "false_alarm")


class FeedbackStore:
    """Thread-safe store of operator decisions, persisted to a small JSON file."""

    def __init__(self, path: str | Path | None = None):
        self._lock = threading.RLock()
        self.path = Path(path) if path else None
        self.records: dict[str, dict[str, Any]] = {}
        self.allowlist: dict[str, str] = {}
        if self.path and self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.records = data.get("records", {})
                self.allowlist = data.get("allowlist", {})
            except (OSError, ValueError):
                pass

    def _save(self) -> None:
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({"records": self.records, "allowlist": self.allowlist}, indent=1), encoding="utf-8")
        except OSError:
            pass  # persistence is best-effort; in-memory state remains authoritative

    # ------------------------------------------------------------------ #
    def set_status(self, alert, status: str, operator: str = "operator") -> dict[str, Any]:
        if status not in STATUSES:
            raise ValueError(f"unknown status: {status}")
        with self._lock:
            rec = self.records.setdefault(alert.id, {"notes": []})
            rec.update({"status": status, "mmsis": alert.mmsis, "kinds": alert.kinds, "lat": alert.lat, "lon": alert.lon,
                        "title": alert.title, "updated": time.time(), "operator": operator})
            rec["notes"].append({"t": time.time(), "operator": operator, "text": f"Status set to {status.replace('_', ' ')}", "system": True})
            self._save()
            return rec

    def add_note(self, alert, text: str, operator: str = "operator") -> dict[str, Any]:
        with self._lock:
            rec = self.records.setdefault(alert.id, {"notes": [], "status": "new", "mmsis": alert.mmsis, "kinds": alert.kinds,
                                                     "lat": alert.lat, "lon": alert.lon, "title": alert.title})
            rec["notes"].append({"t": time.time(), "operator": operator, "text": text, "system": False})
            rec["updated"] = time.time()
            self._save()
            return rec

    def apply(self, alert) -> None:
        rec = self.records.get(alert.id)
        if rec:
            alert.status = rec.get("status", "new")
            alert.notes = list(rec.get("notes", []))

    def allow(self, mmsi: str, reason: str) -> None:
        with self._lock:
            self.allowlist[mmsi] = reason
            self._save()

    def disallow(self, mmsi: str) -> None:
        with self._lock:
            self.allowlist.pop(mmsi, None)
            self._save()

    def clear(self) -> None:
        with self._lock:
            self.records.clear()
            self.allowlist.clear()
            self._save()

    # ------------------------------------------------------------------ #
    def risk_modifier(self, mmsis: list[str], kinds: list[str], events) -> tuple[float, str | None]:
        """Multiplier applied to a new alert's risk, from past operator decisions."""

        factor, why = 1.0, None
        with self._lock:
            for rid, rec in self.records.items():
                st = rec.get("status")
                if st not in ("false_alarm", "confirmed", "escalated"):
                    continue
                same_vessel = bool(set(rec.get("mmsis", [])) & set(mmsis))
                same_kind = bool(set(rec.get("kinds", [])) & set(kinds))
                near = False
                if same_kind and not same_vessel and rec.get("lat") is not None:
                    near = any(
                        haversine_m(rec["lat"], rec["lon"], e.lat, e.lon) / NM_M < 8.0 and e.kind in rec.get("kinds", [])
                        for e in events
                    )
                if st == "false_alarm":
                    if same_vessel and same_kind:
                        if 0.45 < factor:
                            factor, why = 0.45, "Same vessel and behaviour was dismissed as a false alarm earlier"
                    elif near and 0.75 < factor:
                        factor, why = 0.75, "A similar event at this location was dismissed as a false alarm earlier"
                elif same_vessel and factor == 1.0:
                    factor, why = 1.15, "This vessel was confirmed as noteworthy earlier"
        return factor, why


def default_store() -> FeedbackStore:
    p = os.environ.get("SEAWATCH_OPERATOR_STATE")
    return FeedbackStore(p) if p else FeedbackStore(None)
