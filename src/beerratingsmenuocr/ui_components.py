"""Reusable UI components for the beer ratings app."""

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER, BOLD


ACTIVE_COLOR = "#007AFF"
INACTIVE_COLOR = "#888888"
ARROW_DOWN = " \u25BC"
ARROW_UP = " \u25B2"


def build_home_view(on_take_photo, on_select_image) -> list:
    """Build the home screen widgets."""
    title = toga.Label(
        "BeerRated",
        style=Pack(
            text_align=CENTER,
            font_size=24,
            font_weight=BOLD,
            padding_top=60,
            padding_bottom=10,
        ),
    )

    subtitle = toga.Label(
        "Take a photo of a beer menu to get\ninstant ratings and details",
        style=Pack(
            text_align=CENTER,
            font_size=14,
            padding_bottom=40,
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

    return [title, subtitle, button_box]


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
      - add_photo_view(annotated_image) to add the photo toggle
    """

    def __init__(self, card_refs, card_widgets, beer_names,
                 progress_label, progress_bar,
                 content_box, list_scroll, header_box, view_container,
                 on_scan_another, sort_box, sort_buttons):
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

        self._btn_default, self._btn_rating, self._btn_name = sort_buttons
        self._all_sort_buttons = list(sort_buttons)

        self._ratings = [None] * len(card_widgets)
        self._sort_mode = "default"
        self._sort_state = {"rating_desc": True, "name_desc": False}

        # Wire up sort handlers
        self._btn_default.on_press = self._on_sort_default
        self._btn_rating.on_press = self._on_sort_rating
        self._btn_name.on_press = self._on_sort_name

    # ── Sorting ───────────────────────────────────────────────────

    def _set_active(self, active_btn):
        for btn in self._all_sort_buttons:
            btn.style.color = ACTIVE_COLOR if btn is active_btn else INACTIVE_COLOR

    def _update_sort_labels(self):
        s = self._sort_state
        self._btn_rating.text = (
            ("Rating" + (ARROW_DOWN if s["rating_desc"] else ARROW_UP))
            if self._sort_mode.startswith("rating") else "Rating"
        )
        self._btn_name.text = (
            ("Name" + (ARROW_UP if not s["name_desc"] else ARROW_DOWN))
            if self._sort_mode.startswith("name") else "Name"
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

        return indices

    def _apply_sort(self):
        """Reorder card widgets inside cards_box to match current sort."""
        indices = self._get_sorted_indices()
        self.content_box.clear()
        for i in indices:
            self.content_box.add(self._card_widgets[i])

    # ── Progress + card updates ───────────────────────────────────

    def set_progress(self, current: int, total: int):
        """Update the progress indicator."""
        self.progress_label.text = f"Rated {current} of {total}..."
        self.progress_bar.value = current
        self.progress_bar.max = total

    def update_card(self, index: int, rating):
        """Update a single beer card in-place with its rating data."""
        refs = self.card_refs[index]
        self._ratings[index] = rating
        tier = _get_rating_tier(rating)

        # Update rating labels
        if rating.rating_untappd is not None:
            refs["untappd"].text = f"\u2605 {rating.rating_untappd:.1f}"
            refs["untappd"].style.color = tier["accent"]
        else:
            refs["untappd"].text = ""

        if rating.rating_beer_advocate is not None:
            refs["ba"].text = f"BA: {rating.rating_beer_advocate}"
            refs["ba"].style.color = tier["badge_text"]
            refs["ba"].style.background_color = tier["badge_bg"]
        else:
            refs["ba"].text = ""

        # Update details
        refs["brewery"].text = rating.brewery or "Unknown Brewery"
        refs["tier"].text = tier["label"]
        refs["tier"].style.color = tier["accent"]

        style_parts = [rating.style]
        if rating.abv:
            style_parts.append(rating.abv)
        refs["style"].text = " \u00b7 ".join(style_parts)

        refs["description"].text = rating.description

        confidence_color = {
            "high": "#2e7d32", "medium": "#f57f17", "low": "#c62828",
        }.get(rating.confidence, "#888888")
        refs["confidence"].text = f"Confidence: {rating.confidence}"
        refs["confidence"].style.color = confidence_color

        refs["divider"].style.color = tier["accent"]

        # Hide loading status
        refs["status"].text = ""
        refs["status"].style.padding_top = 0

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

        # Final re-sort with complete data
        if self._sort_mode != "default":
            self._apply_sort()

    def add_photo_view(self, annotated_image_bytes):
        """Add List/Photo toggle after annotation is ready."""
        photo_image = toga.Image(data=annotated_image_bytes)
        photo_view = toga.ImageView(photo_image, style=Pack(flex=1))
        photo_box = toga.Box(
            style=Pack(direction=COLUMN, padding_left=10, padding_right=10, padding_top=5),
            children=[photo_view],
        )
        photo_scroll = toga.ScrollContainer(
            content=photo_box,
            horizontal=False,
            style=Pack(flex=1),
        )

        sort_box = self._sort_box
        list_scroll = self.list_scroll
        view_container = self.view_container

        btn_list = toga.Button("List", style=Pack(font_size=12, padding=4, color=ACTIVE_COLOR))
        btn_photo = toga.Button("Photo", style=Pack(font_size=12, padding=4, color=INACTIVE_COLOR))

        def on_show_list(widget):
            view_container.clear()
            view_container.add(sort_box)
            view_container.add(list_scroll)
            btn_list.style.color = ACTIVE_COLOR
            btn_photo.style.color = INACTIVE_COLOR

        def on_show_photo(widget):
            view_container.clear()
            view_container.add(photo_scroll)
            btn_list.style.color = INACTIVE_COLOR
            btn_photo.style.color = ACTIVE_COLOR

        btn_list.on_press = on_show_list
        btn_photo.on_press = on_show_photo

        toggle_box = toga.Box(style=Pack(direction=ROW, alignment=CENTER, padding_left=10, padding_right=10, padding_bottom=5))
        toggle_box.add(toga.Label("View:", style=Pack(font_size=12, color="#777777", padding_right=6)))
        toggle_box.add(btn_list)
        toggle_box.add(btn_photo)

        # Insert toggle between header area and view_container
        parent = self.header_box.parent
        if parent is not None:
            parent.remove(self.view_container)
            parent.add(toggle_box)
            parent.add(self.view_container)


def build_incremental_results_view(ocr_beers, on_scan_another):
    """Build the results screen with placeholder cards for incremental updates.

    Sort buttons are shown immediately — name sort works right away since
    all names are known from OCR, and rating sort works with partial data
    (unrated beers are placed at the bottom).

    Args:
        ocr_beers: list of OcrBeer from the OCR step (names only, no ratings)
        on_scan_another: callback for the "Scan Another" button

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
            padding_left=20, padding_bottom=4,
        ),
    )
    progress_bar = toga.ProgressBar(
        max=total, value=0,
        style=Pack(padding_left=20, padding_right=20, padding_bottom=10, height=6),
    )

    # ── Sort controls (active from the start) ──────────────────────
    btn_default = toga.Button("Default", style=Pack(font_size=12, padding=4, color=ACTIVE_COLOR))
    btn_rating = toga.Button("Rating", style=Pack(font_size=12, padding=4, color=INACTIVE_COLOR))
    btn_name = toga.Button("Name", style=Pack(font_size=12, padding=4, color=INACTIVE_COLOR))

    sort_box = toga.Box(style=Pack(direction=ROW, padding_left=10, padding_right=10, padding_bottom=5, alignment=CENTER))
    sort_box.add(toga.Label("Sort:", style=Pack(font_size=12, color="#777777", padding_right=6)))
    sort_box.add(btn_default)
    sort_box.add(btn_rating)
    sort_box.add(btn_name)

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

    # ── View container (sort controls + scrollable list) ───────────
    view_container = toga.Box(style=Pack(direction=COLUMN, flex=1))
    view_container.add(sort_box)
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
        sort_buttons=(btn_default, btn_rating, btn_name),
    )

    return [header_box, progress_label, progress_bar, view_container], updater


