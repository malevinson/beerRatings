"""Data models for beer identification and ratings."""

from pydantic import BaseModel, Field
from typing import Optional


class BeerIdentification(BaseModel):
    """A single beer identified from a menu image."""

    name: str = Field(description="The beer name as shown on the menu")
    brewery: Optional[str] = Field(
        default=None,
        description="The brewery name, if visible or identifiable",
    )
    style_hint: Optional[str] = Field(
        default=None,
        description="Any style info visible on the menu (e.g., IPA, Stout)",
    )
    abv_on_menu: Optional[str] = Field(
        default=None,
        description="ABV percentage if shown on the menu",
    )
    price: Optional[str] = Field(
        default=None,
        description="Price if shown on the menu",
    )
    y_position: Optional[float] = Field(
        default=None,
        description="Approximate vertical position of this beer on the menu as a fraction from 0.0 (top) to 1.0 (bottom)",
    )
    x_end: Optional[float] = Field(
        default=None,
        description="Approximate horizontal position where the beer name text ends, as a fraction from 0.0 (left) to 1.0 (right)",
    )


class MenuAnalysis(BaseModel):
    """The complete analysis of a beer menu image."""

    beers: list[BeerIdentification] = Field(
        description="All beers identified on the menu"
    )
    menu_notes: Optional[str] = Field(
        default=None,
        description="Any general notes about the menu",
    )


class BeerRating(BaseModel):
    """Detailed rating and info for a single beer."""

    name: str = Field(description="Beer name")
    brewery: str = Field(description="Brewery name")
    style: str = Field(
        description="Beer style (e.g., New England IPA, Imperial Stout)"
    )
    abv: Optional[str] = Field(
        default=None,
        description="ABV percentage (e.g., '6.5%')",
    )
    rating_untappd: Optional[float] = Field(
        default=None,
        description="Approximate Untappd rating (0.0-5.0 scale), or null if unknown",
    )
    rating_beer_advocate: Optional[int] = Field(
        default=None,
        description="Approximate BeerAdvocate score (0-100 scale), or null if unknown",
    )
    description: str = Field(
        description="1-2 sentence description of the beer's flavor profile and character"
    )
    confidence: str = Field(
        description="How confident in this identification: 'high', 'medium', or 'low'"
    )
    brand_colors: Optional[list[str]] = Field(
        default=None,
        description="2-3 hex color codes representing the beer's bottle, can, or brand colors (e.g., ['#c8102e', '#ffffff']). Use the brewery's brand palette or the dominant packaging colors.",
    )


class BeerRatingsResult(BaseModel):
    """The complete ratings result for all identified beers."""

    beers: list[BeerRating] = Field(
        description="Ratings and details for each identified beer"
    )


def make_strict_schema(model_class) -> dict:
    """Convert a Pydantic model's JSON schema to OpenAI strict format.

    OpenAI's strict mode requires additionalProperties: false on all objects
    and all properties listed in required. Pydantic v2 doesn't emit these
    by default, so we patch the schema recursively.
    """
    schema = model_class.model_json_schema()
    _enforce_strict(schema)
    # Also process any $defs
    if "$defs" in schema:
        for def_schema in schema["$defs"].values():
            _enforce_strict(def_schema)
    return schema


def _enforce_strict(obj):
    """Recursively set additionalProperties: false and required on all objects."""
    if isinstance(obj, dict):
        if obj.get("type") == "object" or "properties" in obj:
            obj["additionalProperties"] = False
            if "properties" in obj:
                obj["required"] = list(obj["properties"].keys())
        for value in obj.values():
            _enforce_strict(value)
    elif isinstance(obj, list):
        for item in obj:
            _enforce_strict(item)
