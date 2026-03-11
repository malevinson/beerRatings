"""Reusable UI components for the beer ratings app."""

from pathlib import Path

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER, BOLD

_ICON_PATH = Path(__file__).parent / "resources" / "beerratingsmenuocr-1024.png"


ACTIVE_COLOR = "#007AFF"
INACTIVE_COLOR = "#888888"
ARROW_DOWN = " \u25BC"
ARROW_UP = " \u25B2"

# Maps granular beer substyles to broader display categories.
_STYLE_CATEGORIES = {
    "ipa": "IPA", "india pale ale": "IPA", "neipa": "IPA",
    "new england ipa": "IPA", "hazy ipa": "IPA", "double ipa": "IPA",
    "imperial ipa": "IPA", "west coast ipa": "IPA", "session ipa": "IPA",
    "stout": "Stout", "imperial stout": "Stout", "milk stout": "Stout",
    "oatmeal stout": "Stout", "pastry stout": "Stout",
    "porter": "Porter", "baltic porter": "Porter", "robust porter": "Porter",
    "lager": "Lager", "pilsner": "Lager", "helles": "Lager",
    "vienna lager": "Lager", "mexican lager": "Lager",
    "pale ale": "Pale Ale", "american pale ale": "Pale Ale",
    "wheat": "Wheat", "hefeweizen": "Wheat", "witbier": "Wheat",
    "belgian wit": "Wheat",
    "sour": "Sour", "gose": "Sour", "berliner weisse": "Sour",
    "fruited sour": "Sour", "kettle sour": "Sour",
    "amber": "Amber/Red", "red ale": "Amber/Red", "amber ale": "Amber/Red",
    "brown ale": "Brown Ale", "english brown ale": "Brown Ale",
    "saison": "Saison", "farmhouse ale": "Saison",
    "belgian": "Belgian", "belgian blonde": "Belgian",
    "tripel": "Belgian", "dubbel": "Belgian", "quad": "Belgian",
    "kölsch": "Kölsch", "kolsch": "Kölsch",
    "blonde ale": "Blonde", "golden ale": "Blonde",
    "barleywine": "Barleywine", "barley wine": "Barleywine",
    "cream ale": "Cream Ale",
    "scotch ale": "Scotch Ale", "wee heavy": "Scotch Ale",
}


# Color coding for style filter tags by beer family.
_STYLE_COLORS = {
    # Ales — Hoppy
    "IPA":        {"color": "#8b4513", "bg": "#ffe0b2"},  # orange-amber
    "Pale Ale":   {"color": "#8b4513", "bg": "#ffe0b2"},
    # Ales — Dark
    "Stout":      {"color": "#ffffff", "bg": "#4e342e"},  # dark brown
    "Porter":     {"color": "#ffffff", "bg": "#5d4037"},
    "Brown Ale":  {"color": "#ffffff", "bg": "#6d4c41"},
    # Ales — Wheat
    "Wheat":      {"color": "#7c6200", "bg": "#fff9c4"},  # golden yellow
    # Ales — Belgian & Sour
    "Belgian":    {"color": "#4a148c", "bg": "#e1bee7"},  # plum/purple
    "Saison":     {"color": "#4a148c", "bg": "#e1bee7"},
    "Sour":       {"color": "#880e4f", "bg": "#fce4ec"},  # rose pink
    # Lagers
    "Lager":      {"color": "#1b5e20", "bg": "#c8e6c9"},  # crisp green
    "Kölsch":     {"color": "#1b5e20", "bg": "#c8e6c9"},
    "Cream Ale":  {"color": "#1b5e20", "bg": "#c8e6c9"},
    # Other
    "Amber/Red":  {"color": "#b71c1c", "bg": "#ffcdd2"},  # red
    "Blonde":     {"color": "#f57f17", "bg": "#fff9c4"},  # light gold
    "Barleywine": {"color": "#bf360c", "bg": "#ffccbc"},  # deep amber
    "Scotch Ale": {"color": "#bf360c", "bg": "#ffccbc"},
}
_DEFAULT_STYLE_COLOR = {"color": "#555555", "bg": "#e0e0e0"}  # neutral gray


def _normalize_style(raw_style: str) -> str:
    """Map a detailed beer style to a broad display category."""
    lower = raw_style.strip().lower()
    # Try exact match first
    if lower in _STYLE_CATEGORIES:
        return _STYLE_CATEGORIES[lower]
    # Try substring match (longest first to prefer more specific)
    for key in sorted(_STYLE_CATEGORIES, key=len, reverse=True):
        if key in lower:
            return _STYLE_CATEGORIES[key]
    # Fallback: title-case the raw style
    return raw_style.strip().title()


def _valid_hex_color(c):
    """Return a valid 7-char hex color string, or None if malformed."""
    if not isinstance(c, str):
        return None
    c = c.strip().lstrip("#")
    if len(c) == 3:
        c = c[0]*2 + c[1]*2 + c[2]*2
    if len(c) != 6:
        return None
    try:
        int(c, 16)
    except ValueError:
        return None
    return f"#{c}"


def _sort_colors_light_to_dark(colors):
    """Sort hex colors from lightest to darkest by perceived luminance."""
    valid = [_valid_hex_color(c) for c in colors]
    valid = [c for c in valid if c is not None]
    def luminance(hex_color):
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return 0.299 * r + 0.587 * g + 0.114 * b
    return sorted(valid, key=luminance, reverse=True)  # lightest first


def build_home_view(on_take_photo, on_select_image, on_history=None) -> list:
    """Build the home screen widgets."""

    # App icon
    logo_box = toga.Box(style=Pack(direction=COLUMN, alignment=CENTER, padding_top=40))
    try:
        logo_image = toga.Image(_ICON_PATH)
        logo_view = toga.ImageView(
            logo_image,
            style=Pack(width=120, height=120, alignment=CENTER),
        )
        logo_box.add(logo_view)
    except Exception:
        pass  # Skip logo if image can't be loaded

    title = toga.Label(
        "BeerRated",
        style=Pack(
            text_align=CENTER,
            font_size=24,
            font_weight=BOLD,
            padding_top=12,
            padding_bottom=4,
        ),
    )

    subtitle = toga.Label(
        "Take a photo of a beer menu to get\ninstant ratings and details",
        style=Pack(
            text_align=CENTER,
            font_size=14,
            padding_bottom=30,
        ),
    )

    camera_btn = toga.Button(
        "Take Photo",
        on_press=on_take_photo,
        style=Pack(padding=10, width=250, alignment=CENTER, font_size=16),
    )

    library_btn = toga.Button(
        "Select from Library",
        on_press=on_select_image,
        style=Pack(padding=10, width=250, alignment=CENTER, font_size=16),
    )

    button_box = toga.Box(
        style=Pack(direction=COLUMN, alignment=CENTER, padding=20),
        children=[camera_btn, library_btn],
    )

    widgets = [logo_box, title, subtitle, button_box]

    if on_history is not None:
        history_btn = toga.Button(
            "History",
            on_press=on_history,
            style=Pack(
                padding=5, width=250, alignment=CENTER,
                font_size=14, color=ACTIVE_COLOR,
            ),
        )
        history_box = toga.Box(
            style=Pack(direction=COLUMN, alignment=CENTER),
            children=[history_btn],
        )
        widgets.append(history_box)

    return widgets


