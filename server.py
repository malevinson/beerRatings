"""Local API server that proxies OpenAI calls for the mobile app.

Run with:  uvicorn server:app --host 0.0.0.0 --port 8888
"""

import base64
import io
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException
from openai import OpenAI
from PIL import Image as PILImage, ImageDraw, ImageFont, ImageOps
from pydantic import BaseModel

# Load .env from project root
load_dotenv(Path(__file__).resolve().parent / ".env")

from src.beerratingsmenuocr.models import (
    MenuAnalysis,
    BeerIdentification,
    BeerRating,
    BeerRatingsResult,
    make_strict_schema,
)

# ── Prompts ──────────────────────────────────────────────────────

MENU_ANALYSIS_SYSTEM_PROMPT = """\
You are an expert beer menu reader and OCR system.

Your task: Given a photograph of a beer menu, tap list, beer board, or beer
list, identify EVERY beer shown on the menu.

Instructions:
- Read the menu carefully. Extract the name of each beer.
- If the brewery name is visible, include it.
- If style information is shown (IPA, Stout, Lager, etc.), include it.
- If ABV is shown, include it.
- If price is shown, include it.
- For each beer, estimate its approximate vertical position on the menu as a
  fraction from 0.0 (very top of the image) to 1.0 (very bottom). This helps
  us annotate the original photo. Set the y_position field for each beer.
- Do NOT guess or invent beers that are not visible.
- If the image is blurry or some text is unreadable, do your best and note
  uncertainty in the beer name (e.g., append "[unclear]").
- If the image does not appear to be a beer menu at all, return an empty
  beers list and explain in menu_notes.

Be thorough. It is better to include a beer you are uncertain about (and
flag it) than to miss one."""

RATINGS_LOOKUP_SYSTEM_PROMPT = """\
You are a knowledgeable beer expert with deep knowledge of craft beer,
beer ratings, and brewing.

Your task: For each beer provided, supply detailed information including:
- The correct brewery (confirm or identify if not provided)
- The beer style
- Approximate ABV
- An approximate Untappd rating (0.0-5.0 scale)
- An approximate BeerAdvocate score (0-100 scale)
- A short, appealing 1-2 sentence description of the beer

Important guidelines:
- Use your training knowledge to provide approximate ratings. These do NOT
  need to be exact -- approximate is fine and expected.
- If you recognize the beer, provide your best estimate of its community
  ratings.
- If you do NOT recognize a specific beer, try to identify the brewery and
  style, and provide a reasonable rating estimate based on the brewery's
  reputation and the style.
- Set confidence to "high" if you are confident in the identification,
  "medium" if you are somewhat sure, and "low" if you are guessing.
- For ABV, provide your best estimate if not already known from the menu.
- Never fabricate a rating for a beer you cannot identify at all -- set
  ratings to null and confidence to "low" in that case.
- Ratings should reflect the general community consensus, not personal
  opinion."""


# ── Image annotation ─────────────────────────────────────────────

def _get_font(size: int) -> ImageFont.FreeTypeFont:
    """Try to load a readable font, falling back to PIL default."""
    for name in [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSText.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "Arial",
    ]:
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default(size=size)


def annotate_image(
    image_data: bytes,
    ocr_beers: list[BeerIdentification],
    rated_beers: list[BeerRating],
) -> str:
    """Draw rating annotations on the menu image. Returns base64 JPEG."""
    img = PILImage.open(io.BytesIO(image_data))
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")

    # Use RGBA overlay so we can draw semi-transparent backgrounds
    overlay = PILImage.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    width, height = img.size
    font_size = max(18, height // 30)
    font = _get_font(font_size)

    for i, rated in enumerate(rated_beers):
        # Get y position from OCR data (fall back to even spacing)
        if i < len(ocr_beers) and ocr_beers[i].y_position is not None:
            y_frac = ocr_beers[i].y_position
        else:
            y_frac = (i + 0.5) / max(len(rated_beers), 1)

        # Build rating label
        parts = []
        if rated.rating_beer_advocate is not None:
            parts.append(f"BA:{rated.rating_beer_advocate}")
        if rated.rating_untappd is not None:
            parts.append(f"\u2605{rated.rating_untappd:.1f}")
        if not parts:
            continue

        text = " ".join(parts)
        y = int(y_frac * height)

        # Measure text
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = width - tw - 15
        # Keep within image bounds
        y = max(5, min(y - th // 2, height - th - 5))

        # Draw semi-transparent dark background pill
        pad = 4
        draw.rounded_rectangle(
            [x - pad, y - pad, x + tw + pad, y + th + pad],
            radius=6,
            fill=(0, 0, 0, 180),
        )

        # Draw red text
        draw.text((x, y), text, fill=(255, 50, 50, 255), font=font)

    # Composite overlay onto original image
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    img = PILImage.alpha_composite(img, overlay)
    img = img.convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


# ── FastAPI app ──────────────────────────────────────────────────

app = FastAPI(title="Beer Menu Scanner API")

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
MODEL = "gpt-4o"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze")
async def analyze_menu(image: UploadFile = File(...)):
    """Accept a menu image, return identified + rated beers in one call."""
    image_data = await image.read()
    base64_image = base64.b64encode(image_data).decode("utf-8")

    # Detect mime type from filename
    ext = (image.filename or "image.png").rsplit(".", 1)[-1].lower()
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "webp": "image/webp", "heic": "image/heic"}.get(ext, "image/png")

    try:
        # Step 1: Vision OCR — identify beers
        ocr_resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": MENU_ANALYSIS_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Please analyze this beer menu image and identify every beer listed.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{base64_image}"},
                        },
                    ],
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "menu_analysis",
                    "strict": True,
                    "schema": make_strict_schema(MenuAnalysis),
                },
            },
            max_tokens=4096,
        )

        menu = MenuAnalysis.model_validate_json(ocr_resp.choices[0].message.content)

        if not menu.beers:
            return {"beers": [], "menu_notes": menu.menu_notes}

        # Step 2: Ratings lookup
        beer_lines = []
        for i, b in enumerate(menu.beers, 1):
            parts = [f"{i}. {b.name}"]
            if b.brewery:
                parts.append(f"   Brewery: {b.brewery}")
            if b.style_hint:
                parts.append(f"   Style: {b.style_hint}")
            if b.abv_on_menu:
                parts.append(f"   ABV: {b.abv_on_menu}")
            beer_lines.append("\n".join(parts))

        ratings_resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": RATINGS_LOOKUP_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Please provide ratings and details for these "
                        f"{len(menu.beers)} beers from a menu I just scanned:\n\n"
                        + "\n\n".join(beer_lines)
                    ),
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "beer_ratings_result",
                    "strict": True,
                    "schema": make_strict_schema(BeerRatingsResult),
                },
            },
            max_tokens=4096,
        )

        result = BeerRatingsResult.model_validate_json(
            ratings_resp.choices[0].message.content
        )

        # Step 3: Annotate the original image with ratings
        annotated_b64 = None
        try:
            annotated_b64 = annotate_image(image_data, menu.beers, result.beers)
        except Exception as ann_err:
            logger.exception("Image annotation failed: %s", ann_err)

        return {
            "beers": [b.model_dump() for b in result.beers],
            "menu_notes": menu.menu_notes,
            "annotated_image": annotated_b64,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
