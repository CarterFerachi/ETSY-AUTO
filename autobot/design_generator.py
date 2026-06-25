"""Generate t-shirt artwork via Recraft 4.1 and return a transparent PNG file path."""
from __future__ import annotations

import logging
import re
import tempfile
import time
from pathlib import Path

import httpx
from PIL import Image
import io

from .config import get_settings

log = logging.getLogger(__name__)

_RECRAFT_BASE = "https://external.api.recraft.ai/v1"

_CUSTOM_PROMPTS: dict[str, str] = {
    "patriotic raccoon holding American flag": (
        "Hyper-realistic photorealistic raccoon wearing a blue baseball cap, heart-shaped red sunglasses, "
        "and a stars-and-stripes bandana. Holding a small American flag in one hand and a hot dog in the other. "
        "Ultra-detailed fur texture, cinematic dramatic lighting, vivid red white and blue colors. "
        "Handwritten retro text 'AMERICA' at the bottom. Pure white background. DTG t-shirt print ready."
    ),
    "bald eagle wearing sunglasses fourth of july": (
        "Hyper-realistic photorealistic bald eagle with fierce intense eyes wearing gold aviator sunglasses. "
        "American flag draped over its wings like a cape. Fireworks exploding behind it. "
        "Ultra-detailed feather texture, dramatic lighting, patriotic red white blue. "
        "Bold retro text 'FREEDOM' at the bottom. Pure white background. DTG t-shirt print ready."
    ),
    "patriotic golden retriever with hot dog and flag": (
        "Hyper-realistic photorealistic golden retriever with a huge joyful grin, wearing a stars-and-stripes "
        "party hat and heart sunglasses, holding a hot dog in one paw and a tiny American flag in the other. "
        "Rich golden fur detail, warm cinematic lighting. Fun handwritten text 'GOOD BOY' at the bottom. "
        "Pure white background. DTG t-shirt print ready."
    ),
    "american bulldog fourth of july vibes": (
        "Hyper-realistic photorealistic American bulldog wearing a red white and blue bandana and aviator sunglasses, "
        "holding a sparkler. Confident tough expression. Ultra-detailed wrinkled skin and fur. "
        "Bold text 'MURICA' at the bottom in a distressed vintage font. Pure white background. DTG t-shirt print ready."
    ),
    "patriotic bear drinking beer with flag": (
        "Hyper-realistic photorealistic grizzly bear wearing a stars-and-stripes trucker hat and sunglasses, "
        "holding a cold beer can with an American flag on it. Relaxed happy expression. "
        "Ultra-detailed fur texture, golden hour lighting. Casual handwritten text 'BEAR WITH IT' at bottom. "
        "Pure white background. DTG t-shirt print ready."
    ),
    "feral cat fourth of july chaos": (
        "Hyper-realistic photorealistic chaotic feral cat with wild eyes wearing a tiny American flag bandana, "
        "surrounded by lit fireworks and sparklers it knocked over. Mischievous unhinged expression. "
        "Ultra-detailed fur, dramatic lighting. Handwritten text 'FERAL AND FREE' at the bottom. "
        "Pure white background. DTG t-shirt print ready."
    ),
    "patriotic labrador with fireworks": (
        "Hyper-realistic photorealistic black labrador retriever wearing star-shaped sunglasses and a patriotic bow tie, "
        "sitting proudly with fireworks bursting around it. Excited happy expression. "
        "Ultra-detailed fur and lighting. Fun text 'LAB TESTED AMERICAN APPROVED' at bottom. "
        "Pure white background. DTG t-shirt print ready."
    ),
    "american raccoon eating hot dog": (
        "Hyper-realistic photorealistic raccoon sitting and enthusiastically eating a hot dog with both tiny hands, "
        "wearing a patriotic stars-and-stripes bandana and tiny sunglasses. Absolute joy on its face. "
        "Ultra-detailed fur, dramatic lighting. Handwritten text 'LIVING THE DREAM' at bottom. "
        "Pure white background. DTG t-shirt print ready."
    ),
    "patriotic corgi wearing stars and stripes": (
        "Hyper-realistic photorealistic corgi wearing a stars-and-stripes outfit and tiny sunglasses, "
        "sitting proudly with an American flag behind it. Happy derpy corgi smile. "
        "Ultra-detailed fur and fluffy butt. Fun text 'CORGI OF THE FREE' at bottom. "
        "Pure white background. DTG t-shirt print ready."
    ),
    "bald eagle screaming freedom": (
        "Hyper-realistic photorealistic bald eagle with beak wide open screaming, wearing aviator sunglasses, "
        "American flag pattern on wings, fireworks exploding in the background. Pure raw patriotic energy. "
        "Ultra-detailed feathers, cinematic lighting. Bold text 'FREEDOM' in distressed font at bottom. "
        "Pure white background. DTG t-shirt print ready."
    ),
    "America 250th birthday 1776 2026": (
        "Stunning patriotic graphic design celebrating America's 250th birthday. "
        "A majestic bald eagle at center with wings spread, surrounded by stars, fireworks, and a banner reading "
        "'250 YEARS' with '1776 - 2026' below it. Red white and blue color palette, vintage Americana style, "
        "distressed textures, bold typography. Pure white background. DTG t-shirt print ready."
    ),
    "250 years of freedom 1776 2026": (
        "Bold patriotic typography t-shirt design. Large distressed text '250 YEARS OF FREEDOM' as the centerpiece. "
        "'1776 - 2026' in vintage stamp style. Stars, stripes, and an eagle silhouette as accents. "
        "Aged vintage Americana aesthetic, red white and blue, worn distressed textures. "
        "Pure white background. DTG t-shirt print ready."
    ),
    "Americas 250th anniversary celebration": (
        "Vintage retro Americana poster style t-shirt design celebrating 250 years. "
        "Circular badge design with bald eagle at top, stars around the border, "
        "text 'AMERICA 250TH ANNIVERSARY' and '1776 - 2026'. Red white blue distressed vintage style. "
        "Pure white background. DTG t-shirt print ready."
    ),
    "party like its 1776": (
        "Hyper-realistic photorealistic raccoon in a colonial tricorn hat and tiny waistcoat, "
        "holding a sparkler and a mug, wild party expression. "
        "Ultra-detailed fur, dramatic lighting. Bold handwritten text 'PARTY LIKE IT IS 1776' at bottom. "
        "Pure white background. DTG t-shirt print ready."
    ),
    "merica fourth of july party": (
        "Hyper-realistic photorealistic golden retriever wearing an American flag bandana and sunglasses, "
        "standing next to a grill with hot dogs. Big happy grin. Summer cookout energy. "
        "Ultra-detailed fur, warm sunny lighting. Bold text 'MERICA' at bottom in distressed font. "
        "Pure white background. DTG t-shirt print ready."
    ),
    "wtf is a kilometer bald eagle": (
        "Detailed ink illustration of a bald eagle head with flowing white feathers styled like a colonial wig, "
        "wearing red American flag wayfarer sunglasses with stars and stripes on the lenses. "
        "Bold brush-stroke text below: 'WTF IS A' in navy blue and 'KILOMETER?' in red with a question mark. "
        "Vintage engraving crosshatch style, high contrast black and white illustration with red and blue accents. "
        "Pure white background. DTG t-shirt print ready."
    ),
    "dream team of 1776 founding fathers basketball": (
        "Illustrated portrait of five founding fathers — George Washington, Benjamin Franklin, Thomas Jefferson, "
        "John Adams, and Alexander Hamilton — dressed in USA Basketball jerseys (red white and blue). "
        "Washington stands tall in the center, others posed confidently around him. "
        "Bold text at bottom: 'DREAM TEAM' in large red letters and 'OF 1776' below with stars. "
        "Vintage sports poster style, detailed illustration, navy blue background with red and white accents. "
        "DTG t-shirt print ready."
    ),
    "ben drankin benjamin franklin fourth of july": (
        "Vintage illustrated portrait of Benjamin Franklin wearing American flag aviator sunglasses and a red "
        "stars-and-stripes headband, holding up a glass of whiskey with a grin. "
        "Distressed American flag in the background. Bold text: 'BEN' at top and 'DRANKIN' below in large "
        "white distressed varsity font with stars on either side. "
        "Worn vintage patriotic style, red white and blue color palette. DTG t-shirt print ready."
    ),
    "1776 national champs founding fathers": (
        "Illustrated group portrait of six founding fathers in colonial uniforms and suits, all wearing "
        "cool black sunglasses, posed like a championship team photo. George Washington front and center. "
        "Large bold collegiate text at top: '1776' and 'NATIONAL CHAMPS' in cream and gold. "
        "Banner at bottom reading 'EST. 1776' with an eagle crest shield. "
        "Slate blue vintage collegiate style, detailed illustration. DTG t-shirt print ready."
    ),
    "its only treason if you lose george washington": (
        "Illustrated George Washington in full colonial military uniform and powdered wig, wearing aviator "
        "sunglasses, walking confidently with fireworks exploding dramatically behind him. "
        "Cinematic action-hero composition, vivid red white and blue fireworks. "
        "Bold text at bottom: 'IT\\'S ONLY TREASON IF YOU LOSE' in clean white font. "
        "Pure white background. DTG t-shirt print ready."
    ),
}

