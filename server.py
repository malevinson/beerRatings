"""API server for the BeerRated mobile app.

OCR:     Gemini 2.5 Flash-Lite (vision, minimal schema)
Ratings: Gemini 2.5 Flash-Lite (text, structured output)

Local dev:   uvicorn server:app --host 0.0.0.0 --port 8888
Production:  deployed via Procfile (Railway / Render / Fly.io)
"""

import base64
import io
import json
import logging
import os
import re
import time as _time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def _log(msg: str):
    """Print timing/debug info. print() always shows in uvicorn terminal,
    unlike logger.info() which uvicorn's logging config can swallow."""
    print(f"[taplens] {msg}", flush=True)

from google import genai
from google.genai import types as genai_types
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from openai import OpenAI
from PIL import Image as PILImage, ImageDraw, ImageFont, ImageOps
from pydantic import BaseModel, Field
from typing import Optional

# Load .env from project root
load_dotenv(Path(__file__).resolve().parent / ".env")

# ── MongoDB Atlas cache (optional) ──────────────────────────────
import motor.motor_asyncio  # noqa: E402

_mongo_uri = os.environ.get("MONGODB_URI", "")
_no_cache = os.environ.get("NO_CACHE", "").strip().lower() in ("1", "true", "yes")

if _no_cache:
    _mongo_client = None
    _db = None
    _beer_cache = None
    _log("⚠️  NO_CACHE=1 — MongoDB cache DISABLED (simulating first-time user)")
elif _mongo_uri:
    _mongo_client = motor.motor_asyncio.AsyncIOMotorClient(_mongo_uri)
    _db = _mongo_client["taplens"]
    _beer_cache = _db["beer_ratings"]
    _log("MongoDB cache enabled  (db=taplens)")
else:
    _mongo_client = None
    _db = None
    _beer_cache = None
    _log("MongoDB cache disabled  (no MONGODB_URI in .env)")


def _cache_key(name: str, brewery: str = "") -> str:
    """Normalize name+brewery into a stable cache key."""
    raw = f"{name}::{brewery}".lower().strip()
    return re.sub(r"\s+", " ", raw)

from models import (
    MenuAnalysis,
    MenuOcrLite,
    BeerIdentification,
    BeerRating,
    BeerRatingsResult,
    BeerQuickRatingsResult,
    BeerDetailsResult,
    make_strict_schema,
)

# ── MongoDB cache helpers ────────────────────────────────────────


async def _cache_lookup(keys: list[str]) -> dict[str, dict]:
    """Fetch cached beer docs by key. Returns {key: doc} for hits."""
    if not _beer_cache or not keys:
        return {}
    try:
        docs = {}
        async for doc in _beer_cache.find({"_id": {"$in": keys}}):
            docs[doc["_id"]] = doc
        return docs
    except Exception as e:
        _log(f"cache lookup error: {e}")
        return {}


async def _cache_store_quick(key: str, quick: dict):
    """Upsert Phase 1 quick-rating fields into cache."""
    if not _beer_cache:
        return
    try:
        await _beer_cache.update_one(
            {"_id": key},
            {
                "$set": {
                    "name": quick.get("name", ""),
                    "brewery": quick.get("brewery", ""),
                    "rating_beer_advocate": quick.get("rating_beer_advocate"),
                    "confidence": quick.get("confidence", "low"),
                    "updated_at": datetime.now(timezone.utc),
                },
                "$setOnInsert": {"created_at": datetime.now(timezone.utc)},
            },
            upsert=True,
        )
    except Exception as e:
        _log(f"cache store (quick) error: {e}")


async def _cache_store_details(key: str, details: dict):
    """Upsert Phase 2 detail fields into cache."""
    if not _beer_cache:
        return
    try:
        await _beer_cache.update_one(
            {"_id": key},
            {
                "$set": {
                    "style": details.get("style", ""),
                    "abv": details.get("abv"),
                    "rating_untappd": details.get("rating_untappd"),
                    "description": details.get("description", ""),
                    "brand_colors": details.get("brand_colors"),
                    "updated_at": datetime.now(timezone.utc),
                },
                "$setOnInsert": {"created_at": datetime.now(timezone.utc)},
            },
            upsert=True,
        )
    except Exception as e:
        _log(f"cache store (details) error: {e}")