def build_settings_view(current_url, on_save, on_cancel) -> list:
    """Build the settings screen for configuring the server URL."""
    title = toga.Label(
        "Settings",
        style=Pack(
            text_align=CENTER,
            font_size=22,
            font_weight=BOLD,
            padding_top=40,
            padding_bottom=20,
        ),
    )

    hint = toga.Label(
        "Enter your server's IP address.\n"
        "Mac: ipconfig getifaddr en0\n"
        "Windows: ipconfig | findstr IPv4\n"
        "Linux: hostname -I",
        style=Pack(text_align=CENTER, font_size=12, color="#777777", padding_bottom=10),
    )

    ip_label = toga.Label(
        "Server URL:",
        style=Pack(font_size=14, padding_left=30, padding_bottom=4),
    )

    url_input = toga.TextInput(
        value=current_url,
        placeholder="http://192.168.x.x:8888",
        style=Pack(padding_left=30, padding_right=30, padding_bottom=20, width=340),
    )

    save_btn = toga.Button(
        "Save",
        on_press=lambda w: on_save(url_input.value.strip()),
        style=Pack(padding=10, width=250, alignment=CENTER, font_size=16),
    )

    cancel_btn = toga.Button(
        "Cancel",
        on_press=on_cancel,
        style=Pack(padding=10, width=250, alignment=CENTER, font_size=14),
    )

    button_box = toga.Box(
        style=Pack(direction=COLUMN, alignment=CENTER, padding=10),
        children=[save_btn, cancel_btn],
    )

    return [title, hint, ip_label, url_input, button_box]


# ── Incremental results view ─────────────────────────────────────


