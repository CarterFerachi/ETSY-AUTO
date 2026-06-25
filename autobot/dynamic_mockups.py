"""Dynamic Mockups API client — t-shirt lifestyle mockup generation via catalog templates."""
from __future__ import annotations

import logging

import httpx

from .config import get_settings

log = logging.getLogger(__name__)

_BASE = "https://app.dynamicmockups.com/api/v1"

# Cached per process — reset on restart
_template_cache: dict[str, str] = {}

# Known good DM catalog mockup search terms (tried in order until one with smart objects is found)
_SEARCH_TERMS = [
    "t-shirt lifestyle model",
    "t-shirt man model",
    "tshirt model",
    "t-shirt model outdoor",
    "unisex t-shirt",
    "t-shirt",
]


def _headers() -> dict[str, str]:
    settings = get_settings()
    return {
        "x-api-key": settings.dynamic_mockups_api_key,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


async def _find_catalog_template(client: httpx.AsyncClient) -> tuple[str, str] | None:
    """
    Search the DM catalog for a t-shirt mockup that has at least one smart object.
    Returns (mockup_uuid, smart_object_uuid) or None if nothing found.
    """
    for term in _SEARCH_TERMS:
        try:
            r = await client.get(
                f"{_BASE}/mockups",
                headers=_headers(),
                params={"search": term, "per_page": 20},
                timeout=30,
            )
            if not r.is_success:
                log.debug("Catalog search %r failed: %s", term, r.status_code)
                continue
            body = r.json()
            # Response may be {"data": [...]} or a bare list
            items = body.get("data") or body if isinstance(body, list) else []
            for item in items:
                uuid = item.get("uuid") or item.get("id", "")
                smart_objects = item.get("smart_objects", [])
                if uuid and smart_objects:
                    log.info(
                        "Catalog template found: %r → uuid=%s smart_objects=%d",
                        item.get("name", term), uuid, len(smart_objects),
                    )
                    return uuid, smart_objects[0]["uuid"]
            log.debug("Catalog search %r: %d items, none with smart objects", term, len(items))
        except Exception as exc:
            log.debug("Catalog search %r error: %s", term, exc)
    return None


async def _get_mockup_detail(client: httpx.AsyncClient, uuid: str) -> tuple[str, str] | None:
    """Fetch a single catalog mockup by UUID and return (mockup_uuid, smart_object_uuid)."""
    r = await client.get(f"{_BASE}/mockups/{uuid}", headers=_headers(), timeout=30)
    if not r.is_success:
        return None
    item = r.json().get("data") or r.json()
    smart_objects = item.get("smart_objects", [])
    if smart_objects:
        return uuid, smart_objects[0]["uuid"]
    return None


async def _resolve_template(client: httpx.AsyncClient) -> tuple[str, str]:
    """Return (mockup_uuid, smart_object_uuid), searching catalog or raising."""
    result = await _find_catalog_template(client)
    if result:
        return result
    raise RuntimeError(
        "Dynamic Mockups: no catalog t-shirt template with smart objects found. "
        "Check your API key permissions or try a different search term."
    )


async def generate_lifestyle_mockup(design_url: str) -> str:
    """
    Render the design onto a catalog t-shirt mockup.
    Returns the rendered image URL (JPG, 1500px wide).
    """
    async with httpx.AsyncClient(timeout=60) as client:
        if not _template_cache:
            mockup_uuid, smart_object_uuid = await _resolve_template(client)
            _template_cache["mockup_uuid"] = mockup_uuid
            _template_cache["smart_object_uuid"] = smart_object_uuid
        else:
            mockup_uuid = _template_cache["mockup_uuid"]
            smart_object_uuid = _template_cache["smart_object_uuid"]

        log.info("Dynamic Mockups: rendering design on mockup %s…", mockup_uuid)
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
            log.error("Dynamic Mockups render error: %s %s", r.status_code, r.text)
        r.raise_for_status()
        export_url: str = r.json()["data"]["export_path"]
        log.info("Dynamic Mockups render complete: %s", export_url)
        return export_url
