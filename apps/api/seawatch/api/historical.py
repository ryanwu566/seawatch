"""Read-only historical vessel-baseline API."""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, status

from ..historical.store import (
    HistoricalBaselineUnavailableError,
    get_historical_baseline_store,
)


router = APIRouter(prefix="/historical", tags=["historical"])

_OPAQUE_PUBLIC_ID = re.compile(r"^v_[A-Za-z0-9_-]+$")
_MAX_PUBLIC_ID_LENGTH = 128


@router.get(
    "/vessels/{public_id}/baseline",
    summary="Historical GFW presence baseline for an opaque live vessel ID",
)
def historical_vessel_baseline(public_id: str) -> dict:
    if (
        len(public_id) > _MAX_PUBLIC_ID_LENGTH
        or _OPAQUE_PUBLIC_ID.fullmatch(public_id) is None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid public vessel identifier",
        )

    try:
        baseline = get_historical_baseline_store().get(public_id)
    except HistoricalBaselineUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Historical baseline unavailable",
        ) from None

    if baseline is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Historical baseline not found",
        )
    return baseline.to_dict()