class ResultsUpdater:
    """Manages in-place updates to the results view as ratings arrive.

    Sort buttons are visible from the start so the user can sort by name
    immediately (all names are known from OCR) or by rating as they arrive.
    Cards are reordered dynamically — no full rebuild needed.

    Built by build_incremental_results_view(). The app calls:
      - set_progress(current, total) after each rating completes
      - update_card(index, rating) when a rating arrives
      - mark_failed(index) if a rating fails
      - finalize(rated_beers) when all ratings are done
    """

    def __init__(self, card_refs, card_widgets, beer_names,
                 progress_label, progress_bar,
                 content_box, list_scroll, header_box, view_container,
                 on_scan_another, sort_box, sort_buttons,
                 header_label=None, filter_box=None, filter_rows=None):
        self.card_refs = card_refs       # list of dicts with label references
        self._card_widgets = card_widgets  # card Box widgets, indexed by OCR order
        self._beer_names = beer_names      # original names for name-sorting
        self.progress_label = progress_label
        self.progress_bar = progress_bar
        self.content_box = content_box   # the box inside list_scroll
        self.list_scroll = list_scroll
        self.header_box = header_box
        self.view_container = view_container
        self.on_scan_another = on_scan_another
        self._sort_box = sort_box
        self._header_label = header_label

        self._btn_default, self._btn_rating, self._btn_name, self._btn_style = sort_buttons
        self._all_sort_buttons = list(sort_buttons)

        self._ratings = [None] * len(card_widgets)
        self._sort_mode = "default"
        self._sort_state = {"rating_desc": True, "name_desc": False, "style_desc": False}

        # Loading animation state
        self._loading = True
        self._dot_phase = 0  # cycles 0→1→2 for ". " ".. " "..."

        # ".." indicator below the last card in the list
        self._loading_indicator = toga.Label(
            "..",
            style=Pack(
                font_size=14, color="#999999",
                padding_top=4, padding_bottom=8,
                alignment=CENTER,
            ),
        )
        self.content_box.add(self._loading_indicator)

        # Style filter state
        self._filter_box = filter_box
        self._filter_rows = list(filter_rows) if filter_rows else []
        self._max_per_row = 5
        self._card_styles = {}        # card index → normalized style string
        self._hidden_styles = set()   # styles the user has toggled off
        self._style_buttons = {}      # style string → Button widget
        self._style_colors_cache = {} # style string → {"color": ..., "bg": ...}

        # "All" reset button — shown when any filter is active
        self._all_btn = toga.Button(
            "All",
            on_press=self._on_reset_filters,
            style=Pack(
                font_size=8, padding_top=0, padding_bottom=0,
                padding_left=4, padding_right=4,
                color="#007AFF",
            ),
        )
        self._all_btn_visible = False

        # Placeholder style tag shown during loading
        self._placeholder_tag = toga.Label(
            "...",
            style=Pack(
                font_size=8, padding_top=0, padding_bottom=0,
                padding_left=4, padding_right=4,
                color="#999999", background_color="#e8e8e8",
            ),
        )
        self._placeholder_visible = False
        if self._filter_rows:
            self._filter_rows[0].add(self._placeholder_tag)
            self._placeholder_visible = True

        # Wire up sort handlers
        self._btn_default.on_press = self._on_sort_default
        self._btn_rating.on_press = self._on_sort_rating
        self._btn_name.on_press = self._on_sort_name
        self._btn_style.on_press = self._on_sort_style

    # ── Sorting ───────────────────────────────────────────────────

    def _set_active(self, active_btn):
        for btn in self._all_sort_buttons:
            btn.style.color = ACTIVE_COLOR if btn is active_btn else INACTIVE_COLOR

    def _update_sort_labels(self):
        s = self._sort_state
        self._btn_rating.text = (
            ("BA Rating" + (ARROW_DOWN if s["rating_desc"] else ARROW_UP))
            if self._sort_mode.startswith("rating") else "BA Rating"
        )
        self._btn_name.text = (
            ("Name" + (ARROW_UP if not s["name_desc"] else ARROW_DOWN))
            if self._sort_mode.startswith("name") else "Name"
        )
        self._btn_style.text = (
            ("Style" + (ARROW_DOWN if s["style_desc"] else ARROW_UP))
            if self._sort_mode.startswith("style") else "Style"
        )

    def _on_sort_default(self, widget):
        self._sort_mode = "default"
        self._set_active(self._btn_default)
        self._update_sort_labels()
        self._apply_sort()

    def _on_sort_rating(self, widget):
        if self._sort_mode.startswith("rating"):
            self._sort_state["rating_desc"] = not self._sort_state["rating_desc"]
        else:
            self._sort_state["rating_desc"] = True
        self._sort_mode = "rating_desc" if self._sort_state["rating_desc"] else "rating_asc"
        self._set_active(self._btn_rating)
        self._update_sort_labels()
        self._apply_sort()

    def _on_sort_name(self, widget):
        if self._sort_mode.startswith("name"):
            self._sort_state["name_desc"] = not self._sort_state["name_desc"]
        else:
            self._sort_state["name_desc"] = False
        self._sort_mode = "name_desc" if self._sort_state["name_desc"] else "name_asc"
        self._set_active(self._btn_name)
        self._update_sort_labels()
        self._apply_sort()

    def _on_sort_style(self, widget):
        if self._sort_mode.startswith("style"):
            self._sort_state["style_desc"] = not self._sort_state["style_desc"]
        else:
            self._sort_state["style_desc"] = False
        self._sort_mode = "style_desc" if self._sort_state["style_desc"] else "style_asc"
        self._set_active(self._btn_style)
        self._update_sort_labels()
        self._apply_sort()

    def _get_sorted_indices(self):
        n = len(self._card_widgets)
        indices = list(range(n))

        if self._sort_mode == "default":
            return indices

        if self._sort_mode.startswith("rating"):
            desc = self._sort_state["rating_desc"]

            def rating_key(i):
                r = self._ratings[i]
                if r is None or r.rating_beer_advocate is None:
                    return -1 if desc else 999
                return r.rating_beer_advocate

            indices.sort(key=rating_key, reverse=desc)

        elif self._sort_mode.startswith("name"):
            desc = self._sort_state["name_desc"]
            indices.sort(
                key=lambda i: self._beer_names[i].lower(), reverse=desc,
            )

        elif self._sort_mode.startswith("style"):
            desc = self._sort_state["style_desc"]
            indices.sort(
                key=lambda i: self._card_styles.get(i, "\uffff").lower(),
                reverse=desc,
            )

        return indices

    def _get_visible_indices(self):
        """Get sorted indices, then filter out hidden styles."""
        indices = self._get_sorted_indices()
        if not self._hidden_styles:
            return indices
        return [i for i in indices
                if self._card_styles.get(i) not in self._hidden_styles]

    def _apply_sort(self):
        """Reorder card widgets inside cards_box to match current sort + filter."""
        indices = self._get_visible_indices()
        self.content_box.clear()
        for i in indices:
            self.content_box.add(self._card_widgets[i])
        # Keep loading indicator at the bottom
        if self._loading:
            self.content_box.add(self._loading_indicator)

    # ── Dynamic card addition (streaming mode) ─────────────────────

    def add_beer(self, index, beer_name):
        """Dynamically add a new beer card during streaming OCR."""
        card, refs = _build_placeholder_card(index + 1, beer_name)
        self.card_refs.append(refs)
        self._card_widgets.append(card)
        self._beer_names.append(beer_name)
        self._ratings.append(None)
        # Remove loading indicator, add card, re-add indicator at end
        if self._loading:
            try:
                self.content_box.remove(self._loading_indicator)
            except ValueError:
                pass
        self.content_box.add(card)
        if self._loading:
            self.content_box.add(self._loading_indicator)

    def update_header(self, count):
        """Update the header label with the current beer count."""
        if self._header_label is not None:
            if self._loading:
                self._dot_phase = (self._dot_phase + 1) % 3
                dots = "." * (self._dot_phase + 1)
                self._header_label.text = f"Found {count} Beers{dots}"
                self._update_placeholder_animation()
            else:
                self._header_label.text = f"Found {count} Beers"

    def _update_placeholder_animation(self):
        """Cycle the placeholder style tag and list loading indicator."""
        dots = "." * (self._dot_phase + 1)
        # Animate the list loading indicator
        if self._loading:
            self._loading_indicator.text = dots
        # Animate the placeholder style tag
        if not self._placeholder_visible:
            return
        self._placeholder_tag.text = dots
        # Pulse opacity via color: alternate between lighter and darker gray
        opacity_colors = ["#cccccc", "#aaaaaa", "#999999"]
        self._placeholder_tag.style.color = opacity_colors[self._dot_phase]
        bg_colors = ["#f0f0f0", "#e8e8e8", "#e0e0e0"]
        self._placeholder_tag.style.background_color = bg_colors[self._dot_phase]

    def _remove_placeholder_tag(self):
        """Remove the loading placeholder from the style filter row."""
        if not self._placeholder_visible:
            return
        self._placeholder_visible = False
        for row in self._filter_rows:
            try:
                row.remove(self._placeholder_tag)
            except (ValueError, AttributeError):
                pass

    def _check_loading_complete(self):
        """Check if enough beers are rated to remove the placeholder tag."""
        if not self._loading:
            return
        total = len(self._card_widgets)
        if total == 0:
            return
        rated = sum(1 for r in self._ratings if r is not None)
        # Remove placeholder when ≥2/3 of beers are rated
        if rated >= (total * 2 / 3):
            self._loading = False
            self._remove_placeholder_tag()
            try:
                self.content_box.remove(self._loading_indicator)
            except ValueError:
                pass

    def switch_to_determinate(self, current, total):
        """Switch from indeterminate to determinate progress bar."""
        try:
            self.progress_bar.stop()
        except Exception:
            pass
        self.progress_bar.max = total
        self.progress_bar.value = current
        self.progress_label.text = f"Rated {current} of {total}..."

    # ── Progress + card updates ───────────────────────────────────

    def set_progress(self, current: int, total: int):
        """Update the progress indicator."""
        if self._loading:
            dots = "." * (self._dot_phase + 1)
            self.progress_label.text = f"Rated {current} of {total}{dots}"
        else:
            self.progress_label.text = f"Rated {current} of {total}..."
        self.progress_bar.value = current
        self.progress_bar.max = total

    def update_card(self, index: int, rating):
        """Update a single beer card in-place with its rating data."""
        refs = self.card_refs[index]
        self._ratings[index] = rating
        tier = _get_rating_tier(rating)

        # Update rating labels (neutral colors — no tier coloring)
        if rating.rating_untappd is not None:
            refs["untappd_prefix"].text = "Untappd"
            refs["untappd_prefix"].style.color = "#666666"
            refs["untappd"].text = f"\u2605 {rating.rating_untappd:.1f}"
            refs["untappd"].style.color = "#666666"
        else:
            refs["untappd_prefix"].text = ""
            refs["untappd"].text = ""

        if rating.rating_beer_advocate is not None:
            refs["ba"].text = f"BA: {rating.rating_beer_advocate}"
            refs["ba"].style.color = "#666666"
            refs["ba"].style.background_color = "#e8e8e8"
        else:
            refs["ba"].text = ""

        # Brand color dots (sorted lightest→darkest for contrast near name)
        if rating.brand_colors:
            sorted_colors = _sort_colors_light_to_dark(rating.brand_colors[:4])
            for j, color in enumerate(sorted_colors):
                refs["color_dots"][j].text = "\u25cf"
                refs["color_dots"][j].style.color = color

        # Brewery + ABV on same row
        brewery_text = rating.brewery or "Unknown Brewery"
        if rating.abv:
            brewery_text += f" \u00b7 {rating.abv}"
        refs["brewery"].text = brewery_text
        refs["tier"].text = tier["label"]
        refs["tier"].style.color = "#888888"

        refs["description"].text = rating.description

        # Confidence — only show if NOT high
        if rating.confidence and rating.confidence != "high":
            confidence_color = {
                "medium": "#f57f17", "low": "#c62828",
            }.get(rating.confidence, "#888888")
            refs["confidence"].text = f"Confidence: {rating.confidence}"
            refs["confidence"].style.color = confidence_color
            refs["confidence"].style.padding_top = 2
        else:
            refs["confidence"].text = ""
            refs["confidence"].style.padding_top = 0

        refs["divider"].style.color = tier["accent"]

        # Hide loading status
        refs["status"].text = ""
        refs["status"].style.padding_top = 0

        # Style tag next to beer name + filter tag
        if rating.style:
            category = _normalize_style(rating.style)
            colors = _STYLE_COLORS.get(category, _DEFAULT_STYLE_COLOR)
            refs["style_tag"].text = category
            refs["style_tag"].style.color = colors["color"]
            refs["style_tag"].style.background_color = colors["bg"]

            self._card_styles[index] = category
            if self._filter_box is not None and category not in self._style_buttons:
                self._add_style_tag(category)

        # Advance loading animation and check if we should remove placeholder
        if self._loading:
            self._dot_phase = (self._dot_phase + 1) % 3
            self._update_placeholder_animation()
            self._check_loading_complete()

    def update_card_primary(self, index: int, quick_rating: dict):
        """Phase 1: Update card with brewery + BA score (no description/style yet)."""
        refs = self.card_refs[index]

        # BA rating badge
        ba_score = quick_rating.get("rating_beer_advocate")
        if ba_score is not None:
            refs["ba"].text = f"BA: {ba_score}"
            refs["ba"].style.color = "#666666"
            refs["ba"].style.background_color = "#e8e8e8"

        # Brewery
        brewery = quick_rating.get("brewery", "")
        if brewery:
            refs["brewery"].text = brewery

        # Confidence — only show if NOT high
        confidence = quick_rating.get("confidence", "")
        if confidence and confidence != "high":
            confidence_color = {
                "medium": "#f57f17", "low": "#c62828",
            }.get(confidence, "#888888")
            refs["confidence"].text = f"Confidence: {confidence}"
            refs["confidence"].style.color = confidence_color
            refs["confidence"].style.padding_top = 2
        else:
            refs["confidence"].text = ""
            refs["confidence"].style.padding_top = 0

        # Show animated placeholder for description
        refs["description"].text = "..."
        refs["status"].text = "Loading details..."
        refs["status"].style.color = "#999999"
        refs["status"].style.padding_top = 2

    def _add_style_tag(self, style):
        """Create a color-coded toggle tag for a beer style."""
        colors = _STYLE_COLORS.get(style, _DEFAULT_STYLE_COLOR)
        self._style_colors_cache[style] = colors

        def on_press(widget):
            self._on_toggle_style(style)

        btn = toga.Button(
            f"{style} \u2715",
            on_press=on_press,
            style=Pack(
                font_size=8, padding_top=0, padding_bottom=0,
                padding_left=2, padding_right=4,
                color=colors["color"],
                background_color=colors["bg"],
            ),
        )
        self._style_buttons[style] = btn
        # Remove placeholder temporarily so new tag goes before it
        if self._placeholder_visible:
            for row in self._filter_rows:
                try:
                    row.remove(self._placeholder_tag)
                except (ValueError, AttributeError):
                    pass
        # Add to appropriate row, creating new rows as needed
        self._add_btn_to_row(btn)
        # Re-add placeholder at the end (always last)
        if self._placeholder_visible:
            self._filter_rows[-1].add(self._placeholder_tag)

    def _add_btn_to_row(self, btn):
        """Add a button to the correct filter row, creating new rows as needed."""
        # Count existing tag buttons (exclude "Style:" label, "All" btn, placeholder)
        total_tags = len(self._style_buttons)
        # "All" button occupies a slot in row 0 when visible
        row_idx = (total_tags - 1) // self._max_per_row
        while row_idx >= len(self._filter_rows):
            new_row = toga.Box(style=Pack(
                direction=ROW, padding_left=10, padding_right=14,
                padding_bottom=1, alignment=CENTER,
            ))
            self._filter_rows.append(new_row)
            if self._filter_box is not None:
                self._filter_box.add(new_row)
        self._filter_rows[row_idx].add(btn)

    def _on_toggle_style(self, style):
        """Toggle a style filter: hide or show beers of this style."""
        btn = self._style_buttons.get(style)
        if btn is None:
            return
        if style in self._hidden_styles:
            # Re-activate: show beers, restore colored styling
            self._hidden_styles.discard(style)
            colors = self._style_colors_cache.get(
                style, _DEFAULT_STYLE_COLOR,
            )
            btn.text = f"{style} \u2715"
            btn.style.color = colors["color"]
            btn.style.background_color = colors["bg"]
        else:
            # Deactivate: hide beers, gray out
            self._hidden_styles.add(style)
            btn.text = style
            btn.style.color = "#999999"
            btn.style.background_color = "#e8e8e8"
        # Show/hide "All" button
        self._update_all_btn_visibility()
        self._apply_sort()

    def _update_all_btn_visibility(self):
        """Show 'All' button when any filters active, hide when none."""
        if not self._filter_rows:
            return
        row1 = self._filter_rows[0]
        if self._hidden_styles and not self._all_btn_visible:
            # Insert after the "Style:" label (index 1)
            row1.insert(1, self._all_btn)
            self._all_btn_visible = True
        elif not self._hidden_styles and self._all_btn_visible:
            try:
                row1.remove(self._all_btn)
            except ValueError:
                pass
            self._all_btn_visible = False

    def _on_reset_filters(self, widget):
        """Clear all hidden style filters, restore all beers."""
        self._hidden_styles.clear()
        # Re-color all buttons back to active state
        for style, btn in self._style_buttons.items():
            colors = self._style_colors_cache.get(
                style, _DEFAULT_STYLE_COLOR,
            )
            btn.text = f"{style} \u2715"
            btn.style.color = colors["color"]
            btn.style.background_color = colors["bg"]
        # Hide "All" button
        self._update_all_btn_visibility()
        self._apply_sort()

    def _redistribute_style_tags(self):
        """Rebalance style tag buttons across filter rows (dynamic count)."""
        if not self._filter_rows:
            return
        # Collect all current buttons in order
        buttons = list(self._style_buttons.values())
        # Clear all rows (keep "Style:" label in row0, remove extra rows)
        row0 = self._filter_rows[0]
        while len(row0.children) > 1:
            row0.remove(row0.children[-1])
        for extra_row in self._filter_rows[1:]:
            extra_row.clear()
            if self._filter_box is not None:
                try:
                    self._filter_box.remove(extra_row)
                except ValueError:
                    pass
        self._filter_rows = [row0]
        # Re-add "All" button if needed
        if self._all_btn_visible:
            row0.add(self._all_btn)
        # Re-add all tag buttons using index-based row assignment
        for i, btn in enumerate(buttons):
            row_idx = i // self._max_per_row
            while row_idx >= len(self._filter_rows):
                new_row = toga.Box(style=Pack(
                    direction=ROW, padding_left=10, padding_right=14,
                    padding_bottom=1, alignment=CENTER,
                ))
                self._filter_rows.append(new_row)
                if self._filter_box is not None:
                    self._filter_box.add(new_row)
            self._filter_rows[row_idx].add(btn)
        # Re-add placeholder at the end if visible
        if self._placeholder_visible:
            self._filter_rows[-1].add(self._placeholder_tag)

    def mark_failed(self, index: int):
        """Mark a beer card as failed to rate."""
        refs = self.card_refs[index]
        refs["status"].text = "Rating unavailable"
        refs["status"].style.color = "#c62828"
        refs["untappd"].text = ""
        refs["ba"].text = ""

    def finalize(self, rated_beers):
        """All ratings done. Hide progress and do a final re-sort."""
        self._ratings = list(rated_beers)
        self.progress_label.text = "All ratings loaded"
        self.progress_bar.max = 1
        self.progress_bar.value = 1

        # Stop loading animation, remove placeholder and loading indicator
        self._loading = False
        self._remove_placeholder_tag()
        try:
            self.content_box.remove(self._loading_indicator)
        except ValueError:
            pass

        # Update header to final state (no trailing dots)
        if self._header_label is not None:
            total = len(self._card_widgets)
            self._header_label.text = f"Found {total} Beers"

        # Final re-sort with complete data
        if self._sort_mode != "default":
            self._apply_sort()


