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
from typing import Any, Optional

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
    key = settings.etsy_api_key
    log.info("Etsy auth: key=%s…%s token=%s…", key[:4], key[-4:], token[-6:])
    return {
        "Authorization": f"Bearer {token}",
        "x-api-key": key,
        "Content-Type": "application/json",
    }


async def create_listing(
    title: str,
    description: str,
    tags: list[str],
    price_usd: float,
    image_path: str,
) -> str:
    """Create an active Etsy listing with an uploaded image. Returns listing_id."""
    settings = get_settings()
    headers = await _etsy_headers()

    # Step 1: create draft listing
    shipping_profile_id = await _get_default_shipping_profile(settings.etsy_shop_id, headers)
    payload: dict[str, Any] = {
        "quantity": 999,
        "title": title,
        "description": description,
        "price": price_usd,
        "who_made": "i_did",
        "when_made": "made_to_order",
        "taxonomy_id": 1063,  # Clothing > Shirts & Tops > T-shirts
        "tags": tags[:13],
        "state": "active",
        "type": "physical",
    }
    if shipping_profile_id is not None:
        payload["shipping_profile_id"] = shipping_profile_id

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{_ETSY_BASE}/shops/{settings.etsy_shop_id}/listings",
            json=payload,
            headers=headers,
        )
        if not r.is_success:
            log.error("Etsy create_listing error: %s %s", r.status_code, r.text)
        r.raise_for_status()

    listing_id: str = str(r.json()["listing_id"])
    log.info("Created Etsy listing %s: %r", listing_id, title)

    # Step 2: upload image to the listing
    await _upload_listing_image(listing_id, image_path)

    return listing_id


async def _get_default_shipping_profile(shop_id: str, headers: dict) -> int | None:
    """Return the first shipping profile ID for the shop, or None if unavailable."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{_ETSY_BASE}/shops/{shop_id}/shipping-profiles",
                headers=headers,
            )
            r.raise_for_status()
        profiles = r.json().get("results", [])
        if profiles:
            return profiles[0]["shipping_profile_id"]
    except Exception as exc:
        log.warning("Could not fetch shipping profiles (%s) — listing without one", exc)
    return None


async def _upload_listing_image(listing_id: str, image_path: str) -> None:
    """Upload a PNG file as the listing's primary image."""
    settings = get_settings()
    token = await _get_access_token()
    # Image upload must be multipart, not JSON
    headers = {
        "Authorization": f"Bearer {token}",
        "x-api-key": settings.etsy_api_key,
    }
    async with httpx.AsyncClient(timeout=60) as client:
        with open(image_path, "rb") as f:
            r = await client.post(
                f"{_ETSY_BASE}/shops/{settings.etsy_shop_id}/listings/{listing_id}/images",
                headers=headers,
                files={"image": (image_path.split("/")[-1], f, "image/png")},
                data={"rank": "1", "overwrite": "true"},
            )
            if not r.is_success:
                log.error("Etsy image upload error: %s %s", r.status_code, r.text)
            r.raise_for_status()
    log.info("Uploaded image to Etsy listing %s", listing_id)


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
