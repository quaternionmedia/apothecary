"""Fifel - A printable fife/recorder musical instrument.

A parametric design for a simple wind instrument with configurable
hole positions, sizes, and rotations.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from apothecary.models import Vector3D

from .base import BasePart
from .skeleton import ROOT


class FifelParams(BaseModel):
    """Parameters for the fifel instrument."""

    height: float = Field(default=200, description="Total length of the fife in mm")
    bore: float = Field(default=20, description="Inner diameter of the resonating chamber")
    wall: float = Field(default=4, description="Wall thickness in mm")


def create(metadata_root: Path) -> BasePart:
    """Create the fifel part instance."""
    scad = metadata_root / "parts" / "fifel" / "fifel.scad"
    return BasePart(
        name="fifel",
        source_file=scad,
        description="A printable fife/recorder musical instrument",
        params_model=FifelParams,
        category="music",
        tags=["instrument", "fife", "recorder", "music", "printable"],
        # Rotate to stand tall on Z axis (originally lies along Y)
        display_rotation=Vector3D(x=90, y=0, z=0),
    )


DEFAULT = create(ROOT)
