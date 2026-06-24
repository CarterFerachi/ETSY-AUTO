"""
Keyword source for the daily pipeline.

Uses a large curated pool of proven t-shirt niches and rotates through them
randomly each day. This avoids scraping blocks while still producing variety.
"""
from __future__ import annotations

import logging
import random

log = logging.getLogger(__name__)

# Broad pool of evergreen + trending t-shirt niches
_KEYWORD_POOL = [
    # Hobbies & interests
    "hiking adventure", "camping life", "fishing dad", "rock climbing",
    "mountain biker", "trail runner", "kayaking lover", "surfing vibes",
    "yoga life", "gym motivation", "weightlifting", "running club",
    "cycling enthusiast", "skateboarding", "snowboarding", "hunting season",
    # Professions
    "nurse life", "teacher appreciation", "engineer mindset", "firefighter proud",
    "police officer", "military veteran", "chef life", "mechanic garage",
    "farmer life", "trucker life", "construction worker", "electrician",
    "plumber life", "dentist humor", "doctor life", "pharmacist",
    # Family & relationships
    "dog mom", "cat dad", "dog dad", "cat mom", "plant mom",
    "new dad", "girl dad", "boy mom", "grandma life", "grandpa life",
    "best uncle", "best aunt", "big sister", "little brother",
    # Humor & attitude
    "introverted but willing to discuss cats", "coffee before talkie",
    "nap queen", "sarcasm loading", "monday hater", "weekend vibes",
    "adulting is hard", "pizza lover", "taco tuesday", "donut worry",
    # Lifestyle
    "beach life", "lake life", "desert vibes", "city life", "country life",
    "van life", "tiny house", "minimalist living", "off grid living",
    "plant based", "vegan life", "sustainable living",
    # Pets
    "golden retriever mom", "french bulldog dad", "labrador lover",
    "german shepherd", "dachshund life", "corgi obsessed", "pug life",
    "beagle lover", "pitbull mom", "rescue dog parent",
    # Pop culture themes (safe, generic)
    "retro aesthetic", "vintage vibes", "80s lover", "90s kid",
    "sunset lover", "dark academia", "cottagecore", "y2k aesthetic",
    # Sports (generic, no team names)
    "baseball mom", "football dad", "soccer life", "basketball lover",
    "volleyball player", "tennis player", "swimmer life", "wrestling dad",
    # Seasons & holidays (generic)
    "summer vibes", "fall lover", "winter warrior", "spring garden",
    "halloween lover", "christmas spirit", "grateful thankful blessed",
    # Motivational
    "hustle hard", "dream big", "never give up", "grind mindset",
    "rise and shine", "built different", "level up", "stay humble",
    "be kind", "spread love", "good vibes only", "positive energy",
]


async def get_trending_keywords(top_n: int = 10) -> list[str]:
    """Return *top_n* keywords sampled from the curated pool."""
    keywords = random.sample(_KEYWORD_POOL, min(top_n, len(_KEYWORD_POOL)))
    log.info("Trending keywords: %s", keywords)
    return keywords
