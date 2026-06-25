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
    " Vintage worn screen-print style. Exaggerated caricature illustration — big expressive faces, "
    "bold outlines, slightly cartoonish but detailed. Each person must look distinctly different. "
    "Limited color palette: navy blue, red, cream/off-white only. "
    "Aged ink texture, distressed halftone grain, slightly faded like a well-loved vintage tee. "
    "NO photorealism, NO gradients, NO drop shadows. "
    "SOLID WHITE (#FFFFFF) background only."
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
        "Vintage sports poster t-shirt graphic. Caricature illustration of five wildly different founding fathers "
        "in USA Basketball jerseys: Washington center with enormous tall powdered wig and aviator shades, "
        "chubby round-faced Adams far left with tiny glasses, tall lanky red-haired Jefferson, "
        "bald-on-top wispy-haired pot-bellied Franklin with bifocals, young sharp-jawed Hamilton far right. "
        "Each face exaggerated and immediately distinct. Posed like a championship team photo. "
        "Bold distressed text: 'DREAM TEAM' arched at top, 'OF 1776' below with stars."
    ),
    "ben drankin benjamin franklin fourth of july": (
        "Vintage t-shirt graphic. Caricature of Benjamin Franklin — bald on top with long wispy white hair "
        "on the sides, round chubby face, double chin, big nose, wide grin. "
        "Wearing American flag aviator sunglasses and a stars-and-stripes headband, "
        "holding up a glass of whiskey triumphantly. "
        "Bold distressed varsity text: 'BEN' arched at top in navy with stars, 'DRANKIN' large at bottom in red."
    ),
    "1776 national champs founding fathers": (
        "Vintage championship t-shirt graphic. Caricature illustration of five founding fathers "
        "all wearing black sunglasses: Washington center with massive tall wig, stern square jaw, "
        "short round Adams far left, lanky red-haired Jefferson, pot-bellied bald Franklin with side hair, "
        "young chiseled Hamilton far right. All wildly different body types and faces. "
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
        "Vintage t-shirt graphic. Exactly 5 founding fathers caricatures — Washington with huge tall wig and aviators, "
        "tiny round Adams, pot-bellied Franklin with bifocals and wispy side hair, "
        "tall red-haired Jefferson, young sharp-jawed Hamilton. All in colonial attire, different sunglasses, "
        "posed like a modern squad photo, confident and cool. "
        "Bold distressed navy blue text 'SQUAD GOALS' large at top, 'EST. 1776' in red at bottom with stars."
    ),
    "benjamin franklin original founding bro": (
        "Vintage t-shirt graphic. Portrait of a colonial-era statesman with wispy long grey hair "
        "and round spectacles, wearing cool sunglasses, lightning bolt striking dramatically behind him. "
        "NO name text anywhere. Bold distressed retro text: 'ORIGINAL FOUNDING BRO' at bottom. Stars accents."
    ),
    "1776 original bad boys founding fathers": (
        "Vintage movie poster t-shirt graphic. Caricature lineup of five founding fathers, "
        "each wildly different: Washington center with enormous powdered wig and aviator shades, "
        "tiny bowling-ball-headed Adams, lanky stretched-neck Jefferson with red hair, "
        "pot-bellied bald-on-top Franklin with round bifocals, boyish-faced Hamilton. "
        "All wearing different sunglasses, stone-cold tough expressions like an action movie. "
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
        "Vintage t-shirt graphic. Clean detailed illustration of a colonial-era statesman "
        "with a sharp well-defined face, powdered wig, holding up a modern coffee cup triumphantly. "
        "Clear facial features, not distorted. Red circle behind the figure. "
        "Bold distressed vintage text: 'GIVE ME LIBERTY' at top, 'OR GIVE ME COFFEE' at bottom, 'COFFEE' largest in red."
    ),
    "george washington first in war first in peace first in swag": (
        "Vintage t-shirt graphic. Bold portrait of George Washington in colonial uniform "
        "wearing aviator sunglasses, confident pose, stars on each side. "
        "Three lines of bold distressed text only at bottom, no other text anywhere: "
        "Line 1: 'FIRST IN WAR.' Line 2: 'FIRST IN PEACE.' Line 3: 'FIRST IN SWAG.'"
    ),
    "America 250th birthday 1776 2026": (
        "Vintage patriotic t-shirt graphic. NO people, NO faces, NO portraits anywhere. "
        "Only a majestic bald eagle with wings fully spread, American flag shield on chest, "
        "burst of rays behind it, stars scattered around. "
        "Bold distressed collegiate text '250 YEARS' at top in navy with red outline. "
        "'1776 - 2026' in distressed text at bottom with stars on each side."
    ),
    "250 years of freedom 1776 2026": (
        "Vintage typographic t-shirt design. Large distressed text '250 YEARS OF FREEDOM' "
        "as centerpiece. '1776 - 2026' in aged stamp style below. "
        "Stars, stripes, eagle silhouette as accents."
    ),
    "party like its 1776": (
        "Vintage t-shirt graphic. Caricature of three founding fathers partying wildly — "
        "Washington with his massive wig tilted sideways holding a beer, "
        "pot-bellied Franklin with bifocals askew raising a whiskey glass, "
        "tall lanky red-haired Jefferson dancing. All with huge grins and exaggerated expressions. "
        "Bold distressed text in navy blue at top: 'PARTY LIKE', 'IT\\'S 1776' in large red at bottom."
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


def _remove_green_background(image_bytes: bytes, threshold: int = 15) -> bytes:
    """Sample corner color and remove only pixels very close to it."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    w, h = img.size

    # Sample corners to detect background color
    corners = [
        img.getpixel((0, 0))[:3],
        img.getpixel((w - 1, 0))[:3],
        img.getpixel((0, h - 1))[:3],
        img.getpixel((w - 1, h - 1))[:3],
    ]
    bg_r = int(sum(c[0] for c in corners) / 4)
    bg_g = int(sum(c[1] for c in corners) / 4)
    bg_b = int(sum(c[2] for c in corners) / 4)
    log.info("Detected background color: rgb(%d,%d,%d)", bg_r, bg_g, bg_b)

    data = img.getdata()
    new_data = []
    for r, g, b, a in data:
        if abs(r - bg_r) <= threshold and abs(g - bg_g) <= threshold and abs(b - bg_b) <= threshold:
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

    log.info("Removing background for %r", keyword)
    transparent_bytes = _remove_green_background(image_bytes)

    filename = f"{_slugify(keyword)}_{int(time.time())}.png"
    dest = out_dir / filename
    dest.write_bytes(transparent_bytes)
    log.info("Design saved → %s", dest)
    return dest