def build_incremental_results_view(ocr_beers, on_scan_another, thumbnail=None):
    """Build the results screen with placeholder cards for incremental updates.

    Sort buttons are shown immediately — name sort works right away since
    all names are known from OCR, and rating sort works with partial data
    (unrated beers are placed at the bottom).

    Args:
        ocr_beers: list of OcrBeer from the OCR step (names only, no ratings)
        on_scan_another: callback for the "Scan Another" button
        thumbnail: optional JPEG bytes for a menu thumbnail in the header

    Returns:
        (widgets_list, ResultsUpdater) — widgets to add to content_box,
        and an updater object for in-place card updates.
    """
    total = len(ocr_beers)

    # ── Header ─────────────────────────────────────────────────────
    header_box = toga.Box(style=Pack(direction=ROW, padding=10, alignment=CENTER))
    header_box.add(
        toga.Label(
            f"Found {total} Beers",
            style=Pack(font_size=20, font_weight=BOLD, flex=1, padding_left=10),
        )
    )
    if thumbnail:
        try:
            thumb_img = toga.Image(data=thumbnail)
            header_box.add(toga.ImageView(
                thumb_img,
                style=Pack(width=35, height=50, padding_right=8),
            ))
        except Exception:
            pass
    header_box.add(
        toga.Button(
            "Scan Another",
            on_press=on_scan_another,
            style=Pack(padding=5),
        )
    )

    # ── Progress indicator ─────────────────────────────────────────
    progress_label = toga.Label(
        f"Rating 1 of {total}...",
        style=Pack(
            font_size=13, color="#777777",
            padding_left=20, padding_bottom=2,
        ),
    )
    progress_bar = toga.ProgressBar(
        max=total, value=0,
        style=Pack(padding_left=20, padding_right=20, padding_bottom=5, height=6),
    )

    # ── Sort controls (active from the start) ──────────────────────
    btn_default = toga.Button("Menu order", style=Pack(font_size=10, padding_top=2, padding_bottom=2, padding_left=2, padding_right=4, color=ACTIVE_COLOR))
    btn_rating = toga.Button("BA Rating", style=Pack(font_size=10, padding_top=2, padding_bottom=2, padding_left=2, padding_right=4, color=INACTIVE_COLOR))
    btn_name = toga.Button("Name", style=Pack(font_size=10, padding_top=2, padding_bottom=2, padding_left=2, padding_right=4, color=INACTIVE_COLOR))
    btn_style = toga.Button("Style", style=Pack(font_size=10, padding_top=2, padding_bottom=2, padding_left=2, padding_right=4, color=INACTIVE_COLOR))

    sort_box = toga.Box(style=Pack(direction=ROW, padding_left=10, padding_right=10, padding_bottom=2, alignment=CENTER))
    sort_box.add(toga.Label("Sort:", style=Pack(font_size=10, color="#777777", padding_right=4)))
    sort_box.add(btn_default)
    sort_box.add(btn_rating)
    sort_box.add(btn_name)
    sort_box.add(btn_style)

    # ── Placeholder cards ──────────────────────────────────────────
    cards_box = toga.Box(style=Pack(direction=COLUMN, padding=5))
    card_refs = []
    card_widgets = []

    for i, beer in enumerate(ocr_beers):
        card, refs = _build_placeholder_card(i + 1, beer.name)
        cards_box.add(card)
        card_refs.append(refs)
        card_widgets.append(card)

    list_scroll = toga.ScrollContainer(
        content=cards_box,
        horizontal=False,
        style=Pack(flex=1),
    )

    # ── Style filter tags (dynamic rows) ────────────────────────
    filter_row1 = toga.Box(style=Pack(direction=ROW, padding_left=10, padding_right=14, padding_bottom=1, alignment=CENTER))
    filter_row1.add(toga.Label("Style:", style=Pack(font_size=10, color="#777777", padding_right=4)))

    filter_box = toga.Box(style=Pack(direction=COLUMN))
    filter_box.add(filter_row1)

    # ── View container (sort controls + filter + scrollable list) ──
    view_container = toga.Box(style=Pack(direction=COLUMN, flex=1))
    view_container.add(sort_box)
    view_container.add(filter_box)
    view_container.add(list_scroll)

    updater = ResultsUpdater(
        card_refs=card_refs,
        card_widgets=card_widgets,
        beer_names=[b.name for b in ocr_beers],
        progress_label=progress_label,
        progress_bar=progress_bar,
        content_box=cards_box,
        list_scroll=list_scroll,
        header_box=header_box,
        view_container=view_container,
        on_scan_another=on_scan_another,
        sort_box=sort_box,
        sort_buttons=(btn_default, btn_rating, btn_name, btn_style),
        filter_box=filter_box,
        filter_rows=[filter_row1],
    )

    return [header_box, progress_label, progress_bar, view_container], updater


