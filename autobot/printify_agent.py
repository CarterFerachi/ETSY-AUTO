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

# Colors to enable (lowercase match against Printify color labels)
_ENABLED_COLORS = {
    "white", "black", "navy", "navy blue", "grey", "gray",
    "heather grey", "heather gray", "dark grey", "dark gray",
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
        opts = v.get("options", {})
        if isinstance(opts, dict):
            color = opts.get("color", "").lower()
            size = opts.get("size", "").lower()
        elif isinstance(opts, list) and opts and isinstance(opts[0], dict):
            opt_map = {o["name"].lower(): o["value"].lower() for o in opts}
            color = opt_map.get("color", "")
            size = opt_map.get("size", "")
        else:
            color, size = "", ""

        color_match = not color or any(c in color for c in _ENABLED_COLORS)
        size_match = not size or size in _ENABLED_SIZES
        if color_match and size_match:
            filtered.append({"id": v["id"], "price": 0, "is_enabled": True})

    if not filtered:
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
    preview_url: str = data.get("preview_url", "")
    log.info("Uploaded image → Printify ID %s", image_id)
    return image_id, preview_url


async def create_product(
    title: str,
    description: str,
    image_id: str,
    tags: list[str],
    retail_price_cents: int,
    mockup_url: str | None = None,
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

    # Lifestyle mockup as the first/default image so Etsy thumbnail looks realistic
    if mockup_url:
        product_payload["images"] = [
            {"src": mockup_url, "position": "front", "is_default": True, "is_selected_for_publishing": True}
        ]

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


async def get_product_mockup_url(product_id: str) -> str | None:
    """Return the first auto-generated mockup image URL for a Printify product."""
    settings = get_settings()
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{_BASE}/shops/{settings.printify_shop_id}/products/{product_id}.json",
            headers=_headers(),
        )
        if not r.is_success:
            log.warning("Could not fetch product %s for mockup URL: %s", product_id, r.status_code)
            return None
    images = r.json().get("images", [])
    for img in images:
        src = img.get("src", "")
        if src:
            log.info("Printify auto-mockup for %s: %s", product_id, src)
            return src
    return None


async def add_lifestyle_image(product_id: str, image_url: str) -> None:
    """Add a lifestyle mockup image URL to an existing Printify product."""
    settings = get_settings()
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.put(
            f"{_BASE}/shops/{settings.printify_shop_id}/products/{product_id}.json",
            json={"images": [{"src": image_url, "position": "other", "is_default": False, "is_selected_for_publishing": True}]},
            headers=_headers(),
        )
        if not r.is_success:
            log.warning("Could not add lifestyle image to product %s: %s %s", product_id, r.status_code, r.text)
        else:
            log.info("Added lifestyle image to product %s", product_id)


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
