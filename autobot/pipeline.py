"""
Main daily pipeline:
  trend_scout → design_generator → printify_agent → (Etsy listing via Printify publish)
"""
from __future__ import annotations

import logging
from pathlib import Path

from .config import get_settings
from .design_generator import generate_design
from .printify_agent import create_product, publish_product, upload_image
from .trend_scout import get_trending_keywords

log = logging.getLogger(__name__)

_DESIGNS_DIR = Path("designs")


async def run_pipeline(top_n_trends: int = 5) -> None:
    """Discover trends, generate designs, create & publish products."""
    settings = get_settings()
    retail_price_cents = int(settings.base_price_usd * 100)

    log.info("=== Pipeline start ===")
    keywords = await get_trending_keywords(top_n=top_n_trends)
    if not keywords:
        log.warning("No keywords found — aborting pipeline")
        return

    for kw in keywords:
        try:
            await _process_keyword(kw, retail_price_cents)
        except Exception:
            log.exception("Failed to process keyword %r — continuing", kw)

    log.info("=== Pipeline complete ===")


async def _process_keyword(keyword: str, retail_price_cents: int) -> None:
    log.info("Processing keyword: %r", keyword)

    # 1. Generate artwork
    design_path = await generate_design(keyword, out_dir=_DESIGNS_DIR)

    # 2. Upload to Printify
    image_id = await upload_image(design_path)

    # 3. Build metadata
    title = _make_title(keyword)
    description = _make_description(keyword)
    tags = _make_tags(keyword)

    # 4. Create Printify product
    product_id = await create_product(
        title=title,
        description=description,
        image_id=image_id,
        tags=tags,
        retail_price_cents=retail_price_cents,
    )

    # 5. Publish to Etsy via Printify sales channel
    await publish_product(product_id)

    log.info("Done: keyword=%r product_id=%s", keyword, product_id)


def _make_title(keyword: str) -> str:
    kw = keyword.title()
    return f"{kw} T-Shirt | Graphic Tee | Unisex Cotton Shirt"


def _make_description(keyword: str) -> str:
    kw = keyword.title()
    return (
        f"Express yourself with our {kw} graphic t-shirt! "
        "Printed on premium unisex cotton using direct-to-garment technology. "
        "Soft, comfortable, and true-to-size. Makes a perfect gift.\n\n"
        "• High-quality graphic print\n"
        "• 100% ring-spun cotton\n"
        "• Available in S–2XL\n"
        "• Ships within 3–7 business days"
    )


def _make_tags(keyword: str) -> list[str]:
    words = keyword.lower().split()
    base = ["graphic tee", "unisex shirt", "gift", "cool shirt", "trendy"]
    specific = [keyword, *words]
    return list(dict.fromkeys(specific + base))[:13]
