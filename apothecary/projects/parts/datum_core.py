"""
datum-core - enclosure for a 40 x 40 mm control-surface board.

Four contact openings, one indicator light pipe, an edge connector cutout and
four board standoffs, in a printable tray and a printable lid.

The board dimensions are assumptions carried as parameters, not measurements:
no schematic exists yet. Tune them here and in the SCAD defaults together.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from pydantic import BaseModel, Field

from apothecary.models import BoundingBox3D, Color, Vector3D

from .base import BasePart, ContestedValue
from .skeleton import ROOT


class Params(BaseModel):
    """Parameters mirroring the SCAD defaults.

    Attributes:
        show: Which piece to render - tray, lid, or the exploded assembly
        board_x: Board width in mm
        board_y: Board depth in mm
        board_t: Board thickness in mm
        board_clearance: Gap between the board edge and the cavity wall
        walls: Side wall thickness (house constant)
        tolerence: Total fit clearance (house constant)
        floor_t: Tray floor thickness
        lid_t: Lid plate thickness
        standoff_h: Floor to board underside
        headroom: Board top to lid underside
        explode_gap: Separation between the pieces in the exploded preview
    """

    show: str = Field("tray", pattern="^(tray|lid|exploded)$")
    # Manufacturing facts, house defaults. A consumer overrides these for its
    # own printer; it does not own them.
    walls: float = Field(3.0, gt=0)
    tolerence: float = Field(0.4, ge=0)
    board_x: float = Field(40.0, gt=0)
    board_y: float = Field(40.0, gt=0)
    board_t: float = Field(1.6, gt=0)
    board_clearance: float = Field(0.4, ge=0)
    floor_t: float = Field(2.0, gt=0)
    lid_t: float = Field(2.0, gt=0)
    standoff_h: float = Field(4.0, ge=0)
    headroom: float = Field(8.0, ge=0)
    lip_h: float = Field(3.0, ge=0)
    explode_gap: float = Field(12.0, ge=0)


class DatumCorePart(BasePart):
    """Enclosure whose bounds follow from the board it is sized around."""

    def get_bounds(self, params: Optional[Dict] = None) -> BoundingBox3D:
        """Outer envelope of whichever piece is rendered.

        The tray and the lid share a footprint, so only the height depends on
        the ``show`` parameter.
        """
        values = Params(**(params or {}))

        outer_x = values.board_x + 2 * values.board_clearance + 2 * values.walls
        outer_y = values.board_y + 2 * values.board_clearance + 2 * values.walls
        tray_h = values.floor_t + values.standoff_h + values.board_t + values.headroom
        lid_h = values.lid_t + values.lip_h

        if values.show == "tray":
            height = tray_h
        elif values.show == "lid":
            height = lid_h
        else:
            height = tray_h + values.explode_gap + lid_h

        return BoundingBox3D(
            min_point=Vector3D(x=-outer_x / 2, y=-outer_y / 2, z=0),
            max_point=Vector3D(x=outer_x / 2, y=outer_y / 2, z=height),
        )


def create(metadata_root: Path) -> DatumCorePart:
    scad = metadata_root / "parts" / "datum-core" / "datum-core.scad"
    return DatumCorePart(
        name="datum-core",
        source_file=scad,
        description="Enclosure for a 40 x 40 mm control-surface board: tray, lid, standoffs",
        params_model=Params,
        category="enclosure",
        tags=["datum", "enclosure", "case", "control-surface", "pcb"],
        readme_path=metadata_root / "parts" / "datum-core" / "README.md",
        preview_color=Color.from_hex("#3E7CB1"),
        # Three numbers this project's own sources state differently. None is a
        # typo to be quietly corrected: each has a document behind it, and the
        # dashboard exists so the choice is made by looking rather than arguing.
        contested={
            "walls": [
                ContestedValue(
                    value=3.0,
                    source=(
                        "governance/qm/adr/"
                        "DRAFT-enclosure-parts-live-in-apothecary.md, clause 3"
                    ),
                    note="House constant from parts/footpedal/button.scad, print-validated "
                    "on QM hardware. The record requires a part that differs to say why.",
                ),
                ContestedValue(
                    value=2.4,
                    source="parts/datum/datum.scad",
                    note="Cites the same record for this value, which the record does not "
                    "contain. Lighter, and unvalidated on hardware.",
                ),
            ],
            "tolerence": [
                ContestedValue(
                    value=0.4,
                    source=(
                        "governance/qm/adr/"
                        "DRAFT-enclosure-parts-live-in-apothecary.md, clause 3"
                    ),
                    note="House constant. Total fit clearance; the lid lip takes half per side.",
                ),
                ContestedValue(
                    value=0.2,
                    source="parts/datum/datum.scad",
                    note="Tighter fit. Same misattribution as walls.",
                ),
            ],
            "board_y": [
                ContestedValue(
                    value=40.0,
                    source="datum HANDOFF.md, WP-4",
                    note="Board outline is specified as at most 40 x 40 mm, so this is the "
                    "worst case an enclosure must accept.",
                ),
                ContestedValue(
                    value=30.0,
                    source="parts/datum/datum.scad",
                    note="A specific board rather than the bound. No schematic exists to "
                    "settle which is real.",
                ),
            ],
        },
    )


DEFAULT = create(ROOT)