def _build_placeholder_card(number: int, name: str):
    """Build a beer card with placeholder ratings for incremental loading.

    Returns (card_box, refs_dict) where refs_dict holds mutable Label references
    that can be updated in-place when the rating arrives.
    """
    card = toga.Box(
        style=Pack(direction=COLUMN, padding=10, padding_bottom=5),
    )

    # Row 1: Number + Name + placeholder rating slots
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
    name_row.add(
        toga.Label(
            name,
            style=Pack(font_size=16, font_weight=BOLD, flex=1),
        )
    )

    untappd_label = toga.Label(
        "",
        style=Pack(font_size=13, font_weight=BOLD, color="#999999", padding_right=8),
    )
    ba_label = toga.Label(
        "",
        style=Pack(
            font_size=12, font_weight=BOLD,
            color="#666666", background_color="#e0e0e0",
            padding_left=6, padding_right=6,
            padding_top=2, padding_bottom=2,
        ),
    )
    name_row.add(untappd_label)
    name_row.add(ba_label)
    card.add(name_row)

    # Row 2: Brewery + tier label (empty until rated)
    brewery_row = toga.Box(style=Pack(direction=ROW, padding_top=2))
    brewery_label = toga.Label("", style=Pack(font_size=13, color="#555555", flex=1))
    tier_label = toga.Label("", style=Pack(font_size=10, font_weight=BOLD, color="#999999"))
    brewery_row.add(brewery_label)
    brewery_row.add(tier_label)
    card.add(brewery_row)

    # Row 3: Style and ABV (empty until rated)
    style_label = toga.Label("", style=Pack(font_size=12, color="#777777", padding_top=2))
    card.add(style_label)

    # Row 4: Description (empty until rated)
    description_label = toga.Label("", style=Pack(font_size=12, padding_top=6, padding_bottom=4))
    card.add(description_label)

    # Row 5: Confidence (empty until rated)
    confidence_label = toga.Label("", style=Pack(font_size=11, color="#888888", padding_top=2))
    card.add(confidence_label)

    # Status label (shows loading state)
    status_label = toga.Label(
        "Looking up rating...",
        style=Pack(font_size=11, color="#999999", padding_top=4),
    )
    card.add(status_label)

    # Divider
    divider = toga.Divider(style=Pack(padding_top=8, color="#999999"))
    card.add(divider)

    refs = {
        "name_text": name,
        "untappd": untappd_label,
        "ba": ba_label,
        "brewery": brewery_label,
        "tier": tier_label,
        "style": style_label,
        "description": description_label,
        "confidence": confidence_label,
        "status": status_label,
        "divider": divider,
    }

    return card, refs


