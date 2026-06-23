"""
Scrape Etsy search pages to surface trending t-shirt keywords.

Strategy:
  1. Hit Etsy's public search for several seed queries.
  2. Pull listing titles from the HTML response.
  3. Score recurring n-grams; return the top-N as trend keywords.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Sequence

import httpx
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

_SEED_QUERIES = [
    "trending t-shirt",
    "funny graphic tee",
    "vintage shirt design",
    "aesthetic t-shirt",
    "motivational tshirt",
]

_STOP_WORDS = {
    "t", "shirt", "tee", "tshirt", "t-shirt", "unisex", "womens", "mens",
    "funny", "cool", "cute", "gift", "for", "the", "a", "an", "and", "or",
    "with", "in", "of", "to", "is", "my", "your", "i", "you",
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


async def _fetch_listing_titles(client: httpx.AsyncClient, query: str) -> list[str]:
    url = "https://www.etsy.com/search"
    params = {"q": query, "explicit": "1", "ref": "pagination"}
    try:
        r = await client.get(url, params=params, headers=_HEADERS, timeout=15)
        r.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("Etsy fetch failed for %r: %s", query, exc)
        return []

    soup = BeautifulSoup(r.text, "lxml")
    titles: list[str] = []
    for el in soup.select("h3.wt-text-caption, h2[data-listing-id]"):
        text = el.get_text(separator=" ", strip=True)
        if text:
            titles.append(text.lower())
    return titles


def _extract_keywords(titles: Sequence[str], top_n: int = 10) -> list[str]:
    counter: Counter[str] = Counter()
    for title in titles:
        words = re.findall(r"[a-z]+", title)
        meaningful = [w for w in words if w not in _STOP_WORDS and len(w) > 3]
        # unigrams
        counter.update(meaningful)
        # bigrams
        counter.update(f"{a} {b}" for a, b in zip(meaningful, meaningful[1:]))

    return [kw for kw, _ in counter.most_common(top_n)]


async def get_trending_keywords(top_n: int = 10) -> list[str]:
    """Return up to *top_n* trending t-shirt keyword phrases from Etsy."""
    all_titles: list[str] = []
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for q in _SEED_QUERIES:
            titles = await _fetch_listing_titles(client, q)
            log.info("Seed %r → %d titles", q, len(titles))
            all_titles.extend(titles)

    keywords = _extract_keywords(all_titles, top_n=top_n)
    log.info("Trending keywords: %s", keywords)
    return keywords
