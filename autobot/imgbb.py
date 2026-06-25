"""imgbb image hosting helper."""
from __future__ import annotations

import base64
import logging
from pathlib import Path

import httpx

from .config import get_settings

log = logging.getLogger(__name__)


async def upload_to_imgbb(image_path: Path) -> str:
    """Upload an image to imgbb and return the public URL. Returns empty string on failure."""
    settings = get_settings()
    if not settings.imgbb_api_key:
        log.warning("IMGBB_API_KEY not set — skipping upload")
        return ""
    b64 = base64.b64encode(image_path.read_bytes()).decode()
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            "https://api.imgbb.com/1/upload",
            data={"key": settings.imgbb_api_key, "image": b64},
        )
    if r.is_success:
        url: str = r.json()["data"]["url"]
        log.info("Uploaded to imgbb: %s", url)
        return url
    log.warning("imgbb upload failed: %s %s", r.status_code, r.text)
    return ""
