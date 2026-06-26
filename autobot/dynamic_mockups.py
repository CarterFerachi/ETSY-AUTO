"""Dynamic Mockups API client — catalog template rendering."""
from __future__ import annotations

import json
import logging

import httpx

from .config import get_settings

log = logging.getLogger(__name__)

_BASE = "https://app.dynamicmockups.com/api/v1"

_cache: dict[str, str] = {}

_CATALOG_QUERIES = [
    "t-shirt model",
    "t-shirt lifestyle",
    "tshirt man",
    "unisex tee model",
    "t-shirt",
]


def _headers() -> dict[str, str]:
    return {
        "x-api-key": get_settings().dynamic_mockups_api_key,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


async def _find_catalog_template(client: httpx.AsyncClient) -> tuple[str, str] | None:
    """
    Search DM's pre-built catalog for a t-shirt template that has smart objects.
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
            log.info("DM catalog search %r → HTTP %s", term, r.status_code)
            if not r.is_success:
                log.warning("DM catalog error: %s", r.text[:300])
                continue

            body = r.json()
            items = body.get("data") if isinstance(body, dict) else (body if isinstance(body, list) else [])
            log.info("DM catalog %r: %d items", term, len(items))
            for item in items[:5]:
                log.info("  [%s] %s — smart_objects=%d",
                         item.get("uuid", "?"), item.get("name", "?"),
                         len(item.get("smart_objects", [])))

            for item in items:
                uuid = item.get("uuid") or item.get("id", "")
                smart_objects = item.get("smart_objects", [])
                if uuid and smart_objects:
                    log.info("DM catalog template chosen: %r uuid=%s", item.get("name"), uuid)
                    return uuid, smart_objects[0]["uuid"]

        except Exception as exc:
            log.warning("DM catalog search %r error: %s", term, exc)

    log.info("DM catalog: no template with smart objects found — logging full response for first term")
    try:
        r = await client.get(
            f"{_BASE}/mockups",
            headers=_headers(),
            params={"per_page": 5},
            timeout=30,
        )
        log.info("DM /mockups raw (no search): HTTP %s body=%s", r.status_code, r.text[:1000])
    except Exception as exc:
        log.info("DM /mockups diagnostic failed: %s", exc)
    return None


async def generate_lifestyle_mockup(design_url: str) -> str:
    """
    Render the design onto a DM catalog t-shirt template.
    Raises RuntimeError if no suitable template is found.
    """
    async with httpx.AsyncClient(timeout=60) as client:
        if not _cache:
            result = await _find_catalog_template(client)
            if not result:
                raise RuntimeError("DM catalog: no t-shirt template with smart objects available")
            _cache["mockup_uuid"], _cache["smart_object_uuid"] = result

        mockup_uuid = _cache["mockup_uuid"]
        smart_object_uuid = _cache["smart_object_uuid"]

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
