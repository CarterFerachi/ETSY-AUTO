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


async def _poll_task(client: httpx.AsyncClient, task_id: str) -> dict:
    """Poll a MockAnything task until SUCCESS. Returns the data dict."""
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
        log.debug("Task %s: %s", task_id, state)
        if state == "SUCCESS":
            return data
        if state not in ("PROGRESS", "PENDING"):
            raise RuntimeError(f"Dynamic Mockups task failed: state={state}, data={data}")
    raise TimeoutError(f"Dynamic Mockups task timed out after {_POLL_TIMEOUT}s")


async def _create_template(client: httpx.AsyncClient) -> tuple[str, str]:
    """
    Two-step template creation:
    1. Generate a lifestyle photo from a prompt.
    2. Feed that photo back via image_url so DM can detect smart objects.
    Returns (mockup_uuid, smart_object_uuid).
    """
    # ── Step 1: generate lifestyle photo ─────────────────────────────────────
    log.info("Dynamic Mockups: step 1 — generating lifestyle photo…")
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
        log.error("Dynamic Mockups step-1 error: %s %s", r.status_code, r.text)
    r.raise_for_status()
    task_id: str = r.json()["data"]["task_id"]
    log.info("Dynamic Mockups: step-1 task %s", task_id)

    data = await _poll_task(client, task_id)
    photo_url: str = data.get("image_url", "")
    if not photo_url:
        raise RuntimeError(f"No image_url in step-1 result: {data}")
    log.info("Dynamic Mockups: lifestyle photo ready → %s", photo_url)

    # ── Step 2: re-submit with image_url so DM detects print area ────────────
    log.info("Dynamic Mockups: step 2 — detecting smart objects on photo…")
    r = await client.post(
        f"{_BASE}/mock-anything/create",
        headers=_headers(),
        json={"image_url": photo_url},
        timeout=30,
    )
    if not r.is_success:
        log.error("Dynamic Mockups step-2 error: %s %s", r.status_code, r.text)
    r.raise_for_status()
    task_id2: str = r.json()["data"]["task_id"]
    log.info("Dynamic Mockups: step-2 task %s", task_id2)

    data2 = await _poll_task(client, task_id2)
    mockup = data2.get("mockup") or {}
    mockup_uuid: str = mockup.get("uuid", "")
    smart_objects = mockup.get("smart_objects", [])
    log.info("Template ready: mockup=%s smart_objects=%d", mockup_uuid, len(smart_objects))

    if not mockup_uuid:
        raise RuntimeError(f"No mockup UUID in step-2 result: {data2}")
    if not smart_objects:
        raise RuntimeError(
            f"Dynamic Mockups template {mockup_uuid} has no smart objects after two-step flow — "
            f"photo_url={photo_url}"
        )

    smart_object_uuid: str = smart_objects[0]["uuid"]
    return mockup_uuid, smart_object_uuid


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
