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

# Only keywords with custom art prompts + text configs in design_generator.py
_JULY4TH_POOL = [
    "wtf is a kilometer bald eagle",
    "dream team of 1776 founding fathers basketball",
    "ben drankin benjamin franklin fourth of july",
    "1776 national champs founding fathers",
    "its only treason if you lose george washington",
    "george washington crossing the delaware sunglasses",
    "founding fathers fourth of july squad goals",
    "benjamin franklin original founding bro",
    "1776 original bad boys founding fathers",
    "we the people fourth of july founding fathers",
    "america est 1776 founding fathers vintage",
    "patrick henry give me liberty or give me coffee",
    "george washington first in war first in peace first in swag",
    "America 250th birthday 1776 2026",
    "250 years of freedom 1776 2026",
    "party like its 1776",
    "its only treason if you lose",
    "hail mary to freedom george washington football",
    "philadelphia liberty bells world series champs 1776",
    "revolutionary slam founding father basketball dunk",
    "1776 independence championship ring",
    "founding fathers hockey team sons of liberty",
    "george washington golfer fore independence",
    "redcoat roast 1776 founding fathers bbq",
    "fight night usa vs uk george washington boxer",
    "founding fathers freedom gamers playing video games",
    "long run to liberty george washington marathon",
    "give me liberty cheerleaders l-i-b-e-r-t-y",
    "1776 trophy case america wins founding fathers",
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