def build_streaming_results_view(on_scan_another, thumbnail=None):
    """Build results view for streaming OCR — starts with zero cards.

    Beer cards are added dynamically via updater.add_beer() as OCR streams in.

    Args:
        on_scan_another: callback for the "Scan Another" button
        thumbnail: optional JPEG bytes for a menu thumbnail in the header

    Returns:
        (widgets_list, ResultsUpdater) — widgets to add to content_box,
        and an updater object that supports dynamic card addition.
    """
    # ── Header ─────────────────────────────────────────────────────
    header_label = toga.Label(
        "Scanning menu...",
        style=Pack(font_size=20, font_weight=BOLD, flex=1, padding_left=10),
    )
    header_box = toga.Box(style=Pack(direction=ROW, padding=10, alignment=CENTER))
    header_box.add(header_label)
    if thumbnail:
        try:
            thumb_img = toga.Image(data=thumbnail)
            header_box.add(toga.ImageView(
                thumb_img,
                style=Pack(width=35, height=50, padding_right=8),
            ))
        except Exception:
            pass
    header_box.add(
        toga.Button(
            "Scan Another",
            on_press=on_scan_another,
            style=Pack(padding=5),
        )
    )

    # ── Indeterminate progress ─────────────────────────────────────
    progress_label = toga.Label(
        "Reading menu...",
        style=Pack(
            font_size=13, color="#777777",
            padding_left=20, padding_bottom=2,
        ),
    )
    progress_bar = toga.ProgressBar(
        max=None,
        style=Pack(padding_left=20, padding_right=20, padding_bottom=5, height=6),
    )
    progress_bar.start()

    # ── Sort controls ──────────────────────────────────────────────
    btn_default = toga.Button("Menu order", style=Pack(font_size=10, padding_top=2, padding_bottom=2, padding_left=2, padding_right=4, color=ACTIVE_COLOR))
    btn_rating = toga.Button("BA Rating", style=Pack(font_size=10, padding_top=2, padding_bottom=2, padding_left=2, padding_right=4, color=INACTIVE_COLOR))
    btn_name = toga.Button("Name", style=Pack(font_size=10, padding_top=2, padding_bottom=2, padding_left=2, padding_right=4, color=INACTIVE_COLOR))
    btn_style = toga.Button("Style", style=Pack(font_size=10, padding_top=2, padding_bottom=2, padding_left=2, padding_right=4, color=INACTIVE_COLOR))

    sort_box = toga.Box(style=Pack(direction=ROW, padding_left=10, padding_right=10, padding_bottom=2, alignment=CENTER))
    sort_box.add(toga.Label("Sort:", style=Pack(font_size=10, color="#777777", padding_right=4)))
    sort_box.add(btn_default)
    sort_box.add(btn_rating)
    sort_box.add(btn_name)
    sort_box.add(btn_style)

    # ── Empty cards container ──────────────────────────────────────
    cards_box = toga.Box(style=Pack(direction=COLUMN, padding=5))

    list_scroll = toga.ScrollContainer(
        content=cards_box,
        horizontal=False,
        style=Pack(flex=1),
    )

    # ── Style filter tags (dynamic rows) ────────────────────────
    filter_row1 = toga.Box(style=Pack(direction=ROW, padding_left=10, padding_right=14, padding_bottom=1, alignment=CENTER))
    filter_row1.add(toga.Label("Style:", style=Pack(font_size=10, color="#777777", padding_right=4)))

    filter_box = toga.Box(style=Pack(direction=COLUMN))
    filter_box.add(filter_row1)

    view_container = toga.Box(style=Pack(direction=COLUMN, flex=1))
    view_container.add(sort_box)
    view_container.add(filter_box)
    view_container.add(list_scroll)

    updater = ResultsUpdater(
        card_refs=[],
        card_widgets=[],
        beer_names=[],
        progress_label=progress_label,
        progress_bar=progress_bar,
        content_box=cards_box,
        list_scroll=list_scroll,
        header_box=header_box,
        view_container=view_container,
        on_scan_another=on_scan_another,
        sort_box=sort_box,
        sort_buttons=(btn_default, btn_rating, btn_name, btn_style),
        header_label=header_label,
        filter_box=filter_box,
        filter_rows=[filter_row1],
    )

    return [header_box, progress_label, progress_bar, view_container], updater


