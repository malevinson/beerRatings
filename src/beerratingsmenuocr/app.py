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
    build_results_view,
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

    def show_results_view(self, beers: list, annotated_image: bytes = None):
        self.content_box.clear()
        widgets = build_results_view(
            beers=beers,
            on_scan_another=self.on_scan_another,
            annotated_image=annotated_image,
        )
        for w in widgets:
            self.content_box.add(w)

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
        """Run the parallel AI pipeline: split image → 5 OCR streams → rate ASAP → annotate.

        The menu image is split into 4 overlapping quadrants plus a full-image
        scan. All 5 OCR streams run in parallel, and beers are deduplicated as
        they arrive. Rating tasks start the moment each new beer is identified.
        Previously-rated beers are served from a cache for instant results.
        """
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

            # Load rating cache from history + split image into quadrants
            # (both are CPU work, run concurrently in executor)
            cache_future = loop.run_in_executor(
                None, _build_rating_cache, self.paths.data
            )
            quad_future = loop.run_in_executor(
                None, self._split_quadrants, image_data
            )
            rating_cache = await cache_future
            quadrants = await quad_future

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
            )
            for w in widgets:
                self.content_box.add(w)
            await asyncio.sleep(0)  # render

            # ── Parallel OCR via background threads + asyncio.Queue ─
            beer_queue = asyncio.Queue()
            ocr_beers = []
            seen_beers = {}          # normalized_key → index in ocr_beers
            rated_beers_map = {}
            rating_tasks = []
            completed = [0]
            semaphore = asyncio.Semaphore(6)

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

            # Determine number of OCR streams
            if quadrants:
                total_streams = len(quadrants) + 1  # quadrants + full image
                for quad_bytes, quad_label, mapping in quadrants:
                    loop.run_in_executor(
                        None, make_stream_worker(quad_bytes, quad_label, mapping)
                    )
            else:
                total_streams = 1  # fallback: just the full image

            # Always run full-image OCR (5th stream, or only stream if no quadrants)
            loop.run_in_executor(
                None, make_stream_worker(image_data, "full", None)
            )

            async def rate_one(i, beer):
                """Rate a single beer, checking cache first."""
                async with semaphore:
                    if my_gen != self._scan_generation:
                        return

                    # Check cache for instant rating
                    cache_key = _normalize_beer_key(beer.name)
                    cached = rating_cache.get(cache_key)

                    if cached is not None:
                        if my_gen != self._scan_generation:
                            return
                        rated_beers_map[i] = cached
                        updater.update_card(i, cached)
                    else:
                        try:
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
                            rated_beers_map[i] = rating
                            updater.update_card(i, rating)
                        except Exception:
                            if my_gen != self._scan_generation:
                                return
                            updater.mark_failed(i)

                    completed[0] += 1
                    if my_gen == self._scan_generation and ocr_done[0]:
                        updater.set_progress(completed[0], len(ocr_beers))

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
                        # Duplicate — if from full image, update position
                        if source == "full" and data.y_position is not None:
                            existing_idx = seen_beers[key]
                            ocr_beers[existing_idx].y_position = data.y_position
                        continue

                    # New beer — add to UI and start rating
                    i = len(ocr_beers)
                    seen_beers[key] = i
                    ocr_beers.append(data)
                    updater.add_beer(i, data.name)
                    updater.update_header(len(ocr_beers))
                    task = asyncio.create_task(rate_one(i, data))
                    rating_tasks.append(task)

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

            # Switch progress to determinate now that we know the total
            ocr_done[0] = True
            updater.switch_to_determinate(completed[0], len(ocr_beers))

            # Wait for all rating tasks to complete
            if rating_tasks:
                await asyncio.gather(*rating_tasks)

            if my_gen != self._scan_generation:
                return

            # ── Finalize + annotate photo ──────────────────────────
            rated_beers = [rated_beers_map.get(i) for i in range(len(ocr_beers))]
            updater.finalize(rated_beers)

            # Save to scan history
            try:
                save_scan(self.paths.data, ocr_beers, rated_beers)
            except Exception:
                pass  # History save is non-critical

            try:
                # Filter both lists in tandem so index alignment is preserved
                # (annotate_image uses ocr_beers[i].y_position for rated_beers[i])
                paired = [
                    (ocr, rated)
                    for ocr, rated in zip(ocr_beers, rated_beers)
                    if rated is not None
                ]
                if paired:
                    valid_ocr, valid_rated = zip(*paired)
                    valid_ocr = list(valid_ocr)
                    valid_rated = list(valid_rated)
                else:
                    valid_ocr, valid_rated = [], []
                annotated = await loop.run_in_executor(
                    None,
                    self.agent.get_annotated_image,
                    image_data,
                    valid_ocr,
                    valid_rated,
                )
                if my_gen == self._scan_generation:
                    updater.add_photo_view(annotated)
            except Exception:
                pass  # Photo annotation is optional

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
