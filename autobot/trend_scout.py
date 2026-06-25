"""
Keyword source for the daily pipeline.

Currently focused on America's 250th birthday (July 4th 2026) — the biggest
patriotic shopping event in a generation. Will switch to evergreen pool after July 4th.
"""
from __future__ import annotations

import logging
import random
from datetime import date

log = logging.getLogger(__name__)

# July 4th 2026 — America's 250th birthday keywords
_JULY4TH_POOL = [
    # Patriotic animals (viral Etsy style)
    "patriotic raccoon holding American flag",
    "bald eagle wearing sunglasses fourth of july",
    "patriotic golden retriever with hot dog and flag",
    "american bulldog fourth of july vibes",
    "patriotic bear drinking beer with flag",
    "feral cat fourth of july chaos",
    "patriotic labrador with fireworks",
    "american raccoon eating hot dog",
    "patriotic corgi wearing stars and stripes",
    "bald eagle screaming freedom",
    # 250th anniversary specific
    "America 250th birthday 1776 2026",
    "250 years of freedom 1776 2026",
    "Americas 250th anniversary celebration",
    "semiquincentennial celebration America",
    "250 years strong America birthday",
    # Classic patriotic
    "merica fourth of july party",
    "fourth of july barbecue squad",
    "land of the free home of the brave",
    "born on the fourth of july",
    "fireworks and freedom fourth of july",
    "red white and boom fourth of july",
    "stars stripes and summer vibes",
    "all american summer cookout",
    "july fourth grilling and chilling",
    "proud american fourth of july",
    # Funny patriotic
    "lets get this bread fourth of july",
    "hot dogs hotdogs america july fourth",
    "fireworks director fourth of july",
    "american by birth patriot by choice",
    "freedom aint free july fourth",
    "party like its 1776",
    "1776 vibes only fourth of july",
    "mullet and fireworks fourth of july",
    # Founding fathers viral style
    "wtf is a kilometer bald eagle",
    "dream team of 1776 founding fathers basketball",
    "ben drankin benjamin franklin fourth of july",
    "1776 national champs founding fathers",
    "its only treason if you lose george washington",
]

# Evergreen pool — used after July 4th passes
_EVERGREEN_POOL = [
    "hiking adventure", "camping life", "fishing dad", "dog mom",
    "cat dad", "nurse life", "teacher appreciation", "military veteran",
    "golden retriever mom", "retro aesthetic", "vintage vibes",
    "beach life", "lake life", "country life", "hustle hard",
    "built different", "good vibes only", "weekend vibes",
]


def _active_pool() -> list[str]:
    today = date.today()
    # Use July 4th pool from now until July 10th 2026
    if date(2026, 6, 1) <= today <= date(2026, 7, 10):
        return _JULY4TH_POOL
    return _EVERGREEN_POOL


async def get_trending_keywords(top_n: int = 10) -> list[str]:
    """Return *top_n* keywords from the active seasonal pool."""
    pool = _active_pool()
    keywords = random.sample(pool, min(top_n, len(pool)))
    log.info("Trending keywords: %s", keywords)
    return keywords
