"""
Etsy OAuth2 + listing management.

Handles token refresh automatically.
Listing creation delegates to Printify's publish endpoint (which creates the
Etsy listing via the Etsy sales-channel integration).  This module handles
any supplementary Etsy API calls such as activating or updating listings.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from .config import get_settings

log = logging.getLogger(__name__)

_ETSY_BASE = "https://openapi.etsy.com/v3/application"
_TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"

# Simple in-memory token cache
_token_cache: dict[str, Any] = {}


async def _get_access_token() -> str:
    """Return a valid Etsy access token, refreshing if necessary."""
    settings = get_settings()
    now = time.time()

    if _token_cache.get("expires_at", 0) > now + 60:
        return _token_cache["access_token"]  # type: ignore[return-value]

    log.info("Refreshing Etsy access token")
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            _TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": settings.etsy_api_key,
                "refresh_token": settings.etsy_refresh_token,
            },
        )
        r.raise_for_status()

    token_data = r.json()
    _token_cache["access_token"] = token_data["access_token"]
    _token_cache["expires_at"] = now + token_data.get("expires_in", 3600)
    if "refresh_token" in token_data:
        # persist updated refresh token in settings object (runtime only)
        settings.etsy_refresh_token = token_data["refresh_token"]
    return _token_cache["access_token"]  # type: ignore[return-value]


async def _etsy_headers() -> dict[str, str]:
    token = await _get_access_token()
    settings = get_settings()
    return {
        "Authorization": f"Bearer {token}",
        "x-api-key": settings.etsy_api_key,
        "Content-Type": "application/json",
    }


async def activate_listing(listing_id: str) -> None:
    """Set a draft Etsy listing to 'active' (visible to buyers)."""
    settings = get_settings()
    headers = await _etsy_headers()
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.patch(
            f"{_ETSY_BASE}/shops/{settings.etsy_shop_id}/listings/{listing_id}",
            json={"state": "active"},
            headers=headers,
        )
        r.raise_for_status()
    log.info("Etsy listing %s activated", listing_id)


async def get_order(receipt_id: str) -> dict[str, Any]:
    """Fetch an Etsy order receipt (used during fulfillment)."""
    settings = get_settings()
    headers = await _etsy_headers()
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{_ETSY_BASE}/shops/{settings.etsy_shop_id}/receipts/{receipt_id}",
            headers=headers,
        )
        r.raise_for_status()
    return r.json()  # type: ignore[return-value]
