"""
Printful API agent.

Responsibilities:
  - Upload a design image
  - Create a product with 4 colors (Black, White, Sand, Sport Grey)
  - Push the product to the connected Etsy store
  - Submit an order to Printful when fulfillment is needed
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

import httpx

from .config import get_settings

log = logging.getLogger(__name__)

_BASE = "https://api.printful.com"

# Printful variant IDs for Gildan 18000 Heavy Blend Crewneck (4 colors x 5 sizes)
# These are Printful's catalog variant IDs — confirmed for this product
_VARIANTS = [
    {"id": 4012, "color": "Black",      "size": "S"},
    {"id": 4013, "color": "Black",      "size": "M"},
    {"id": 4014, "color": "Black",      "size": "L"},
    {"id": 4015, "color": "Black",      "size": "XL"},
    {"id": 4016, "color": "Black",      "size": "2XL"},
    {"id": 4017, "color": "White",      "size": "S"},
    {"id": 4018, "color": "White",      "size": "M"},
    {"id": 4019, "color": "White",      "size": "L"},
    {"id": 4020, "color": "White",      "size": "XL"},
    {"id": 4021, "color": "White",      "size": "2XL"},
    {"id": 4022, "color": "Sand",       "size": "S"},
    {"id": 4023, "color": "Sand",       "size": "M"},
    {"id": 4024, "color": "Sand",       "size": "L"},
    {"id": 4025, "color": "Sand",       "size": "XL"},
    {"id": 4026, "color": "Sand",       "size": "2XL"},
    {"id": 4027, "color": "Sport Grey", "size": "S"},
    {"id": 4028, "color": "Sport Grey", "size": "M"},
    {"id": 4029, "color": "Sport Grey", "size": "L"},
    {"id": 4030, "color": "Sport Grey", "size": "XL"},
    {"id": 4031, "color": "Sport Grey", "size": "2XL"},
]


def _headers() -> dict[str, str]:
    settings = get_settings()
    return {
        "Authorization": f"Bearer {settings.printful_api_key}",
        "Content-Type": "application/json",
        "X-PF-Store-Id": settings.printful_store_id,
    }


async def get_variant_ids() -> list[dict]:
    """Fetch real variant IDs from Printful catalog for Gildan 18000."""
    settings = get_settings()
    target_colors = {"Black", "White", "Sand", "Sport Grey"}
    target_sizes = {"S", "M", "L", "XL", "2XL"}

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{_BASE}/products/71/variants",
            headers=_headers(),
        )
        r.raise_for_status()

    variants = []
    for v in r.json().get("result", []):
        color = v.get("color", "")
        size = v.get("size", "")
        if color in target_colors and size in target_sizes:
            variants.append({"id": v["id"], "color": color, "size": size})

    log.info("Fetched %d Printful variants", len(variants))
    return variants


async def upload_image(image_path: Path) -> str:
    """Upload a PNG to Printful files API and return the file URL."""
    raw = image_path.read_bytes()
    b64 = base64.b64encode(raw).decode()

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{_BASE}/files",
            json={
                "type": "default",
                "filename": image_path.name,
                "contents": b64,
            },
            headers=_headers(),
        )
        r.raise_for_status()

    file_url: str = r.json()["result"]["url"]
    log.info("Uploaded image → Printful URL %s", file_url)
    return file_url


async def create_product(
    title: str,
    description: str,
    image_url: str,
    tags: list[str],
    retail_price: float,
) -> str:
    """Create a Printful sync product and return its sync product ID."""
    settings = get_settings()

    # Fetch real variant IDs from Printful catalog
    variants = await get_variant_ids()
    if not variants:
        raise RuntimeError("No Printful variants found — check product ID")

    sync_variants = [
        {
            "variant_id": v["id"],
            "retail_price": str(retail_price),
            "files": [{"type": "front", "url": image_url}],
        }
        for v in variants
    ]

    payload = {
        "sync_product": {
            "name": title,
            "description": description,
            "tags": tags[:13],
        },
        "sync_variants": sync_variants,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{_BASE}/store/products",
            json=payload,
            headers=_headers(),
        )
        r.raise_for_status()

    product_id: str = str(r.json()["result"]["id"])
    log.info("Created Printful product %s: %r", product_id, title)
    return product_id


async def submit_order(printful_order: dict[str, Any]) -> str:
    """Submit a fulfillment order to Printful; returns the order ID."""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{_BASE}/orders",
            json=printful_order,
            headers=_headers(),
        )
        r.raise_for_status()
    order_id: str = str(r.json()["result"]["id"])
    log.info("Submitted fulfillment order → Printful order %s", order_id)
    return order_id