def _build_placeholder_card(number: int, name: str):
    """Build a beer card with placeholder ratings for incremental loading.

    Returns (card_box, refs_dict) where refs_dict holds mutable Label references
    that can be updated in-place when the rating arrives.
    """
    card = toga.Box(
        style=Pack(direction=COLUMN, padding=8, padding_bottom=2),
    )

    # Row 1: Number + Name + brand color dots + rating slots
    name_row = toga.Box(style=Pack(direction=ROW))
    name_row.add(
        toga.Label(
            f"#{number}",
            style=Pack(
                font_size=12, font_weight=BOLD,
                color="#666666", padding_right=6, padding_top=3,
            ),
        )
    )

    # Name + color dots grouped together with flex=1
    name_group = toga.Box(style=Pack(direction=ROW, flex=1))
    name_group.add(
        toga.Label(
            name,
            style=Pack(font_size=16, font_weight=BOLD),
        )
    )
    # Brand color dot placeholders (filled in update_card)
    color_dots = []
    for _ in range(4):
        dot = toga.Label("", style=Pack(font_size=20, padding_left=2, padding_top=0))
        name_group.add(dot)
        color_dots.append(dot)
    name_row.add(name_group)

    untappd_prefix = toga.Label(
        "",
        style=Pack(font_size=11, color="#666666", padding_right=2, padding_top=2),
    )
    untappd_label = toga.Label(
        "",
        style=Pack(font_size=13, font_weight=BOLD, color="#666666", padding_right=8),
    )
    ba_label = toga.Label(
        "",
        style=Pack(
            font_size=12, font_weight=BOLD,
            color="#666666", background_color="#e8e8e8",
            padding_left=6, padding_right=6,
            padding_top=2, padding_bottom=2,
        ),
    )
    name_row.add(untappd_prefix)
    name_row.add(untappd_label)
    name_row.add(ba_label)
    card.add(name_row)

    # Row 2: Brewery (+ ABV when rated) + style tag + tier label
    brewery_row = toga.Box(style=Pack(direction=ROW, padding_top=2))
    brewery_label = toga.Label("", style=Pack(font_size=13, color="#555555", flex=1))
    style_tag_label = toga.Label(
        "",
        style=Pack(font_size=10, padding_left=6, padding_right=6, padding_top=2),
    )
    tier_label = toga.Label("", style=Pack(font_size=10, font_weight=BOLD, color="#888888"))
    brewery_row.add(brewery_label)
    brewery_row.add(style_tag_label)
    brewery_row.add(tier_label)
    card.add(brewery_row)

    # Row 3: Description
    description_label = toga.Label("", style=Pack(font_size=12, padding_top=2))
    card.add(description_label)

    # Row 4: Confidence (hidden for high confidence)
    confidence_label = toga.Label("", style=Pack(font_size=11, color="#888888"))
    card.add(confidence_label)

    # Status label (shows loading state)
    status_label = toga.Label(
        "Looking up rating...",
        style=Pack(font_size=11, color="#999999", padding_top=2),
    )
    card.add(status_label)

    # Divider
    divider = toga.Divider(style=Pack(padding_top=2, color="#999999"))
    card.add(divider)

    refs = {
        "name_text": name,
        "style_tag": style_tag_label,
        "color_dots": color_dots,
        "untappd_prefix": untappd_prefix,
        "untappd": untappd_label,
        "ba": ba_label,
        "brewery": brewery_label,
        "tier": tier_label,
        "description": description_label,
        "confidence": confidence_label,
        "status": status_label,
        "divider": divider,
    }

    return card, refs


# ── History views ────────────────────────────────────────────────


def build_history_list_view(entries, on_view, on_delete, on_home) -> list:
    """Build a scrollable list of past scans.

    Args:
        entries: list of history dicts (newest first)
        on_view: callable(index) → handler — returns a press handler for viewing entry
        on_delete: callable(index) → handler — returns a press handler for deleting entry
        on_home: callback for "Back" button
    """
    header_box = toga.Box(style=Pack(direction=ROW, padding=10, alignment=CENTER))
    header_box.add(
        toga.Label(
            "Scan History",
            style=Pack(font_size=20, font_weight=BOLD, flex=1, padding_left=10),
        )
    )
    header_box.add(
        toga.Button("Back", on_press=on_home, style=Pack(padding=5)),
    )

    if not entries:
        empty_label = toga.Label(
            "No scans yet.\nScan a beer menu to get started!",
            style=Pack(
                text_align=CENTER, font_size=14,
                color="#999999", padding_top=60,
            ),
        )
        return [header_box, empty_label]

    cards_box = toga.Box(style=Pack(direction=COLUMN, padding=5))

    for i, entry in enumerate(entries):
        beers = entry.get("beers", [])
        date_str = entry.get("date", "")
        # Format date nicely
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(date_str)
            display_date = dt.strftime("%b %d, %Y  %I:%M %p")
        except Exception:
            display_date = date_str[:16] if date_str else "Unknown date"

        beer_count = len(beers)
        # Show first few beer names as preview
        preview_names = [b.get("name", "?") for b in beers[:3]]
        preview = ", ".join(preview_names)
        if beer_count > 3:
            preview += f" +{beer_count - 3} more"

        card = toga.Box(style=Pack(direction=ROW, padding=10, padding_bottom=5))

        # Thumbnail (if saved in history)
        thumb_b64 = entry.get("thumbnail")
        if thumb_b64:
            try:
                import base64
                thumb_bytes = base64.b64decode(thumb_b64)
                thumb_img = toga.Image(data=thumb_bytes)
                card.add(toga.ImageView(
                    thumb_img,
                    style=Pack(width=30, height=40, padding_right=8),
                ))
            except Exception:
                pass

        # Card text content (right of thumbnail)
        card_content = toga.Box(style=Pack(direction=COLUMN, flex=1))

        # Date + beer count row
        top_row = toga.Box(style=Pack(direction=ROW))
        top_row.add(toga.Label(
            display_date,
            style=Pack(font_size=14, font_weight=BOLD, flex=1),
        ))
        top_row.add(toga.Label(
            f"{beer_count} beers",
            style=Pack(font_size=12, color="#777777", padding_top=2),
        ))
        card_content.add(top_row)

        # Preview names
        card_content.add(toga.Label(
            preview,
            style=Pack(font_size=12, color="#555555", padding_top=4),
        ))

        # Action buttons
        btn_row = toga.Box(style=Pack(direction=ROW, padding_top=6))
        btn_row.add(toga.Button(
            "View",
            on_press=on_view(i),
            style=Pack(font_size=12, padding=3, color=ACTIVE_COLOR),
        ))
        btn_row.add(toga.Button(
            "Delete",
            on_press=on_delete(i),
            style=Pack(font_size=12, padding=3, color="#c62828"),
        ))
        card_content.add(btn_row)
        card.add(card_content)

        card.add(toga.Divider(style=Pack(padding_top=8)))
        cards_box.add(card)

    list_scroll = toga.ScrollContainer(
        content=cards_box,
        horizontal=False,
        style=Pack(flex=1),
    )

    return [header_box, list_scroll]


def build_history_detail_view(entry, on_back, on_home) -> list:
    """Build a detail view showing all beers from a past scan.

    Args:
        entry: a single history dict with "date" and "beers" keys
        on_back: callback for "Back to History" button
        on_home: callback for "Scan Another" button
    """
    date_str = entry.get("date", "")
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(date_str)
        display_date = dt.strftime("%b %d, %Y  %I:%M %p")
    except Exception:
        display_date = date_str[:16] if date_str else "Unknown date"

    beers = entry.get("beers", [])

    # Header
    header_box = toga.Box(style=Pack(direction=ROW, padding=10, alignment=CENTER))
    header_box.add(toga.Label(
        f"{len(beers)} Beers",
        style=Pack(font_size=20, font_weight=BOLD, flex=1, padding_left=10),
    ))
    header_box.add(toga.Button(
        "Back",
        on_press=on_back,
        style=Pack(padding=5),
    ))

    date_label = toga.Label(
        display_date,
        style=Pack(font_size=13, color="#777777", padding_left=20, padding_bottom=10),
    )

    # Beer cards
    cards_box = toga.Box(style=Pack(direction=COLUMN, padding=5))
    for i, beer_data in enumerate(beers):
        card = _build_history_beer_card(i + 1, beer_data)
        cards_box.add(card)

    list_scroll = toga.ScrollContainer(
        content=cards_box,
        horizontal=False,
        style=Pack(flex=1),
    )

    return [header_box, date_label, list_scroll]


