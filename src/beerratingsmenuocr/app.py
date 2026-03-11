"""BeerRated - Main Application."""

import asyncio
from pathlib import Path

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, CENTER, BOLD

from .ai_agent import BeerMenuAgent, BeerRating
from .history import load_history, save_scan
from .ui_components import (
    build_home_view,
    build_history_list_view,
    build_history_detail_view,
    build_incremental_results_view,
    build_streaming_results_view,
)


# ── Helpers for parallel OCR ─────────────────────────────────────


def _normalize_beer_key(name: str) -> str:
    """Normalize a beer name for deduplication.

    Lowercases, strips whitespace, removes [unclear] tags,
    and collapses multiple spaces.
    """
    key = name.lower().strip()
    key = key.replace("[unclear]", "").strip()
    key = " ".join(key.split())
    return key


def _build_rating_cache(data_dir) -> dict:
    """Build a name-keyed cache of BeerRating objects from scan history.

    Returns dict mapping normalized beer name → BeerRating for beers
    that were previously successfully rated. Enables instant ratings
    for beers the user has seen before.
    """
    cache = {}
    history = load_history(data_dir)
    for entry in history:
        for beer in entry.get("beers", []):
            name = beer.get("name")
            if not name:
                continue
            key = _normalize_beer_key(name)
            if key in cache:
                continue  # keep the most recent (history is newest-first)
            # Only cache if it has a rating
            if beer.get("rating_beer_advocate") is not None or beer.get("rating_untappd") is not None:
                cache[key] = BeerRating(
                    name=beer.get("name", "Unknown"),
                    brewery=beer.get("brewery", "Unknown"),
                    style=beer.get("style", "Unknown"),
                    abv=beer.get("abv"),
                    rating_untappd=beer.get("rating_untappd"),
                    rating_beer_advocate=beer.get("rating_beer_advocate"),
                    description=beer.get("description", ""),
                    confidence=beer.get("confidence", "low"),
                    brand_colors=beer.get("brand_colors"),
                )
    return cache


