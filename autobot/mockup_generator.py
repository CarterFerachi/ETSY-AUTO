"""
Generate lifestyle product mockup images via Higgsfield marketing_studio_image.
Takes the flat t-shirt design PNG and returns a mockup image as bytes.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

_HIGGSFIELD_API = "https://api.higgsfield.ai"


async def generate_mockup(design_path: Path, keyword: str, api_key: str) -> bytes:
    """Upload design to Higgsfield, generate a lifestyle mockup, return PNG bytes."""

    headers = {"Authorization": f"Bearer {api_key}"}

    # Step 1: Get presigned upload URL
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{_HIGGSFIELD_API}/v1/media/upload",
            json={"filename": design_path.name, "method": "upload_url"},
            headers=headers,
        )
        r.raise_for_status()
        upload_data = r.json()

    media_id = upload_data["media_id"]
    upload_url = upload_data["upload_url"]

    # Step 2: Upload the design image
    design_bytes = design_path.read_bytes()
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.put(
            upload_url,
            content=design_bytes,
            headers={"Content-Type": "image/png"},
        )
        r.raise_for_status()

    # Step 3: Confirm upload
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{_HIGGSFIELD_API}/v1/media/confirm",
            json={"media_id": media_id, "type": "image"},
            headers=headers,
        )
        r.raise_for_status()

    # Step 4: Generate mockup
    prompt = (
        f"Professional lifestyle product photo of a '{keyword}' graphic t-shirt. "
        "A person wearing the shirt in a natural, stylish setting. "
        "Clean, bright ecommerce product photography style."
    )

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{_HIGGSFIELD_API}/v1/generate/image",
            json={
                "model": "marketing_studio_image",
                "prompt": prompt,
                "aspect_ratio": "1:1",
                "params": {"resolution": "1k"},
                "medias": [{"value": media_id, "role": "image"}],
            },
            headers=headers,
        )
        r.raise_for_status()
        job_data = r.json()

    job_id = job_data.get("id") or job_data.get("job_id")
    if not job_id:
        raise RuntimeError(f"No job ID returned: {job_data}")

    log.info("Higgsfield mockup job started: %s", job_id)

    # Step 5: Poll for result
    for attempt in range(30):
        await asyncio.sleep(10)
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"{_HIGGSFIELD_API}/v1/jobs/{job_id}",
                headers=headers,
            )
            r.raise_for_status()
            status_data = r.json()

        status = status_data.get("status", "")
        log.info("Mockup job %s status: %s", job_id, status)

        if status == "completed":
            result_url = (
                status_data.get("result", {}).get("url")
                or status_data.get("output_url")
                or (status_data.get("results") or [{}])[0].get("url")
            )
            if not result_url:
                raise RuntimeError(f"No result URL in completed job: {status_data}")
            async with httpx.AsyncClient(timeout=60) as client:
                img_r = await client.get(result_url)
                img_r.raise_for_status()
            log.info("Mockup downloaded for keyword %r", keyword)
            return img_r.content

        if status in ("failed", "error", "cancelled"):
            raise RuntimeError(f"Higgsfield job {job_id} failed: {status_data}")

    raise RuntimeError(f"Higgsfield job {job_id} timed out after 300s")
