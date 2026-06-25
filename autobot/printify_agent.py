"""
Printify API agent.

Responsibilities:
  - Upload a design image
  - Create a product (blueprint + print provider)
  - Publish the product to the connected Etsy store
  - Submit an order to Printify when fulfillment is needed
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

import httpx

from .config import get_settings

log = logging.getLogger(__name__)

_BASE = "https://api.printify.com/v1"

# Comfort Colors colors to enable (lowercase match against Printify color labels)
_COMFORT_COLORS = {
    "white", "ivory", "pepper", "blue jean", "seafoam",
    "butter", "moss", "crimson", "grey", "washed denim",
}

# Sizes to enable
_ENABLED_SIZES = {"s", "m", "l", "xl", "2xl"}

# Cache: (blueprint_id, print_provider_id) → list of variant dicts
_variant_cache: dict[tuple[int, int], list[dict]] = {}


async def _fetch_variants(blueprint_id: int, print_provider_id: int) -> list[dict]:
    """
    Fetch available variants from Printify catalog and filter to desired
    Comfort Colors colors + standard sizes. Results are cached in memory.
    """
    cache_key = (blueprint_id, print_provider_id)
    if cache_key in _variant_cache:
        return _variant_cache[cache_key]

    settings = get_settings()
    url = f"{_BASE}/catalog/blueprints/{blueprint_id}/print_providers/{print_provider_id}/variants.json"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, headers=_headers())
        r.raise_for_status()

    all_variants = r.json().get("variants", [])
    log.info("Fetched %d variants for blueprint %d / provider %d",
             len(all_variants), blueprint_id, print_provider_id)

    filtered = []
    for v in all_variants:
        options = {o["name"].lower(): o["value"].lower() for o in v.get("options", [])}
        color = options.get("color", "")
        size = options.get("size", "")
        if color in _COMFORT_COLORS and size in _ENABLED_SIZES:
            filtered.append({"id": v["id"], "price": 0, "is_enabled": True})

    if not filtered:
        # Fallback: enable all variants if filter matched nothing
        log.warning("Color/size filter matched 0 variants — enabling all %d", len(all_variants))
        filtered = [{"id": v["id"], "price": 0, "is_enabled": True} for v in all_variants]

    log.info("Using %d variants after filtering", len(filtered))
    _variant_cache[cache_key] = filtered
    return filtered


def _headers() -> dict[str, str]:
    settings = get_settings()
    return {
        "Authorization": f"Bearer {settings.printify_api_key}",
        "Content-Type": "application/json",
    }


async def upload_image(image_path: Path) -> str:
    """Upload a PNG to Printify and return the image ID."""
    settings = get_settings()
    raw = image_path.read_bytes()
    payload = {
        "file_name": image_path.name,
        "contents": base64.b64encode(raw).decode(),
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{_BASE}/uploads/images.json",
            json=payload,
            headers=_headers(),
        )
        r.raise_for_status()
    data = r.json()
    image_id: str = data["id"]
    log.info("Uploaded image → Printify ID %s", image_id)
    return image_id


async def create_product(
    title: str,
    description: str,
    image_id: str,
    tags: list[str],
    retail_price_cents: int,
) -> str:
    """Create a Printify product and return its product ID."""
    settings = get_settings()

    base_variants = await _fetch_variants(
        settings.printify_blueprint_id,
        settings.printify_print_provider_id,
    )
    variants = [{**v, "price": retail_price_cents} for v in base_variants]

    product_payload: dict[str, Any] = {
        "title": title,
        "description": description,
        "blueprint_id": settings.printify_blueprint_id,
        "print_provider_id": settings.printify_print_provider_id,
        "variants": variants,
        "print_areas": [
            {
                "variant_ids": [v["id"] for v in base_variants],
                "placeholders": [
                    {
                        "position": "front",
                        "images": [
                            {
                                "id": image_id,
                                "x": 0.5,
                                "y": 0.5,
                                "scale": 1,
                                "angle": 0,
                            }
                        ],
                    }
                ],
            }
        ],
        "tags": tags[:13],  # Etsy allows 13
    }

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{_BASE}/shops/{settings.printify_shop_id}/products.json",
            json=product_payload,
            headers=_headers(),
        )
        r.raise_for_status()

    product_id: str = r.json()["id"]
    log.info("Created Printify product %s: %r", product_id, title)
    return product_id


async def publish_product(product_id: str) -> None:
    """Push the product to the connected Etsy sales channel."""
    settings = get_settings()
    publish_payload = {
        "title": True,
        "description": True,
        "images": True,
        "variants": True,
        "tags": True,
        "keyFeatures": True,
        "shipping_template": True,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{_BASE}/shops/{settings.printify_shop_id}/products/{product_id}/publish.json",
            json=publish_payload,
            headers=_headers(),
        )
        r.raise_for_status()
    log.info("Published product %s to sales channel", product_id)


async def submit_order(printify_order: dict[str, Any]) -> str:
    """Submit a fulfilment order to Printify; returns the Printify order ID."""
    settings = get_settings()
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{_BASE}/shops/{settings.printify_shop_id}/orders.json",
            json=printify_order,
            headers=_headers(),
        )
        r.raise_for_status()
    order_id: str = r.json()["id"]
    log.info("Submitted fulfillment order → Printify order %s", order_id)
    return order_id
