"""
Main daily pipeline with Etsy suspension safeguards:
  - Rate limits listings per day (max 3 for new shops, increases over time)
  - Adds random delays between listings to look human
  - Filters keywords for trademark/copyright risk
  - Varies titles and descriptions to avoid duplicate content flags
  - Keeps a log of published keywords to avoid repeats
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from datetime import date
from pathlib import Path

from .config import get_settings
from .design_generator import generate_design
from .printify_agent import create_product, publish_product, upload_image
from .trend_scout import get_trending_keywords

log = logging.getLogger(__name__)

_DESIGNS_DIR = Path("designs")
_PUBLISHED_LOG = Path("published_keywords.json")

# Trademarked/risky terms to never use
_BLOCKED_TERMS = {
    "nike", "adidas", "supreme", "gucci", "disney", "marvel", "dc comics",
    "star wars", "pokemon", "harry potter", "nfl", "nba", "mlb", "nhl",
    "coca cola", "pepsi", "apple", "google", "amazon", "netflix",
    "minecraft", "fortnite", "roblox", "among us", "copyright", "trademark",
}

# Title variations to avoid duplicate content
_TITLE_SUFFIXES = [
    "Graphic Tee | Unisex Cotton Shirt",
    "T-Shirt Gift | Soft Unisex Tee",
    "Shirt | Perfect Gift Idea",
    "Tee Shirt | Comfortable Unisex Fit",
    "Graphic T-Shirt | Casual Wear",
]

_DESCRIPTION_INTROS = [
    "Show off your style with this unique {kw} graphic t-shirt!",
    "This {kw} t-shirt is the perfect way to express yourself.",
    "A great gift for anyone who loves {kw}.",
    "Stand out from the crowd with this bold {kw} design.",
    "Looking for the perfect {kw} shirt? You found it.",
]

_DESCRIPTION_BODIES = [
    (
        "Printed on premium unisex cotton using direct-to-garment technology. "
        "Soft, comfortable, and true-to-size.\n\n"
        "• High-quality graphic print\n"
        "• 100% ring-spun cotton\n"
        "• Available in S–2XL\n"
        "• Ships within 3–7 business days"
    ),
    (
        "Made with soft, breathable cotton and printed with vibrant, long-lasting ink.\n\n"
        "• Premium DTG print\n"
        "• Unisex sizing S–2XL\n"
        "• Machine washable\n"
        "• Ships within 3–5 business days"
    ),
    (
        "Comfortable everyday wear with a bold graphic print that won't fade.\n\n"
        "• 100% cotton construction\n"
        "• True-to-size unisex fit\n"
        "• Sizes S through 2XL\n"
        "• Fast fulfillment, ships in 3–7 days"
    ),
]


def _load_published() -> set[str]:
    if _PUBLISHED_LOG.exists():
        return set(json.loads(_PUBLISHED_LOG.read_text()))
    return set()


def _save_published(keywords: set[str]) -> None:
    _PUBLISHED_LOG.write_text(json.dumps(sorted(keywords)))


def _is_safe_keyword(keyword: str) -> bool:
    kw_lower = keyword.lower()
    for blocked in _BLOCKED_TERMS:
        if blocked in kw_lower:
            log.warning("Blocked risky keyword: %r (matches %r)", keyword, blocked)
            return False
    return True


def _daily_listing_limit() -> int:
    """
    Ramp up slowly to avoid triggering Etsy's new-shop filters.
    Start at 2/day, increase to 5 after 30 days of the log existing.
    """
    if not _PUBLISHED_LOG.exists():
        return 2
    published = _load_published()
    if len(published) < 20:
        return 2
    if len(published) < 60:
        return 3
    return 5


async def run_pipeline(top_n_trends: int = 10) -> None:
    """Discover trends, generate designs, create & publish products safely."""
    settings = get_settings()
    retail_price_cents = int(settings.base_price_usd * 100)
    published = _load_published()
    limit = _daily_listing_limit()

    log.info("=== Pipeline start | daily limit=%d ===", limit)
    keywords = await get_trending_keywords(top_n=top_n_trends)
    if not keywords:
        log.warning("No keywords found — aborting pipeline")
        return

    # Filter out unsafe and already-published keywords
    safe_keywords = [
        kw for kw in keywords
        if _is_safe_keyword(kw) and kw not in published
    ]

    if not safe_keywords:
        log.info("No new safe keywords to process today")
        return

    processed = 0
    for kw in safe_keywords:
        if processed >= limit:
            log.info("Daily listing limit (%d) reached — stopping", limit)
            break
        try:
            await _process_keyword(kw, retail_price_cents)
            published.add(kw)
            _save_published(published)
            processed += 1

            if processed < limit:
                # Random delay between listings (8-20 min) to look human
                delay = random.randint(480, 1200)
                log.info("Waiting %d seconds before next listing...", delay)
                await asyncio.sleep(delay)

        except Exception:
            log.exception("Failed to process keyword %r — continuing", kw)

    log.info("=== Pipeline complete | listed %d products ===", processed)


async def _process_keyword(keyword: str, retail_price_cents: int) -> None:
    log.info("Processing keyword: %r", keyword)

    design_path = await generate_design(keyword, out_dir=_DESIGNS_DIR)
    image_id = await upload_image(design_path)

    title = _make_title(keyword)
    description = _make_description(keyword)
    tags = _make_tags(keyword)

    product_id = await create_product(
        title=title,
        description=description,
        image_id=image_id,
        tags=tags,
        retail_price_cents=retail_price_cents,
    )

    await publish_product(product_id)
    log.info("Done: keyword=%r product_id=%s", keyword, product_id)


def _make_title(keyword: str) -> str:
    kw = keyword.title()
    suffix = random.choice(_TITLE_SUFFIXES)
    return f"{kw} T-Shirt | {suffix}"


def _make_description(keyword: str) -> str:
    kw = keyword.title()
    intro = random.choice(_DESCRIPTION_INTROS).format(kw=kw)
    body = random.choice(_DESCRIPTION_BODIES)
    return f"{intro}\n\n{body}"


def _make_tags(keyword: str) -> list[str]:
    words = keyword.lower().split()
    base_options = [
        ["graphic tee", "unisex shirt", "gift idea", "cool shirt", "casual wear"],
        ["shirt gift", "graphic shirt", "tee shirt", "unique gift", "fun shirt"],
        ["novelty tee", "unisex tee", "cotton shirt", "gift for him", "gift for her"],
    ]
    base = random.choice(base_options)
    specific = [keyword] + words
    return list(dict.fromkeys(specific + base))[:13]
