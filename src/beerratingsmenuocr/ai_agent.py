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

    def analyze_image(self, image_data: bytes) -> AnalysisResult:
        """Send image to the server and get back rated beers + annotated image.

        Args:
            image_data: Raw image bytes (PNG or JPEG).

        Returns:
            AnalysisResult with beers list and optional annotated image bytes.

        Raises:
            RuntimeError: If the server is unreachable or returns an error.
        """
        url = urljoin(self.server_url.rstrip("/") + "/", "analyze")

        # Build multipart/form-data manually (no external deps needed)
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
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            method="POST",
        )

        try:
            with urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            raise RuntimeError(
                f"Could not reach the server at {self.server_url}. "
                f"Make sure server.py is running.\n\n"
                f"Start it with:\n"
                f"  uvicorn server:app --host 0.0.0.0 --port 8888\n\n"
                f"Error: {e}"
            )

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