async def _cache_store_combined(key: str, data: dict):
    """Upsert all rating fields into cache at once (combined endpoint)."""
    if not _beer_cache:
        return
    try:
        await _beer_cache.update_one(
            {"_id": key},
            {
                "$set": {
                    "name": data.get("name", ""),
                    "brewery": data.get("brewery", ""),
                    "rating_beer_advocate": data.get("rating_beer_advocate"),
                    "confidence": data.get("confidence", "low"),
                    "style": data.get("style", ""),
                    "abv": data.get("abv"),
                    "rating_untappd": data.get("rating_untappd"),
                    "description": data.get("description", ""),
                    "brand_colors": data.get("brand_colors"),
                    "updated_at": datetime.now(timezone.utc),
                },
                "$setOnInsert": {"created_at": datetime.now(timezone.utc)},
            },
            upsert=True,
        )
    except Exception as e:
        _log(f"cache store (combined) error: {e}")


# ── Prompts ──────────────────────────────────────────────────────

# Short prompt for the fast lite OCR (strips) — only extracts names + breweries
OCR_LITE_PROMPT = "List every beer name and brewery visible on this menu."

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

app = FastAPI(title="TapLens API")

_openai_key = os.environ.get("OPENAI_API_KEY")
client = OpenAI(api_key=_openai_key) if _openai_key else None
RATINGS_MODEL = "gpt-4o-mini"  # Legacy fallback (OpenAI)

# Gemini for OCR + Ratings — higher rate limits, lower latency
GEMINI_OCR_MODEL = "gemini-2.5-flash-lite"
GEMINI_RATINGS_MODEL = "gemini-2.5-flash-lite"
gemini_client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))


@app.on_event("startup")
async def _startup():
    """Ensure MongoDB indexes exist on startup."""
    if _beer_cache is not None:
        try:
            await _beer_cache.create_index("name")
            await _beer_cache.create_index("brewery")
            count = await _beer_cache.count_documents({})
            _log(f"MongoDB cache ready — {count} beers cached")
        except Exception as e:
            _log(f"MongoDB startup warning: {e}")


@app.get("/health")
def health():
    return {"status": "ok", "cache_disabled": _no_cache}


@app.get("/cache-stats")
async def cache_stats():
    """Return cache statistics."""
    if not _beer_cache:
        return {"enabled": False, "count": 0, "no_cache_flag": _no_cache}
    try:
        total = await _beer_cache.count_documents({})
        with_quick = await _beer_cache.count_documents({"rating_beer_advocate": {"$ne": None}})
        with_details = await _beer_cache.count_documents({"style": {"$exists": True}})
        return {
            "enabled": True,
            "total_beers": total,
            "with_quick_rating": with_quick,
            "with_full_details": with_details,
        }
    except Exception as e:
        return {"enabled": True, "error": str(e)}


