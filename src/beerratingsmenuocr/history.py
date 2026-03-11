"""Scan history — persists past menu scans as JSON in app data dir."""

import base64
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path


_HISTORY_FILE = "scan_history.json"
_MAX_ENTRIES = 50  # keep last 50 scans


def _history_path(data_dir: Path) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / _HISTORY_FILE


def load_history(data_dir: Path) -> list[dict]:
    """Load scan history. Returns list of dicts, newest first."""
    path = _history_path(data_dir)
    if not path.exists():
        return []
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
        return entries if isinstance(entries, list) else []
    except Exception:
        return []


def save_scan(data_dir: Path, ocr_beers: list, rated_beers: list,
              thumbnail: bytes = None) -> None:
    """Append a completed scan to history."""
    entry = {
        "date": datetime.now().isoformat(),
        "beers": [],
    }
    if thumbnail:
        entry["thumbnail"] = base64.b64encode(thumbnail).decode("ascii")
    for i, ocr in enumerate(ocr_beers):
        beer = {"name": ocr.name, "brewery": getattr(ocr, "brewery", None)}
        rating = rated_beers[i] if i < len(rated_beers) else None
        if rating is not None:
            beer.update({
                "style": rating.style,
                "abv": rating.abv,
                "rating_untappd": rating.rating_untappd,
                "rating_beer_advocate": rating.rating_beer_advocate,
                "description": rating.description,
                "confidence": rating.confidence,
                "brand_colors": rating.brand_colors,
                "brewery": rating.brewery,
            })
        entry["beers"].append(beer)

    history = load_history(data_dir)
    history.insert(0, entry)  # newest first
    history = history[:_MAX_ENTRIES]

    path = _history_path(data_dir)
    path.write_text(json.dumps(history, indent=2), encoding="utf-8")


def delete_scan(data_dir: Path, index: int) -> None:
    """Delete a single scan entry by index."""
    history = load_history(data_dir)
    if 0 <= index < len(history):
        history.pop(index)
        path = _history_path(data_dir)
        path.write_text(json.dumps(history, indent=2), encoding="utf-8")
