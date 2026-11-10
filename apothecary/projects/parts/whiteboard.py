"""A whiteboard -- the panel on the garage's wall a person draws on.

A flat panel in a thin frame with a tray under it (``parts/whiteboard``). Its
``width`` and ``height`` are the writing surface's own, the part a photograph
shows inside the frame: the surface's width is what sizes a photograph squared
to it (``apothecary/vision/whiteboard.py``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from pydantic import BaseModel, Field

from apothecary.models import BoundingBox3D, Color, Vector3D

from .base import BasePart
from .skeleton import ROOT


class Params(BaseModel):
    """The writing surface's size, and the frame and tray round it."""

    width: float = Field(
        1200.0,
        ge=300,
        le=3000,
        description="The writing surface's width: what sizes a photograph squared to it",
        json_schema_extra={"unit": "mm"},
    )
    height: float = Field(
        900.0,
        ge=200,
        le=1500,
        description="The writing surface's height",
        json_schema_extra={"unit": "mm"},
    )
    frame: float = Field(
        15.0,
        ge=5,
        le=40,
        description="The frame's width round the surface",
        json_schema_extra={"unit": "mm"},
    )
    thickness: float = Field(
        20.0,
        ge=8,
        le=40,
        description="From the wall to the frame's face",
        json_schema_extra={"unit": "mm"},
    )
    tray: float = Field(
        60.0,
        ge=0,
        le=120,
        description="How far the tray stands out from the wall; none at 0",
        json_schema_extra={"unit": "mm"},
    )


def overall(params: Optional[Dict] = None) -> Vector3D:
    """The whole part's size, frame and tray included: along the wall, from the
    front of its tray back to the wall, and up."""
    held = Params(**(params or {}))
    return Vector3D(
        x=held.width + 2 * held.frame,
        y=max(held.thickness, held.tray),
        z=held.height + 2 * held.frame,
    )


def surface(params: Optional[Dict] = None) -> Vector3D:
    """The writing surface's size, as a photograph squared to it has it: its
    width and its height, with nothing out from the wall."""
    held = Params(**(params or {}))
    return Vector3D(x=held.width, y=0.0, z=held.height)


OVERALL = overall()


class WhiteboardPart(BasePart):
    def get_bounds(self, params: Optional[Dict] = None) -> BoundingBox3D:
        return BoundingBox3D(min_point=Vector3D(), max_point=overall(params))


def create(root: Path) -> BasePart:
    return WhiteboardPart(
        name="whiteboard",
        source_file=root / "parts" / "whiteboard" / "whiteboard.scad",
        description="A whiteboard: a flat panel in a thin frame with a tray under it, hung on a "
        "wall -- what a drawing is made on, and what a photograph of one is squared to.",
        params_model=Params,
        category="furniture",
        tags=["whiteboard", "drawing", "wall", "picture"],
        readme_path=root / "parts" / "whiteboard" / "README.md",
        preview_color=Color(r=0.95, g=0.95, b=0.93),
        default_bounds=BoundingBox3D(min_point=Vector3D(), max_point=OVERALL),
    )


DEFAULT = create(ROOT)
