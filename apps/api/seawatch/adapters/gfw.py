"""Global Fishing Watch (GFW) API integration scaffolding.

This module is *scaffolding only*. It documents how a future real Taiwan-area
cohort could be sourced from the Global Fishing Watch API and provides a thin,
token-gated client wrapper. It intentionally:

- reads the API token from the ``GFW_API_TOKEN`` environment variable only,
- never embeds or commits a token,
- fabricates no data and returns nothing unless a token and network are present.

Licensing / suitability notes (verified 2026-09-30):

- GFW requires a personal API access token sent as ``Authorization: Bearer <token>``
  (register an account, create a token, agree to the terms of use, and attribute
  Global Fishing Watch in anything published). Tokens do not expire and must be
  kept private — never commit them.
- Non-commercial use with rate limits (about 50,000 requests/day).
- GFW data is primarily fishing-vessel AIS with events, insights, and gridded
  apparent-fishing-effort. Continuous, dense, per-vessel *trajectories* for an
  arbitrary area are not guaranteed and dataset access is permissioned. Verify
  density and dataset permissions before relying on GFW for demo track geometry.

Because a token cannot be invented here and dense Taiwan trajectories are not
guaranteed, the shipped Taiwan demo uses a clearly-labeled synthetic scenario
(see ``apps/web/src/demo/``). This module is the seam for swapping in real data
later.
"""

from __future__ import annotations

import os

GFW_API_BASE_URL = "https://gateway.api.globalfishingwatch.org/v3"
_TOKEN_ENV = "GFW_API_TOKEN"


class GfwTokenMissingError(RuntimeError):
    """Raised when a GFW API token is required but not configured."""


def get_gfw_token() -> str | None:
    """Return the GFW API token from the environment, or None if unset.

    The token is read exclusively from ``GFW_API_TOKEN``. It is never hard-coded,
    logged, or committed.
    """

    token = os.environ.get(_TOKEN_ENV)
    return token.strip() if token and token.strip() else None


def gfw_available() -> bool:
    """Whether a GFW token is configured (network is still required at call time)."""

    return get_gfw_token() is not None


def auth_headers() -> dict[str, str]:
    """Build the Authorization header for GFW requests.

    Raises:
        GfwTokenMissingError: If no token is configured. Callers should treat this
            as "real GFW data unavailable" and fall back to the labeled demo.
    """

    token = get_gfw_token()
    if token is None:
        raise GfwTokenMissingError(
            "GFW_API_TOKEN is not set. Register at globalfishingwatch.org, create a "
            "token, and export GFW_API_TOKEN. Never commit the token."
        )
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}
