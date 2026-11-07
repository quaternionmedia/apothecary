"""AnoleX 4060-Evo Ultra 2 -- the router in the garage, drawn as the machine is.

A parametric model built from published dimensions (see
``parts/anolex_4060_evo_ultra_2/anolex_4060_evo_ultra_2.scad`` for which
numbers are specifications and which are taken from the maker's listed
footprint or chosen): the base of two side beams carrying the Y rails, the
fixed T-slot table between them, the gantry riding the Y rails with the X
carriage on its cross beam and the Z plate on that, the trim router in its
clamp, the control box at the back. The axes are parameters, so a site can
draw the machine with its tool where the last poll said it was.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from pydantic import BaseModel, Field

from apothecary.models import BoundingBox3D, Color, Vector3D

from .base import BasePart
from .skeleton import ROOT

# The model's frame, in mm, as the SCAD file states it. A site places the
# router by these: the table's top, and where the tool's (0, 0) is when the
# gantry is at its front stop.
FRAME = Vector3D(x=630.0, y=930.0, z=469.5)  # the base, and the Z motor's cap at the top
OVERALL = Vector3D(x=701.5, y=1021.5, z=469.5)  # with the X and Y motors past the frame
WORK = Vector3D(x=400.0, y=600.0, z=80.0)  # the working area, the maker's figure
TABLE = Vector3D(x=460.0, y=680.0, z=20.0)
TABLE_TOP_Z = 100.0
WORK_ORIGIN = Vector3D(
    x=(FRAME.x - WORK.x) / 2,
    y=(FRAME.y - TABLE.y) / 2 + (TABLE.y - WORK.y) / 2,
    z=TABLE_TOP_Z,
)
"""Where the working area starts in the model's frame: the tool at (0, 0, 0)
stands here, at the table's top, and the gantry carries it over the table."""
CONTROL_BOX = BoundingBox3D(
    min_point=Vector3D(x=215.0, y=810.0, z=0.0), max_point=Vector3D(x=415.0, y=910.0, z=90.0)
)
"""The controller's enclosure, in the model's frame: at the back of the base,
between the side beams, standing on the floor."""


class Params(BaseModel):
    """Where the axes stand, and whether the router is in its clamp."""

    x_axis: float = Field(200.0, ge=0, le=400, description="Tool X, in work coordinates (mm)")
    y_axis: float = Field(300.0, ge=0, le=600, description="Gantry Y, in work coordinates (mm)")
    z_axis: float = Field(40.0, ge=0, le=80, description="Tool tip height above the table (mm)")
    with_router: bool = Field(True, description="The trim router in its clamp")


class Anolex4060EvoUltra2Part(BasePart):
    def get_bounds(self, params: Optional[Dict] = None) -> BoundingBox3D:
        Params(**(params or {}))  # the axes move the tool within the frame; the envelope stays
        return BoundingBox3D(min_point=Vector3D(x=0.0, y=0.0, z=0.0), max_point=OVERALL)


def create(root: Path) -> BasePart:
    return Anolex4060EvoUltra2Part(
        name="anolex_4060_evo_ultra_2",
        source_file=root / "parts" / "anolex_4060_evo_ultra_2" / "anolex_4060_evo_ultra_2.scad",
        description="AnoleX 4060-Evo Ultra 2: a desktop CNC router cutting 400 x 600 x 80 mm -- "
        "the base and its Y rails, the T-slot table, the gantry, the X carriage and the Z "
        "plate, the trim router in its clamp, the control box at the back -- from published "
        "dimensions.",
        params_model=Params,
        category="machine",
        machine="router",
        tags=["router", "cnc", "anolex", "grbl"],
        readme_path=root / "parts" / "anolex_4060_evo_ultra_2" / "README.md",
        preview_color=Color(r=0.72, g=0.74, b=0.78),
        default_bounds=BoundingBox3D(min_point=Vector3D(), max_point=OVERALL),
    )


DEFAULT = create(ROOT)