def _build_history_beer_card(number, beer_data):
    """Build a beer card from saved history data (dict, not BeerRating object)."""
    name = beer_data.get("name", "Unknown Beer")
    brewery = beer_data.get("brewery", "")
    style = beer_data.get("style", "")
    abv = beer_data.get("abv", "")
    rating_untappd = beer_data.get("rating_untappd")
    rating_ba = beer_data.get("rating_beer_advocate")
    description = beer_data.get("description", "")
    confidence = beer_data.get("confidence", "")
    brand_colors = beer_data.get("brand_colors")

    # Build a minimal BeerRating-like object for _get_rating_tier
    class _FakeBeer:
        pass
    fake = _FakeBeer()
    fake.rating_beer_advocate = rating_ba
    tier = _get_rating_tier(fake)

    card = toga.Box(style=Pack(direction=COLUMN, padding=8, padding_bottom=2))

    # Row 1: Number + Name + brand dots + ratings
    name_row = toga.Box(style=Pack(direction=ROW))
    name_row.add(toga.Label(
        f"#{number}",
        style=Pack(font_size=12, font_weight=BOLD, color="#666666", padding_right=6, padding_top=3),
    ))

    name_group = toga.Box(style=Pack(direction=ROW, flex=1))
    name_group.add(toga.Label(
        name,
        style=Pack(font_size=16, font_weight=BOLD),
    ))
    if brand_colors:
        for color in _sort_colors_light_to_dark(brand_colors[:4]):
            name_group.add(toga.Label(
                "\u25cf",
                style=Pack(font_size=20, color=color, padding_left=2, padding_top=0),
            ))
    name_row.add(name_group)

    if rating_untappd is not None:
        name_row.add(toga.Label(
            "Untappd",
            style=Pack(font_size=11, color="#666666", padding_right=2, padding_top=2),
        ))
        name_row.add(toga.Label(
            f"\u2605 {rating_untappd:.1f}",
            style=Pack(font_size=13, font_weight=BOLD, color="#666666", padding_right=8),
        ))

    if rating_ba is not None:
        name_row.add(toga.Label(
            f"BA: {rating_ba}",
            style=Pack(
                font_size=12, font_weight=BOLD,
                color="#666666", background_color="#e8e8e8",
                padding_left=6, padding_right=6, padding_top=2, padding_bottom=2,
            ),
        ))
    card.add(name_row)

    # Row 2: Brewery + ABV + style tag + tier
    brewery_text = brewery or "Unknown Brewery"
    if abv:
        brewery_text += f" \u00b7 {abv}"
    brewery_row = toga.Box(style=Pack(direction=ROW, padding_top=2))
    brewery_row.add(toga.Label(
        brewery_text,
        style=Pack(font_size=13, color="#555555", flex=1),
    ))
    if style:
        category = _normalize_style(style)
        s_colors = _STYLE_COLORS.get(category, _DEFAULT_STYLE_COLOR)
        brewery_row.add(toga.Label(
            category,
            style=Pack(
                font_size=10, padding_left=6, padding_right=6, padding_top=2,
                color=s_colors["color"], background_color=s_colors["bg"],
            ),
        ))
    if tier["label"]:
        brewery_row.add(toga.Label(
            tier["label"],
            style=Pack(font_size=10, font_weight=BOLD, color="#888888"),
        ))
    card.add(brewery_row)

    # Row 3: Description
    if description:
        card.add(toga.Label(
            description,
            style=Pack(font_size=12, padding_top=2),
        ))

    # Row 4: Confidence (only if NOT high)
    if confidence and confidence != "high":
        confidence_color = {
            "medium": "#f57f17", "low": "#c62828",
        }.get(confidence, "#888888")
        card.add(toga.Label(
            f"Confidence: {confidence}",
            style=Pack(font_size=11, color=confidence_color, padding_top=2),
        ))

    card.add(toga.Divider(style=Pack(padding_top=2, color=tier["accent"])))
    return card


# ── Legacy results view (kept for backward compat) ────────────────


def build_results_view(beers: list, on_scan_another) -> list:
    """Build the results screen with beer cards in a scroll container."""
    header_box = toga.Box(style=Pack(direction=ROW, padding=10, alignment=CENTER))
    header_box.add(
        toga.Label(
            f"Found {len(beers)} Beers",
            style=Pack(font_size=20, font_weight=BOLD, flex=1, padding_left=10),
        )
    )
    header_box.add(
        toga.Button(
            "Scan Another",
            on_press=on_scan_another,
            style=Pack(padding=5),
        )
    )

    # ── List view — pre-build all sort orders for instant switching ─
    sort_keys = {
        "rating_asc": sorted(beers, key=lambda b: b.rating_beer_advocate if b.rating_beer_advocate is not None else -1),
        "rating_desc": sorted(beers, key=lambda b: b.rating_beer_advocate if b.rating_beer_advocate is not None else -1, reverse=True),
        "name_asc": sorted(beers, key=lambda b: (b.name or "").lower()),
        "name_desc": sorted(beers, key=lambda b: (b.name or "").lower(), reverse=True),
        "style_asc": sorted(beers, key=lambda b: _normalize_style(b.style).lower() if b.style else "\uffff"),
        "style_desc": sorted(beers, key=lambda b: _normalize_style(b.style).lower() if b.style else "\uffff", reverse=True),
    }

    beer_numbers = {id(b): i + 1 for i, b in enumerate(beers)}

    pre_built = {"default": toga.Box(style=Pack(direction=COLUMN, padding=5))}
    for beer in beers:
        pre_built["default"].add(_build_beer_card(beer, number=beer_numbers[id(beer)]))
    for key, sorted_list in sort_keys.items():
        box = toga.Box(style=Pack(direction=COLUMN, padding=5))
        for beer in sorted_list:
            box.add(_build_beer_card(beer, number=beer_numbers[id(beer)]))
        pre_built[key] = box

    list_scroll = toga.ScrollContainer(
        content=pre_built["default"],
        horizontal=False,
        style=Pack(flex=1),
    )

    btn_default = toga.Button("Menu order", style=Pack(font_size=10, padding_top=2, padding_bottom=2, padding_left=2, padding_right=4, color=ACTIVE_COLOR))
    btn_rating = toga.Button("BA Rating", style=Pack(font_size=10, padding_top=2, padding_bottom=2, padding_left=2, padding_right=4, color=INACTIVE_COLOR))
    btn_name = toga.Button("Name", style=Pack(font_size=10, padding_top=2, padding_bottom=2, padding_left=2, padding_right=4, color=INACTIVE_COLOR))
    btn_style = toga.Button("Style", style=Pack(font_size=10, padding_top=2, padding_bottom=2, padding_left=2, padding_right=4, color=INACTIVE_COLOR))
    sort_buttons = [btn_default, btn_rating, btn_name, btn_style]

    sort_state = {"active": "default", "rating_desc": True, "name_desc": False, "style_desc": False}

    def _set_active(active_btn):
        for btn in sort_buttons:
            btn.style.color = ACTIVE_COLOR if btn is active_btn else INACTIVE_COLOR

    def _update_labels():
        btn_rating.text = ("BA Rating" + (ARROW_DOWN if sort_state["rating_desc"] else ARROW_UP)) if sort_state["active"].startswith("rating") else "BA Rating"
        btn_name.text = ("Name" + (ARROW_UP if not sort_state["name_desc"] else ARROW_DOWN)) if sort_state["active"].startswith("name") else "Name"
        btn_style.text = ("Style" + (ARROW_DOWN if sort_state["style_desc"] else ARROW_UP)) if sort_state["active"].startswith("style") else "Style"

    def on_sort_default(widget):
        sort_state["active"] = "default"
        list_scroll.content = pre_built["default"]
        _set_active(btn_default)
        _update_labels()

    def on_sort_rating(widget):
        if sort_state["active"].startswith("rating"):
            sort_state["rating_desc"] = not sort_state["rating_desc"]
        else:
            sort_state["rating_desc"] = True
        key = "rating_desc" if sort_state["rating_desc"] else "rating_asc"
        sort_state["active"] = key
        list_scroll.content = pre_built[key]
        _set_active(btn_rating)
        _update_labels()

    def on_sort_name(widget):
        if sort_state["active"].startswith("name"):
            sort_state["name_desc"] = not sort_state["name_desc"]
        else:
            sort_state["name_desc"] = False
        key = "name_desc" if sort_state["name_desc"] else "name_asc"
        sort_state["active"] = key
        list_scroll.content = pre_built[key]
        _set_active(btn_name)
        _update_labels()

    def on_sort_style(widget):
        if sort_state["active"].startswith("style"):
            sort_state["style_desc"] = not sort_state["style_desc"]
        else:
            sort_state["style_desc"] = False
        key = "style_desc" if sort_state["style_desc"] else "style_asc"
        sort_state["active"] = key
        list_scroll.content = pre_built[key]
        _set_active(btn_style)
        _update_labels()

    btn_default.on_press = on_sort_default
    btn_rating.on_press = on_sort_rating
    btn_name.on_press = on_sort_name
    btn_style.on_press = on_sort_style

    sort_box = toga.Box(style=Pack(direction=ROW, padding_left=10, padding_right=10, padding_bottom=2, alignment=CENTER))
    sort_box.add(toga.Label("Sort:", style=Pack(font_size=10, color="#777777", padding_right=4)))
    sort_box.add(btn_default)
    sort_box.add(btn_rating)
    sort_box.add(btn_name)
    sort_box.add(btn_style)

    # ── View container ────────────────────────────────────────────
    view_container = toga.Box(style=Pack(direction=COLUMN, flex=1))
    view_container.add(sort_box)
    view_container.add(list_scroll)

    return [header_box, view_container]