@app.post("/analyze")
async def analyze_menu(image: UploadFile = File(...)):
    """Accept a menu image, return identified + rated beers in one call."""
    image_data = await image.read()

    # Detect mime type from filename
    ext = (image.filename or "image.png").rsplit(".", 1)[-1].lower()
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "webp": "image/webp", "heic": "image/heic"}.get(ext, "image/png")

    try:
        # Step 1: Vision OCR — identify beers (Gemini 2.0 Flash)
        ocr_resp = gemini_client.models.generate_content(
            model=GEMINI_OCR_MODEL,
            contents=[
                "Please analyze this beer menu image and identify every beer listed.",
                genai_types.Part.from_bytes(data=image_data, mime_type=mime),
            ],
            config=genai_types.GenerateContentConfig(
                system_instruction=MENU_ANALYSIS_SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=MenuAnalysis,
            ),
        )

        menu = MenuAnalysis.model_validate_json(ocr_resp.text)

        if not menu.beers:
            return {"beers": [], "menu_notes": menu.menu_notes}

        # Step 2: Ratings lookup (OpenAI gpt-4o-mini)
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
            model=RATINGS_MODEL,
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
    """Step 1: Read the menu image and identify beers (no ratings). Uses Gemini 2.0 Flash."""
    image_data = await image.read()

    ext = (image.filename or "image.png").rsplit(".", 1)[-1].lower()
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "webp": "image/webp", "heic": "image/heic"}.get(ext, "image/png")

    try:
        response = gemini_client.models.generate_content(
            model=GEMINI_OCR_MODEL,
            contents=[
                "Please analyze this beer menu image and identify every beer listed.",
                genai_types.Part.from_bytes(data=image_data, mime_type=mime),
            ],
            config=genai_types.GenerateContentConfig(
                system_instruction=MENU_ANALYSIS_SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=MenuAnalysis,
            ),
        )

        menu = MenuAnalysis.model_validate_json(response.text)
        return {
            "beers": [b.model_dump() for b in menu.beers],
            "menu_notes": menu.menu_notes,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _split_halves(image_data: bytes, overlap_pct: float = 0.03,
                   save_samples: bool = False):
    """Split image into LEFT and RIGHT halves with overlap.

    Beer menus often have two columns. Left/right splitting keeps each
    column intact, giving the OCR model complete beer entries per half.

    Returns list of (jpeg_bytes, half_label, y_start_frac, y_end_frac).
    y_start/y_end are 0.0/1.0 for both halves (vertical range is full).
    """
    import time
    t0 = time.monotonic()

    img = PILImage.open(io.BytesIO(image_data))
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")

    width, height = img.size

    # Beer menus are typically portrait — rotate landscape if needed
    if width > height * 1.3:
        img = img.rotate(90, expand=True)
        width, height = img.size

    # Convert to grayscale — ~60% smaller JPEG, faster inference
    img = img.convert("L")

    mid_x = width // 2
    overlap_px = int(width * overlap_pct)

    halves = [
        ("left",  0, min(width, mid_x + overlap_px)),
        ("right", max(0, mid_x - overlap_px), width),
    ]
    strips = []
    for label, left, right in halves:
        strip_img = img.crop((left, 0, right, height))
        buf = io.BytesIO()
        strip_img.save(buf, format="JPEG", quality=60)
        strip_bytes = buf.getvalue()
        strips.append((strip_bytes, label, 0.0, 1.0))

        if save_samples:
            sample_path = Path(__file__).parent / f"_sample_{label}.jpg"
            sample_path.write_bytes(strip_bytes)
            _log(f"Saved sample strip: {sample_path}  ({len(strip_bytes) // 1024} KB)")

    _log(f"_split_halves: {time.monotonic() - t0:.2f}s  (L/R, {int(overlap_pct * 100)}% overlap, grayscale, q60)")
    return strips


def _normalize_beer_name(name: str) -> str:
    """Normalize beer name for deduplication across halves."""
    return name.lower().strip().replace("[unclear]", "").strip()


def _ocr_one_strip(strip_bytes: bytes, y_start: float, y_end: float, label: str):
    """Call Gemini OCR on a single strip using the minimal lite schema.

    Returns (label, y_start, y_end, MenuOcrLite, elapsed_sec, error).
    """
    import time

    t0 = time.monotonic()
    try:
        response = gemini_client.models.generate_content(
            model=GEMINI_OCR_MODEL,
            contents=[
                OCR_LITE_PROMPT,
                genai_types.Part.from_bytes(
                    data=strip_bytes, mime_type="image/jpeg"
                ),
            ],
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=MenuOcrLite,
            ),
        )
        menu = MenuOcrLite.model_validate_json(response.text)
        elapsed = time.monotonic() - t0
        return (label, y_start, y_end, menu, elapsed, None)
    except Exception as e:
        elapsed = time.monotonic() - t0
        return (label, y_start, y_end, None, elapsed, e)


