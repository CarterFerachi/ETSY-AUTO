"""Printful Mockup Generator API — lifestyle t-shirt photos."""
from __future__ import annotations

import asyncio
import logging
import time

import httpx

from .config import get_settings

log = logging.getLogger(__name__)

_BASE = "https://api.printful.com"
_POLL_INTERVAL = 5
_POLL_TIMEOUT = 120

# Cached after first successful discovery
_cache: dict[str, int] = {}

# Searched in order; first short-sleeve white result wins
_PRODUCT_QUERIES = [
    "Bella Canvas 3001",
    "Gildan 64000 Softstyle",
    "Comfort Colors 1717",
    "unisex jersey t-shirt",
    "unisex t-shirt",
]

# Words that identify a lifestyle/model photo in the extra list
_LIFESTYLE_KEYS = ("male", "female", "model", "person", "lifestyle", "wearing")


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_settings().printful_api_key}"}


async def _discover(client: httpx.AsyncClient) -> tuple[int, int] | None:
    """
    Discover a short-sleeve white t-shirt product and variant from Printful's catalog.
    Returns (product_id, variant_id) or None.
    """
    for query in _PRODUCT_QUERIES:
        try:
            r = await client.get(
                f"{_BASE}/products",
                headers=_headers(),
                params={"search": query},
                timeout=30,
            )
            log.info("Printful product search %r → HTTP %s", query, r.status_code)
            if not r.is_success:
                log.warning("Printful search error: %s", r.text[:300])
                continue

            products = r.json().get("result", [])
            log.info("Printful search %r: %d results", query, len(products))
            for p in products[:5]:
                log.info("  [%s] %s", p.get("id"), p.get("title"))

            for product in products:
                pid = product.get("id")
                title = (product.get("title") or "").lower()
                if not pid:
                    continue
                # Skip anything that's not a regular short-sleeve tee
                if any(s in title for s in (
                    "long sleeve", "hoodie", "sweatshirt", "polo",
                    "tank", "pocket tee", "v-neck",
                )):
                    continue

                # Fetch variants for this product
                rv = await client.get(
                    f"{_BASE}/products/{pid}",
                    headers=_headers(),
                    timeout=30,
                )
                if not rv.is_success:
                    continue

                variants = rv.json().get("result", {}).get("variants", [])
                # Prefer White / M; fall back to any White variant
                chosen = None
                for v in variants:
                    color = (v.get("color") or "").lower()
                    size = (v.get("size") or "").lower()
                    if "white" in color:
                        if size == "m":
                            chosen = v
                            break
                        if chosen is None:
                            chosen = v

                if chosen:
                    log.info(
                        "Printful: product_id=%s title=%r variant_id=%s name=%r",
                        pid, product.get("title"), chosen["id"], chosen.get("name"),
                    )
                    return int(pid), int(chosen["id"])

        except Exception as exc:
            log.warning("Printful discovery error for %r: %s", query, exc)

    log.error("Printful: no suitable short-sleeve white t-shirt found")
    return None


async def generate_lifestyle_mockup(design_url: str) -> str | None:
    """
    Render the design onto a Printful t-shirt and return a lifestyle model photo URL.
    Returns None on failure so the caller can fall back gracefully.
    """
    settings = get_settings()
    if not settings.printful_api_key:
        log.info("PRINTFUL_API_KEY not set — skipping Printful mockup")
        return None

    async with httpx.AsyncClient(timeout=120) as client:
        # ── Discover product + variant (cached after first run) ───────────
        if "product_id" not in _cache:
            found = await _discover(client)
            if not found:
                return None
            _cache["product_id"], _cache["variant_id"] = found

        product_id = _cache["product_id"]
        variant_id = _cache["variant_id"]

        # ── Create mockup task ────────────────────────────────────────────
        task_body = {
            "variant_ids": [variant_id],
            "format": "jpg",
            "files": [
                {
                    "placement": "front",
                    "image_url": design_url,
                    "position": {
                        # Standard DTG print area for most unisex tees
                        "area_width": 1800,
                        "area_height": 2400,
                        "width": 1800,
                        "height": 1800,
                        "top": 300,
                        "left": 0,
                    },
                }
            ],
        }

        log.info("Printful: creating mockup task (product=%s, variant=%s, design=%s)",
                 product_id, variant_id, design_url)
        r = await client.post(
            f"{_BASE}/mockup-generator/create-task/{product_id}",
            headers=_headers(),
            json=task_body,
            timeout=30,
        )
        if not r.is_success:
            log.error("Printful create-task error: %s %s", r.status_code, r.text[:500])
            return None

        body = r.json()
        task_key = (body.get("result") or {}).get("task_key")
        if not task_key:
            log.error("Printful: no task_key in response: %s", str(body)[:500])
            return None
        log.info("Printful mockup task: %s", task_key)

        # ── Poll until done ───────────────────────────────────────────────
        deadline = time.monotonic() + _POLL_TIMEOUT
        while time.monotonic() < deadline:
            await asyncio.sleep(_POLL_INTERVAL)
            r = await client.get(
                f"{_BASE}/mockup-generator/task",
                headers=_headers(),
                params={"task_key": task_key},
                timeout=30,
            )
            if not r.is_success:
                log.debug("Printful poll error: %s", r.status_code)
                continue

            result = r.json().get("result", {})
            status = result.get("status", "")
            log.debug("Printful task %s: %s", task_key, status)

            if status == "completed":
                mockups = result.get("mockups", [])
                log.info("Printful complete: %d mockup(s)", len(mockups))
                for m in mockups:
                    extras = m.get("extra", [])
                    log.info("  extras: %s", [e.get("title") for e in extras])
                    # Prefer a lifestyle/model photo from the extra list
                    for extra in extras:
                        title = (extra.get("title") or "").lower()
                        url = extra.get("url", "")
                        if url and any(k in title for k in _LIFESTYLE_KEYS):
                            log.info("Printful lifestyle photo chosen: %r → %s",
                                     extra.get("title"), url)
                            return url
                    # Fall back to the flat mockup if no lifestyle found
                    flat_url = m.get("mockup_url", "")
                    if flat_url:
                        log.info("Printful flat mockup (no lifestyle extra): %s", flat_url)
                        return flat_url

                log.warning("Printful: completed but no usable URL found")
                return None

            if status == "failed":
                log.error("Printful mockup task failed: %s", result)
                return None

        log.error("Printful mockup timed out after %ss", _POLL_TIMEOUT)
        return None
