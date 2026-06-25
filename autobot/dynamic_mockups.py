"""Dynamic Mockups API client — lifestyle t-shirt mockup generation."""
from __future__ import annotations

import asyncio
import json
import logging
import time

import httpx

from .config import get_settings

log = logging.getLogger(__name__)

_BASE = "https://app.dynamicmockups.com/api/v1"
_POLL_INTERVAL = 3
_POLL_TIMEOUT = 120

# Cached per process — reset on restart
_template_cache: dict[str, str] = {}

# Product searches tried in order; first short-sleeve result wins
_PRODUCT_QUERIES = [
    "bella canvas 3001",
    "gildan softstyle 64000",
    "comfort colors 1717",
    "unisex short sleeve t-shirt",
    "unisex t-shirt",
]

# DM catalog search terms tried in order
_CATALOG_QUERIES = [
    "t-shirt model",
    "t-shirt lifestyle",
    "tshirt man",
    "unisex tee model",
    "t-shirt",
]


def _headers() -> dict[str, str]:
    settings = get_settings()
    return {
        "x-api-key": settings.dynamic_mockups_api_key,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Tier 1: DM catalog templates (pre-built, smart objects always defined)
# ---------------------------------------------------------------------------

async def _find_catalog_template(client: httpx.AsyncClient) -> tuple[str, str] | None:
    """
    Search the DM catalog for a t-shirt mockup that already has smart objects.
    Returns (mockup_uuid, smart_object_uuid) or None.
    """
    for term in _CATALOG_QUERIES:
        try:
            r = await client.get(
                f"{_BASE}/mockups",
                headers=_headers(),
                params={"search": term, "per_page": 50},
                timeout=30,
            )
            log.info("DM catalog search %r → %s", term, r.status_code)
            if not r.is_success:
                continue
            body = r.json()
            # Log a summary so we know what the catalog contains
            items = body.get("data") if isinstance(body, dict) else body
            if not isinstance(items, list):
                log.info("DM catalog unexpected format for %r: %s", term, json.dumps(body)[:500])
                continue
            log.info("DM catalog %r → %d items", term, len(items))
            for item in items[:5]:
                log.info("  catalog item: name=%r uuid=%s smart_objects=%d",
                         item.get("name", "?"),
                         item.get("uuid", "?"),
                         len(item.get("smart_objects", [])))
            for item in items:
                uuid = item.get("uuid") or item.get("id", "")
                smart_objects = item.get("smart_objects", [])
                if uuid and smart_objects:
                    log.info("DM catalog template chosen: %r uuid=%s", item.get("name"), uuid)
                    return uuid, smart_objects[0]["uuid"]
        except Exception as exc:
            log.warning("DM catalog search %r error: %s", term, exc)
    return None


# ---------------------------------------------------------------------------
# Tier 2: MockAnything AI with correct product selection
# ---------------------------------------------------------------------------

async def _find_short_sleeve_product(client: httpx.AsyncClient) -> str | None:
    """Search DM product catalog; skip long-sleeve / pocket variants."""
    for query in _PRODUCT_QUERIES:
        try:
            r = await client.get(
                f"{_BASE}/mock-anything/products",
                headers=_headers(),
                params={"query": query},
                timeout=30,
            )
            if not r.is_success:
                continue
            items = r.json().get("data", [])
            log.info("DM product search %r → %d results", query, len(items))
            for item in items[:3]:
                log.info("  product: name=%r uuid=%s", item.get("name"), item.get("uuid"))
            for item in items:
                name = item.get("name", "").lower()
                # Skip long-sleeve and any pocket variants
                if any(skip in name for skip in ("long sleeve", "long-sleeve", "pocket", "hoodie", "sweatshirt")):
                    continue
                uuid = item.get("uuid")
                if uuid:
                    log.info("DM product chosen: %r uuid=%s", item.get("name"), uuid)
                    return uuid
        except Exception as exc:
            log.warning("DM product search %r error: %s", query, exc)
    return None


async def _poll_task(client: httpx.AsyncClient, task_id: str) -> dict:
    """Poll MockAnything task until SUCCESS; returns the data dict."""
    deadline = time.monotonic() + _POLL_TIMEOUT
    while time.monotonic() < deadline:
        await asyncio.sleep(_POLL_INTERVAL)
        r = await client.get(
            f"{_BASE}/mock-anything/status/{task_id}",
            headers=_headers(),
            timeout=30,
        )
        r.raise_for_status()
        body = r.json()
        data = body.get("data", body)
        state = data.get("state", "")
        log.debug("DM task %s: %s", task_id, state)
        if state == "SUCCESS":
            log.info("DM task %s SUCCESS — raw: %s", task_id, json.dumps(body)[:1000])
            return data
        if state not in ("PROGRESS", "PENDING"):
            raise RuntimeError(f"DM task {task_id} failed: state={state}")
    raise TimeoutError(f"DM task {task_id} timed out after {_POLL_TIMEOUT}s")


def _extract_smart_objects(data: dict) -> tuple[str, list]:
    """
    Try every known response path to find (mockup_uuid, smart_objects list).
    DM's response structure varies between prompt and image_url flows.
    """
    # Path 1: data.mockup.smart_objects (most common)
    mockup = data.get("mockup") or {}
    uuid = mockup.get("uuid", "")
    sos = mockup.get("smart_objects", [])
    if uuid and sos:
        return uuid, sos

    # Path 2: top-level smart_objects
    sos = data.get("smart_objects", [])
    uuid = uuid or data.get("uuid") or data.get("mockup_uuid", "")
    if uuid and sos:
        return uuid, sos

    # Path 3: data.result.*
    result = data.get("result") or {}
    uuid2 = result.get("uuid") or result.get("mockup_uuid", "")
    sos = result.get("smart_objects", [])
    if uuid2 and sos:
        return uuid2, sos

    # Log all top-level keys to diagnose
    log.warning("DM smart_objects not found. Top-level keys: %s | mockup keys: %s",
                list(data.keys()), list(mockup.keys()) if mockup else "none")
    return uuid or uuid2, []


async def _create_mockanything_template(client: httpx.AsyncClient) -> tuple[str, str] | None:
    """Try MockAnything AI flow. Returns (mockup_uuid, smart_object_uuid) or None."""
    product_uuid = await _find_short_sleeve_product(client)

    payload: dict = {
        "prompt": (
            "Male model with tattoos wearing a plain white crew-neck t-shirt. "
            "Patriotic American flag bokeh background with fireworks. "
            "Waist-up shot, confident relaxed pose, slight smirk. "
            "Professional Etsy product photography, high contrast, vibrant colors."
        ),
        "model": "seedream_4_5",
    }
    if product_uuid:
        payload["product"] = {
            "uuid": product_uuid,
            "decorations": [{"location": "front_chest"}],
        }

    r = await client.post(
        f"{_BASE}/mock-anything/create",
        headers=_headers(),
        json=payload,
        timeout=30,
    )
    if not r.is_success:
        log.error("DM MockAnything create error: %s %s", r.status_code, r.text)
        return None
    task_id: str = r.json()["data"]["task_id"]
    log.info("DM MockAnything task: %s", task_id)

    try:
        data = await _poll_task(client, task_id)
    except Exception as exc:
        log.error("DM MockAnything poll failed: %s", exc)
        return None

    mockup_uuid, smart_objects = _extract_smart_objects(data)
    if not smart_objects:
        log.warning("DM MockAnything: smart_objects still empty (product_uuid=%s)", product_uuid)
        return None

    log.info("DM MockAnything template: mockup=%s smart_objects=%d", mockup_uuid, len(smart_objects))
    return mockup_uuid, smart_objects[0]["uuid"]


# ---------------------------------------------------------------------------
# Template resolver: tries all tiers
# ---------------------------------------------------------------------------

async def _resolve_template(client: httpx.AsyncClient) -> tuple[str, str]:
    """Return (mockup_uuid, smart_object_uuid), trying catalog then MockAnything."""
    # Tier 1: catalog templates (pre-built, always have smart objects)
    result = await _find_catalog_template(client)
    if result:
        log.info("Using DM catalog template")
        return result

    # Tier 2: MockAnything AI with correct product
    log.info("Catalog returned nothing — trying MockAnything AI")
    result = await _create_mockanything_template(client)
    if result:
        log.info("Using DM MockAnything template")
        return result

    raise RuntimeError(
        "Dynamic Mockups: all template approaches exhausted — "
        "check API key, catalog access, and Railway logs for details."
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def generate_lifestyle_mockup(design_url: str) -> str:
    """
    Render the design onto a t-shirt lifestyle mockup.
    Returns the rendered image URL (JPG, 1500px wide).
    Raises on failure so the caller can fall back to Printify's images.
    """
    async with httpx.AsyncClient(timeout=120) as client:
        if not _template_cache:
            mockup_uuid, smart_object_uuid = await _resolve_template(client)
            _template_cache["mockup_uuid"] = mockup_uuid
            _template_cache["smart_object_uuid"] = smart_object_uuid
        else:
            mockup_uuid = _template_cache["mockup_uuid"]
            smart_object_uuid = _template_cache["smart_object_uuid"]

        log.info("DM render: mockup=%s design=%s", mockup_uuid, design_url)
        r = await client.post(
            f"{_BASE}/renders",
            headers=_headers(),
            json={
                "mockup_uuid": mockup_uuid,
                "smart_objects": [
                    {
                        "uuid": smart_object_uuid,
                        "asset": {"url": design_url, "fit": "contain"},
                    }
                ],
                "export_options": {
                    "image_format": "jpg",
                    "image_size": 1500,
                    "mode": "view",
                },
            },
            timeout=60,
        )
        if not r.is_success:
            log.error("DM render error: %s %s", r.status_code, r.text)
        r.raise_for_status()
        export_url: str = r.json()["data"]["export_path"]
        log.info("DM render complete: %s", export_url)
        return export_url