def _stream_ocr_generator(image_data: bytes, mime: str):
    """Sync generator: OCRs the whole image in a single Gemini call and
    yields NDJSON lines — one per beer, then a _flush, then _done.
    """
    import time

    t_total = time.monotonic()
    _log(f"OCR starting: whole image, single call  ({GEMINI_OCR_MODEL})")

    try:
        t_ocr = time.monotonic()
        response = gemini_client.models.generate_content(
            model=GEMINI_OCR_MODEL,
            contents=[
                OCR_LITE_PROMPT,
                genai_types.Part.from_bytes(data=image_data, mime_type=mime),
            ],
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=MenuOcrLite,
            ),
        )
        menu = MenuOcrLite.model_validate_json(response.text)
        ocr_elapsed = time.monotonic() - t_ocr
        _log(f"OCR call done: {ocr_elapsed:.2f}s  → {len(menu.beers)} beers")
    except Exception as e:
        _log(f"OCR call FAILED: {time.monotonic() - t_total:.2f}s  — {e}")
        yield json.dumps({"_done": True, "menu_notes": None}) + "\n"
        return

    seen_names: set[str] = set()
    for beer_idx, beer in enumerate(menu.beers):
        norm = _normalize_beer_name(beer.name)
        if norm in seen_names:
            continue
        seen_names.add(norm)

        est_y = (beer_idx + 0.5) / max(len(menu.beers), 1)
        obj = {
            "name": beer.name,
            "brewery": beer.brewery,
            "y_position": round(est_y, 3),
        }
        yield json.dumps(obj) + "\n"

    _log(f"OCR yielded {len(seen_names)} unique beers (deduped from {len(menu.beers)})")

    # Flush so client starts rating immediately
    yield json.dumps({"_flush": True}) + "\n"

    total_elapsed = time.monotonic() - t_total
    _log(f"OCR stream total: {total_elapsed:.2f}s  → {len(seen_names)} unique beers")

    yield json.dumps({"_done": True, "menu_notes": None}) + "\n"


@app.post("/ocr-stream")
async def ocr_menu_stream(image: UploadFile = File(...)):
    """Stream OCR results as NDJSON — one beer per line, then a _done line."""
    image_data = await image.read()

    ext = (image.filename or "image.png").rsplit(".", 1)[-1].lower()
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "webp": "image/webp", "heic": "image/heic"}.get(ext, "image/png")

    return StreamingResponse(
        _stream_ocr_generator(image_data, mime),
        media_type="application/x-ndjson",
    )


# ── /ocr-positions — locate beer names on the menu image ──────

class BeerPosition(BaseModel):
    name: str = Field(description="Beer name (exactly as provided)")
    y_position: float = Field(description="Vertical center of the beer name, 0.0=top to 1.0=bottom")
    x_end: float = Field(description="Where the beer name text ends horizontally, 0.0=left to 1.0=right")

class BeerPositionsResult(BaseModel):
    beers: list[BeerPosition] = Field(description="Position for each beer on the menu")

class OcrPositionsRequest(BaseModel):
    beer_names: list[str] = Field(description="Beer names to locate on the menu")

OCR_POSITIONS_PROMPT = """Look at this beer menu image. For each beer name listed below, find where it appears on the menu and return:
- y_position: the vertical center of that beer name as a fraction from 0.0 (top of image) to 1.0 (bottom)
- x_end: the horizontal position where the beer name text ENDS as a fraction from 0.0 (left) to 1.0 (right)

Be precise — x_end should mark exactly where the name text stops (not the description or price after it).

Beer names to locate:
"""