# ── Shared card helpers ───────────────────────────────────────────


def _get_rating_tier(beer):
    """Determine the color tier based on BeerAdvocate score.

    Tiers:
        92+   → Top Tier (gold)
        85-91 → Great (green)
        75-84 → Good (blue)
        65-74 → Average (gray)
        <65   → Below Average (muted red)
        None  → Unknown (neutral gray)
    """
    score = beer.rating_beer_advocate
    if score is None:
        return {
            "badge_bg": "#e0e0e0",
            "badge_text": "#666666",
            "accent": "#999999",
            "label": "",
        }
    if score >= 92:
        return {
            "badge_bg": "#fff3cd",
            "badge_text": "#856404",
            "accent": "#d4a017",
            "label": "TOP TIER",
        }
    if score >= 85:
        return {
            "badge_bg": "#d4edda",
            "badge_text": "#155724",
            "accent": "#28a745",
            "label": "GREAT",
        }
    if score >= 75:
        return {
            "badge_bg": "#d6eaf8",
            "badge_text": "#1a5276",
            "accent": "#2e86c1",
            "label": "GOOD",
        }
    if score >= 65:
        return {
            "badge_bg": "#e8e8e8",
            "badge_text": "#555555",
            "accent": "#888888",
            "label": "AVERAGE",
        }
    return {
        "badge_bg": "#f8d7da",
        "badge_text": "#721c24",
        "accent": "#c0392b",
        "label": "BELOW AVG",
    }


def _build_beer_card(beer, number=None) -> toga.Box:
    """Build a single beer result card.

    Layout:
    ┌──────────────────────────────────────┐
    │ #1  Beer Name  ●●●   Untappd  BA: 92│
    │     Brewery · ABV        [IPA]  GREAT│
    │     Description text (scrollable)    │
    │     Confidence: medium (if not high) │
    └──────────────────────────────────────┘
    """
    tier = _get_rating_tier(beer)

    card = toga.Box(
        style=Pack(direction=COLUMN, padding=8, padding_bottom=2),
    )

    # Row 1: Number + Name + brand dots + ratings
    name_row = toga.Box(style=Pack(direction=ROW))
    if number is not None:
        name_row.add(
            toga.Label(
                f"#{number}",
                style=Pack(
                    font_size=12, font_weight=BOLD,
                    color="#666666", padding_right=6, padding_top=3,
                ),
            )
        )

    name_group = toga.Box(style=Pack(direction=ROW, flex=1))
    name_group.add(
        toga.Label(
            beer.name,
            style=Pack(font_size=16, font_weight=BOLD),
        )
    )
    if beer.brand_colors:
        for color in _sort_colors_light_to_dark(beer.brand_colors[:4]):
            name_group.add(toga.Label(
                "\u25cf",
                style=Pack(font_size=20, color=color, padding_left=2, padding_top=0),
            ))
    name_row.add(name_group)

    # Untappd rating (neutral color)
    if beer.rating_untappd is not None:
        name_row.add(
            toga.Label(
                "Untappd",
                style=Pack(font_size=11, color="#666666", padding_right=2, padding_top=2),
            )
        )
        name_row.add(
            toga.Label(
                f"\u2605 {beer.rating_untappd:.1f}",
                style=Pack(font_size=13, font_weight=BOLD, color="#666666", padding_right=8),
            )
        )

    # BA score badge (neutral color)
    ba_score = beer.rating_beer_advocate
    if ba_score is not None:
        name_row.add(
            toga.Label(
                f"BA: {ba_score}",
                style=Pack(
                    font_size=12, font_weight=BOLD,
                    color="#666666", background_color="#e8e8e8",
                    padding_left=6, padding_right=6,
                    padding_top=2, padding_bottom=2,
                ),
            )
        )
    card.add(name_row)

    # Row 2: Brewery + ABV + style tag + tier label
    brewery_text = beer.brewery or "Unknown Brewery"
    if beer.abv:
        brewery_text += f" \u00b7 {beer.abv}"
    brewery_row = toga.Box(style=Pack(direction=ROW, padding_top=2))
    brewery_row.add(
        toga.Label(
            brewery_text,
            style=Pack(font_size=13, color="#555555", flex=1),
        )
    )
    if beer.style:
        _cat = _normalize_style(beer.style)
        _sc = _STYLE_COLORS.get(_cat, _DEFAULT_STYLE_COLOR)
        brewery_row.add(
            toga.Label(
                _cat,
                style=Pack(
                    font_size=10, padding_left=6, padding_right=6, padding_top=2,
                    color=_sc["color"], background_color=_sc["bg"],
                ),
            )
        )
    if tier["label"]:
        brewery_row.add(
            toga.Label(
                tier["label"],
                style=Pack(font_size=10, font_weight=BOLD, color="#888888"),
            )
        )
    card.add(brewery_row)

    # Row 3: Description
    card.add(toga.Label(
        beer.description,
        style=Pack(font_size=12, padding_top=2),
    ))

    # Row 4: Confidence (only if NOT high)
    if beer.confidence and beer.confidence != "high":
        confidence_color = {
            "medium": "#f57f17",
            "low": "#c62828",
        }.get(beer.confidence, "#888888")
        card.add(
            toga.Label(
                f"Confidence: {beer.confidence}",
                style=Pack(font_size=11, color=confidence_color, padding_top=2),
            )
        )

    # Colored divider matching the tier
    card.add(
        toga.Divider(
            style=Pack(padding_top=2, color=tier["accent"]),
        )
    )

    return card
