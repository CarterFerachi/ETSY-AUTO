"""Higgsfield REST API client — image generation + background removal."""
from __future__ import annotations

import asyncio
import logging
import time
import tempfile
from pathlib import Path

import httpx

from .config import get_settings

log = logging.getLogger(__name__)

_BASE = "https://api.higgsfield.ai/v1"
_POLL_INTERVAL = 5   # seconds between job status checks
_POLL_TIMEOUT  = 180 # max seconds to wait for a job

# Recraft v4.1 vector — best for t-shirt illustration + baked-in text
_MODEL       = "recraft-v4-1"
_MODEL_TYPE  = "vector"
_COLORS      = ["#1B2A4A", "#CC2222", "#F5F0E0", "#FFFFFF"]  # navy, red, cream, white


async def _post(client: httpx.AsyncClient, path: str, json: dict) -> dict:
    settings = get_settings()
    r = await client.post(
        f"{_BASE}{path}",
        headers={
            "Authorization": f"Bearer {settings.higgsfield_api_key}",
            "Content-Type": "application/json",
        },
        json=json,
        timeout=60,
    )
    if not r.is_success:
        log.error("Higgsfield %s error: %s %s", path, r.status_code, r.text)
    r.raise_for_status()
    return r.json()


async def _wait_for_job(client: httpx.AsyncClient, job_id: str) -> dict:
    settings = get_settings()
    headers = {"Authorization": f"Bearer {settings.higgsfield_api_key}"}
    deadline = time.monotonic() + _POLL_TIMEOUT
    while time.monotonic() < deadline:
        await asyncio.sleep(_POLL_INTERVAL)
        r = await client.get(
            f"{_BASE}/jobs/{job_id}",
            headers=headers,
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        status = data.get("status", "")
        log.debug("Job %s status: %s", job_id, status)
        if status == "completed":
            return data
        if status in ("failed", "error"):
            raise RuntimeError(f"Higgsfield job {job_id} failed: {data}")
    raise TimeoutError(f"Higgsfield job {job_id} timed out after {_POLL_TIMEOUT}s")


async def _upload_media(client: httpx.AsyncClient, image_path: Path) -> str:
    """Upload a local image to Higgsfield and return the media_id."""
    settings = get_settings()
    headers = {"Authorization": f"Bearer {settings.higgsfield_api_key}"}

    # Step 1: Request presigned upload URL
    r = await client.post(
        f"{_BASE}/media",
        headers={**headers, "Content-Type": "application/json"},
        json={"filename": image_path.name},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    media_id = data["id"]
    upload_url = data["upload_url"]

    # Step 2: PUT file bytes
    raw = image_path.read_bytes()
    put_r = await client.put(upload_url, content=raw, headers={"Content-Type": "image/png"}, timeout=60)
    put_r.raise_for_status()

    # Step 3: Confirm
    confirm_r = await client.post(
        f"{_BASE}/media/{media_id}/confirm",
        headers={**headers, "Content-Type": "application/json"},
        json={"type": "image"},
        timeout=30,
    )
    confirm_r.raise_for_status()

    log.info("Uploaded media to Higgsfield: %s", media_id)
    return media_id


async def generate_mockup(design_path: Path, out_dir: Path | None = None) -> Path:
    """
    Generate a photorealistic lifestyle mockup of someone wearing the t-shirt design.
    Uses GPT Image 2 with the design as a reference image.
    Returns path to the saved mockup PNG.
    """
    if out_dir is None:
        out_dir = Path(tempfile.mkdtemp(prefix="autobot_mockups_"))
    out_dir.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(timeout=120) as client:
        media_id = await _upload_media(client, design_path)

        prompt = (
            "Photorealistic lifestyle photo of a young adult wearing a white garment-dyed "
            "t-shirt with this exact graphic design printed large and centered on the front. "
            "Casual outdoor setting, natural daylight, clean background. "
            "The design is clearly visible and faithfully reproduced on the shirt. "
            "Professional product photography, slight smile, relaxed pose."
        )

        log.info("Higgsfield: generating lifestyle mockup…")
        gen = await _post(client, "/images/generate", {
            "model": "gpt_image_2",
            "prompt": prompt,
            "medias": [{"role": "image", "value": media_id}],
            "aspect_ratio": "3:4",
            "quality": "medium",
            "resolution": "1k",
        })

        job_id = gen.get("id") or gen.get("job_id") or (gen.get("results") or [{}])[0].get("id")
        if not job_id:
            raise ValueError(f"No job_id in mockup generate response: {gen}")

        log.info("Higgsfield mockup job: %s", job_id)
        result = await _wait_for_job(client, job_id)
        results = result.get("results") or {}
        mockup_url = results.get("rawUrl") or results.get("minUrl") or result.get("url")
        if not mockup_url:
            raise ValueError(f"No URL in Higgsfield mockup result: {result}")

        dl = await client.get(mockup_url, timeout=60)
        dl.raise_for_status()

    filename = f"mockup_{job_id}_{int(time.time())}.png"
    dest = out_dir / filename
    dest.write_bytes(dl.content)
    log.info("Mockup saved → %s", dest)
    return dest


async def generate_and_remove_bg(prompt: str, out_dir: Path | None = None) -> Path:
    """
    Generate a t-shirt design via Higgsfield (Recraft v4.1 vector),
    then strip the background using Higgsfield's AI segmentation.
    Returns path to the saved transparent PNG.
    """
    if out_dir is None:
        out_dir = Path(tempfile.mkdtemp(prefix="autobot_designs_"))
    out_dir.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(timeout=120) as client:
        # ── Step 1: Generate ──────────────────────────────────────────────
        log.info("Higgsfield: generating image…")
        gen = await _post(client, "/images/generate", {
            "model":       _MODEL,
            "model_type":  _MODEL_TYPE,
            "prompt":      prompt,
            "aspect_ratio": "1:1",
            "colors":      _COLORS,
            "background_color": "#FFFFFF",
            "resolution":  "1k",
        })

        job_id = gen.get("id") or gen.get("job_id") or (gen.get("results") or [{}])[0].get("id")
        if not job_id:
            raise ValueError(f"No job_id in Higgsfield generate response: {gen}")

        log.info("Higgsfield generate job: %s", job_id)
        gen_result = await _wait_for_job(client, job_id)

        # Extract the image URL from the completed job
        results = gen_result.get("results") or {}
        image_url = (
            results.get("rawUrl")
            or results.get("minUrl")
            or gen_result.get("url")
        )
        if not image_url:
            raise ValueError(f"No image URL in Higgsfield job result: {gen_result}")
        log.info("Higgsfield image URL: %s", image_url)

        # ── Step 2: Remove background ─────────────────────────────────────
        log.info("Higgsfield: removing background (job_id=%s)…", job_id)
        bg_resp = await _post(client, "/images/remove-background", {
            "media_id":   job_id,
            "media_type": "image",
        })

        bg_job_id = (
            bg_resp.get("id")
            or bg_resp.get("job_id")
            or (bg_resp.get("results") or [{}])[0].get("id")
        )
        if not bg_job_id:
            # Some providers return the result immediately
            transparent_url = bg_resp.get("url") or bg_resp.get("rawUrl")
        else:
            log.info("Higgsfield bg-removal job: %s", bg_job_id)
            bg_result = await _wait_for_job(client, bg_job_id)
            bg_results = bg_result.get("results") or {}
            transparent_url = (
                bg_results.get("rawUrl")
                or bg_results.get("minUrl")
                or bg_result.get("url")
            )

        if not transparent_url:
            raise ValueError(f"No URL in Higgsfield bg-removal result: {bg_resp}")
        log.info("Higgsfield transparent image: %s", transparent_url)

        # ── Step 3: Download ──────────────────────────────────────────────
        dl = await client.get(transparent_url, timeout=60)
        dl.raise_for_status()

    filename = f"design_{job_id}_{int(time.time())}.png"
    dest = out_dir / filename
    dest.write_bytes(dl.content)
    log.info("Design saved → %s", dest)
    return dest
