"""What a picture yields: flat shapes, with no size and no certainty.

Everything here is deliberately unitless. A picture gives positions as
fractions of the picture — 0.0 is the left or top edge, 1.0 is the right or
bottom. Turning those into millimetres needs a real-world reference, and there
is no default for that. See ``ScaleReference`` and ``apothecary.vision.compose``.

PROTOTYPE — not ratified. See ``docs/plans/edits/apothecary-model.md``.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

from ..models.vectors import Vector2D


class ShapeKind(str, Enum):
    """The rough family a found shape belongs to."""

    RECT = "rect"
    DISC = "disc"
    TRI = "tri"
    POLY = "poly"
    LINE = "line"


class FoundShape(BaseModel):
    """One flat shape somebody or something spotted in a picture.

    ``origin`` says where this came from, so a later reader can tell a measured
    thing from a guessed one. It mirrors ``BlackBox.source`` in
    ``apothecary/models/blackbox.py``, which exists for the same reason.

    ``confidence`` is how sure the finder is, from 0.0 to 1.0. A hand-written
    description is 1.0 because a person said so, not because it is right.
    """

    kind: ShapeKind
    min_point: Vector2D
    max_point: Vector2D
    points: List[Vector2D] = Field(default_factory=list)
    confidence: float = Field(1.0, ge=0.0, le=1.0)
    origin: str = "stub"
    label: Optional[str] = None
    turned_degrees: float = Field(0.0, ge=0.0, lt=180.0)
    """Which way the shape's long side runs, if it has one.

    Zero for anything round or square, where there is nothing to be turned.
    """

    long_side: float = Field(0.0, ge=0.0)
    short_side: float = Field(0.0, ge=0.0)
    """The shape's own two sides, ignoring how it is turned.

    Both are fractions of the picture's width, and both assume square pixels,
    which is true of any ordinary picture. Zero means nobody measured them, and
    the upright box is all there is to go on.
    """

    @property
    def measured_sides(self) -> bool:
        """True when the shape's own sides are known, not just its upright box."""
        return self.long_side > 0 and self.short_side > 0

    @model_validator(mode="after")
    def _box_makes_sense(self) -> "FoundShape":
        if self.max_point.x < self.min_point.x or self.max_point.y < self.min_point.y:
            raise ValueError(
                "a shape's box runs from its top left to its bottom right, "
                f"and this one runs backwards: {self.min_point} to {self.max_point}"
            )
        for name, point in (("min_point", self.min_point), ("max_point", self.max_point)):
            for axis in ("x", "y"):
                value = getattr(point, axis)
                if not -0.001 <= value <= 1.001:
                    raise ValueError(
                        f"{name}.{axis} is {value}; positions are fractions of the "
                        "picture and belong between 0 and 1"
                    )
        return self

    @property
    def width(self) -> float:
        return self.max_point.x - self.min_point.x

    @property
    def height(self) -> float:
        return self.max_point.y - self.min_point.y

    @property
    def centre(self) -> Vector2D:
        return Vector2D(
            x=(self.min_point.x + self.max_point.x) / 2,
            y=(self.min_point.y + self.max_point.y) / 2,
        )

    @property
    def aspect(self) -> float:
        """Width divided by height. 1.0 is square. Never divides by zero."""
        return self.width / self.height if self.height > 0 else 0.0


class Picture(BaseModel):
    """Everything one finder saw in one picture.

    ``pixel_width`` and ``pixel_height`` are recorded so a fraction can be
    turned back into a pixel count later. They are not a size in the world.
    """

    name: str
    pixel_width: int = Field(gt=0)
    pixel_height: int = Field(gt=0)
    shapes: List[FoundShape] = Field(default_factory=list)
    finder: str = "stub"

    @property
    def guessed(self) -> bool:
        """True when nothing in here was stated by a person."""
        return all(s.origin != "stated" for s in self.shapes)


class AmbiguousReference(ValueError):
    """More than one shape carries the label a reference names."""


class ScaleReference(BaseModel):
    """How to turn fractions of a picture into millimetres.

    There is no default and nothing is inferred. Somebody has to say one of:

    - ``millimetres_across`` — how wide the whole picture is in the world;
    - ``known_shape`` and ``known_width_mm`` — the label of one shape whose
      real width is known.

    Without a reference, shapes are placed without a size and marked as such,
    so the overlap check stays quiet rather than being confidently wrong.
    """

    millimetres_across: Optional[float] = Field(None, gt=0, allow_inf_nan=False)
    known_shape: Optional[str] = None
    known_width_mm: Optional[float] = Field(None, gt=0, allow_inf_nan=False)

    def millimetres_per_unit(self, picture: Picture) -> Optional[float]:
        """How many millimetres one full width of the picture stands for."""
        if self.millimetres_across is not None:
            return self.millimetres_across
        if self.known_shape and self.known_width_mm:
            matches = [s for s in picture.shapes if s.label == self.known_shape]
            if len(matches) > 1:
                raise AmbiguousReference(
                    f"{len(matches)} shapes are labelled {self.known_shape!r}; "
                    "a reference has to name one thing"
                )
            for shape in matches:
                # The shape's own long side, not the upright box round it. A
                # ruler photographed at an angle has an upright box much wider
                # than the ruler, and measuring against that scales the whole
                # build wrong with no warning.
                across = shape.long_side if shape.measured_sides else shape.width
                if across > 0:
                    return self.known_width_mm / across
        return None
