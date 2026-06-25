"""Generate t-shirt artwork via Recraft and overlay text with Pillow."""
from __future__ import annotations

import logging
import re
import tempfile
import time
from pathlib import Path
import io

import httpx
from PIL import Image, ImageDraw, ImageFont

from .config import get_settings

log = logging.getLogger(__name__)

_RECRAFT_BASE = "https://external.api.recraft.ai/v1"
_FONTS_DIR = Path("/app/fonts")
_FALLBACK_FONT = None  # PIL built-in

# Appended to every art prompt — Recraft must not render any text
_NO_TEXT = (
    " NO text, NO words, NO letters, NO numbers, NO typography, NO captions anywhere in the image."
)

# ---------------------------------------------------------------------------
# Art prompts — pure visual art only, text added by Pillow afterward
# ---------------------------------------------------------------------------
_ART_PROMPTS: dict[str, str] = {
    "wtf is a kilometer bald eagle": (
        "Detailed ink illustration of a bald eagle head with flowing white feathers styled like a colonial wig, "
        "wearing red American flag wayfarer sunglasses with stars and stripes on the lenses. "
        "Vintage engraving crosshatch style, high contrast black and white with red and blue accents. "
        "Pure white background. DTG t-shirt print ready."
    ),
    "dream team of 1776 founding fathers basketball": (
        "Illustrated portrait of five founding fathers — George Washington center, Benjamin Franklin, "
        "Thomas Jefferson, John Adams, Alexander Hamilton — wearing USA Basketball jerseys red white blue. "
        "Vintage sports poster style, detailed illustration. Pure white background. DTG t-shirt print ready."
    ),
    "ben drankin benjamin franklin fourth of july": (
        "Vintage illustrated portrait of Benjamin Franklin wearing American flag aviator sunglasses "
        "and a red stars-and-stripes headband, holding up a glass of whiskey with a grin. "
        "Distressed American flag in the background. Red white and blue. Pure white background. DTG t-shirt print ready."
    ),
    "1776 national champs founding fathers": (
        "Illustrated group of six founding fathers in colonial uniforms all wearing cool black sunglasses, "
        "posed like a championship team photo. George Washington front and center, confident poses. "
        "Eagle crest badge. Slate blue vintage style. Pure white background. DTG t-shirt print ready."
    ),
    "its only treason if you lose george washington": (
        "Illustrated George Washington in full colonial military uniform, wearing aviator sunglasses, "
        "walking confidently with fireworks exploding dramatically behind him. Action hero composition. "
        "Pure white background. DTG t-shirt print ready."
    ),
    "george washington crossing the delaware sunglasses": (
        "Dramatic illustrated scene of George Washington standing boldly at the front of a boat "
        "crossing a river, wearing aviator sunglasses, American flag waving behind him. "
        "Epic cinematic composition, red white and blue. Pure white background. DTG t-shirt print ready."
    ),
    "founding fathers fourth of july squad goals": (
        "Illustrated group portrait of Washington, Franklin, Jefferson, Hamilton, and Adams "
        "all wearing sunglasses, posed like a modern squad photo. Casual confident energy. "
        "Red white and blue vintage style. Pure white background. DTG t-shirt print ready."
    ),
    "benjamin franklin original founding bro": (
        "Vintage illustrated portrait of Benjamin Franklin looking cool and confident, "
        "wearing sunglasses, lightning bolt in background referencing his electricity discovery. "
        "Stars and stripes accents. Pure white background. DTG t-shirt print ready."
    ),
    "1776 original bad boys founding fathers": (
        "Illustrated movie-poster style lineup of five founding fathers in colonial attire "
        "all wearing sunglasses, serious tough expressions like a police lineup. "
        "High contrast black white red blue. Pure white background. DTG t-shirt print ready."
    ),
    "we the people fourth of july founding fathers": (
        "Bold eagle silhouette with stars and stripes, aged parchment texture aesthetic. "
        "Red white and blue. Pure white background. DTG t-shirt print ready."
    ),
    "america est 1776 founding fathers vintage": (
        "Vintage circular badge design with an eagle at center, stars around the border. "
        "Distressed aged texture, red white and blue, classic Americana stamp style. "
        "Pure white background. DTG t-shirt print ready."
    ),
    "patrick henry give me liberty or give me coffee": (
        "Illustrated portrait of Patrick Henry at a podium, dramatic expression, pointing finger, "
        "holding a coffee cup instead of a torch. Colonial setting with dramatic lighting. "
        "Pure white background. DTG t-shirt print ready."
    ),
    "george washington first in war first in peace first in swag": (
        "Cool illustrated portrait of George Washington in colonial uniform wearing sunglasses, "
        "relaxed confident pose. Stars and flag accents, vintage red white blue. "
        "Pure white background. DTG t-shirt print ready."
    ),
    "America 250th birthday 1776 2026": (
        "Stunning patriotic graphic — majestic bald eagle at center with wings spread, "
        "surrounded by stars and fireworks. Vintage Americana style, "
        "distressed textures, red white blue. Pure white background. DTG print ready."
    ),
    "250 years of freedom 1776 2026": (
        "Bold patriotic eagle silhouette with stars, stripes, aged vintage Americana aesthetic. "
        "Red white blue distressed style. Pure white background. DTG print ready."
    ),
    "party like its 1776": (
        "Illustrated founding fathers — Washington, Franklin, Jefferson — with "
        "powdered wigs askew, holding drinks, celebrating. Fun chaotic party energy. "
        "Pure white background. DTG t-shirt print ready."
    ),
    "its only treason if you lose": (
        "Eagle silhouette and stars as accents, aged vintage distressed style. "
        "Red white blue. Pure white background. DTG t-shirt print ready."
    ),
}

