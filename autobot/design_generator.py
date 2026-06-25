"""Generate t-shirt artwork via Recraft 4.1 and return a transparent PNG file path."""
from __future__ import annotations

import logging
import re
import tempfile
import time
from pathlib import Path
import io

import httpx
from PIL import Image

from .config import get_settings

log = logging.getLogger(__name__)

_RECRAFT_BASE = "https://external.api.recraft.ai/v1"

_CUSTOM_PROMPTS: dict[str, str] = {
    "wtf is a kilometer bald eagle": (
        "Detailed ink illustration of a bald eagle head with flowing white feathers styled like a colonial wig, "
        "wearing red American flag wayfarer sunglasses with stars and stripes on the lenses. "
        "Bold brush-stroke text below: 'WTF IS A' in navy blue and 'KILOMETER?' in red. "
        "Vintage engraving crosshatch style, high contrast black and white with red and blue accents. "
        "Pure white background. DTG t-shirt print ready."
    ),
    "dream team of 1776 founding fathers basketball": (
        "Illustrated portrait of five founding fathers — George Washington center, Benjamin Franklin, "
        "Thomas Jefferson, John Adams, Alexander Hamilton — wearing USA Basketball jerseys red white blue. "
        "Bold text at bottom: 'DREAM TEAM' in large red letters, 'OF 1776' below with stars. "
        "Vintage sports poster style, detailed illustration. Pure white background. DTG t-shirt print ready."
    ),
    "ben drankin benjamin franklin fourth of july": (
        "Vintage illustrated portrait of Benjamin Franklin wearing American flag aviator sunglasses "
        "and a red stars-and-stripes headband, holding up a glass of whiskey with a grin. "
        "Distressed American flag in the background. Bold text: 'BEN' at top and 'DRANKIN' below "
        "in large white distressed varsity font with stars. Red white and blue. DTG t-shirt print ready."
    ),
    "1776 national champs founding fathers": (
        "Illustrated group of six founding fathers in colonial uniforms all wearing cool black sunglasses, "
        "posed like a championship team photo. George Washington front and center, confident poses. "
        "Large bold text at top: '1776 NATIONAL CHAMPS' in cream and gold collegiate font. "
        "Banner at bottom: 'EST. 1776' with eagle crest. Slate blue vintage style. DTG t-shirt print ready."
    ),
    "its only treason if you lose george washington": (
        "Illustrated George Washington in full colonial military uniform, wearing aviator sunglasses, "
        "walking confidently with fireworks exploding dramatically behind him. Action hero composition. "
        "Bold text at bottom: 'IT\\'S ONLY TREASON IF YOU LOSE' in clean white font. "
        "Pure white background. DTG t-shirt print ready."
    ),
    "george washington crossing the delaware sunglasses": (
        "Dramatic illustrated scene of George Washington standing boldly at the front of a boat "
        "crossing a river, wearing aviator sunglasses, American flag waving behind him. "
        "Epic cinematic composition, red white and blue. Bold text: 'UNBOTHERED' at bottom. "
        "Pure white background. DTG t-shirt print ready."
    ),
    "founding fathers fourth of july squad goals": (
        "Illustrated group portrait of Washington, Franklin, Jefferson, Hamilton, and Adams "
        "all wearing sunglasses, posed like a modern squad photo. Casual confident energy. "
        "Bold text: 'SQUAD GOALS' at top, 'EST. 1776' at bottom with stars. "
        "Red white and blue vintage style. Pure white background. DTG t-shirt print ready."
    ),
    "benjamin franklin original founding bro": (
        "Vintage illustrated portrait of Benjamin Franklin looking cool and confident, "
        "wearing sunglasses, lightning bolt in background referencing his electricity discovery. "
        "Bold retro text: 'ORIGINAL FOUNDING BRO' in distressed font. Stars and stripes accents. "
        "Pure white background. DTG t-shirt print ready."
    ),
    "1776 original bad boys founding fathers": (
        "Illustrated movie-poster style lineup of five founding fathers in colonial attire "
        "all wearing sunglasses, serious tough expressions like a police lineup. "
        "Bold text at top: 'ORIGINAL BAD BOYS' and '1776' in large vintage font at bottom. "
        "High contrast black white red blue. Pure white background. DTG t-shirt print ready."
    ),
    "we the people fourth of july founding fathers": (
        "Bold typographic t-shirt design centered on 'WE THE PEOPLE' in massive distressed "
        "varsity font. Stars, eagle silhouette, and 'EST. 1776' as accents. "
        "Red white and blue aged parchment texture aesthetic. "
        "Pure white background. DTG t-shirt print ready."
    ),
    "america est 1776 founding fathers vintage": (
        "Vintage circular badge design with an eagle at center, stars around the border, "
        "bold text 'AMERICA' at top and 'EST. 1776' at bottom. Distressed aged texture, "
        "red white and blue, classic Americana stamp style. "
        "Pure white background. DTG t-shirt print ready."
    ),
    "patrick henry give me liberty or give me coffee": (
        "Illustrated portrait of Patrick Henry at a podium, dramatic expression, pointing finger, "
        "holding a coffee cup instead of a torch. Colonial setting with dramatic lighting. "
        "Bold text: 'GIVE ME LIBERTY OR GIVE ME COFFEE' in distressed font. "
        "Pure white background. DTG t-shirt print ready."
    ),
    "george washington first in war first in peace first in swag": (
        "Cool illustrated portrait of George Washington in colonial uniform wearing sunglasses, "
        "relaxed confident pose. Bold text: 'FIRST IN WAR. FIRST IN PEACE. FIRST IN SWAG.' "
        "Stars and flag accents, vintage red white blue. Pure white background. DTG t-shirt print ready."
    ),
    "America 250th birthday 1776 2026": (
        "Stunning patriotic graphic celebrating America's 250th birthday. "
        "Majestic bald eagle at center with wings spread, surrounded by stars and fireworks, "
        "banner reading '250 YEARS' with '1776 - 2026' below. Vintage Americana style, "
        "distressed textures, bold typography, red white blue. Pure white background. DTG print ready."
    ),
    "250 years of freedom 1776 2026": (
        "Bold patriotic typography design. Large distressed text '250 YEARS OF FREEDOM' as centerpiece. "
        "'1776 - 2026' in vintage stamp style. Stars, stripes, eagle silhouette as accents. "
        "Aged vintage Americana aesthetic, red white blue. Pure white background. DTG print ready."
    ),
    "party like its 1776": (
        "Illustrated founding fathers at a wild party — Washington, Franklin, Jefferson with "
        "powdered wigs askew, holding drinks, celebrating. Fun chaotic energy. "
        "Bold handwritten text: 'PARTY LIKE IT\\'S 1776' at bottom. "
        "Pure white background. DTG t-shirt print ready."
    ),
    "its only treason if you lose": (
        "Bold typographic design with distressed text 'IT\\'S ONLY TREASON IF YOU LOSE' "
        "as the main statement. Eagle silhouette and stars as accents, aged vintage style. "
        "Red white blue distressed fonts. Pure white background. DTG t-shirt print ready."
    ),
}

