"""Footpedal - A 3D printable MIDI foot controller.

A wedge-shaped pedalboard with button cutouts for arcade-style switches,
designed to work with an Arduino Nano for MIDI control.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from .base import BasePart
from .skeleton import ROOT


class FootpedalParams(BaseModel):
    """Parameters for the foot pedal."""

    x: float = Field(default=180, description="Width of the pedalboard in mm")
    y: float = Field(default=100, description="Depth of the pedalboard in mm")
    z: float = Field(default=30, description="Height of the pedalboard in mm")
    wall: float = Field(default=4, description="Wall thickness in mm")
    theta: float = Field(default=-16, description="Wedge angle in degrees")


def create(metadata_root: Path) -> BasePart:
    """Create the footpedal part instance."""
    scad = metadata_root / "parts" / "footpedal" / "footpedal.scad"
    return BasePart(
        name="footpedal",
        source_file=scad,
        description="A 3D printable MIDI foot controller with Arduino Nano",
        params_model=FootpedalParams,
        category="electronics",
        tags=["midi", "controller", "arduino", "music", "pedal"],
        # No display_rotation: its SCAD lays it on its button face, the way up it prints.
    )


DEFAULT = create(ROOT)
