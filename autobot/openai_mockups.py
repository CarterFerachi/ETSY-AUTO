"""OpenAI lifestyle mockup generation — GPT-4o describes the design, DALL-E 3 renders it."""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import httpx
from openai import AsyncOpenAI

from .config import get_settings
from .imgbb import upload_to_imgbb

log = logging.getLogger(__name__)


async def generate_lifestyle_mockup(design_url: str) -> str | None:
    """
    1. GPT-4o-mini describes the design in the image.
    2. DALL-E 3 generates a professional lifestyle photo of a male model
       wearing a white t-shirt with that design on the front.
    3. Uploads the result to imgbb and returns the permanent URL.

    Returns None on failure.
    """
    settings = get_settings()
    if not settings.openai_api_key:
        log.warning("OpenAI API key not set")
        return None

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    # Step 1: Describe the design with vision
    try:
        log.info("OpenAI mockup: describing design via GPT-4o-mini…")
        vision = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": design_url, "detail": "high"},
                        },
                        {
                            "type": "text",
                            "text": (
                                "Describe this t-shirt graphic design in precise detail for use "
                                "in an image generation prompt. Include: all text and exact wording, "
                                "colors, graphical elements, style (vintage, modern, illustrated, etc.), "
                                "and overall composition. Be specific and concise, max 120 words."
                            ),
                        },
                    ],
                }
            ],
            max_tokens=180,
        )
        design_description = vision.choices[0].message.content.strip()
        log.info("Design description: %s", design_description)
    except Exception:
        log.exception("GPT-4o-mini vision failed")
        return None

    # Step 2: Generate lifestyle photo with DALL-E 3
    try:
        log.info("OpenAI mockup: generating lifestyle photo via DALL-E 3…")
        prompt = (
            f"Professional Etsy product photography. A male model with tattoos wearing a white "
            f"crew-neck t-shirt. The shirt has a bold graphic printed large on the front: "
            f"{design_description}. "
            f"Patriotic American flag bokeh background with soft fireworks. Waist-up shot, "
            f"confident relaxed pose. High contrast, vibrant colors. Studio quality."
        )
        response = await client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1792",
            quality="hd",
            n=1,
        )
        image_url = response.data[0].url
        log.info("DALL-E 3 lifestyle image: %s", image_url)
    except Exception:
        log.exception("DALL-E 3 generation failed")
        return None

    # Step 3: Download and re-host on imgbb (DALL-E URLs expire in 1 hour)
    try:
        async with httpx.AsyncClient(timeout=60) as http:
            dl = await http.get(image_url)
            dl.raise_for_status()

        tmp = Path(tempfile.mkdtemp()) / "openai_mockup.jpg"
        tmp.write_bytes(dl.content)
        permanent_url = await upload_to_imgbb(tmp)
        tmp.unlink(missing_ok=True)

        if permanent_url:
            log.info("OpenAI mockup uploaded to imgbb: %s", permanent_url)
            return permanent_url
        log.warning("imgbb upload failed — returning DALL-E temp URL")
        return image_url
    except Exception:
        log.exception("OpenAI mockup download/upload failed")
        return image_url  # Return temp URL as last resort