_FALLBACK_PROMPT = (
    "A viral Etsy best-seller graphic t-shirt design. "
    "Theme: {theme}. "
    "Style: hyper-realistic photorealistic animal illustration with humor and personality. "
    "The animal wears fun patriotic accessories — sunglasses, hats, bandanas — "
    "and holds props like American flags, hot dogs, or sparklers. "
    "Ultra-detailed fur or feather texture, cinematic lighting, vivid red white and blue colors. "
    "Short bold fun text at the bottom that matches the theme. "
    "Pure white background. DTG t-shirt print ready."
)


def _remove_white_background(image_bytes: bytes, threshold: int = 240) -> bytes:
    """Replace near-white pixels with transparency using Pillow — no ML model needed."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    data = img.getdata()
    new_data = []
    for r, g, b, a in data:
        if r >= threshold and g >= threshold and b >= threshold:
            new_data.append((r, g, b, 0))  # transparent
        else:
            new_data.append((r, g, b, a))
    img.putdata(new_data)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


async def generate_design(keyword: str, out_dir: Path | None = None) -> Path:
    """Generate design via Recraft 4.1, remove background, save transparent PNG."""
    settings = get_settings()
    prompt = _CUSTOM_PROMPTS.get(keyword) or _FALLBACK_PROMPT.format(theme=keyword)
    log.info("Generating design for %r via Recraft 4.1", keyword)

    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            f"{_RECRAFT_BASE}/images/generations",
            headers={
                "Authorization": f"Bearer {settings.recraft_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "prompt": prompt,
                "model": "recraftv3",
                "style": "realistic_image",
                "size": "1024x1024",
            },
        )
        if not r.is_success:
            log.error("Recraft error: %s %s", r.status_code, r.text)
        r.raise_for_status()

    image_url: str = r.json()["data"][0]["url"]
    log.info("Recraft generated image URL: %s", image_url)

    # Download the image
    async with httpx.AsyncClient(timeout=60) as client:
        img_r = await client.get(image_url)
        img_r.raise_for_status()
    image_bytes = img_r.content

    if out_dir is None:
        out_dir = Path(tempfile.mkdtemp(prefix="autobot_designs_"))
    out_dir.mkdir(parents=True, exist_ok=True)

    # Remove white background → transparent PNG using Pillow flood fill
    log.info("Removing white background for %r", keyword)
    transparent_bytes = _remove_white_background(image_bytes)

    filename = f"{_slugify(keyword)}_{int(time.time())}.png"
    dest = out_dir / filename
    dest.write_bytes(transparent_bytes)
    log.info("Design saved (transparent) → %s", dest)
    return dest
