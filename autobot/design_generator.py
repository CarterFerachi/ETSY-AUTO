"""Generate t-shirt artwork via Ideogram v2 with text baked in."""
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

_IDEOGRAM_BASE = "https://api.ideogram.ai"

# ---------------------------------------------------------------------------
# Full prompts — art + text instructions together, let Ideogram handle it
# ---------------------------------------------------------------------------
_PROMPTS: dict[str, str] = {
    "wtf is a kilometer bald eagle": (
        "Vintage t-shirt graphic design. Detailed ink illustration of a bald eagle head "
        "with flowing white feathers styled like a colonial wig, wearing red American flag "
        "wayfarer sunglasses. Bold brush-stroke text: 'WTF IS A' at top in navy blue, "
        "'KILOMETER?' below in red. Vintage engraving crosshatch style, high contrast "
        "black and white with red and blue accents. Pure white background. DTG print ready."
    ),
    "dream team of 1776 founding fathers basketball": (
        "Vintage sports poster t-shirt graphic. Illustrated portrait of five founding fathers — "
        "George Washington center, Benjamin Franklin, Thomas Jefferson, John Adams, Alexander Hamilton — "
        "wearing USA Basketball jerseys in red white blue. Bold text at top: 'DREAM TEAM' in large "
        "red letters, 'OF 1776' below with stars. Pure white background. DTG print ready."
    ),
    "ben drankin benjamin franklin fourth of july": (
        "Vintage t-shirt graphic. Illustrated portrait of Benjamin Franklin wearing American flag "
        "aviator sunglasses and a red stars-and-stripes headband, holding up a glass of whiskey "
        "with a wide grin. Distressed American flag in background. Bold varsity text: 'BEN' at top, "
        "'DRANKIN' large below in white distressed font with stars. Red white and blue. "
        "Pure white background. DTG print ready."
    ),
    "1776 national champs founding fathers": (
        "Vintage championship poster t-shirt graphic. Group of six founding fathers in colonial "
        "uniforms all wearing cool black sunglasses, posed like a championship team photo. "
        "George Washington front and center. Bold collegiate text at top: '1776 NATIONAL CHAMPS' "
        "in cream and gold. Banner at bottom: 'EST. 1776' with eagle crest. Slate blue vintage style. "
        "Pure white background. DTG print ready."
    ),
    "its only treason if you lose george washington": (
        "Vintage t-shirt graphic. George Washington in colonial military uniform, wearing aviator "
        "sunglasses, striding confidently with fireworks exploding behind him. Action hero composition. "
        "Bold clean text at bottom: 'IT'S ONLY TREASON IF YOU LOSE' in white. "
        "Pure white background. DTG print ready."
    ),
    "george washington crossing the delaware sunglasses": (
        "Dramatic vintage t-shirt graphic. George Washington standing boldly at the front of a boat "
        "crossing a river, wearing aviator sunglasses, American flag waving behind him. "
        "Epic cinematic composition, red white and blue. Bold text at bottom: 'UNBOTHERED' in white. "
        "Pure white background. DTG print ready."
    ),
    "founding fathers fourth of july squad goals": (
        "Vintage t-shirt graphic. Group portrait of Washington, Franklin, Jefferson, Hamilton, and Adams "
        "all wearing sunglasses, posed like a modern friend squad photo. Confident casual energy. "
        "Bold text: 'SQUAD GOALS' at top, 'EST. 1776' at bottom with stars. "
        "Red white and blue vintage style. Pure white background. DTG print ready."
    ),
    "benjamin franklin original founding bro": (
        "Vintage t-shirt graphic. Portrait of Benjamin Franklin looking cool and confident, "
        "wearing sunglasses, lightning bolt in background. Bold retro text: "
        "'ORIGINAL FOUNDING BRO' below portrait. Stars and stripes accents. "
        "Pure white background. DTG print ready."
    ),
    "1776 original bad boys founding fathers": (
        "Movie poster style vintage t-shirt graphic. Lineup of five founding fathers in colonial attire "
        "all wearing sunglasses, tough serious expressions like a police lineup or action movie poster. "
        "Bold text at top: 'ORIGINAL BAD BOYS', large '1776' at bottom in vintage font. "
        "High contrast red white and blue. Pure white background. DTG print ready."
    ),
    "we the people fourth of july founding fathers": (
        "Bold typographic vintage t-shirt design. Large distressed varsity text 'WE THE PEOPLE' "
        "as centerpiece. Eagle silhouette, stars, and 'EST. 1776' as accents. "
        "Red white and blue aged parchment aesthetic. Pure white background. DTG print ready."
    ),
    "america est 1776 founding fathers vintage": (
        "Vintage circular badge t-shirt design. Eagle at center, stars around the border. "
        "Bold text 'AMERICA' at top of badge, 'EST. 1776' at bottom. "
        "Distressed aged texture, red white and blue Americana stamp style. "
        "Pure white background. DTG print ready."
    ),
    "patrick henry give me liberty or give me coffee": (
        "Vintage t-shirt graphic. Illustrated Patrick Henry at a podium, dramatic expression, "
        "pointing finger, holding a coffee cup instead of a torch. Colonial setting. "
        "Bold distressed text: 'GIVE ME LIBERTY OR GIVE ME COFFEE'. "
        "Pure white background. DTG print ready."
    ),
    "george washington first in war first in peace first in swag": (
        "Vintage t-shirt graphic. Cool portrait of George Washington in colonial uniform "
        "wearing sunglasses, relaxed confident pose. Bold text: "
        "'FIRST IN WAR. FIRST IN PEACE. FIRST IN SWAG.' Stars and flag accents, "
        "vintage red white blue. Pure white background. DTG print ready."
    ),
    "America 250th birthday 1776 2026": (
        "Patriotic vintage t-shirt graphic celebrating America's 250th birthday. "
        "Majestic bald eagle with wings spread, surrounded by stars and fireworks. "
        "Bold text: '250 YEARS' at top, '1776 - 2026' below. Vintage Americana style, "
        "distressed textures, red white blue. Pure white background. DTG print ready."
    ),
    "250 years of freedom 1776 2026": (
        "Bold patriotic vintage t-shirt typography design. Large distressed text "
        "'250 YEARS OF FREEDOM' as centerpiece. '1776 - 2026' in vintage stamp style below. "
        "Stars, stripes, eagle silhouette as accents. Aged Americana aesthetic, red white blue. "
        "Pure white background. DTG print ready."
    ),
    "party like its 1776": (
        "Fun vintage t-shirt graphic. Founding fathers — Washington, Franklin, Jefferson — "
        "with powdered wigs askew, holding drinks, celebrating wildly. "
        "Bold handwritten text: 'PARTY LIKE IT'S 1776' at bottom. "
        "Pure white background. DTG print ready."
    ),
    "its only treason if you lose": (
        "Bold vintage t-shirt typographic design. Large distressed text "
        "'IT'S ONLY TREASON IF YOU LOSE' as the main statement. "
        "Eagle silhouette and stars as accents, aged vintage style. "
        "Red white blue distressed fonts. Pure white background. DTG print ready."
    ),
}

