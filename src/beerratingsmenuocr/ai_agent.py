"""Client that sends menu images to the local API server for analysis."""

import base64
import json
import os
from dataclasses import dataclass, field
from typing import Optional
from urllib.request import Request, urlopen
from urllib.parse import urljoin

# Default to localhost; override with SERVER_URL env var for real devices
DEFAULT_SERVER_URL = "http://localhost:8888"


def _normalize_url(url: str) -> str:
    """Ensure the URL has an http:// scheme."""
    url = url.strip()
    if url and not url.startswith(("http://", "https://")):
        url = f"http://{url}"
    return url


@dataclass
class BeerRating:
    """Beer rating data returned from the server. Pure Python, no Rust deps."""

    name: str
    brewery: str
    style: str
    description: str
    confidence: str
    abv: Optional[str] = None
    rating_untappd: Optional[float] = None
    rating_beer_advocate: Optional[int] = None


@dataclass
class AnalysisResult:
    """Complete result from the server: beers + optional annotated image."""

    beers: list[BeerRating]
    annotated_image: Optional[bytes] = None


@dataclass
class OcrBeer:
    """A single beer identified by OCR (no ratings yet)."""

    name: str
    brewery: Optional[str] = None
    style_hint: Optional[str] = None
    abv: Optional[str] = None
    y_position: Optional[float] = None


@dataclass
class OcrResult:
    """OCR-only result: identified beer names and positions."""

    beers: list[OcrBeer]
    menu_notes: Optional[str] = None


class BeerMenuAgent:
    """Client that sends images to the backend server and parses results.

    On desktop (briefcase dev), the server runs on localhost.
    On iPad/iPhone on the same Wi-Fi, point SERVER_URL to your Mac's IP.
    """

    def __init__(self, server_url: str | None = None):
        self.server_url = _normalize_url(
            server_url
            or os.environ.get("SERVER_URL")
            or DEFAULT_SERVER_URL
        )

    def _build_url(self, path: str) -> str:
        """Build a full URL for the given endpoint path."""
        return urljoin(self.server_url.rstrip("/") + "/", path)

    def _post_multipart(self, path: str, image_data: bytes, timeout: int = 120) -> dict:
        """POST image as multipart/form-data, return parsed JSON."""
        url = self._build_url(path)
        boundary = "----BeerMenuBoundary"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="image"; filename="menu.png"\r\n'
            f"Content-Type: image/png\r\n"
            f"\r\n"
        ).encode("utf-8") + image_data + f"\r\n--{boundary}--\r\n".encode("utf-8")

        req = Request(
            url,
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )

        try:
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            raise RuntimeError(
                f"Could not reach the server at {self.server_url}. "
                f"Make sure server.py is running.\n\n"
                f"Start it with:\n"
                f"  uvicorn server:app --host 0.0.0.0 --port 8888\n\n"
                f"Error: {e}"
            )

    def _post_json(self, path: str, payload: dict, timeout: int = 60) -> dict:
        """POST JSON body, return parsed JSON."""
        url = self._build_url(path)
        body = json.dumps(payload).encode("utf-8")

        req = Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            raise RuntimeError(
                f"Server request failed ({path}): {e}"
            )

    # ── Legacy single-call method ─────────────────────────────────

    def analyze_image(self, image_data: bytes) -> AnalysisResult:
        """Send image to the server and get back rated beers + annotated image.

        Args:
            image_data: Raw image bytes (PNG or JPEG).

        Returns:
            AnalysisResult with beers list and optional annotated image bytes.

        Raises:
            RuntimeError: If the server is unreachable or returns an error.
        """
        data = self._post_multipart("analyze", image_data)

        if "beers" not in data:
            raise RuntimeError(f"Unexpected server response: {data}")

        beers = [
            BeerRating(
                name=b.get("name", "Unknown"),
                brewery=b.get("brewery", "Unknown"),
                style=b.get("style", "Unknown"),
                abv=b.get("abv"),
                rating_untappd=b.get("rating_untappd"),
                rating_beer_advocate=b.get("rating_beer_advocate"),
                description=b.get("description", ""),
                confidence=b.get("confidence", "low"),
            )
            for b in data["beers"]
        ]

        # Decode annotated image if present
        annotated_image = None
        if data.get("annotated_image"):
            annotated_image = base64.b64decode(data["annotated_image"])

        return AnalysisResult(beers=beers, annotated_image=annotated_image)

    # ── Incremental methods ───────────────────────────────────────

    def ocr_image(self, image_data: bytes) -> OcrResult:
        """Step 1: Send image to server for OCR only (no ratings).

        Returns identified beer names and their approximate positions.
        """
        data = self._post_multipart("ocr", image_data)

        if "beers" not in data:
            raise RuntimeError(f"Unexpected server response: {data}")

        beers = [
            OcrBeer(
                name=b.get("name", "Unknown"),
                brewery=b.get("brewery"),
                style_hint=b.get("style_hint"),
                abv=b.get("abv_on_menu"),
                y_position=b.get("y_position"),
            )
            for b in data["beers"]
        ]

        return OcrResult(beers=beers, menu_notes=data.get("menu_notes"))

    def rate_beer(self, name: str, brewery: str = None,
                  style_hint: str = None, abv: str = None) -> BeerRating:
        """Step 2: Get rating + details for a single beer."""
        payload = {"name": name}
        if brewery:
            payload["brewery"] = brewery
        if style_hint:
            payload["style_hint"] = style_hint
        if abv:
            payload["abv"] = abv

        data = self._post_json("rate", payload)

        return BeerRating(
            name=data.get("name", name),
            brewery=data.get("brewery", "Unknown"),
            style=data.get("style", "Unknown"),
            abv=data.get("abv"),
            rating_untappd=data.get("rating_untappd"),
            rating_beer_advocate=data.get("rating_beer_advocate"),
            description=data.get("description", ""),
            confidence=data.get("confidence", "low"),
        )

    def get_annotated_image(self, image_data: bytes,
                            ocr_beers: list[OcrBeer],
                            rated_beers: list[BeerRating]) -> bytes:
        """Step 3: Get the annotated menu image with numbered markers."""
        payload = {
            "image_base64": base64.b64encode(image_data).decode("utf-8"),
            "ocr_beers": [
                {
                    "name": b.name,
                    "brewery": b.brewery,
                    "style_hint": b.style_hint,
                    "abv_on_menu": b.abv,
                    "y_position": b.y_position,
                }
                for b in ocr_beers
            ],
            "rated_beers": [
                {
                    "name": b.name,
                    "brewery": b.brewery,
                    "style": b.style,
                    "abv": b.abv,
                    "rating_untappd": b.rating_untappd,
                    "rating_beer_advocate": b.rating_beer_advocate,
                    "description": b.description,
                    "confidence": b.confidence,
                }
                for b in rated_beers
            ],
        }

        data = self._post_json("annotate", payload, timeout=30)

        if data.get("annotated_image"):
            return base64.b64decode(data["annotated_image"])
        raise RuntimeError("No annotated image returned")
