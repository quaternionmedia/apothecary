"""A finder that reads shapes somebody wrote down by hand.

Given ``kettle.png`` it looks for ``kettle.shapes.json`` beside it. Nothing is
guessed, so every shape comes back marked ``stated`` with full confidence —
which records that a person said so, not that they were right.

This is what the tests use. It gives the same answer every time, needs no
picture library, and lets everything downstream be checked without depending on
how well any real finder happens to work.

PROTOTYPE — not ratified.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..models.vectors import Vector2D
from .models import FoundShape, Picture, ShapeKind


class MissingDescriptionError(FileNotFoundError):
    """No hand-written description sits beside the picture."""


class UnreadableDescription(ValueError):
    """The description is there and cannot be made sense of."""


class StatedFinder:
    """Reads a hand-written description instead of looking at pixels."""

    def name(self) -> str:
        return "stated"

    def description_path(self, image: Path) -> Path:
        return Path(image).with_suffix(".shapes.json")

    def look(self, image: Path) -> Picture:
        # Take a plain string too. The protocol says Path, and everything inside
        # here needs one, but a caller with a string should get a picture rather
        # than a puzzle about a missing attribute.
        image = Path(image)
        described = self.description_path(image)
        if not described.exists():
            raise MissingDescriptionError(
                f"expected a hand-written description at {described}; "
                "the stated finder never guesses"
            )
        try:
            raw = json.loads(described.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise UnreadableDescription(
                f"{described} is not readable as a description: {exc}"
            ) from exc
        try:
            shapes = [
                FoundShape(
                    kind=ShapeKind(entry["kind"]),
                    min_point=Vector2D(x=entry["min"][0], y=entry["min"][1]),
                    max_point=Vector2D(x=entry["max"][0], y=entry["max"][1]),
                    points=[Vector2D(x=pt[0], y=pt[1]) for pt in entry.get("points", [])],
                    confidence=float(entry.get("confidence", 1.0)),
                    origin="stated",
                    label=entry.get("label"),
                    turned_degrees=float(entry.get("turned_degrees", 0.0)) % 180.0,
                    long_side=float(entry.get("long_side", 0.0)),
                    short_side=float(entry.get("short_side", 0.0)),
                )
                for entry in raw["shapes"]
            ]
            return Picture(
                name=raw.get("name", image.stem),
                pixel_width=int(raw["pixel_width"]),
                pixel_height=int(raw["pixel_height"]),
                shapes=shapes,
                finder=self.name(),
            )
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            raise UnreadableDescription(
                f"{described} is missing something or has the wrong shape: {exc}"
            ) from exc
