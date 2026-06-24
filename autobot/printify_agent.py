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

# Standard sizes for a unisex tee; adjust as needed
_DEFAULT_VARIANTS = [
    {"id": 12126, "price": 0, "is_enabled": True},  # Black / S
    {"id": 12125, "price": 0, "is_enabled": True},  # Black / M
    {"id": 12124, "price": 0, "is_enabled": True},  # Black / L
    {"id": 12127, "price": 0, "is_enabled": True},  # Black / XL
    {"id": 12128, "price": 0, "is_enabled": True},  # Black / 2XL
]


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
    mockup_image_id: str | None = None,
) -> str:
    """Create a Printify product and return its product ID."""
    settings = get_settings()

    variants = [
        {**v, "price": retail_price_cents}
        for v in _DEFAULT_VARIANTS
    ]

    images = [{"id": image_id, "x": 0.5, "y": 0.5, "scale": 1, "angle": 0}]
    if mockup_image_id:
        images.append({"id": mockup_image_id, "x": 0.5, "y": 0.5, "scale": 1, "angle": 0})

    product_payload: dict[str, Any] = {
        "title": title,
        "description": description,
        "blueprint_id": settings.printify_blueprint_id,
        "print_provider_id": settings.printify_print_provider_id,
        "variants": variants,
        "print_areas": [
            {
                "variant_ids": [v["id"] for v in _DEFAULT_VARIANTS],
                "placeholders": [
                    {
                        "position": "front",
                        "images": images,
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
