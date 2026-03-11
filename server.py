"""API server that proxies OpenAI calls for the BeerRated mobile app.

Local dev:   uvicorn server:app --host 0.0.0.0 --port 8888
Production:  deployed via Procfile (Railway / Render / Fly.io)
"""

import base64
import io
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from openai import OpenAI
from PIL import Image as PILImage, ImageDraw, ImageFont, ImageOps
from pydantic import BaseModel
from typing import Optional

# Load .env from project root
load_dotenv(Path(__file__).resolve().parent / ".env")

from src.beerratingsmenuocr.models import (
    MenuAnalysis,
    BeerIdentification,
    BeerRating,
    BeerRatingsResult,
    BeerQuickRatingsResult,
    BeerDetailsResult,
    make_strict_schema,
)

# ── Prompts ──────────────────────────────────────────────────────

MENU_ANALYSIS_SYSTEM_PROMPT = """\
You are an expert beer menu reader. Given a photo of a beer menu, tap list,
or beer board, identify every beer shown.

For each beer extract: name, brewery (if visible), style (if shown), ABV
(if shown), and price (if shown). If text is unclear, append "[unclear]".
Do not invent beers. If the image is not a beer menu, return an empty list
with an explanation in menu_notes."""

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
  opinion.
- For brand_colors, provide 2-3 hex color codes representing the beer's
  bottle, can, or brand packaging colors. If unsure about the specific
  beer, use the brewery's brand palette instead."""


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
    """Draw numbered markers on the menu image. Returns base64 JPEG.

    Each beer gets a numbered circle placed at its approximate vertical
    position along the right edge. Numbers match the beer cards in the list.
    """
    img = PILImage.open(io.BytesIO(image_data))
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")

    width, height = img.size

    # Beer menus are typically portrait. If still landscape after EXIF
    # correction, rotate 90° counter-clockwise.
    if width > height * 1.3:
        img = img.rotate(90, expand=True)
        width, height = img.size

    overlay = PILImage.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font_size = max(16, height // 35)
    font = _get_font(font_size)

    for i, rated in enumerate(rated_beers):
        if rated.rating_beer_advocate is None:
            continue

        num = str(i + 1)

        # Vertical position from OCR data
        if i < len(ocr_beers) and ocr_beers[i].y_position is not None:
            y_frac = ocr_beers[i].y_position
        else:
            y_frac = (i + 0.5) / max(len(rated_beers), 1)

        y = int(y_frac * height)

        # Measure text for centering inside circle
        bbox = draw.textbbox((0, 0), num, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

        # Place along right edge
        radius = max(tw, th) // 2 + 6
        cx = width - radius - 10
        cy = max(radius + 5, min(y, height - radius - 5))

        # Dark circle background
        draw.ellipse(
            [cx - radius, cy - radius, cx + radius, cy + radius],
            fill=(0, 0, 0, 200),
        )

        # White number centered in circle
        draw.text(
            (cx - tw // 2, cy - th // 2), num,
            fill=(255, 255, 255, 255), font=font,
        )

    if img.mode != "RGBA":
        img = img.convert("RGBA")
    img = PILImage.alpha_composite(img, overlay)
    img = img.convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


# ── FastAPI app ──────────────────────────────────────────────────

app = FastAPI(title="BeerRated API")

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
MODEL = "gpt-4o-mini"         # OCR — supports vision, much faster
RATINGS_MODEL = "gpt-4o-mini"  # Ratings — text-only


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


# ── Incremental endpoints ────────────────────────────────────────


@app.post("/ocr")
async def ocr_menu(image: UploadFile = File(...)):
    """Step 1: Read the menu image and identify beers (no ratings)."""
    image_data = await image.read()
    base64_image = base64.b64encode(image_data).decode("utf-8")

    ext = (image.filename or "image.png").rsplit(".", 1)[-1].lower()
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "webp": "image/webp", "heic": "image/heic"}.get(ext, "image/png")

    try:
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
        return {
            "beers": [b.model_dump() for b in menu.beers],
            "menu_notes": menu.menu_notes,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _stream_ocr_generator(base64_image: str, mime: str):
    """Sync generator that streams beers as NDJSON lines from OpenAI."""
    decoder = json.JSONDecoder()
    buffer = ""
    beers_array_start = -1
    next_parse_pos = -1

    stream = client.chat.completions.create(
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
        stream=True,
    )

    for chunk in stream:
        if not chunk.choices:
            continue
        delta_content = chunk.choices[0].delta.content
        if not delta_content:
            continue
        buffer += delta_content

        # Find the start of the beers array (once)
        if beers_array_start == -1:
            idx = buffer.find('"beers"')
            if idx != -1:
                bracket_idx = buffer.find("[", idx)
                if bracket_idx != -1:
                    beers_array_start = bracket_idx
                    next_parse_pos = bracket_idx + 1

        # Try to extract complete beer objects using raw_decode
        if beers_array_start != -1:
            while next_parse_pos < len(buffer):
                # Skip whitespace and commas
                stripped = buffer[next_parse_pos:].lstrip(" \t\n\r,")
                if not stripped or stripped[0] == "]":
                    break
                adj = len(buffer[next_parse_pos:]) - len(stripped)
                try_pos = next_parse_pos + adj
                if try_pos >= len(buffer) or buffer[try_pos] != "{":
                    break
                try:
                    obj, end_offset = decoder.raw_decode(buffer, try_pos)
                    # Validate with Pydantic model
                    try:
                        BeerIdentification(**obj)
                        yield json.dumps(obj) + "\n"
                    except Exception:
                        pass
                    next_parse_pos = end_offset
                except json.JSONDecodeError:
                    break  # incomplete object, wait for more data

    # Stream complete — extract menu_notes from the full JSON
    menu_notes = None
    try:
        full = json.loads(buffer)
        menu_notes = full.get("menu_notes")
    except Exception:
        pass

    yield json.dumps({"_done": True, "menu_notes": menu_notes}) + "\n"


@app.post("/ocr-stream")
async def ocr_menu_stream(image: UploadFile = File(...)):
    """Stream OCR results as NDJSON — one beer per line, then a _done line."""
    image_data = await image.read()
    base64_image = base64.b64encode(image_data).decode("utf-8")

    ext = (image.filename or "image.png").rsplit(".", 1)[-1].lower()
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "webp": "image/webp", "heic": "image/heic"}.get(ext, "image/png")

    return StreamingResponse(
        _stream_ocr_generator(base64_image, mime),
        media_type="application/x-ndjson",
    )


class BeerRateRequest(BaseModel):
    name: str
    brewery: Optional[str] = None
    style_hint: Optional[str] = None
    abv: Optional[str] = None


@app.post("/rate")
async def rate_beer(request: BeerRateRequest):
    """Step 2: Get rating + details for a single beer."""
    parts = [f"1. {request.name}"]
    if request.brewery:
        parts.append(f"   Brewery: {request.brewery}")
    if request.style_hint:
        parts.append(f"   Style: {request.style_hint}")
    if request.abv:
        parts.append(f"   ABV: {request.abv}")
    beer_text = "\n".join(parts)

    try:
        resp = client.chat.completions.create(
            model=RATINGS_MODEL,
            messages=[
                {"role": "system", "content": RATINGS_LOOKUP_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Please provide ratings and details for this beer "
                        f"from a menu I just scanned:\n\n{beer_text}"
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
            max_tokens=1024,
        )

        result = BeerRatingsResult.model_validate_json(resp.choices[0].message.content)
        if result.beers:
            return result.beers[0].model_dump()
        raise HTTPException(status_code=500, detail="No rating returned")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


QUICK_RATINGS_SYSTEM_PROMPT = """\
You are a knowledgeable beer expert. For each beer provided, identify:
- The correct brewery name
- An approximate BeerAdvocate score (0-100 scale)
- Confidence: "high" if you recognize it, "medium" if you're somewhat sure, "low" if guessing

Use your training knowledge for approximate ratings. If you don't recognize a beer,
estimate based on the brewery's reputation. Never fabricate — set rating to null
and confidence to "low" if you truly cannot identify the beer."""

DETAILS_SYSTEM_PROMPT = """\
You are a knowledgeable beer expert. For each beer provided, supply:
- Beer style (e.g., New England IPA, Imperial Stout)
- Approximate ABV
- Approximate Untappd rating (0.0-5.0 scale), or null if unknown
- A short, appealing 1-2 sentence description of the beer's flavor profile
- 2-3 hex color codes for the beer's brand/packaging colors (brewery palette or dominant can/bottle colors)

Use your training knowledge. Ratings should reflect community consensus.
If you cannot identify a beer, provide reasonable estimates based on style."""


class BeerBatchRequest(BaseModel):
    beers: list[dict]


@app.post("/rate-batch")
async def rate_beer_batch(request: BeerBatchRequest):
    """Phase 1: Get quick ratings (brewery + BA score) for a batch of beers."""
    beer_lines = []
    for i, b in enumerate(request.beers, 1):
        parts = [f"{i}. {b.get('name', 'Unknown')}"]
        if b.get("brewery"):
            parts.append(f"   Brewery: {b['brewery']}")
        beer_lines.append("\n".join(parts))

    try:
        resp = client.chat.completions.create(
            model=RATINGS_MODEL,
            messages=[
                {"role": "system", "content": QUICK_RATINGS_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Provide quick ratings for these {len(request.beers)} beers "
                        f"from a menu:\n\n" + "\n\n".join(beer_lines)
                    ),
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "beer_quick_ratings_result",
                    "strict": True,
                    "schema": make_strict_schema(BeerQuickRatingsResult),
                },
            },
            max_tokens=1024,
        )

        result = BeerQuickRatingsResult.model_validate_json(
            resp.choices[0].message.content
        )
        return {"beers": [b.model_dump() for b in result.beers]}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/rate-details")
async def rate_beer_details(request: BeerBatchRequest):
    """Phase 2: Get detailed info (style, description, colors) for a batch."""
    beer_lines = []
    for i, b in enumerate(request.beers, 1):
        parts = [f"{i}. {b.get('name', 'Unknown')}"]
        if b.get("brewery"):
            parts.append(f"   Brewery: {b['brewery']}")
        beer_lines.append("\n".join(parts))

    try:
        resp = client.chat.completions.create(
            model=RATINGS_MODEL,
            messages=[
                {"role": "system", "content": DETAILS_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Provide detailed info for these {len(request.beers)} beers "
                        f"from a menu:\n\n" + "\n\n".join(beer_lines)
                    ),
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "beer_details_result",
                    "strict": True,
                    "schema": make_strict_schema(BeerDetailsResult),
                },
            },
            max_tokens=2048,
        )

        result = BeerDetailsResult.model_validate_json(
            resp.choices[0].message.content
        )
        return {"beers": [b.model_dump() for b in result.beers]}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class AnnotateRequest(BaseModel):
    image_base64: str
    ocr_beers: list[dict]
    rated_beers: list[dict]


@app.post("/annotate")
async def annotate_menu_image(request: AnnotateRequest):
    """Step 3: Annotate the original menu image with numbered markers."""
    try:
        image_data = base64.b64decode(request.image_base64)

        ocr_beers = [BeerIdentification(**b) for b in request.ocr_beers]
        rated_beers = [BeerRating(**b) for b in request.rated_beers]

        annotated_b64 = annotate_image(image_data, ocr_beers, rated_beers)
        return {"annotated_image": annotated_b64}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
