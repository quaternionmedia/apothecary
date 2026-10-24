"""
Theatre - a proscenium theatre's shell, sized by sliders.

The stage floor, its side and upstage walls, the proscenium wall with its opening,
the pit below the stage, and the side walls running downstage into the house
(parts/theatre/theatre.scad). Each size is a parameter with a range, so Part › Edit
shows it as a slider, and Apply draws the resized shell where the site stands it.
Every default is a measurement of one real stage house, traced from its plan.

Frame: millimetres; the origin is the plaster line's centre on the stage floor;
+x is to the right as the house sees the stage, +y upstage, +z up. The theatre
site (apothecary/theatre_site.py) stands the shell at the site's origin and hangs
a lighting rig in the same frame.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from pydantic import BaseModel, Field

from apothecary.models import BoundingBox3D, Color, Vector3D

from .base import BasePart
from .skeleton import ROOT

MM = {"unit": "mm"}

# Fixed in the SCAD (its [Hidden] section): thicknesses and the pit's front edge.
STAGE_FLOOR = 200
SIDE_WALL = 1365
UPSTAGE_WALL = 3900
PIT_FRONT = 1170


class Params(BaseModel):
    """The theatre's sizes, in millimetres; the ranges are the SCAD's sliders."""

    stage_width: float = Field(
        23010, ge=8000, le=40000, description="Stage floor, wall to wall", json_schema_extra=MM
    )
    stage_depth: float = Field(
        24375,
        ge=6000,
        le=40000,
        description="Plaster line to the upstage wall",
        json_schema_extra=MM,
    )
    wall_height: float = Field(
        9000, ge=4000, le=20000, description="Walls, from the stage floor", json_schema_extra=MM
    )
    house_depth: float = Field(
        10920,
        ge=0,
        le=40000,
        description="How far the side walls run downstage of the plaster line",
        json_schema_extra=MM,
    )
    proscenium_width: float = Field(
        15015, ge=4000, le=40000, description="The proscenium opening", json_schema_extra=MM
    )
    proscenium_height: float = Field(
        9000,
        ge=3000,
        le=20000,
        description="The opening's height; the wall's, for no header",
        json_schema_extra=MM,
    )
    pit_width: float = Field(
        20748, ge=0, le=40000, description="The pit below the stage", json_schema_extra=MM
    )
    pit_length: float = Field(
        14040, ge=0, le=40000, description="The pit, downstage to upstage", json_schema_extra=MM
    )
    pit_depth: float = Field(
        1200,
        ge=0,
        le=4000,
        description="The pit, below the stage floor's underside",
        json_schema_extra=MM,
    )


class TheatrePart(BasePart):
    """The shell, its envelope worked out from its sizes as the SCAD draws them."""

    def get_bounds(self, params: Optional[Dict] = None) -> BoundingBox3D:
        p = Params(**(params or {}))
        half = p.stage_width / 2 + SIDE_WALL
        pit = p.pit_width > 0 and p.pit_length > 0 and p.pit_depth > 0
        return BoundingBox3D(
            min_point=Vector3D(
                x=-max(half, p.pit_width / 2 if pit else 0),
                y=-max(p.house_depth, PIT_FRONT if pit else 0),
                z=-STAGE_FLOOR - (p.pit_depth if pit else 0),
            ),
            max_point=Vector3D(
                x=max(half, p.pit_width / 2 if pit else 0),
                y=max(p.stage_depth + UPSTAGE_WALL, p.pit_length - PIT_FRONT if pit else 0),
                z=p.wall_height,
            ),
        )


def create(metadata_root: Path) -> TheatrePart:
    scad = metadata_root / "parts" / "theatre" / "theatre.scad"
    return TheatrePart(
        name="theatre",
        source_file=scad,
        description="A proscenium theatre's shell, its stage, walls, opening and pit sized by sliders",
        params_model=Params,
        # A building: a site's, not one of the bench's parts (example_parts_library.py).
        category="building",
        tags=["theatre", "stage", "lighting", "building"],
        readme_path=metadata_root / "parts" / "README.md",
        preview_color=Color.from_hex("#6b5b4b"),
    )


DEFAULT = create(ROOT)
