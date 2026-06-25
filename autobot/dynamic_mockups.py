"""Dynamic Mockups API client — lifestyle t-shirt mockup generation."""
from __future__ import annotations

import asyncio
import logging
import time

import httpx

from .config import get_settings

log = logging.getLogger(__name__)

_BASE = "https://app.dynamicmockups.com/api/v1"
_POLL_INTERVAL = 3
_POLL_TIMEOUT = 120

# Cached per process — regenerated on restart
_template_cache: dict[str, str] = {}


def _headers() -> dict[str, str]:
    settings = get_settings()
    return {
        "x-api-key": settings.dynamic_mockups_api_key,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


async def _create_template(client: httpx.AsyncClient) -> tuple[str, str]:
    """Generate a blank lifestyle shirt template. Returns (mockup_uuid, smart_object_uuid)."""
    log.info("Dynamic Mockups: generating lifestyle template…")
    r = await client.post(
        f"{_BASE}/mock-anything/create",
        headers=_headers(),
        json={
            "prompt": (
                "Male model with tattoos wearing a plain white crew-neck t-shirt. "
                "Patriotic American flag bokeh background with fireworks. "
                "Waist-up shot, confident relaxed pose, slight smirk. "
                "Professional Etsy product photography, high contrast, vibrant colors."
            ),
            "model": "seedream_4_5",
        },
        timeout=30,
    )
    if not r.is_success:
        log.error("Dynamic Mockups create error: %s %s", r.status_code, r.text)
    r.raise_for_status()
    task_id: str = r.json()["data"]["task_id"]
    log.info("Dynamic Mockups: template task %s", task_id)

    deadline = time.monotonic() + _POLL_TIMEOUT
    while time.monotonic() < deadline:
        await asyncio.sleep(_POLL_INTERVAL)
        r = await client.get(
            f"{_BASE}/mock-anything/status/{task_id}",
            headers=_headers(),
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()["data"]
        state = data["state"]
        log.debug("Template task %s: %s", task_id, state)
        if state == "SUCCESS":
            mockup = data["mockup"]
            mockup_uuid: str = mockup["uuid"]
            smart_object_uuid: str = mockup["smart_objects"][0]["uuid"]
            log.info("Template ready: mockup=%s smart_object=%s", mockup_uuid, smart_object_uuid)
            return mockup_uuid, smart_object_uuid
        if state not in ("PROGRESS", "PENDING"):
            raise RuntimeError(f"Dynamic Mockups template failed: state={state}, data={data}")

    raise TimeoutError(f"Dynamic Mockups template timed out after {_POLL_TIMEOUT}s")


async def generate_lifestyle_mockup(design_url: str) -> str:
    """
    Render a lifestyle mockup of the design on a model wearing a white t-shirt.
    Returns the rendered image URL (JPG, 1500px wide).
    """
    async with httpx.AsyncClient(timeout=90) as client:
        if not _template_cache:
            mockup_uuid, smart_object_uuid = await _create_template(client)
            _template_cache["mockup_uuid"] = mockup_uuid
            _template_cache["smart_object_uuid"] = smart_object_uuid
        else:
            mockup_uuid = _template_cache["mockup_uuid"]
            smart_object_uuid = _template_cache["smart_object_uuid"]

        log.info("Dynamic Mockups: rendering design on template %s…", mockup_uuid)
        r = await client.post(
            f"{_BASE}/renders",
            headers=_headers(),
            json={
                "mockup_uuid": mockup_uuid,
                "smart_objects": [
                    {
                        "uuid": smart_object_uuid,
                        "asset": {"url": design_url, "fit": "contain"},
                        "decoration_method": {"method": "dtg"},
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
