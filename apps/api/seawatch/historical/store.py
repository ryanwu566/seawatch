"""Lazy process-wide access to privacy-safe GFW vessel baselines."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import logging
import threading

from ..live import get_live_runtime
from .pipeline import build_gfw_baselines
from .schema import VesselBaseline


logger = logging.getLogger("seawatch.historical.store")


class HistoricalBaselineUnavailableError(RuntimeError):
    """Raised with sanitized detail when historical data cannot be served."""


BaselineBuilder = Callable[[], Mapping[str, VesselBaseline]]


def _build_process_baselines() -> Mapping[str, VesselBaseline]:
    runtime = get_live_runtime()
    if runtime.config.identity_key is None:
        raise RuntimeError("historical identity configuration unavailable")
    return build_gfw_baselines(identity_registry=runtime.identity_registry)


class HistoricalBaselineStore:
    """Build the historical index once, then provide O(1) opaque-ID lookups."""

    def __init__(self, builder: BaselineBuilder = _build_process_baselines) -> None:
        self._builder = builder
        self._lock = threading.RLock()
        self._baselines: dict[str, VesselBaseline] | None = None
        self._unavailable = False

    def get(self, public_id: str) -> VesselBaseline | None:
        with self._lock:
            if self._unavailable:
                raise HistoricalBaselineUnavailableError(
                    "Historical baseline unavailable"
                )
            if self._baselines is None:
                try:
                    self._baselines = dict(self._builder())
                except Exception:  # noqa: BLE001 - sanitize every init failure
                    self._unavailable = True
                    logger.warning(
                        "Historical baseline initialization failed; "
                        "service remains unavailable until restart"
                    )
                    raise HistoricalBaselineUnavailableError(
                        "Historical baseline unavailable"
                    ) from None
            return self._baselines.get(public_id)


_store: HistoricalBaselineStore | None = None
_store_lock = threading.Lock()


def get_historical_baseline_store() -> HistoricalBaselineStore:
    global _store
    with _store_lock:
        if _store is None:
            _store = HistoricalBaselineStore()
        return _store


def reset_historical_baseline_store() -> None:
    """Reset process-wide historical state for isolated tests only."""

    global _store
    with _store_lock:
        _store = None
