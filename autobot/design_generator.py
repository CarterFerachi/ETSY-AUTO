"""Generate t-shirt artwork via gpt-image-1 and return a PNG file path."""
from __future__ import annotations

import base64
import logging
import re
import tempfile
import time
from pathlib import Path

from openai import AsyncOpenAI

from .config import get_settings

log = logging.getLogger(__name__)

_PROMPT_TEMPLATE = (
    "A viral Etsy best-seller graphic t-shirt design on a pure white background. "
    "Theme: {theme}. "
    "Style: hyper-realistic photorealistic animal or character illustration with humor and personality. "
    "The animal or character wears fun patriotic accessories like sunglasses, hats, bandanas, "
    "and holds props like American flags, hot dogs, sparklers, or fireworks. "
    "Ultra-detailed fur or feather texture, cinematic lighting, vivid red white and blue colors. "
    "Include a short bold fun text phrase in a casual handwritten or retro font that fits the theme — "
    "placed naturally at the bottom of the design. "
    "Centered on a pure white background, no extra borders or background colors. "
    "Print-ready for direct-to-garment, extremely high detail, professional quality."
)


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


async def generate_design(keyword: str, out_dir: Path | None = None) -> Path:
    """Call gpt-image-1, decode base64 result, save to out_dir. Returns PNG path."""
    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    prompt = _PROMPT_TEMPLATE.format(theme=keyword)
    log.info("Generating design for %r", keyword)

    response = await client.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        size="1024x1024",
        quality="high",
        n=1,
    )

    image_b64 = response.data[0].b64_json
    if not image_b64:
        raise RuntimeError("gpt-image-1 returned no image data")

    image_bytes = base64.b64decode(image_b64)

    if out_dir is None:
        out_dir = Path(tempfile.mkdtemp(prefix="autobot_designs_"))
    out_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{_slugify(keyword)}_{int(time.time())}.png"
    dest = out_dir / filename
    dest.write_bytes(image_bytes)
    log.info("Design saved → %s", dest)
    return dest