# ── Legacy results view (kept for backward compat) ────────────────


def build_results_view(beers: list, on_scan_another, annotated_image: bytes = None) -> list:
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

    btn_default = toga.Button("Default", style=Pack(font_size=12, padding=4, color=ACTIVE_COLOR))
    btn_rating = toga.Button("Rating", style=Pack(font_size=12, padding=4, color=INACTIVE_COLOR))
    btn_name = toga.Button("Name", style=Pack(font_size=12, padding=4, color=INACTIVE_COLOR))
    sort_buttons = [btn_default, btn_rating, btn_name]

    sort_state = {"active": "default", "rating_desc": True, "name_desc": False}

    def _set_active(active_btn):
        for btn in sort_buttons:
            btn.style.color = ACTIVE_COLOR if btn is active_btn else INACTIVE_COLOR

    def _update_labels():
        btn_rating.text = ("Rating" + (ARROW_DOWN if sort_state["rating_desc"] else ARROW_UP)) if sort_state["active"].startswith("rating") else "Rating"
        btn_name.text = ("Name" + (ARROW_UP if not sort_state["name_desc"] else ARROW_DOWN)) if sort_state["active"].startswith("name") else "Name"

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

    btn_default.on_press = on_sort_default
    btn_rating.on_press = on_sort_rating
    btn_name.on_press = on_sort_name

    sort_box = toga.Box(style=Pack(direction=ROW, padding_left=10, padding_right=10, padding_bottom=5, alignment=CENTER))
    sort_box.add(toga.Label("Sort:", style=Pack(font_size=12, color="#777777", padding_right=6)))
    sort_box.add(btn_default)
    sort_box.add(btn_rating)
    sort_box.add(btn_name)

    # ── View container (swaps between list and photo) ────────────
    view_container = toga.Box(style=Pack(direction=COLUMN, flex=1))

    # Start with list view
    view_container.add(sort_box)
    view_container.add(list_scroll)

    if annotated_image:
        # ── Photo view ───────────────────────────────────────────
        photo_image = toga.Image(data=annotated_image)
        photo_view = toga.ImageView(photo_image, style=Pack(flex=1))
        photo_box = toga.Box(
            style=Pack(direction=COLUMN, padding_left=10, padding_right=10, padding_top=5),
            children=[photo_view],
        )
        photo_scroll = toga.ScrollContainer(
            content=photo_box,
            horizontal=False,
            style=Pack(flex=1),
        )

        # ── Toggle buttons ───────────────────────────────────────
        btn_list = toga.Button("List", style=Pack(font_size=12, padding=4, color=ACTIVE_COLOR))
        btn_photo = toga.Button("Photo", style=Pack(font_size=12, padding=4, color=INACTIVE_COLOR))

        def on_show_list(widget):
            view_container.clear()
            view_container.add(sort_box)
            view_container.add(list_scroll)
            btn_list.style.color = ACTIVE_COLOR
            btn_photo.style.color = INACTIVE_COLOR

        def on_show_photo(widget):
            view_container.clear()
            view_container.add(photo_scroll)
            btn_list.style.color = INACTIVE_COLOR
            btn_photo.style.color = ACTIVE_COLOR

        btn_list.on_press = on_show_list
        btn_photo.on_press = on_show_photo

        toggle_box = toga.Box(style=Pack(direction=ROW, alignment=CENTER, padding_left=10, padding_right=10, padding_bottom=5))
        toggle_box.add(
            toga.Label("View:", style=Pack(font_size=12, color="#777777", padding_right=6))
        )
        toggle_box.add(btn_list)
        toggle_box.add(btn_photo)

        return [header_box, toggle_box, view_container]

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
    """Build a single beer result card, color-coded by rating tier.

    Layout:
    ┌──────────────────────────────────────┐
    │ #1  Beer Name          ★ 4.2  BA: 92│
    │     Brewery Name          [TOP TIER] │
    │     Style · ABV                      │
    │     Description text here...         │
    │     Confidence: high                 │
    └──────────────────────────────────────┘
    """
    tier = _get_rating_tier(beer)

    card = toga.Box(
        style=Pack(direction=COLUMN, padding=10, padding_bottom=5),
    )

    # Row 1: Number + Name + Untappd rating + BA score
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
    name_row.add(
        toga.Label(
            beer.name,
            style=Pack(font_size=16, font_weight=BOLD, flex=1),
        )
    )

    # Untappd rating (star + score)
    if beer.rating_untappd is not None:
        name_row.add(
            toga.Label(
                f"\u2605 {beer.rating_untappd:.1f}",
                style=Pack(
                    font_size=13, font_weight=BOLD,
                    color=tier["accent"], padding_right=8,
                ),
            )
        )

    # BA score badge
    ba_score = beer.rating_beer_advocate
    if ba_score is not None:
        name_row.add(
            toga.Label(
                f"BA: {ba_score}",
                style=Pack(
                    font_size=12, font_weight=BOLD,
                    color=tier["badge_text"],
                    background_color=tier["badge_bg"],
                    padding_left=6, padding_right=6,
                    padding_top=2, padding_bottom=2,
                ),
            )
        )
    card.add(name_row)

    # Row 2: Brewery + tier label
    brewery_row = toga.Box(style=Pack(direction=ROW, padding_top=2))
    brewery_row.add(
        toga.Label(
            beer.brewery or "Unknown Brewery",
            style=Pack(font_size=13, color="#555555", flex=1),
        )
    )
    if tier["label"]:
        brewery_row.add(
            toga.Label(
                tier["label"],
                style=Pack(
                    font_size=10, font_weight=BOLD,
                    color=tier["accent"],
                ),
            )
        )
    card.add(brewery_row)

    # Row 3: Style and ABV
    style_parts = [beer.style]
    if beer.abv:
        style_parts.append(beer.abv)
    card.add(
        toga.Label(
            " \u00b7 ".join(style_parts),
            style=Pack(font_size=12, color="#777777", padding_top=2),
        )
    )

    # Row 4: Description
    card.add(
        toga.Label(
            beer.description,
            style=Pack(font_size=12, padding_top=6, padding_bottom=4),
        )
    )

    # Row 5: Confidence
    confidence_color = {
        "high": "#2e7d32",
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
            style=Pack(padding_top=8, color=tier["accent"]),
        )
    )

    return card
