"""BeerRated - Main Application."""

import asyncio
from pathlib import Path

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, CENTER, BOLD

from .ai_agent import BeerMenuAgent
from .history import save_scan
from .ui_components import (
    build_home_view,
    build_history_list_view,
    build_history_detail_view,
    build_incremental_results_view,
    build_results_view,
    build_streaming_results_view,
)


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
        """Run the streaming AI pipeline: stream OCR → rate each immediately → annotate.

        Beers appear on screen one-by-one as OCR streams them in.
        Each beer's rating starts fetching the moment it's identified.
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

            # ── Stream OCR via background thread + asyncio.Queue ───
            beer_queue = asyncio.Queue()
            ocr_beers = []
            rated_beers_map = {}
            rating_tasks = []
            completed = [0]
            semaphore = asyncio.Semaphore(3)

            def stream_worker():
                try:
                    for event_type, data in self.agent.ocr_image_stream(image_data):
                        if my_gen != self._scan_generation:
                            return
                        loop.call_soon_threadsafe(
                            beer_queue.put_nowait, (event_type, data)
                        )
                except Exception as e:
                    loop.call_soon_threadsafe(
                        beer_queue.put_nowait, ("error", str(e))
                    )
                finally:
                    loop.call_soon_threadsafe(
                        beer_queue.put_nowait, ("_end", None)
                    )

            loop.run_in_executor(None, stream_worker)

            async def rate_one(i, beer):
                async with semaphore:
                    if my_gen != self._scan_generation:
                        return
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

            # ── Consume streaming events ───────────────────────────
            menu_notes = None
            ocr_done = [False]
            stream_error = None

            while True:
                event_type, data = await beer_queue.get()
                if my_gen != self._scan_generation:
                    return

                if event_type == "_end":
                    break
                elif event_type == "error":
                    stream_error = data
                    break
                elif event_type == "beer":
                    i = len(ocr_beers)
                    ocr_beers.append(data)
                    updater.add_beer(i, data.name)
                    updater.update_header(len(ocr_beers))
                    # Immediately start rating this beer
                    task = asyncio.create_task(rate_one(i, data))
                    rating_tasks.append(task)
                elif event_type == "done":
                    menu_notes = data
                    ocr_done[0] = True

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
                valid_rated = [r for r in rated_beers if r is not None]
                annotated = await loop.run_in_executor(
                    None,
                    self.agent.get_annotated_image,
                    image_data,
                    ocr_beers,
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


def main():
    return BeerRatingsApp(
        "BeerRated",
        "com.mattlevinson.beerratingsmenuocr",
    )
