"""Creality Ender 3 -- the printers on the garage bench, drawn as the machine is.

A parametric model built from published dimensions (see ``parts/ender3/ender3.scad``
for which numbers are specifications and which are measured): the frame of
2040/2020 extrusion, the bed on its springs, the X gantry with the hotend, the
power supply on the right side behind the upright, the electronics box under
the bed at the front left, the LCD off the front-right corner, the spool on
its bracket over the top bar. The axes are parameters, so a site can draw the
machine with its nozzle where the last poll said it was.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from pydantic import BaseModel, Field

from apothecary.models import BoundingBox3D, Color, Vector3D

from .base import BasePart
from .skeleton import ROOT

# The model's frame, in mm, as the SCAD file states it. A site places the
# printer by these: the bed's build surface, and where the nozzle's (0, 0) is
# when the bed is at home.
FRAME = Vector3D(x=400.0, y=410.0, z=440.0)  # the base frame and the top of the crossbar
OVERALL = Vector3D(x=470.0, y=454.0, z=570.0)  # with the LCD, the PSU and a spool on the holder
BED_TOP_Z = 95.0
BUILD = Vector3D(x=220.0, y=220.0, z=250.0)
BED_PLATE = 235.0
NOZZLE_Y = 100.0  # 30 mm in front of the X gantry (upright_y - rail - 30)
BUILD_ORIGIN = Vector3D(x=(FRAME.x - BED_PLATE) / 2 + 7.5, y=NOZZLE_Y, z=BED_TOP_Z)
"""Where the printable volume starts in the model's frame: the nozzle at (0, 0, 0)
stands here, and the bed moves under it."""
PSU = BoundingBox3D(min_point=Vector3D(x=400, y=195, z=20), max_point=Vector3D(x=450, y=410, z=135))
ELECTRONICS_BOX = BoundingBox3D(
    min_point=Vector3D(x=66, y=40, z=21), max_point=Vector3D(x=196, y=220, z=66)
)


class Params(BaseModel):
    """Where the axes stand, and what hangs on the frame."""

    z_axis: float = Field(150.0, ge=0, le=250, description="Nozzle height above the bed (mm)")
    x_axis: float = Field(110.0, ge=0, le=220, description="Nozzle X, in bed coordinates (mm)")
    y_axis: float = Field(110.0, ge=0, le=220, description="Bed Y, in bed coordinates (mm)")
    with_spool: bool = Field(True, description="A spool on the holder")
    with_lcd: bool = Field(True, description="The LCD and its bracket")


class Ender3Part(BasePart):
    def get_bounds(self, params: Optional[Dict] = None) -> BoundingBox3D:
        p = Params(**(params or {}))
        top = OVERALL.z if p.with_spool else FRAME.z + 42.5  # the spool, or just the tube
        front = -41.0 if p.with_lcd else min(0.0, NOZZLE_Y - 7.5 - p.y_axis)
        return BoundingBox3D(
            min_point=Vector3D(x=-2.0, y=front, z=0.0),
            max_point=Vector3D(x=OVERALL.x, y=FRAME.y + 3, z=top),
        )


def create(root: Path) -> BasePart:
    return Ender3Part(
        name="ender3",
        source_file=root / "parts" / "ender3" / "ender3.scad",
        description="Creality Ender 3 (2018): frame, bed, gantry, the power supply on the right, "
        "the electronics box front-left, the LCD, the spool holder -- from published dimensions.",
        params_model=Params,
        category="machine",
        tags=["printer", "ender3", "creality", "fdm"],
        readme_path=root / "parts" / "ender3" / "README.md",
        preview_color=Color(r=0.75, g=0.75, b=0.78),
        default_bounds=BoundingBox3D(min_point=Vector3D(x=-2.0, y=-41.0, z=0.0), max_point=OVERALL),
    )


DEFAULT = create(ROOT)
