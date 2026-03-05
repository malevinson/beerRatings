# Plan: Incremental Beer Ratings with Real-time UI Updates

## Goal
Instead of one slow request that returns all ratings at once, split into OCR → rate-one-at-a-time, updating the list in real-time with a progress tracker.

## Current Flow
```
App → POST /analyze (image) → [OCR + all ratings + annotation] → full JSON → show results
```
Single 20-40 second blocking call. User sees spinner the entire time.

## New Flow
```
App → POST /ocr (image) → beer names → show list with placeholders
  → POST /rate (beer 1) → update card 1   "Rating 1 of 12..."
  → POST /rate (beer 2) → update card 2   "Rating 2 of 12..."
  → ...
  → POST /rate (beer N) → update card N   "Rating 12 of 12"
  → POST /annotate (image + data) → add photo view, enable sorting
```
User sees beer names ~5 seconds in, then ratings fill in one by one.

---

## Changes by File

### 1. `server.py` — Add `/ocr` and `/rate` endpoints

**`POST /ocr`** — Takes image file, returns OCR-only results:
```python
@app.post("/ocr")
async def ocr_menu(image: UploadFile):
    # Same OCR logic as step 1 of /analyze
    # Returns: {beers: [{name, brewery, style_hint, abv_on_menu, y_position, ...}], menu_notes}
```

**`POST /rate`** — Takes single beer info as JSON, returns its rating:
```python
class BeerRateRequest(BaseModel):
    name: str
    brewery: Optional[str] = None
    style_hint: Optional[str] = None
    abv: Optional[str] = None

@app.post("/rate")
async def rate_beer(request: BeerRateRequest):
    # Single OpenAI call with RATINGS_LOOKUP_SYSTEM_PROMPT for just 1 beer
    # Returns: {name, brewery, style, abv, rating_untappd, rating_beer_advocate, description, confidence}
```

**`POST /annotate`** — Takes image + beer data as JSON, returns annotated image:
```python
class AnnotateRequest(BaseModel):
    image_base64: str
    ocr_beers: list[dict]
    rated_beers: list[dict]

@app.post("/annotate")
async def annotate_menu(request: AnnotateRequest):
    # Same annotate_image() logic
    # Returns: {annotated_image: "base64..."}
```

Keep existing `/analyze` endpoint for backward compatibility.

### 2. `ai_agent.py` — Add incremental methods

Add three new methods to `BeerMenuAgent`:

- **`ocr_image(image_data) -> OcrResult`** — POST to `/ocr`, returns list of identified beers (names/positions only, no ratings)
- **`rate_beer(name, brewery, style, abv) -> BeerRating`** — POST JSON to `/rate`, returns single rated beer
- **`get_annotated_image(image_data, ocr_beers, rated_beers) -> bytes`** — POST JSON to `/annotate`, returns annotated image bytes

New dataclass for OCR results:
```python
@dataclass
class OcrBeer:
    name: str
    brewery: Optional[str] = None
    style_hint: Optional[str] = None
    abv: Optional[str] = None
    y_position: Optional[float] = None

@dataclass
class OcrResult:
    beers: list[OcrBeer]
    menu_notes: Optional[str] = None
```

### 3. `app.py` — Refactor `process_image()` for incremental flow

Replace the single `analyze_image` call with:

```python
async def process_image(self, image):
    image_data = self._image_to_bytes(image)
    loop = asyncio.get_event_loop()

    # Phase 1: OCR (fast ~5s)
    self.status_label.text = "Reading menu..."
    ocr_result = await loop.run_in_executor(None, self.agent.ocr_image, image_data)

    # Phase 2: Show results with placeholders, then rate one by one
    updater = self.show_incremental_results(ocr_result.beers)
    rated_beers = []
    for i, beer in enumerate(ocr_result.beers):
        updater.set_progress(i, len(ocr_result.beers))
        try:
            rating = await loop.run_in_executor(
                None, self.agent.rate_beer, beer.name, beer.brewery, beer.style_hint, beer.abv
            )
            updater.update_card(i, rating)
            rated_beers.append(rating)
        except Exception:
            updater.mark_failed(i)
            rated_beers.append(None)

    # Phase 3: Enable sorting + get annotated photo
    updater.finalize(rated_beers)
    try:
        annotated = await loop.run_in_executor(
            None, self.agent.get_annotated_image, image_data, ocr_result.beers, rated_beers
        )
        updater.add_photo_view(annotated)
    except Exception:
        pass  # Photo annotation is optional
```

Each `await` yields to the event loop, so Toga renders the UI updates between iterations.

### 4. `ui_components.py` — Incremental results view with progress

New function: **`build_incremental_results_view(ocr_beers, on_scan_another)`**

Returns `(widgets_list, ResultsUpdater)` where `ResultsUpdater` has methods:

**Initial state** — Shows for each beer:
```
┌──────────────────────────────────────┐
│ #1  Beer Name                  ···  │
│     Looking up rating...            │
│─────────────────────────────────────│
```

**Progress bar** — Below the header:
```
Found 12 Beers              [Scan Another]
Rating 3 of 12...
[████████░░░░░░░░░░░░░░░░░░]
```

**After rating arrives** — Card updates in-place via label.text / style mutations:
```
┌──────────────────────────────────────┐
│ #1  Beer Name          ★ 4.2  BA: 92│
│     Brewery Name          [TOP TIER] │
│     Style · ABV                      │
│     Description text here...         │
│     Confidence: high                 │
│─────────────────────────────────────│
```

**`ResultsUpdater` class** — holds references to mutable widgets per card:
- `update_card(index, rating)` — updates labels in-place (text, colors, tier badge)
- `set_progress(current, total)` — updates progress label + bar
- `mark_failed(index)` — shows "Rating unavailable" on that card
- `finalize(rated_beers)` — hides progress, rebuilds with sort controls enabled
- `add_photo_view(annotated_image)` — adds List/Photo toggle

**Key technique**: Build each placeholder card keeping references to the mutable Label widgets (untappd_label, ba_label, brewery_label, style_label, description_label, confidence_label, divider). When a rating arrives, just set `.text` and `.style.color` on those existing widgets — no DOM rebuild needed, no scroll position lost.

**Sorting**: Only enabled after `finalize()`. At that point, pre-build the 5 sort orders (same as today) since all data is available.

---

## Summary of endpoint calls (per scan)
| Step | Endpoint | Payload | ~Latency |
|------|----------|---------|----------|
| 1 | `POST /ocr` | image file | ~5s |
| 2 | `POST /rate` × N | JSON per beer | ~2s each |
| 3 | `POST /annotate` | image + JSON | ~1s |

Total time is similar or slightly longer, but UX is dramatically better — user sees results filling in after ~5s instead of waiting 30+ seconds.
