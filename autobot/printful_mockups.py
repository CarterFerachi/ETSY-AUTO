"""Printful Mockup Generator API — lifestyle t-shirt photos."""
from __future__ import annotations

import asyncio
import base64
import logging
import time

import httpx

from .config import get_settings

log = logging.getLogger(__name__)

_BASE = "https://api.printful.com"
_POLL_INTERVAL = 5
_POLL_TIMEOUT = 120

_cache: dict[str, int] = {}

_LIFESTYLE_KEYS = ("male", "female", "model", "person", "lifestyle", "wearing")


def _bearer_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_settings().printful_api_key}"}


def _basic_headers() -> dict[str, str]:
    key = get_settings().printful_api_key
    encoded = base64.b64encode(f"{key}:".encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


async def _get(client: httpx.AsyncClient, path: str, **kwargs) -> httpx.Response | None:
    """Try Bearer auth first, then Basic auth if 401."""
    for headers in (_bearer_headers(), _basic_headers()):
        r = await client.get(f"{_BASE}{path}", headers=headers, **kwargs)
        log.debug("GET %s → %s (auth=%s)", path, r.status_code,
                  "bearer" if "Bearer" in headers["Authorization"] else "basic")
        if r.status_code != 401:
            return r
    log.error("Printful auth failed for GET %s — check PRINTFUL_API_KEY", path)
    return None


async def _post(client: httpx.AsyncClient, path: str, **kwargs) -> httpx.Response | None:
    """Try Bearer auth first, then Basic auth if 401."""
    for headers in (_bearer_headers(), _basic_headers()):
        r = await client.post(f"{_BASE}{path}", headers=headers, **kwargs)
        log.debug("POST %s → %s (auth=%s)", path, r.status_code,
                  "bearer" if "Bearer" in headers["Authorization"] else "basic")
        if r.status_code != 401:
            return r
    log.error("Printful auth failed for POST %s — check PRINTFUL_API_KEY", path)
    return None


async def _discover(client: httpx.AsyncClient) -> tuple[int, int] | None:
    """Find a short-sleeve white t-shirt in Printful's catalog.
    Returns (product_id, variant_id) or None."""
    r = await _get(client, "/products", timeout=30)
    if not r or not r.is_success:
        log.error("Printful GET /products failed: %s", r.text[:300] if r else "no response")
        return None

    body = r.json()
    products = body.get("result", [])
    log.info("Printful catalog: %d total products", len(products))

    # Filter to short-sleeve unisex tees
    tshirts = []
    for p in products:
        title = (p.get("title") or "").lower()
        pid = p.get("id")
        if not pid:
            continue
        if any(s in title for s in ("long sleeve", "hoodie", "sweatshirt", "polo",
                                     "tank", "v-neck", "crop", "mug", "hat", "bag")):
            continue
        if any(k in title for k in ("t-shirt", "tee", "shirt")):
            tshirts.append(p)

    log.info("Printful: %d short-sleeve tees found", len(tshirts))
    for p in tshirts[:10]:
        log.info("  [%s] %s", p.get("id"), p.get("title"))

    for product in tshirts:
        pid = product["id"]
        rv = await _get(client, f"/products/{pid}", timeout=30)
        if not rv or not rv.is_success:
            continue
        variants = rv.json().get("result", {}).get("variants", [])
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
            log.info("Printful: product_id=%s title=%r variant_id=%s %r",
                     pid, product.get("title"), chosen["id"], chosen.get("name"))
            return int(pid), int(chosen["id"])

    log.error("Printful: no suitable white short-sleeve tee found")
    return None


async def generate_lifestyle_mockup(design_url: str) -> str | None:
    """
    Generate a lifestyle mockup via Printful's Mockup Generator.
    Returns a lifestyle model photo URL, or None on failure.
    """
    if not get_settings().printful_api_key:
        return None

    async with httpx.AsyncClient(timeout=120) as client:
        if "product_id" not in _cache:
            found = await _discover(client)
            if not found:
                return None
            _cache["product_id"], _cache["variant_id"] = found

        product_id = _cache["product_id"]
        variant_id = _cache["variant_id"]

        task_body = {
            "variant_ids": [variant_id],
            "format": "jpg",
            "files": [
                {
                    "placement": "front",
                    "image_url": design_url,
                    "position": {
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

        log.info("Printful: creating mockup task product=%s variant=%s", product_id, variant_id)
        r = await _post(
            client,
            f"/mockup-generator/create-task/{product_id}",
            json=task_body,
            timeout=30,
        )
        if not r or not r.is_success:
            log.error("Printful create-task error: %s %s",
                      r.status_code if r else "no response",
                      r.text[:500] if r else "")
            return None

        body = r.json()
        task_key = (body.get("result") or {}).get("task_key")
        if not task_key:
            log.error("Printful: no task_key in response: %s", str(body)[:500])
            return None
        log.info("Printful mockup task_key: %s", task_key)

        deadline = time.monotonic() + _POLL_TIMEOUT
        while time.monotonic() < deadline:
            await asyncio.sleep(_POLL_INTERVAL)
            r = await _get(
                client,
                "/mockup-generator/task",
                params={"task_key": task_key},
                timeout=30,
            )
            if not r or not r.is_success:
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
                    for extra in extras:
                        title = (extra.get("title") or "").lower()
                        url = extra.get("url", "")
                        if url and any(k in title for k in _LIFESTYLE_KEYS):
                            log.info("Printful lifestyle photo: %r → %s", extra.get("title"), url)
                            return url
                    flat = m.get("mockup_url", "")
                    if flat:
                        log.info("Printful flat mockup (no lifestyle extra): %s", flat)
                        return flat
                return None

            if status == "failed":
                log.error("Printful task failed: %s", result)
                return None

        log.error("Printful timed out after %ss", _POLL_TIMEOUT)
        return None