@app.post("/ocr-positions")
async def ocr_positions(image: UploadFile = File(...), beer_names: str = ""):
    """Find exact x,y positions of beer names on the menu image.

    Called after ratings are complete — not on the critical path.
    Accepts beer_names as a JSON array string in a form field.
    """
    import time

    names = json.loads(beer_names) if beer_names else []
    if not names:
        return {"beers": []}

    image_data = await image.read()
    ext = (image.filename or "image.png").rsplit(".", 1)[-1].lower()
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "webp": "image/webp", "heic": "image/heic"}.get(ext, "image/png")

    prompt = OCR_POSITIONS_PROMPT + "\n".join(f"- {n}" for n in names)

    t0 = time.monotonic()
    _log(f"ocr-positions: locating {len(names)} beers on menu")

    try:
        response = gemini_client.models.generate_content(
            model=GEMINI_OCR_MODEL,
            contents=[
                prompt,
                genai_types.Part.from_bytes(data=image_data, mime_type=mime),
            ],
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=BeerPositionsResult,
            ),
        )
        result = BeerPositionsResult.model_validate_json(response.text)
        elapsed = time.monotonic() - t0
        _log(f"ocr-positions done: {elapsed:.2f}s — {len(result.beers)} positions")
        return result.model_dump()
    except Exception as e:
        elapsed = time.monotonic() - t0
        _log(f"ocr-positions FAILED: {elapsed:.2f}s — {e}")
        return {"beers": []}


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

COMBINED_RATINGS_SYSTEM_PROMPT = """\
You are a knowledgeable beer expert with deep knowledge of craft beer,
beer ratings, and brewing.

For each beer provided, supply ALL of the following in a single response:
- The correct brewery name (confirm or identify if not provided)
- An approximate BeerAdvocate score (0-100 scale)
- Confidence: "high" if you recognize it, "medium" if somewhat sure, "low" if guessing
- The beer style (e.g., New England IPA, Imperial Stout)
- Approximate ABV
- Approximate Untappd rating (0.0-5.0 scale), or null if unknown
- A short, appealing 1-2 sentence description of the beer's flavor profile
- 2-3 hex color codes for the beer's brand/packaging colors

Important guidelines:
- Use your training knowledge for approximate ratings — they don't need to be exact.
- If you recognize the beer, provide your best estimate of community ratings.
- If you don't recognize a specific beer, identify the brewery and style, and estimate
  based on the brewery's reputation.
- Set confidence appropriately: "high", "medium", or "low".
- Never fabricate — set ratings to null and confidence to "low" if you truly cannot identify.
- Ratings should reflect general community consensus, not personal opinion.
- For brand_colors, use the beer's packaging colors or the brewery's brand palette."""


class BeerBatchRequest(BaseModel):
    beers: list[dict]


@app.post("/rate-batch")
async def rate_beer_batch(request: BeerBatchRequest):
    """Phase 1: Get quick ratings (brewery + BA score) for a batch of beers."""
    import time
    t0 = time.monotonic()

    beer_lines = []
    for i, b in enumerate(request.beers, 1):
        parts = [f"{i}. {b.get('name', 'Unknown')}"]
        if b.get("brewery"):
            parts.append(f"   Brewery: {b['brewery']}")
        beer_lines.append("\n".join(parts))

    beer_names = ", ".join(b.get("name", "?") for b in request.beers)

    try:
        resp = gemini_client.models.generate_content(
            model=GEMINI_RATINGS_MODEL,
            contents=[
                f"Provide quick ratings for these {len(request.beers)} beers "
                f"from a menu:\n\n" + "\n\n".join(beer_lines)
            ],
            config=genai_types.GenerateContentConfig(
                system_instruction=QUICK_RATINGS_SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=BeerQuickRatingsResult,
            ),
        )

        result = BeerQuickRatingsResult.model_validate_json(resp.text)
        elapsed = time.monotonic() - t0
        _log(f"rate-batch ({len(request.beers)} beers): {elapsed:.2f}s  [{beer_names}]")
        return {"beers": [b.model_dump() for b in result.beers]}

    except HTTPException:
        raise
    except Exception as e:
        elapsed = time.monotonic() - t0
        _log(f"rate-batch FAILED ({elapsed:.2f}s): {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/rate-details")
