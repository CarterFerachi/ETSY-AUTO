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

# Per-keyword custom prompts — these produce far better results than a generic template.
# Each prompt is hand-crafted to nail the viral Etsy photorealistic animal style.
_CUSTOM_PROMPTS: dict[str, str] = {
    "patriotic raccoon holding American flag": (
        "Hyper-realistic photorealistic raccoon wearing a blue baseball cap, heart-shaped red sunglasses, "
        "and a stars-and-stripes bandana. Holding a small American flag in one hand and a hot dog in the other. "
        "Ultra-detailed fur texture, cinematic dramatic lighting, vivid red white and blue colors. "
        "Handwritten retro text 'america' at the bottom. CRITICAL: Pure white (#FFFFFF) background only. No grey. No shadow. No border. No box. DTG print ready."
    ),
    "bald eagle wearing sunglasses fourth of july": (
        "Hyper-realistic photorealistic bald eagle with fierce intense eyes wearing gold aviator sunglasses. "
        "American flag draped over its wings like a cape. Fireworks exploding behind it. "
        "Ultra-detailed feather texture, dramatic lighting, patriotic red white blue. "
        "Bold retro text 'FREEDOM' at the bottom. CRITICAL: Pure white (#FFFFFF) background only. No grey. No shadow. No border. No box. DTG print ready."
    ),
    "patriotic golden retriever with hot dog and flag": (
        "Hyper-realistic photorealistic golden retriever with a huge joyful grin, wearing a stars-and-stripes "
        "party hat and heart sunglasses, holding a hot dog in one paw and a tiny American flag in the other. "
        "Rich golden fur detail, warm cinematic lighting. Fun handwritten text 'good boy' at the bottom. "
        "CRITICAL: Pure white (#FFFFFF) background only. No grey. No shadow. No border. No box. DTG print ready."
    ),
    "american bulldog fourth of july vibes": (
        "Hyper-realistic photorealistic American bulldog wearing a red white and blue bandana and aviator sunglasses, "
        "holding a sparkler. Confident tough expression. Ultra-detailed wrinkled skin and fur. "
        "Bold text 'MURICA' at the bottom in a distressed vintage font. CRITICAL: Pure white (#FFFFFF) background only. No grey. No shadow. No border. No box. DTG print ready."
    ),
    "patriotic bear drinking beer with flag": (
        "Hyper-realistic photorealistic grizzly bear wearing a stars-and-stripes trucker hat and sunglasses, "
        "holding a cold beer can with an American flag on it. Relaxed happy expression. "
        "Ultra-detailed fur texture, golden hour lighting. Casual handwritten text 'bear with it' at bottom. "
        "CRITICAL: Pure white (#FFFFFF) background only. No grey. No shadow. No border. No box. DTG print ready."
    ),
    "feral cat fourth of july chaos": (
        "Hyper-realistic photorealistic chaotic feral cat with wild eyes wearing a tiny American flag bandana, "
        "surrounded by lit fireworks and sparklers it knocked over. Mischievous unhinged expression. "
        "Ultra-detailed fur, dramatic lighting. Handwritten text 'feral and free' at the bottom. "
        "CRITICAL: Pure white (#FFFFFF) background only. No grey. No shadow. No border. No box. DTG print ready."
    ),
    "patriotic labrador with fireworks": (
        "Hyper-realistic photorealistic black labrador retriever wearing star-shaped sunglasses and a patriotic bow tie, "
        "sitting proudly with fireworks bursting around it. Excited happy expression. "
        "Ultra-detailed fur and lighting. Fun text 'lab tested american approved' at bottom. "
        "CRITICAL: Pure white (#FFFFFF) background only. No grey. No shadow. No border. No box. DTG print ready."
    ),
    "american raccoon eating hot dog": (
        "Hyper-realistic photorealistic raccoon sitting and enthusiastically eating a hot dog with both tiny hands, "
        "wearing a patriotic stars-and-stripes bandana and tiny sunglasses. Absolute joy on its face. "
        "Ultra-detailed fur, dramatic lighting. Handwritten text 'living the dream' at bottom. "
        "CRITICAL: Pure white (#FFFFFF) background only. No grey. No shadow. No border. No box. DTG print ready."
    ),
    "patriotic corgi wearing stars and stripes": (
        "Hyper-realistic photorealistic corgi wearing a stars-and-stripes outfit and tiny sunglasses, "
        "sitting proudly with an American flag behind it. Happy derpy corgi smile. "
        "Ultra-detailed fur and fluffy butt. Fun text 'corgi of the free' at bottom. "
        "CRITICAL: Pure white (#FFFFFF) background only. No grey. No shadow. No border. No box. DTG print ready."
    ),
    "bald eagle screaming freedom": (
        "Hyper-realistic photorealistic bald eagle with beak wide open screaming, wearing aviator sunglasses, "
        "American flag pattern on wings, fireworks exploding in the background. Pure raw patriotic energy. "
        "Ultra-detailed feathers, cinematic lighting. Bold text 'FREEDOM' in distressed font at bottom. "
        "CRITICAL: Pure white (#FFFFFF) background only. No grey. No shadow. No border. No box. DTG print ready."
    ),
    "America 250th birthday 1776 2026": (
        "Stunning patriotic graphic design celebrating America's 250th birthday. "
        "A majestic bald eagle at center with wings spread, surrounded by stars, fireworks, and a banner reading "
        "'250 YEARS' with '1776 — 2026' below it. Red white and blue color palette, vintage Americana style, "
        "distressed textures, bold typography. CRITICAL: Pure white (#FFFFFF) background only. No grey. No shadow. No border. No box. DTG print ready."
    ),
    "250 years of freedom 1776 2026": (
        "Bold patriotic typography t-shirt design. Large distressed text '250 YEARS OF FREEDOM' as the centerpiece. "
        "'1776 — 2026' in vintage stamp style. Stars, stripes, and an eagle silhouette as accents. "
        "Aged vintage Americana aesthetic, red white and blue, worn distressed textures. "
        "CRITICAL: Pure white (#FFFFFF) background only. No grey. No shadow. No border. No box. DTG print ready."
    ),
    "Americas 250th anniversary celebration": (
        "Vintage retro Americana poster style t-shirt design celebrating 250 years. "
        "Circular badge design with bald eagle at top, stars around the border, "
        "text 'AMERICA'S 250TH ANNIVERSARY' and '1776 — 2026'. Red white blue distressed vintage style. "
        "CRITICAL: Pure white (#FFFFFF) background only. No grey. No shadow. No border. No box. DTG print ready."
    ),
    "party like its 1776": (
        "Hyper-realistic photorealistic raccoon in a colonial tricorn hat and tiny waistcoat, "
        "holding a sparkler and a mug, wild party expression. "
        "Ultra-detailed fur, dramatic lighting. Bold handwritten text 'party like it's 1776' at bottom. "
        "CRITICAL: Pure white (#FFFFFF) background only. No grey. No shadow. No border. No box. DTG print ready."
    ),
    "merica fourth of july party": (
        "Hyper-realistic photorealistic golden retriever wearing an American flag bandana and sunglasses, "
        "standing next to a grill with hot dogs. Big happy grin. Summer cookout energy. "
        "Ultra-detailed fur, warm sunny lighting. Bold text 'MERICA' at bottom in distressed font. "
        "CRITICAL: Pure white (#FFFFFF) background only. No grey. No shadow. No border. No box. DTG print ready."
    ),
}

_FALLBACK_PROMPT = (
    "A viral Etsy best-seller graphic t-shirt design. "
    "Theme: {theme}. "
    "Style: hyper-realistic photorealistic animal illustration with humor and personality. "
    "The animal wears fun patriotic accessories — sunglasses, hats, bandanas — "
    "and holds props like American flags, hot dogs, or sparklers. "
    "Ultra-detailed fur or feather texture, cinematic lighting, vivid red white and blue colors. "
    "Short bold fun handwritten text at the bottom that matches the theme. "
    "CRITICAL: Pure white (#FFFFFF) background only. No grey. No shadow. No border. No box. "
    "No background color. The design floats directly on white. DTG print ready."
)


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


async def generate_design(keyword: str, out_dir: Path | None = None) -> Path:
    """Call gpt-image-1, decode base64 result, save to out_dir. Returns PNG path."""
    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    prompt = _CUSTOM_PROMPTS.get(keyword) or _FALLBACK_PROMPT.format(theme=keyword)
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
