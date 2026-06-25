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

# Shared style suffix appended to every prompt
_STYLE = (
    " Vintage worn screen-print style. Limited color palette: navy blue, red, cream/off-white. "
    "Aged ink texture, distressed halftone grain, slightly faded like a well-loved vintage tee. "
    "NO bright colors, NO gradients, NO blue brushstroke backgrounds, NO drop shadows. "
    "Pure white background. DTG print ready."
)

# ---------------------------------------------------------------------------
# Prompts — art + text, style applied via _STYLE suffix
# ---------------------------------------------------------------------------
_PROMPTS: dict[str, str] = {
    "wtf is a kilometer bald eagle": (
        "Vintage t-shirt graphic. Detailed ink illustration of a bald eagle head "
        "with flowing white feathers styled like a colonial wig, wearing red American flag "
        "wayfarer sunglasses with stars on the lenses. "
        "Bold distressed varsity text 'WTF IS A' arched at top in navy, "
        "'KILOMETER?' large below in red. Crosshatch engraving style."
    ),
    "dream team of 1776 founding fathers basketball": (
        "Vintage sports poster t-shirt graphic. Five distinctly different founding fathers "
        "wearing USA Basketball jerseys, each with unique recognizable faces: "
        "George Washington center with tall powdered wig and aviator sunglasses, "
        "Benjamin Franklin left with wispy long hair and round Ben Franklin glasses, "
        "Thomas Jefferson with reddish swept-back hair and cool shades, "
        "Alexander Hamilton far right young and sharp-featured with dark sunglasses, "
        "John Adams far left short stout round face with tinted glasses. "
        "All five clearly different people, posed like a team photo. "
        "Bold distressed text arched at top: 'DREAM TEAM', 'OF 1776' below with stars."
    ),
    "ben drankin benjamin franklin fourth of july": (
        "Vintage t-shirt graphic. Illustrated Benjamin Franklin wearing American flag "
        "aviator sunglasses and a stars-and-stripes headband, holding up a glass of whiskey "
        "with a wide grin. "
        "Bold distressed varsity text: 'BEN' arched at top, 'DRANKIN' large at bottom with stars."
    ),
    "1776 national champs founding fathers": (
        "Vintage championship t-shirt graphic. Five different founding fathers — "
        "George Washington center, Benjamin Franklin, Thomas Jefferson, John Adams, Alexander Hamilton — "
        "each with distinct faces and hairstyles, all wearing cool black sunglasses, "
        "posed like a championship team photo. "
        "Bold distressed collegiate text: '1776 NATIONAL CHAMPS' arched at top, 'FOUNDING FATHERS' at bottom with eagle."
    ),
    "its only treason if you lose george washington": (
        "Vintage t-shirt graphic. George Washington in colonial military uniform, wearing aviator "
        "sunglasses, striding confidently with fireworks bursting behind him. Action hero pose. "
        "Bold distressed text at bottom: 'IT\\'S ONLY TREASON IF YOU LOSE'."
    ),
    "george washington crossing the delaware sunglasses": (
        "Vintage t-shirt graphic. George Washington standing boldly at the front of a rowboat "
        "crossing an icy river, wearing aviator sunglasses, flag waving dramatically behind him. "
        "Bold distressed text at bottom: 'UNBOTHERED'."
    ),
    "founding fathers fourth of july squad goals": (
        "Vintage t-shirt graphic. Group portrait of Washington, Franklin, Jefferson, Hamilton, and Adams "
        "all wearing sunglasses, posed confidently like a modern friend squad. "
        "Bold distressed text: 'SQUAD GOALS' arched at top, 'EST. 1776' at bottom with stars."
    ),
    "benjamin franklin original founding bro": (
        "Vintage t-shirt graphic. Portrait of Benjamin Franklin looking cool and confident "
        "wearing sunglasses, lightning bolt striking in background. "
        "Bold distressed retro text at bottom: 'ORIGINAL FOUNDING BRO'. Stars accents."
    ),
    "1776 original bad boys founding fathers": (
        "Vintage movie poster t-shirt graphic. Lineup of exactly five distinctly different founding fathers "
        "side by side in colonial attire, each with a unique face and hairstyle: "
        "George Washington with tall powdered wig, Benjamin Franklin with long wispy hair and round face, "
        "Thomas Jefferson with reddish hair, Alexander Hamilton young and sharp-faced, "
        "John Adams short and stout with a round face. All five wearing different style sunglasses, "
        "tough serious expressions like an action movie poster. "
        "Bold distressed text: 'ORIGINAL BAD BOYS' at top, large '1776' at bottom."
    ),
    "we the people fourth of july founding fathers": (
        "Vintage typographic t-shirt design. Large distressed varsity text 'WE THE PEOPLE' "
        "as centerpiece. Bold eagle silhouette, stars, and 'EST. 1776' below as accents. "
        "Aged parchment ink texture feel."
    ),
    "america est 1776 founding fathers vintage": (
        "Vintage circular badge t-shirt design. Eagle at center with wings spread, stars around the border. "
        "Bold distressed text 'AMERICA' arched at top of badge, 'EST. 1776' at bottom. "
        "Classic Americana stamp style, aged ink texture."
    ),
    "patrick henry give me liberty or give me coffee": (
        "Vintage t-shirt graphic. Illustrated Patrick Henry at a podium, dramatic pointing finger, "
        "holding a coffee cup instead of a torch. "
        "Bold distressed vintage text: 'GIVE ME LIBERTY' at top, 'OR GIVE ME COFFEE' at bottom."
    ),
    "george washington first in war first in peace first in swag": (
        "Vintage t-shirt graphic. Cool portrait of George Washington in colonial uniform "
        "wearing sunglasses, relaxed confident pose. Stars and flag accents. "
        "Bold distressed text: 'FIRST IN WAR. FIRST IN PEACE. FIRST IN SWAG.' at bottom."
    ),
    "America 250th birthday 1776 2026": (
        "Vintage patriotic t-shirt graphic celebrating America's 250th birthday. "
        "Majestic bald eagle with wings spread, surrounded by stars and burst rays. "
        "Bold distressed text: '250 YEARS' arched at top, '1776 - 2026' at bottom."
    ),
    "250 years of freedom 1776 2026": (
        "Vintage typographic t-shirt design. Large distressed text '250 YEARS OF FREEDOM' "
        "as centerpiece. '1776 - 2026' in aged stamp style below. "
        "Stars, stripes, eagle silhouette as accents."
    ),
    "party like its 1776": (
        "Vintage t-shirt graphic. Founding fathers — Washington, Franklin, Jefferson — "
        "with powdered wigs askew, holding drinks, celebrating wildly. Fun chaotic energy. "
        "Bold distressed handwritten text at bottom: 'PARTY LIKE IT\\'S 1776'."
    ),
    "its only treason if you lose": (
        "Vintage typographic t-shirt design. Large distressed aged text "
        "'IT\\'S ONLY TREASON IF YOU LOSE' as the bold main statement. "
        "Eagle silhouette and stars as accents."
    ),
}

_FALLBACK_PROMPT = (
    "Vintage worn screen-print t-shirt graphic. Founding fathers humor theme: {theme}. "
    "Washington, Franklin, Jefferson, Hamilton in humorous modern situations, colonial attire "
    "with modern accessories like sunglasses. Bold distressed typography. "
    "Limited color palette: navy blue, red, cream. Aged ink texture. Pure white background."
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
    base = _PROMPTS.get(keyword) or _FALLBACK_PROMPT.format(theme=keyword)
    prompt = base + _STYLE
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