async def rate_beer_details(request: BeerBatchRequest):
    """Phase 2: Get detailed info (style, description, colors) for a batch."""
    import time
    t0 = time.monotonic()

    beer_lines = []
    for i, b in enumerate(request.beers, 1):
        parts = [f"{i}. {b.get('name', 'Unknown')}"]
        if b.get("brewery"):
            parts.append(f"   Brewery: {b['brewery']}")
        beer_lines.append("\n".join(parts))

    beer_names = ", ".join(b.get("name", "?") for b in request.beers)

    try:
        resp = gemini_client.models.generate_content(
            model=GEMINI_RATINGS_MODEL,
            contents=[
                f"Provide detailed info for these {len(request.beers)} beers "
                f"from a menu:\n\n" + "\n\n".join(beer_lines)
            ],
            config=genai_types.GenerateContentConfig(
                system_instruction=DETAILS_SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=BeerDetailsResult,
            ),
        )

        result = BeerDetailsResult.model_validate_json(resp.text)
        elapsed = time.monotonic() - t0
        _log(f"rate-details ({len(request.beers)} beers): {elapsed:.2f}s  [{beer_names}]")
        return {"beers": [b.model_dump() for b in result.beers]}

    except HTTPException:
        raise
    except Exception as e:
        elapsed = time.monotonic() - t0
        _log(f"rate-details FAILED ({elapsed:.2f}s): {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/rate-combined")
async def rate_beer_combined(request: BeerBatchRequest):
    """Combined: Get ALL rating info in a single Gemini call per batch.

    Returns brewery, BA score, confidence, style, ABV, Untappd, description,
    and brand colors — everything the app needs in one round trip.
    With MongoDB cache: look up all beers first, only call Gemini for misses.
    """
    t0 = _time.monotonic()

    keys = [_cache_key(b.get("name", ""), b.get("brewery", "")) for b in request.beers]
    cached_docs = await _cache_lookup(keys)

    results: list[dict | None] = [None] * len(request.beers)
    misses: list[tuple[int, dict]] = []

    for i, (b, key) in enumerate(zip(request.beers, keys)):
        doc = cached_docs.get(key)
        # Full cache hit requires both quick + detail fields
        if doc and "rating_beer_advocate" in doc and "style" in doc and "description" in doc:
            results[i] = {
                "name": doc.get("name", b.get("name", "")),
                "brewery": doc.get("brewery", b.get("brewery", "")),
                "rating_beer_advocate": doc.get("rating_beer_advocate"),
                "confidence": doc.get("confidence", "high"),
                "style": doc.get("style", ""),
                "abv": doc.get("abv"),
                "rating_untappd": doc.get("rating_untappd"),
                "description": doc.get("description", ""),
                "brand_colors": doc.get("brand_colors"),
            }
        else:
            misses.append((i, b))

    cache_hits = len(request.beers) - len(misses)
    beer_names = ", ".join(b.get("name", "?") for b in request.beers)

    if misses:
        beer_lines = []
        for seq, (_, b) in enumerate(misses, 1):
            parts = [f"{seq}. {b.get('name', 'Unknown')}"]
            if b.get("brewery"):
                parts.append(f"   Brewery: {b['brewery']}")
            beer_lines.append("\n".join(parts))

        try:
            resp = gemini_client.models.generate_content(
                model=GEMINI_RATINGS_MODEL,
                contents=[
                    f"Provide complete ratings and details for these {len(misses)} beers "
                    f"from a menu:\n\n" + "\n\n".join(beer_lines)
                ],
                config=genai_types.GenerateContentConfig(
                    system_instruction=COMBINED_RATINGS_SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=BeerRatingsResult,
                ),
            )

            gemini_result = BeerRatingsResult.model_validate_json(resp.text)

            for j, rated in enumerate(gemini_result.beers):
                if j < len(misses):
                    orig_idx = misses[j][0]
                    rated_dict = rated.model_dump()
                    results[orig_idx] = rated_dict
                    key = keys[orig_idx]
                    await _cache_store_combined(key, rated_dict)

        except HTTPException:
            raise
        except Exception as e:
            elapsed = _time.monotonic() - t0
            _log(f"rate-combined FAILED ({elapsed:.2f}s): {e}")
            raise HTTPException(status_code=500, detail=str(e))

    elapsed = _time.monotonic() - t0
    _log(f"rate-combined ({len(request.beers)} beers, {cache_hits} cached): {elapsed:.2f}s  [{beer_names}]")
    return {"beers": [r for r in results if r is not None]}


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
