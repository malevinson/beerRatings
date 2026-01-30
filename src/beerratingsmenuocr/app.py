"""Beer Ratings Menu OCR - Main Application."""

import asyncio
import os
from pathlib import Path

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, CENTER, BOLD

from .ai_agent import BeerMenuAgent
from .ui_components import build_home_view, build_results_view


class BeerRatingsApp(toga.App):
    """Main application: scan beer menus and display ratings."""

    def startup(self):
        self.agent = BeerMenuAgent()
        self.content_box = toga.Box(style=Pack(direction=COLUMN, flex=1))

        self.main_window = toga.MainWindow(
            title=self.formal_name,
            size=(400, 700),
        )
        self.main_window.content = self.content_box

        self.show_home_view()
        self.main_window.show()

    # ── View management ──────────────────────────────────────────

    def show_home_view(self):
        self.content_box.clear()
        widgets = build_home_view(
            on_take_photo=self.on_take_photo,
            on_select_image=self.on_select_image,
        )
        for w in widgets:
            self.content_box.add(w)

        # Debug mode: add a button to load a test image
        if os.environ.get("DEBUG_MODE"):
            self.content_box.add(
                toga.Button(
                    "[DEBUG] Use Test Image",
                    on_press=self.on_debug_test,
                    style=Pack(padding=10, width=250, alignment=CENTER),
                )
            )

    def show_loading_view(self):
        self.content_box.clear()
        self.status_label = toga.Label(
            "Analyzing menu...",
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

    def show_results_view(self, beers: list):
        self.content_box.clear()
        widgets = build_results_view(
            beers=beers,
            on_scan_another=self.on_scan_another,
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
                image = toga.Image(file_path)
                await self.process_image(image)
        except Exception as e:
            await self.main_window.dialog(
                toga.InfoDialog("Error", f"Could not load image: {e}")
            )

    async def on_debug_test(self, widget, **kwargs):
        """Load a test image from the resources directory."""
        test_path = Path(__file__).parent / "resources" / "test_menu.jpg"
        if test_path.exists():
            image = toga.Image(test_path)
            await self.process_image(image)
        else:
            await self.main_window.dialog(
                toga.InfoDialog(
                    "No Test Image",
                    f"Place a test image at:\n{test_path}",
                )
            )

    def on_scan_another(self, widget, **kwargs):
        self.show_home_view()

    # ── AI processing pipeline ───────────────────────────────────

    async def process_image(self, image: toga.Image):
        """Run the two-step AI pipeline: OCR → ratings lookup."""
        self.show_loading_view()
        loop = asyncio.get_event_loop()

        try:
            # Get image bytes
            image_data = self._image_to_bytes(image)

            # Step 1: Identify beers from the menu image
            self.status_label.text = "Reading the menu..."
            beers_identified = await loop.run_in_executor(
                None, self.agent.identify_beers_from_image, image_data
            )

            if not beers_identified:
                self.show_error_view(
                    "No beers found on this menu. Try a clearer photo."
                )
                return

            # Step 2: Look up ratings
            self.status_label.text = (
                f"Found {len(beers_identified)} beers. Looking up ratings..."
            )
            rated_beers = await loop.run_in_executor(
                None, self.agent.get_beer_ratings, beers_identified
            )

            # Step 3: Display results
            self.progress_bar.stop()
            self.show_results_view(rated_beers)

        except Exception as e:
            self.progress_bar.stop()
            self.show_error_view(f"AI processing failed: {e}")

    @staticmethod
    def _image_to_bytes(image: toga.Image) -> bytes:
        """Extract raw bytes from a toga.Image."""
        # toga.Image.data returns bytes on most backends
        if hasattr(image, "data") and image.data:
            return image.data

        # Fallback: save to a buffer
        import io

        if hasattr(image, "save"):
            buf = io.BytesIO()
            image.save(buf)
            return buf.getvalue()

        # Last resort: read from the source path
        if hasattr(image, "path") and image.path:
            return Path(image.path).read_bytes()

        raise ValueError("Cannot extract bytes from toga.Image")


def main():
    return BeerRatingsApp(
        "Beer Ratings Menu OCR",
        "com.mattlevinson.beerratingsmenuocr",
    )
