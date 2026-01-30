"""OpenAI-powered agent for beer menu analysis and ratings lookup."""

import os
import base64

from openai import OpenAI

from .models import (
    MenuAnalysis,
    BeerIdentification,
    BeerRatingsResult,
    BeerRating,
    make_strict_schema,
)


MENU_ANALYSIS_SYSTEM_PROMPT = """\
You are an expert beer menu reader and OCR system.

Your task: Given a photograph of a beer menu, tap list, beer board, or beer
list, identify EVERY beer shown on the menu.

Instructions:
- Read the menu carefully. Extract the name of each beer.
- If the brewery name is visible, include it.
- If style information is shown (IPA, Stout, Lager, etc.), include it.
- If ABV is shown, include it.
- If price is shown, include it.
- Do NOT guess or invent beers that are not visible.
- If the image is blurry or some text is unreadable, do your best and note
  uncertainty in the beer name (e.g., append "[unclear]").
- If the image does not appear to be a beer menu at all, return an empty
  beers list and explain in menu_notes.

Be thorough. It is better to include a beer you are uncertain about (and
flag it) than to miss one."""


RATINGS_LOOKUP_SYSTEM_PROMPT = """\
You are a knowledgeable beer expert with deep knowledge of craft beer,
beer ratings, and brewing.

Your task: For each beer provided, supply detailed information including:
- The correct brewery (confirm or identify if not provided)
- The beer style
- Approximate ABV
- An approximate Untappd rating (0.0-5.0 scale)
- An approximate BeerAdvocate score (0-100 scale)
- A short, appealing 1-2 sentence description of the beer

Important guidelines:
- Use your training knowledge to provide approximate ratings. These do NOT
  need to be exact -- approximate is fine and expected.
- If you recognize the beer, provide your best estimate of its community
  ratings.
- If you do NOT recognize a specific beer, try to identify the brewery and
  style, and provide a reasonable rating estimate based on the brewery's
  reputation and the style.
- Set confidence to "high" if you are confident in the identification,
  "medium" if you are somewhat sure, and "low" if you are guessing.
- For ABV, provide your best estimate if not already known from the menu.
- Never fabricate a rating for a beer you cannot identify at all -- set
  ratings to null and confidence to "low" in that case.
- Ratings should reflect the general community consensus, not personal
  opinion."""


class BeerMenuAgent:
    """Agent that analyzes beer menu images and looks up ratings.

    Uses OpenAI GPT-4o for both vision-based menu reading and
    knowledge-based beer rating lookup.
    """

    def __init__(self, api_key: str | None = None, model: str = "gpt-4o"):
        self.model = model
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._client = None

    @property
    def client(self) -> OpenAI:
        """Lazily create the OpenAI client so the app can start without a key."""
        if self._client is None:
            if not self._api_key:
                raise RuntimeError(
                    "OPENAI_API_KEY is not set. "
                    "Set it as an environment variable before scanning."
                )
            self._client = OpenAI(api_key=self._api_key)
        return self._client

    def identify_beers_from_image(
        self, image_data: bytes
    ) -> list[BeerIdentification]:
        """Send the menu image to GPT-4o Vision to identify beers.

        Args:
            image_data: Raw image bytes (PNG or JPEG).

        Returns:
            List of BeerIdentification objects for each beer found.
        """
        base64_image = base64.b64encode(image_data).decode("utf-8")

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": MENU_ANALYSIS_SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Please analyze this beer menu image and "
                                "identify every beer listed."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}",
                            },
                        },
                    ],
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "menu_analysis",
                    "strict": True,
                    "schema": make_strict_schema(MenuAnalysis),
                },
            },
            max_tokens=4096,
        )

        result_json = response.choices[0].message.content
        menu_analysis = MenuAnalysis.model_validate_json(result_json)
        return menu_analysis.beers

    def get_beer_ratings(
        self, beers: list[BeerIdentification]
    ) -> list[BeerRating]:
        """Look up ratings and details for each identified beer.

        Args:
            beers: List of beers identified from the menu image.

        Returns:
            List of BeerRating objects with full details and ratings.
        """
        beer_descriptions = []
        for i, beer in enumerate(beers, 1):
            parts = [f"{i}. {beer.name}"]
            if beer.brewery:
                parts.append(f"   Brewery: {beer.brewery}")
            if beer.style_hint:
                parts.append(f"   Style: {beer.style_hint}")
            if beer.abv_on_menu:
                parts.append(f"   ABV: {beer.abv_on_menu}")
            beer_descriptions.append("\n".join(parts))

        beers_text = "\n\n".join(beer_descriptions)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": RATINGS_LOOKUP_SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": (
                        f"Please provide ratings and details for these "
                        f"{len(beers)} beers from a menu I just scanned:\n\n"
                        f"{beers_text}"
                    ),
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "beer_ratings_result",
                    "strict": True,
                    "schema": make_strict_schema(BeerRatingsResult),
                },
            },
            max_tokens=4096,
        )

        result_json = response.choices[0].message.content
        ratings_result = BeerRatingsResult.model_validate_json(result_json)
        return ratings_result.beers
