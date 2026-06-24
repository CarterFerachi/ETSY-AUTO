"""Generate t-shirt artwork via DALL-E 3 and return a PNG file path."""
from __future__ import annotations

import logging
import re
import tempfile
import time
from pathlib import Path

import httpx
from openai import AsyncOpenAI

from .config import get_settings

log = logging.getLogger(__name__)

_PROMPT_TEMPLATE = (
    "A bold, high-contrast graphic t-shirt design on a pure white background. "
    "Theme: {theme}. "
    "Style: flat vector illustration, vibrant colors, no photograph, no text unless "
    "the theme specifically calls for it. "
    "The artwork must be centered with plenty of white space around it, "
    "print-ready PNG transparency style."
)


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


async def generate_design(keyword: str, out_dir: Path | None = None) -> Path:
    """
    Call DALL-E 3, download the result, and save it to *out_dir*.
    Returns the local PNG path.
    """
    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    prompt = _PROMPT_TEMPLATE.format(theme=keyword)
    log.info("Generating design for %r", keyword)

    response = await client.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        size="1024x1024",
        quality="standard",
        n=1,
    )

    image_url = response.data[0].url
    if not image_url:
        raise RuntimeError("DALL-E returned no image URL")

    # Download the image
    async with httpx.AsyncClient(timeout=60) as http:
        img_response = await http.get(image_url)
        img_response.raise_for_status()

    if out_dir is None:
        out_dir = Path(tempfile.mkdtemp(prefix="autobot_designs_"))
    out_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{_slugify(keyword)}_{int(time.time())}.png"
    dest = out_dir / filename
    dest.write_bytes(img_response.content)
    log.info("Design saved → %s", dest)
    return dest
