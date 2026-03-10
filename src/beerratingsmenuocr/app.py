"""BeerRated - Main Application."""

import asyncio
from pathlib import Path

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, CENTER, BOLD

from .ai_agent import BeerMenuAgent
from .ui_components import (
    build_home_view,
    build_incremental_results_view,
    build_results_view,
)


class BeerRatingsApp(toga.App):
    """Main application: scan beer menus and display ratings."""

    def startup(self):
        self.agent = BeerMenuAgent()
        self.content_box = toga.Box(style=Pack(direction=COLUMN, flex=1))
        self._scan_generation = 0  # incremented each scan; used to cancel stale ones
        self.progress_bar = None
        self.status_label = None

        self.main_window = toga.MainWindow(
            title=self.formal_name,
            size=(400, 700),
        )
        self.main_window.content = self.content_box

        self.show_home_view()
        self.main_window.show()

    # ── View management ──────────────────────────────────────────

    def show_home_view(self):
        # Cancel any in-flight scan so stale tasks don't update removed widgets
        self._scan_generation += 1
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
        )
        for w in widgets:
            self.content_box.add(w)

    def show_loading_view(self):
        self.content_box.clear()
        self.status_label = toga.Label(
            "Reading menu...",
            style=Pack(
                text_align=CENTER, font_size=16,
                padding_top=80, padding_bottom=20,
            ),
        )
        self.progress_bar = toga.ProgressBar(
            max=None,
            style=Pack(padding=20, width=300, alignment=CENTER),
        )
        self.progress_bar.start()
        self.content_box.add(self.status_label)
        self.content_box.add(self.progress_bar)

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
            file_path = await self.main_window.dialog(
                toga.OpenFileDialog(
                    "Select a Beer Menu Image",
                    file_types=["png", "jpg", "jpeg", "heic", "webp"],
                )
            )
            if file_path is not None:
                self.show_loading_view()
                await asyncio.sleep(0)  # yield so UI renders
                image = toga.Image(file_path)
                await self.process_image(image)
        except Exception as e:
            await self.main_window.dialog(
                toga.InfoDialog("Error", f"Could not load image: {e}")
            )

    def on_scan_another(self, widget, **kwargs):
        self.show_home_view()

    # ── AI processing pipeline ───────────────────────────────────

    async def process_image(self, image: toga.Image):
        """Run the incremental AI pipeline: OCR → rate in parallel → annotate.

        Phase 1: OCR the menu image to get beer names (~5s)
        Phase 2: Show beer list immediately, then rate beers in parallel
                 (3 concurrent) with real-time UI updates
        Phase 3: Enable sorting and add annotated photo view
        """
        # Claim a new scan generation; if the user navigates away mid-scan,
        # show_home_view() increments _scan_generation and we stop updating.
        self._scan_generation += 1
        my_gen = self._scan_generation

        if self.progress_bar is None:
            self.show_loading_view()
            await asyncio.sleep(0)
        loop = asyncio.get_event_loop()

        try:
            image_data = self._image_to_bytes(image)

            # ── Phase 1: OCR ──────────────────────────────────────
            self.status_label.text = "Reading menu..."
            ocr_result = await loop.run_in_executor(
                None, self.agent.ocr_image, image_data
            )

            if my_gen != self._scan_generation:
                return  # user navigated away

            if not ocr_result.beers:
                self.progress_bar.stop()
                self.progress_bar = None
                self.show_error_view(
                    "No beers found on this menu. Try a clearer photo."
                )
                return

            # ── Phase 2: Show list + rate in parallel ─────────────
            self.progress_bar.stop()
            self.progress_bar = None
            self.status_label = None
            self.content_box.clear()

            widgets, updater = build_incremental_results_view(
                ocr_beers=ocr_result.beers,
                on_scan_another=self.on_scan_another,
            )
            for w in widgets:
                self.content_box.add(w)

            # Yield so the placeholder cards render before we start rating
            await asyncio.sleep(0)

            total = len(ocr_result.beers)
            rated_beers = [None] * total
            completed = [0]  # mutable counter for closure
            semaphore = asyncio.Semaphore(3)  # max 3 concurrent API calls

            async def rate_one(i, beer):
                async with semaphore:
                    if my_gen != self._scan_generation:
                        return  # scan cancelled
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
                            return  # scan cancelled while waiting
                        rated_beers[i] = rating
                        updater.update_card(i, rating)
                    except Exception:
                        if my_gen != self._scan_generation:
                            return
                        updater.mark_failed(i)

                    completed[0] += 1
                    if my_gen == self._scan_generation:
                        updater.set_progress(completed[0], total)

            # Launch all rating tasks — semaphore limits to 3 concurrent
            tasks = [
                asyncio.create_task(rate_one(i, beer))
                for i, beer in enumerate(ocr_result.beers)
            ]
            await asyncio.gather(*tasks)

            if my_gen != self._scan_generation:
                return  # user navigated away during rating

            # ── Phase 3: Enable sorting + annotate photo ──────────
            updater.finalize(rated_beers)

            # Get annotated photo (non-blocking for the user)
            try:
                valid_rated = [r for r in rated_beers if r is not None]
                annotated = await loop.run_in_executor(
                    None,
                    self.agent.get_annotated_image,
                    image_data,
                    ocr_result.beers,
                    valid_rated,
                )
                if my_gen == self._scan_generation:
                    updater.add_photo_view(annotated)
            except Exception:
                pass  # Photo annotation is optional

        except Exception as e:
            if my_gen != self._scan_generation:
                return  # scan was superseded, don't show error
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