class BeerRatingsApp(toga.App):
    """Main application: scan beer menus and display ratings."""

    def startup(self):
        self.agent = BeerMenuAgent()
        self.content_box = toga.Box(style=Pack(direction=COLUMN, flex=1))
        self._scan_generation = 0  # incremented each scan; used to cancel stale ones
        self.progress_bar = None
        self.status_label = None
        self._timer_running = False

        self.main_window = toga.MainWindow(
            title=self.formal_name,
            size=(400, 700),
        )
        self.main_window.content = self.content_box

        self.show_home_view()
        self.main_window.show()

    # ── View management ──────────────────────────────────────────

    def _stop_timer(self):
        """Stop the elapsed-time counter."""
        self._timer_running = False

    def show_home_view(self):
        # Cancel any in-flight scan so stale tasks don't update removed widgets
        self._scan_generation += 1
        self._stop_timer()
        # Clean up stale widget refs from previous loading views
        if self.progress_bar is not None:
            try:
                self.progress_bar.stop()
            except Exception:
                pass
        self.progress_bar = None
        self.status_label = None

        self.content_box.clear()
        widgets = build_home_view(
            on_take_photo=self.on_take_photo,
            on_select_image=self.on_select_image,
            on_history=self.on_show_history,
        )
        for w in widgets:
            self.content_box.add(w)

    def show_loading_view(self):
        self.content_box.clear()
        self.status_label = toga.Label(
            "Preparing image...",
            style=Pack(
                text_align=CENTER, font_size=16,
                padding_top=80, padding_bottom=20,
            ),
        )
        self._timer_label = toga.Label(
            "0s",
            style=Pack(
                text_align=CENTER, font_size=13,
                color="#999999", padding_bottom=10,
            ),
        )
        self.progress_bar = toga.ProgressBar(
            max=None,
            style=Pack(padding=20, width=300, alignment=CENTER),
        )
        self.progress_bar.start()
        self.content_box.add(self.status_label)
        self.content_box.add(self._timer_label)
        self.content_box.add(self.progress_bar)

        # Start an elapsed-time counter so the user sees activity
        self._timer_seconds = 0
        self._timer_running = True

        async def _tick():
            while self._timer_running:
                await asyncio.sleep(1)
                if not self._timer_running:
                    break
                self._timer_seconds += 1
                try:
                    self._timer_label.text = f"{self._timer_seconds}s"
                except Exception:
                    break

        asyncio.ensure_future(_tick())

    def show_error_view(self, error_message: str):
        self.content_box.clear()
        self.content_box.add(
            toga.Label(
                "Something went wrong",
                style=Pack(
                    text_align=CENTER, padding_top=40,
                    font_weight=BOLD, font_size=18,
                ),
            )
        )
        self.content_box.add(
            toga.Label(
                error_message,
                style=Pack(text_align=CENTER, padding=20),
            )
        )
        self.content_box.add(
            toga.Button(
                "Try Again",
                on_press=self.on_scan_another,
                style=Pack(padding=20, width=200, alignment=CENTER),
            )
        )

    # ── Event handlers ───────────────────────────────────────────

    async def on_take_photo(self, widget, **kwargs):
        try:
            if not self.camera.has_permission:
                await self.camera.request_permission()
            image = await self.camera.take_photo()
            if image is not None:
                self.show_loading_view()
                await asyncio.sleep(0)  # yield so UI renders
                await self.process_image(image)
        except NotImplementedError:
            await self.main_window.dialog(
                toga.InfoDialog(
                    "Not Available",
                    "Camera is not available on this platform. "
                    "Use 'Select from Library' instead.",
                )
            )
        except PermissionError:
            await self.main_window.dialog(
                toga.InfoDialog(
                    "Permission Denied",
                    "Camera permission is required to take photos.",
                )
            )

    async def on_select_image(self, widget, **kwargs):
        try:
            image = await self._pick_image()
            if image is not None:
                self.show_loading_view()
                await asyncio.sleep(0)  # yield so UI renders
                await self.process_image(image)
        except Exception as e:
            await self.main_window.dialog(
                toga.InfoDialog("Error", f"Could not load image: {e}")
            )

    async def _pick_image(self):
        """Pick an image from the gallery, with Android-specific handling."""
        try:
            # Try Android intent-based picker first
            from android.content import Intent  # noqa: F811
            from java.io import ByteArrayOutputStream

            intent = Intent(Intent.ACTION_GET_CONTENT)
            intent.setType("image/*")
            intent.addCategory(Intent.CATEGORY_OPENABLE)

            result = await self._impl.intent_result(
                Intent.createChooser(intent, "Select a Beer Menu Image")
            )

            if result["resultCode"] != -1:  # RESULT_OK = -1
                return None

            uri = result["resultData"].getData()
            resolver = self._impl.native.getContentResolver()
            input_stream = resolver.openInputStream(uri)

            buf = ByteArrayOutputStream()
            chunk = bytearray(8192)
            while True:
                n = input_stream.read(chunk)
                if n == -1:
                    break
                buf.write(chunk, 0, n)
            input_stream.close()

            image_bytes = bytes(buf.toByteArray())
            return toga.Image(data=image_bytes)

        except ImportError:
            # Not on Android — use standard file dialog (Mac/desktop)
            file_path = await self.main_window.dialog(
                toga.OpenFileDialog(
                    "Select a Beer Menu Image",
                    file_types=["png", "jpg", "jpeg", "heic", "webp"],
                )
            )
            if file_path is not None:
                return toga.Image(file_path)
            return None

    def on_scan_another(self, widget, **kwargs):
        self.show_home_view()

    def on_show_history(self, widget, **kwargs):
        from .history import load_history, delete_scan
        entries = load_history(self.paths.data)
        self.content_box.clear()

        def on_view_entry(index):
            def handler(widget):
                entry = entries[index]
                self.content_box.clear()
                widgets = build_history_detail_view(
                    entry=entry,
                    on_back=self.on_show_history,
                    on_home=self.on_scan_another,
                )
                for w in widgets:
                    self.content_box.add(w)
            return handler

        def on_delete_entry(index):
            def handler(widget):
                delete_scan(self.paths.data, index)
                self.on_show_history(widget)
            return handler

        widgets = build_history_list_view(
            entries=entries,
            on_view=on_view_entry,
            on_delete=on_delete_entry,
            on_home=self.on_scan_another,
        )
        for w in widgets:
            self.content_box.add(w)

    # ── AI processing pipeline ───────────────────────────────────

    async def process_image(self, image: toga.Image):
        """Run the two-phase AI pipeline: OCR → batch quick ratings → batch details.

        Phase 0: Split image into 4 overlapping quadrants, run parallel OCR.
        Phase 1: Batch /rate-batch calls for quick ratings (brewery + BA score).
        Phase 2: Batch /rate-details calls for style, description, brand_colors.
        Cached beers bypass both phases entirely.
        """
        BATCH_SIZE = 10

        self._scan_generation += 1
        my_gen = self._scan_generation

        if self.progress_bar is None:
            self.show_loading_view()
            await asyncio.sleep(0)
        loop = asyncio.get_event_loop()

        try:
            # Resize/compress off the main thread to avoid freezing the UI
            image_data = await loop.run_in_executor(
                None, self._image_to_bytes, image
            )

            if my_gen != self._scan_generation:
                return

            # Load rating cache, split quadrants, and make thumbnail concurrently
            cache_future = loop.run_in_executor(
                None, _build_rating_cache, self.paths.data
            )
            quad_future = loop.run_in_executor(
                None, self._split_quadrants, image_data
            )
            thumb_future = loop.run_in_executor(
                None, self._make_thumbnail, image_data
            )
            rating_cache = await cache_future
            quadrants = await quad_future
            thumbnail = await thumb_future

            if my_gen != self._scan_generation:
                return

            # ── Set up streaming results view ──────────────────────
            self._stop_timer()
            if self.progress_bar is not None:
                try:
                    self.progress_bar.stop()
                except Exception:
                    pass
            self.progress_bar = None
            self.status_label = None
            self.content_box.clear()

            widgets, updater = build_streaming_results_view(
                on_scan_another=self.on_scan_another,
                thumbnail=thumbnail,
            )
            for w in widgets:
                self.content_box.add(w)
            await asyncio.sleep(0)  # render

            # ── Parallel OCR via background threads + asyncio.Queue ─
            beer_queue = asyncio.Queue()
            ocr_beers = []
            seen_beers = {}          # normalized_key → index in ocr_beers
            rated_beers_map = {}     # index → BeerRating (fully rated)
            semaphore = asyncio.Semaphore(4)

            # Build worker functions for each OCR stream
            def make_stream_worker(img_bytes, source_label, position_mapping):
                """Create a stream worker for one image (quadrant or full)."""
                def worker():
                    try:
                        for event_type, data in self.agent.ocr_image_stream(img_bytes):
                            if my_gen != self._scan_generation:
                                return
                            # Adjust y_position for quadrant images
                            if (position_mapping is not None
                                    and event_type == "beer"
                                    and data.y_position is not None):
                                data.y_position = (
                                    position_mapping["y_offset"]
                                    + data.y_position * position_mapping["y_scale"]
                                )
                            loop.call_soon_threadsafe(
                                beer_queue.put_nowait,
                                (event_type, data, source_label),
                            )
                    except Exception as e:
                        loop.call_soon_threadsafe(
                            beer_queue.put_nowait, ("error", str(e), source_label)
                        )
                    finally:
                        loop.call_soon_threadsafe(
                            beer_queue.put_nowait, ("_end", None, source_label)
                        )
                return worker

            # Launch OCR streams (quadrants only — no full-image stream)
            if quadrants:
                total_streams = len(quadrants)
                for quad_bytes, quad_label, mapping in quadrants:
                    loop.run_in_executor(
                        None, make_stream_worker(quad_bytes, quad_label, mapping)
                    )
            else:
                # Fallback: just the full image if quadrants unavailable
                total_streams = 1
                loop.run_in_executor(
                    None, make_stream_worker(image_data, "full", None)
                )

            # ── Two-phase batch rating ─────────────────────────────
            pending_batch = []        # (index, OcrBeer) awaiting Phase 1
            rating_tasks = []         # all Phase 1+2 tasks
            completed_phase2 = [0]    # count of beers fully done (cache + phase2)
            cached_count = [0]

            async def _process_batch(batch):
                """Run Phase 1 (quick ratings) then Phase 2 (details) for a batch."""
                if my_gen != self._scan_generation:
                    return

                indices = [idx for idx, _ in batch]
                beers_payload = [
                    {"name": beer.name, "brewery": beer.brewery}
                    for _, beer in batch
                ]

                # Phase 1: Quick ratings (brewery + BA score)
                try:
                    async with semaphore:
                        quick_results = await loop.run_in_executor(
                            None, self.agent.rate_beer_batch, beers_payload
                        )
                    if my_gen != self._scan_generation:
                        return

                    # Match results to cards by position in batch
                    for j, idx in enumerate(indices):
                        if j < len(quick_results):
                            updater.update_card_primary(idx, quick_results[j])
                except Exception:
                    # Phase 1 failed — fall back to individual /rate calls
                    await _fallback_individual(batch)
                    return

                # Phase 2: Details (style, description, colors, untappd)
                try:
                    # Use brewery from Phase 1 results for better Phase 2 accuracy
                    details_payload = []
                    for j, (_, beer) in enumerate(batch):
                        brewery = beer.brewery
                        if j < len(quick_results):
                            brewery = quick_results[j].get("brewery", brewery)
                        details_payload.append(
                            {"name": beer.name, "brewery": brewery}
                        )

                    async with semaphore:
                        detail_results = await loop.run_in_executor(
                            None, self.agent.rate_beer_details, details_payload
                        )
                    if my_gen != self._scan_generation:
                        return

                    # Merge Phase 1 + Phase 2 into full BeerRating objects
                    for j, idx in enumerate(indices):
                        quick = quick_results[j] if j < len(quick_results) else {}
                        detail = detail_results[j] if j < len(detail_results) else {}

                        merged = BeerRating(
                            name=quick.get("name", ocr_beers[idx].name),
                            brewery=quick.get("brewery", "Unknown"),
                            style=detail.get("style", "Unknown"),
                            abv=detail.get("abv"),
                            rating_untappd=detail.get("rating_untappd"),
                            rating_beer_advocate=quick.get("rating_beer_advocate"),
                            description=detail.get("description", ""),
                            confidence=quick.get("confidence", "low"),
                            brand_colors=detail.get("brand_colors"),
                        )
                        rated_beers_map[idx] = merged
                        updater.update_card(idx, merged)

                        completed_phase2[0] += 1
                        total_expected = len(ocr_beers) - cached_count[0]
                        if ocr_done[0] and total_expected > 0:
                            updater.set_progress(
                                completed_phase2[0] + cached_count[0],
                                len(ocr_beers),
                            )
                except Exception:
                    # Phase 2 failed — cards still have Phase 1 data, create partial ratings
                    for j, idx in enumerate(indices):
                        if idx not in rated_beers_map:
                            quick = quick_results[j] if j < len(quick_results) else {}
                            rated_beers_map[idx] = BeerRating(
                                name=quick.get("name", ocr_beers[idx].name),
                                brewery=quick.get("brewery", "Unknown"),
                                style="Unknown",
                                description="",
                                confidence=quick.get("confidence", "low"),
                                rating_beer_advocate=quick.get("rating_beer_advocate"),
                            )
                            completed_phase2[0] += 1

            async def _fallback_individual(batch):
                """Fall back to individual /rate calls if batch fails."""
                for idx, beer in batch:
                    if my_gen != self._scan_generation:
                        return
                    try:
                        async with semaphore:
                            rating = await loop.run_in_executor(
                                None,
                                self.agent.rate_beer,
                                beer.name,
                                beer.brewery,
                                beer.style_hint,
                                beer.abv,
                            )
                        if my_gen != self._scan_generation:
                            return
                        rated_beers_map[idx] = rating
                        updater.update_card(idx, rating)
                    except Exception:
                        updater.mark_failed(idx)

                    completed_phase2[0] += 1
                    if ocr_done[0]:
                        updater.set_progress(
                            completed_phase2[0] + cached_count[0],
                            len(ocr_beers),
                        )

            def _flush_batch():
                """Fire off a batch for Phase 1+2 processing."""
                if not pending_batch:
                    return
                batch = pending_batch.copy()
                pending_batch.clear()
                task = asyncio.create_task(_process_batch(batch))
                rating_tasks.append(task)

            # ── Consume streaming events from all OCR streams ──────
            menu_notes = None
            ocr_done = [False]
            stream_error = None
            streams_remaining = total_streams

            while streams_remaining > 0:
                event_type, data, source = await beer_queue.get()
                if my_gen != self._scan_generation:
                    return

                if event_type == "_end":
                    streams_remaining -= 1
                    continue
                elif event_type == "error":
                    if stream_error is None:
                        stream_error = data
                    continue  # other streams may succeed
                elif event_type == "beer":
                    key = _normalize_beer_key(data.name)
                    if key in seen_beers:
                        continue  # duplicate

                    # New beer — add to UI
                    i = len(ocr_beers)
                    seen_beers[key] = i
                    ocr_beers.append(data)
                    updater.add_beer(i, data.name)
                    updater.update_header(len(ocr_beers))

                    # Check cache first
                    cached = rating_cache.get(key)
                    if cached is not None:
                        rated_beers_map[i] = cached
                        updater.update_card(i, cached)
                        cached_count[0] += 1
                    else:
                        pending_batch.append((i, data))
                        if len(pending_batch) >= BATCH_SIZE:
                            _flush_batch()

                elif event_type == "done":
                    menu_notes = data

            if stream_error and not ocr_beers:
                self.show_error_view(f"Menu scan failed: {stream_error}")
                return

            if not ocr_beers:
                self.show_error_view(
                    "No beers found on this menu. Try a clearer photo."
                )
                return

            # Flush any remaining beers in the pending batch
            _flush_batch()

            # Switch progress to determinate now that we know the total
            ocr_done[0] = True
            updater.switch_to_determinate(
                completed_phase2[0] + cached_count[0], len(ocr_beers),
            )

            # Wait for all rating tasks to complete
            if rating_tasks:
                await asyncio.gather(*rating_tasks)

            if my_gen != self._scan_generation:
                return

            # ── Finalize ──────────────────────────────────────────────
            rated_beers = [rated_beers_map.get(i) for i in range(len(ocr_beers))]
            updater.finalize(rated_beers)

            # Save to scan history (with thumbnail for history view)
            try:
                save_scan(self.paths.data, ocr_beers, rated_beers, thumbnail=thumbnail)
            except Exception:
                pass  # History save is non-critical

        except Exception as e:
            if my_gen != self._scan_generation:
                return
            self._stop_timer()
            if self.progress_bar is not None:
                try:
                    self.progress_bar.stop()
                except Exception:
                    pass
                self.progress_bar = None
                self.status_label = None
            self.show_error_view(f"AI processing failed: {e}")

    @staticmethod
    def _image_to_bytes(image: toga.Image, max_dimension: int = 1500) -> bytes:
        """Extract bytes from a toga.Image, resized and JPEG-compressed.

        Camera images are typically 3000-4000px which is far more than
        GPT vision needs. Downsizing to ~1500px and compressing to JPEG
        dramatically reduces upload time and API latency.
        """
        import io

        # Get raw bytes from the toga.Image
        raw = None
        if hasattr(image, "data") and image.data:
            raw = image.data
        elif hasattr(image, "save"):
            buf = io.BytesIO()
            image.save(buf)
            raw = buf.getvalue()
        elif hasattr(image, "path") and image.path:
            raw = Path(image.path).read_bytes()

        if raw is None:
            raise ValueError("Cannot extract bytes from toga.Image")

        # Resize + compress with PIL (available on Android via Chaquopy)
        try:
            from PIL import Image as PILImage, ImageOps

            img = PILImage.open(io.BytesIO(raw))
            img = ImageOps.exif_transpose(img) or img

            # Downscale if larger than max_dimension
            w, h = img.size
            if max(w, h) > max_dimension:
                ratio = max_dimension / max(w, h)
                img = img.resize(
                    (int(w * ratio), int(h * ratio)),
                    PILImage.LANCZOS,
                )

            # Convert to RGB (JPEG doesn't support alpha)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            out = io.BytesIO()
            img.save(out, format="JPEG", quality=80)
            return out.getvalue()
        except ImportError:
            # PIL not available — return raw bytes uncompressed
            return raw

    @staticmethod
    def _make_thumbnail(image_data: bytes, max_height: int = 50) -> bytes:
        """Create a small JPEG thumbnail from the compressed menu image."""
        import io
        try:
            from PIL import Image as PILImage
            img = PILImage.open(io.BytesIO(image_data))
            ratio = max_height / img.height
            new_w = max(1, int(img.width * ratio))
            img = img.resize((new_w, max_height), PILImage.LANCZOS)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=70)
            return buf.getvalue()
        except ImportError:
            return image_data  # fallback: return full image

    @staticmethod
    def _split_quadrants(image_data: bytes, overlap: float = 0.10):
        """Split a JPEG image into 4 overlapping quadrants for parallel OCR.

        Each quadrant is roughly half the image in each dimension, with a
        configurable overlap band so beers near boundaries are captured
        by at least one quadrant. Returns a list of tuples:
            (quadrant_jpeg_bytes, label_str, position_mapping_dict)

        position_mapping contains y_offset, y_scale, x_offset, x_scale
        for converting quadrant-local fractional positions to full-image
        fractions:  full_y = y_offset + local_y * y_scale

        Returns an empty list if the image is too small to split.
        """
        import io

        try:
            from PIL import Image as PILImage

            img = PILImage.open(io.BytesIO(image_data))
            w, h = img.size

            # Skip splitting if image is too small
            if w < 400 or h < 400:
                return []

            # Convert to RGB if needed
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            # Overlap in pixels
            ov_x = int(w * overlap / 2)
            ov_y = int(h * overlap / 2)
            mid_x = w // 2
            mid_y = h // 2

            # Define quadrants: (crop_box, label, mapping)
            # crop_box = (left, top, right, bottom)
            half_plus_x = 0.5 + overlap / 2   # fraction of full image each quadrant covers
            half_plus_y = 0.5 + overlap / 2
            half_minus_x = 0.5 - overlap / 2   # start fraction for right/bottom quadrants
            half_minus_y = 0.5 - overlap / 2

            quadrant_defs = [
                (
                    (0, 0, mid_x + ov_x, mid_y + ov_y),
                    "top_left",
                    {"y_offset": 0.0, "y_scale": half_plus_y,
                     "x_offset": 0.0, "x_scale": half_plus_x},
                ),
                (
                    (mid_x - ov_x, 0, w, mid_y + ov_y),
                    "top_right",
                    {"y_offset": 0.0, "y_scale": half_plus_y,
                     "x_offset": half_minus_x, "x_scale": half_plus_x},
                ),
                (
                    (0, mid_y - ov_y, mid_x + ov_x, h),
                    "bottom_left",
                    {"y_offset": half_minus_y, "y_scale": half_plus_y,
                     "x_offset": 0.0, "x_scale": half_plus_x},
                ),
                (
                    (mid_x - ov_x, mid_y - ov_y, w, h),
                    "bottom_right",
                    {"y_offset": half_minus_y, "y_scale": half_plus_y,
                     "x_offset": half_minus_x, "x_scale": half_plus_x},
                ),
            ]

            results = []
            for crop_box, label, mapping in quadrant_defs:
                quad_img = img.crop(crop_box)
                buf = io.BytesIO()
                quad_img.save(buf, format="JPEG", quality=80)
                results.append((buf.getvalue(), label, mapping))

            return results

        except ImportError:
            # PIL not available — cannot split
            return []


def main():
    return BeerRatingsApp(
        "BeerRated",
        "com.mattlevinson.beerratingsmenuocr",
    )