_FALLBACK_PROMPT = (
    "Viral Etsy best-seller vintage t-shirt graphic design. Theme: {theme}. "
    "Founding fathers humor style — Washington, Franklin, Jefferson, Hamilton in humorous modern situations. "
    "Colonial attire with modern accessories like sunglasses. Bold distressed typography. "
    "Red white and blue color palette, aged vintage Americana aesthetic. "
    "Pure white background. DTG print ready."
)


def _remove_white_background(image_bytes: bytes, threshold: int = 240) -> bytes:
    """Replace near-white pixels with transparency."""
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
    """Generate design via Ideogram v2 with text baked in, save transparent PNG."""
    settings = get_settings()
    prompt = _PROMPTS.get(keyword) or _FALLBACK_PROMPT.format(theme=keyword)
    log.info("Generating design for %r via Ideogram v2", keyword)

    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            f"{_IDEOGRAM_BASE}/generate",
            headers={
                "Api-Key": settings.ideogram_api_key,
                "Content-Type": "application/json",
            },
            json={
                "image_request": {
                    "prompt": prompt,
                    "model": "V_2",
                    "style_type": "DESIGN",
                    "aspect_ratio": "ASPECT_1_1",
                    "magic_prompt_option": "OFF",
                }
            },
        )
        if not r.is_success:
            log.error("Ideogram error: %s %s", r.status_code, r.text)
        r.raise_for_status()

    image_url: str = r.json()["data"][0]["url"]
    log.info("Ideogram image URL: %s", image_url)

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
    log.info("Design saved → %s", dest)
    return dest
