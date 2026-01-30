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

    cards_box = toga.Box(style=Pack(direction=COLUMN, padding=5))
    for beer in beers:
        cards_box.add(_build_beer_card(beer))

    scroll = toga.ScrollContainer(
        content=cards_box,
        horizontal=False,
        style=Pack(flex=1),
    )

    return [header_box, scroll]


def _build_beer_card(beer) -> toga.Box:
    """Build a single beer result card.

    Layout:
    ┌──────────────────────────────────────┐
    │ Beer Name                    4.2 / 5 │
    │ Brewery Name                         │
    │ Style · ABV                          │
    │ Description text here...             │
    │ BA: 92 · Confidence: high            │
    └──────────────────────────────────────┘
    """
    card = toga.Box(
        style=Pack(direction=COLUMN, padding=10, padding_bottom=5),
    )

    # Row 1: Name + Untappd rating
    name_row = toga.Box(style=Pack(direction=ROW))
    name_row.add(
        toga.Label(
            beer.name,
            style=Pack(font_size=16, font_weight=BOLD, flex=1),
        )
    )
    rating_text = (
        f"{beer.rating_untappd:.1f} / 5"
        if beer.rating_untappd is not None
        else "N/A"
    )
    name_row.add(
        toga.Label(
            rating_text,
            style=Pack(font_size=14, font_weight=BOLD, color="#e8a500"),
        )
    )
    card.add(name_row)

    # Row 2: Brewery
    card.add(
        toga.Label(
            beer.brewery or "Unknown Brewery",
            style=Pack(font_size=13, color="#555555", padding_top=2),
        )
    )

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

    # Row 5: BeerAdvocate score + Confidence
    detail_row = toga.Box(style=Pack(direction=ROW, padding_top=4))
    ba_text = (
        f"BeerAdvocate: {beer.rating_beer_advocate}"
        if beer.rating_beer_advocate is not None
        else "BeerAdvocate: N/A"
    )
    detail_row.add(
        toga.Label(ba_text, style=Pack(font_size=11, color="#888888", flex=1))
    )

    confidence_color = {
        "high": "#2e7d32",
        "medium": "#f57f17",
        "low": "#c62828",
    }.get(beer.confidence, "#888888")
    detail_row.add(
        toga.Label(
            f"Confidence: {beer.confidence}",
            style=Pack(font_size=11, color=confidence_color),
        )
    )
    card.add(detail_row)

    # Divider
    card.add(toga.Divider(style=Pack(padding_top=8)))

    return card
