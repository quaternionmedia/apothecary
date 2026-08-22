"""
datum_cap - the cover for a datum_core tray.

Four contact openings on a 2 x 2 grid and one indicator light pipe, over a lip
that drops into the core's cavity.

Split out of datum_core rather than selected by a parameter there. A `show`
enum picking between the tray and the cover made one part's bounds depend on
which mode you asked for, and the enclosure record asks for one core body with
separate pieces around it.

The board dimensions are assumptions carried as parameters, not measurements:
no schematic exists. They match datum_core's, because the two pieces have to
fit each other.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from pydantic import BaseModel, Field

from apothecary.models import BoundingBox3D, Color, PrintSettings, Vector3D

from .base import BasePart
from .skeleton import ROOT


class Params(BaseModel):
    """Parameters mirroring the SCAD defaults.

    Attributes:
        board_x: Board width in mm, which sets the cover's footprint
        board_y: Board depth in mm
        board_clearance: Gap between the board edge and the cavity wall
        walls: Side wall thickness (house constant)
        tolerence: Total fit clearance; the lip takes half per side (house constant)
        lid_t: Plate thickness
        lip_h: Depth the lip drops into the tray
        contact_d: Diameter of each contact opening
        indicator_d: Diameter of the indicator light pipe
    """

    board_x: float = Field(40.0, gt=0)
    board_y: float = Field(40.0, gt=0)
    board_clearance: float = Field(0.4, ge=0)
    walls: float = Field(3.0, gt=0)
    tolerence: float = Field(0.4, ge=0)
    lid_t: float = Field(2.0, gt=0)
    lip_h: float = Field(3.0, ge=0)
    contact_d: float = Field(12.0, gt=0)
    contact_pitch_x: float = Field(18.0, gt=0)
    contact_pitch_y: float = Field(18.0, gt=0)
    indicator_d: float = Field(4.0, gt=0)
    indicator_x: float = Field(0.0)
    indicator_y: float = Field(14.0)
    corner_r: float = Field(3.0, gt=0)


class DatumCapPart(BasePart):
    """A cover whose footprint is the tray's, because it has to sit on it."""

    def get_bounds(self, params: Optional[Dict] = None) -> BoundingBox3D:
        values = Params(**(params or {}))

        outer_x = values.board_x + 2 * values.board_clearance + 2 * values.walls
        outer_y = values.board_y + 2 * values.board_clearance + 2 * values.walls
        height = values.lid_t + values.lip_h

        return BoundingBox3D(
            min_point=Vector3D(x=-outer_x / 2, y=-outer_y / 2, z=0),
            max_point=Vector3D(x=outer_x / 2, y=outer_y / 2, z=height),
        )


def create(metadata_root: Path) -> DatumCapPart:
    scad = metadata_root / "parts" / "datum_cap" / "datum_cap.scad"
    return DatumCapPart(
        name="datum_cap",
        source_file=scad,
        description="Cover for a datum_core tray: four contact openings and an indicator pipe",
        params_model=Params,
        category="enclosure",
        tags=["datum", "enclosure", "cover", "lid", "control-surface"],
        readme_path=metadata_root / "parts" / "datum_cap" / "README.md",
        # The house constants, so a slicer profile is not guesswork and the
        # part's own `walls`/`tolerence` are not a second opinion about them.
        print_settings=PrintSettings(
            nozzle_diameter=0.4, layer_height=0.2, wall_thickness=3.0, tolerance=0.4
        ),
        preview_color=Color.from_hex("#5A9367"),
        # The same disagreement datum_core carries: these two pieces have to be
        # made on the same printer, so they share the manufacturing facts.
        # Nothing contested remains. `walls` and `tolerence` were disputed
        # only by parts/datum, the single-piece tray the compound replaced,
        # which carried 2.4 and 0.2 while citing the enclosure record for
        # values that record does not contain. Retiring it left the house
        # constants unopposed -- a resolution, not a silencing, because what
        # went away was an artifact making a claim it could not support.
        contested={},
    )


DEFAULT = create(ROOT)
