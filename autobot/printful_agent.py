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

# Printful variant IDs for Comfort Colors 1717 Garment-Dyed Heavyweight T-Shirt
# Product ID 586 — 4 colors x 5 sizes = 20 variants
_VARIANTS = [
    {"id": 15114, "color": "Black", "size": "S"},
    {"id": 15115, "color": "Black", "size": "M"},
    {"id": 15116, "color": "Black", "size": "L"},
    {"id": 15117, "color": "Black", "size": "XL"},
    {"id": 15118, "color": "Black", "size": "2XL"},
    {"id": 15124, "color": "White", "size": "S"},
    {"id": 15125, "color": "White", "size": "M"},
    {"id": 15126, "color": "White", "size": "L"},
    {"id": 15127, "color": "White", "size": "XL"},
    {"id": 15128, "color": "White", "size": "2XL"},
    {"id": 16523, "color": "Ivory", "size": "S"},
    {"id": 16524, "color": "Ivory", "size": "M"},
    {"id": 16525, "color": "Ivory", "size": "L"},
    {"id": 16526, "color": "Ivory", "size": "XL"},
    {"id": 16527, "color": "Ivory", "size": "2XL"},
    {"id": 15176, "color": "Grey",  "size": "S"},
    {"id": 15177, "color": "Grey",  "size": "M"},
    {"id": 15178, "color": "Grey",  "size": "L"},
    {"id": 15179, "color": "Grey",  "size": "XL"},
    {"id": 15180, "color": "Grey",  "size": "2XL"},
]

_PRODUCT_ID = 586  # Comfort Colors 1717 Garment-Dyed Heavyweight T-Shirt


def _headers(include_store: bool = True) -> dict[str, str]:
    settings = get_settings()
    h = {
        "Authorization": f"Bearer {settings.printful_api_key}",
        "Content-Type": "application/json",
    }
    if include_store:
        h["X-PF-Store-Id"] = settings.printful_store_id
    return h


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

    settings = get_settings()
    headers = {
        "Authorization": f"Bearer {settings.printful_api_key}",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{_BASE}/files",
            data={
                "type": "default",
                "filename": image_path.name,
                "url": f"data:image/png;base64,{b64}",
            },
            headers=headers,
        )
        if not r.is_success:
            log.error("Printful file upload error: %s %s", r.status_code, r.text)
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

    sync_variants = [
        {
            "variant_id": v["id"],
            "retail_price": str(retail_price),
            "files": [{"type": "front", "url": image_url}],
        }
        for v in _VARIANTS
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