_FALLBACK_ART_PROMPT = (
    "Vintage illustrated founding fathers humor graphic — Washington, Franklin, Jefferson, Hamilton "
    "in humorous modern situations. Colonial attire with modern accessories like sunglasses. "
    "Red white and blue color palette, aged vintage Americana aesthetic. "
    "Pure white background. DTG t-shirt print ready. Theme: {theme}."
)

# ---------------------------------------------------------------------------
# Text to overlay on each design (top_line, bottom_line, style)
# style: "badge" | "top_bottom" | "bottom_only" | "top_only"
# ---------------------------------------------------------------------------
_DESIGN_TEXT: dict[str, dict] = {
    "wtf is a kilometer bald eagle": {
        "top": "WTF IS A",
        "bottom": "KILOMETER?",
        "style": "top_bottom",
    },
    "dream team of 1776 founding fathers basketball": {
        "top": "DREAM TEAM",
        "bottom": "OF 1776",
        "style": "top_bottom",
    },
    "ben drankin benjamin franklin fourth of july": {
        "top": "BEN",
        "bottom": "DRANKIN",
        "style": "top_bottom",
    },
    "1776 national champs founding fathers": {
        "top": "1776 NATIONAL CHAMPS",
        "bottom": "EST. 1776",
        "style": "top_bottom",
    },
    "its only treason if you lose george washington": {
        "bottom": "IT'S ONLY TREASON IF YOU LOSE",
        "style": "bottom_only",
    },
    "george washington crossing the delaware sunglasses": {
        "bottom": "UNBOTHERED",
        "style": "bottom_only",
    },
    "founding fathers fourth of july squad goals": {
        "top": "SQUAD GOALS",
        "bottom": "EST. 1776",
        "style": "top_bottom",
    },
    "benjamin franklin original founding bro": {
        "bottom": "ORIGINAL FOUNDING BRO",
        "style": "bottom_only",
    },
    "1776 original bad boys founding fathers": {
        "top": "ORIGINAL BAD BOYS",
        "bottom": "1776",
        "style": "top_bottom",
    },
    "we the people fourth of july founding fathers": {
        "top": "WE THE PEOPLE",
        "bottom": "EST. 1776",
        "style": "top_bottom",
    },
    "america est 1776 founding fathers vintage": {
        "top": "AMERICA",
        "bottom": "EST. 1776",
        "style": "top_bottom",
    },
    "patrick henry give me liberty or give me coffee": {
        "bottom": "GIVE ME LIBERTY OR GIVE ME COFFEE",
        "style": "bottom_only",
    },
    "george washington first in war first in peace first in swag": {
        "bottom": "FIRST IN WAR. FIRST IN PEACE. FIRST IN SWAG.",
        "style": "bottom_only",
    },
    "America 250th birthday 1776 2026": {
        "top": "250 YEARS",
        "bottom": "1776 - 2026",
        "style": "top_bottom",
    },
    "250 years of freedom 1776 2026": {
        "top": "250 YEARS OF FREEDOM",
        "bottom": "1776 - 2026",
        "style": "top_bottom",
    },
    "party like its 1776": {
        "bottom": "PARTY LIKE IT'S 1776",
        "style": "bottom_only",
    },
    "its only treason if you lose": {
        "bottom": "IT'S ONLY TREASON IF YOU LOSE",
        "style": "bottom_only",
    },
}


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    # Try bundled fonts first, then system fonts, then Pillow built-in
    search = [
        _FONTS_DIR / "Anton-Regular.ttf",
        _FONTS_DIR / "Oswald-Bold.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    ]
    for path in search:
        if path.exists():
            try:
                font = ImageFont.truetype(str(path), size)
                log.info("Loaded font: %s @ %dpx", path.name, size)
                return font
            except Exception as e:
                log.warning("Failed to load font %s: %s", path, e)
    # Pillow 10+ supports size on load_default
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _text_size(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _overlay_text(image_bytes: bytes, keyword: str) -> bytes:
    """Expand canvas and draw text above/below the art — art is never cropped."""
    text_cfg = _DESIGN_TEXT.get(keyword)
    if not text_cfg:
        return image_bytes

    art = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    w, h = art.size

    top_text = text_cfg.get("top", "")
    bottom_text = text_cfg.get("bottom", "")
    style = text_cfg.get("style", "bottom_only")

    band_h = int(h * 0.14)
    has_top = style in ("top_bottom", "top_only") and top_text
    has_bottom = style in ("top_bottom", "bottom_only") and bottom_text

    total_h = h + (band_h if has_top else 0) + (band_h if has_bottom else 0)
    canvas = Image.new("RGBA", (w, total_h), (255, 255, 255, 0))

    art_y = band_h if has_top else 0
    canvas.paste(art, (0, art_y))

    draw = ImageDraw.Draw(canvas)
    navy = (15, 35, 90, 255)
    red = (180, 20, 20, 255)
    white = (255, 255, 255, 255)

    def draw_band(text: str, y: int, bg: tuple):
        # Fill band
        draw.rectangle([(0, y), (w, y + band_h)], fill=bg)

        font_size = int(band_h * 0.55)
        font = _load_font(font_size)
        tw, th = _text_size(draw, text, font)
        while tw > w * 0.88 and font_size > 14:
            font_size -= 2
            font = _load_font(font_size)
            tw, th = _text_size(draw, text, font)

        tx = (w - tw) // 2
        ty = y + (band_h - th) // 2
        # Shadow
        draw.text((tx + 2, ty + 2), text, font=font, fill=(0, 0, 0, 160))
        # Text
        draw.text((tx, ty), text, font=font, fill=white)

    if has_top:
        draw_band(top_text, 0, navy)
    if has_bottom:
        draw_band(bottom_text, art_y + h, red)

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


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
    """Generate design via Recraft, overlay text with Pillow, save transparent PNG."""
    settings = get_settings()
    prompt = (_ART_PROMPTS.get(keyword) or _FALLBACK_ART_PROMPT.format(theme=keyword)) + _NO_TEXT
    log.info("Generating design for %r via Recraft", keyword)

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
    log.info("Recraft image URL: %s", image_url)

    async with httpx.AsyncClient(timeout=60) as client:
        img_r = await client.get(image_url)
        img_r.raise_for_status()
    image_bytes = img_r.content

    if out_dir is None:
        out_dir = Path(tempfile.mkdtemp(prefix="autobot_designs_"))
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("Removing white background for %r", keyword)
    transparent_bytes = _remove_white_background(image_bytes)

    log.info("Overlaying text for %r", keyword)
    final_bytes = _overlay_text(transparent_bytes, keyword)

    filename = f"{_slugify(keyword)}_{int(time.time())}.png"
    dest = out_dir / filename
    dest.write_bytes(final_bytes)
    log.info("Design saved → %s", dest)
    return dest