_FALLBACK_PROMPT = (
    "A viral Etsy best-seller graphic t-shirt design in founding fathers humor style. "
    "Theme: {theme}. "
    "Style: vintage illustrated portrait or typographic design featuring American founding fathers "
    "— Washington, Franklin, Jefferson, Hamilton — in humorous modern situations. "
    "Colonial attire with modern accessories like sunglasses. Bold distressed typography. "
    "Red white and blue color palette, aged vintage Americana aesthetic. "
    "Pure white background. DTG t-shirt print ready."
)


def _remove_white_background(image_bytes: bytes, threshold: int = 240) -> bytes:
    """Replace near-white pixels with transparency using Pillow — no ML model needed."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    data = img.getdata()
    new_data = []
    for r, g, b, a in data:
        if r >= threshold and g >= threshold and b >= threshold:
            new_data.append((r, g, b, 0))
        else:
            new_data.append((r, g, b, a))
    img.putdata(new_data)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


async def generate_design(keyword: str, out_dir: Path | None = None) -> Path:
    """Generate design via Recraft 4.1, remove white background, save transparent PNG."""
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

    async with httpx.AsyncClient(timeout=60) as client:
        img_r = await client.get(image_url)
        img_r.raise_for_status()
    image_bytes = img_r.content

    if out_dir is None:
        out_dir = Path(tempfile.mkdtemp(prefix="autobot_designs_"))
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("Removing white background for %r", keyword)
    transparent_bytes = _remove_white_background(image_bytes)

    filename = f"{_slugify(keyword)}_{int(time.time())}.png"
    dest = out_dir / filename
    dest.write_bytes(transparent_bytes)
    log.info("Design saved (transparent) → %s", dest)
    return dest
