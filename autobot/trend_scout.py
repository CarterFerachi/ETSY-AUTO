"""
Keyword source for the daily pipeline.

Focused on founding fathers / historical humor style — the viral Etsy niche
for July 4th 2026 / America's 250th birthday.
"""
from __future__ import annotations

import logging
import random
from datetime import date

log = logging.getLogger(__name__)

_JULY4TH_POOL = [
    # Founding fathers viral humor (primary focus)
    "wtf is a kilometer bald eagle",
    "dream team of 1776 founding fathers basketball",
    "ben drankin benjamin franklin fourth of july",
    "1776 national champs founding fathers",
    "its only treason if you lose george washington",
    "george washington crossing the delaware sunglasses",
    "founding fathers fourth of july squad goals",
    "hamilton jefferson washington rap battle 1776",
    "benjamin franklin original founding bro",
    "washington adams jefferson 1776 all stars",
    "founding fathers we did it first america",
    "thomas jefferson wrote that fourth of july",
    "george washington first in war first in peace first in swag",
    "patrick henry give me liberty or give me coffee",
    "founding fathers approved this message 1776",
    "john hancock signed it bigger fourth of july",
    "paul revere the british are coming fourth of july",
    "1776 original bad boys founding fathers",
    "america est 1776 founding fathers vintage",
    "we the people fourth of july founding fathers",
    # 250th anniversary
    "America 250th birthday 1776 2026",
    "250 years of freedom 1776 2026",
    "Americas 250th anniversary celebration",
    "1776 2026 semiquincentennial america",
    "250 years strong america birthday",
    # Classic funny patriotic
    "party like its 1776",
    "its only treason if you lose",
    "freedom aint free july fourth",
    "merica fourth of july party",
    "mullet and fireworks fourth of july",
]

_EVERGREEN_POOL = [
    "hiking adventure", "camping life", "fishing dad", "dog mom",
    "cat dad", "nurse life", "teacher appreciation", "military veteran",
    "golden retriever mom", "retro aesthetic", "vintage vibes",
    "beach life", "lake life", "country life", "hustle hard",
    "built different", "good vibes only", "weekend vibes",
]


def _active_pool() -> list[str]:
    today = date.today()
    if date(2026, 6, 1) <= today <= date(2026, 7, 10):
        return _JULY4TH_POOL
    return _EVERGREEN_POOL


async def get_trending_keywords(top_n: int = 10) -> list[str]:
    """Return *top_n* keywords from the active seasonal pool."""
    pool = _active_pool()
    keywords = random.sample(pool, min(top_n, len(pool)))
    log.info("Trending keywords: %s", keywords)
    return keywords
