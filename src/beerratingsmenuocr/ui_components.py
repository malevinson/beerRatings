"""Reusable UI components for the beer ratings app."""

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER, BOLD


def build_home_view(on_take_photo, on_select_image) -> list:
    """Build the home screen widgets."""
    title = toga.Label(
        "Beer Menu Scanner",
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

    pre_built = {"default": toga.Box(style=Pack(direction=COLUMN, padding=5))}
    for beer in beers:
        pre_built["default"].add(_build_beer_card(beer))
    for key, sorted_list in sort_keys.items():
        box = toga.Box(style=Pack(direction=COLUMN, padding=5))
        for beer in sorted_list:
            box.add(_build_beer_card(beer))
        pre_built[key] = box

    list_scroll = toga.ScrollContainer(
        content=pre_built["default"],
        horizontal=False,
        style=Pack(flex=1),
    )

    ACTIVE_COLOR = "#007AFF"
    INACTIVE_COLOR = "#888888"
    ARROW_DOWN = " \u25BC"
    ARROW_UP = " \u25B2"

    btn_default = toga.Button("Default", style=Pack(font_size=12, padding=4, color=ACTIVE_COLOR))
    btn_rating = toga.Button("Rating", style=Pack(font_size=12, padding=4, color=INACTIVE_COLOR))
    btn_name = toga.Button("Name", style=Pack(font_size=12, padding=4, color=INACTIVE_COLOR))
    sort_buttons = [btn_default, btn_rating, btn_name]

    sort_state = {"active": "default", "rating_desc": True, "name_desc": False}

    def _set_active(active_btn):
        for btn in sort_buttons:
            btn.style.color = ACTIVE_COLOR if btn is active_btn else INACTIVE_COLOR

    def _update_labels():
        btn_rating.text = "Rating" + (ARROW_DOWN if sort_state["rating_desc"] else ARROW_UP) if sort_state["active"].startswith("rating") else "Rating"
        btn_name.text = "Name" + (ARROW_UP if not sort_state["name_desc"] else ARROW_DOWN) if sort_state["active"].startswith("name") else "Name"

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
        photo_box = toga.Box(style=Pack(direction=COLUMN, flex=1, alignment=CENTER))
        photo_box.add(
            toga.ImageView(photo_image, style=Pack(flex=1))
        )
        photo_scroll = toga.ScrollContainer(
            content=photo_box,
            horizontal=True,
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


def _build_beer_card(beer) -> toga.Box:
    """Build a single beer result card, color-coded by rating tier.

    Layout:
    ┌──────────────────────────────────────┐
    │ Beer Name              ★ 4.2  BA: 92│
    │ Brewery Name              [TOP TIER]│
    │ Style · ABV                          │
    │ Description text here...             │
    │ Confidence: high                     │
    └──────────────────────────────────────┘
    """
    tier = _get_rating_tier(beer)

    card = toga.Box(
        style=Pack(direction=COLUMN, padding=10, padding_bottom=5),
    )

    # Row 1: Name + Untappd rating + BA score
    name_row = toga.Box(style=Pack(direction=ROW))
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
