"""
datum_core - enclosure for a 40 x 40 mm control-surface board.

Four contact openings, one indicator light pipe, an edge connector cutout and
four board standoffs, in a printable tray and a printable lid.

The board dimensions are assumptions carried as parameters, not measurements:
no schematic exists yet. Tune them here and in the SCAD defaults together.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from pydantic import BaseModel, Field

from apothecary.models import BoundingBox3D, Color, PrintSettings, Vector3D
from apothecary.models.blackbox import BlackBox

from .base import BasePart, ContestedValue
from .skeleton import ROOT


class Params(BaseModel):
    """Parameters mirroring the SCAD defaults.

    Attributes:
        board_x: Board width in mm
        board_y: Board depth in mm
        board_t: Board thickness in mm
        board_clearance: Gap between the board edge and the cavity wall
        walls: Side wall thickness (house constant)
        tolerence: Total fit clearance (house constant)
        floor_t: Tray floor thickness
        standoff_h: Floor to board underside
        headroom: Board top to lid underside
        corner_r: Shell corner radius
        mount_inset: Mounting hole centres, inset from the board edge
        boss_d: Standoff boss diameter
        screw_d: Pilot hole for the board screw
        connector_w: Edge connector opening width
        connector_h: Edge connector opening height
        connector_margin: Clearance added to the connector opening per side
        antenna_band: Height of the thinned strip at the antenna wall
        antenna_wall: Thickness left at the antenna wall
    """

    # Manufacturing facts, house defaults. A consumer overrides these for its
    # own printer; it does not own them.
    walls: float = Field(3.0, gt=0)
    tolerence: float = Field(0.4, ge=0)
    board_x: float = Field(40.0, gt=0)
    board_y: float = Field(40.0, gt=0)
    board_t: float = Field(1.6, gt=0)
    board_clearance: float = Field(0.4, ge=0)
    floor_t: float = Field(2.0, gt=0)
    standoff_h: float = Field(4.0, ge=0)
    headroom: float = Field(8.0, ge=0)
    # Every remaining top-level number in the SCAD file. A dimension with no
    # control is a dimension nobody tunes; test_parameter_coverage holds this
    # model to the file so the two cannot part company.
    corner_r: float = Field(3.0, gt=0)
    mount_inset: float = Field(3.5, gt=0)
    boss_d: float = Field(5.0, gt=0)
    screw_d: float = Field(2.2, gt=0)
    connector_w: float = Field(9.4, gt=0)
    connector_h: float = Field(3.6, gt=0)
    connector_margin: float = Field(0.6, ge=0)
    antenna_band: float = Field(8.0, ge=0)
    antenna_wall: float = Field(0.8, gt=0)

    # The envelope, defined once. `get_bounds` and any consumer that needs to
    # place this tray in a scene read these rather than each restating the
    # arithmetic and drifting apart.
    @property
    def outer_x(self) -> float:
        return self.board_x + 2 * self.board_clearance + 2 * self.walls

    @property
    def outer_y(self) -> float:
        return self.board_y + 2 * self.board_clearance + 2 * self.walls

    @property
    def outer_z(self) -> float:
        return self.floor_t + self.standoff_h + self.board_t + self.headroom

    def to_scad_overrides(self) -> Dict[str, float]:
        """The ``-D name=value`` set for rendering this iteration."""
        return {k: float(v) for k, v in self.model_dump().items()}


def params_for(board: BlackBox, **overrides: float) -> Params:
    """Derive tray parameters from a black box.

    The entire adapter between "something described the board" and "the tray
    fits it". A provider swap -- a hand-entered stub today, a KiCad outline
    later -- is invisible past this line.

    This seam arrived with ``parts/datum``, the single-piece tray this part
    supersedes. The geometry was replaced by a core and a separate cap; the
    seam was the part worth keeping, so it moved here rather than retiring
    with it.
    """
    env = board.envelope
    inset = (
        min(
            min(m.position.x, env.width - m.position.x, m.position.y, env.height - m.position.y)
            for m in board.mounts
        )
        if board.mounts
        else Params.model_fields["mount_inset"].default
    )
    hole = (
        board.mounts[0].hole_diameter
        if board.mounts
        else Params.model_fields["screw_d"].default
    )

    values: Dict[str, float] = {
        "board_x": env.width,
        "board_y": env.height,  # this library's height is the Y extent
        "board_t": env.depth,  # and depth is Z
        "mount_inset": inset,
        "screw_d": hole,
    }

    # The board's own keepouts choose the openings. `parts/datum` called these
    # usb_w/usb_h; the core names them for what they are, an edge connector.
    for keepout in board.keepouts:
        if keepout.name == "usb-c-mating":
            values["connector_w"] = keepout.box.width
            values["connector_h"] = keepout.box.depth
        elif keepout.name == "antenna":
            values["antenna_band"] = keepout.box.depth

    values.update(overrides)
    return Params(**values)


class DatumCorePart(BasePart):
    """Enclosure whose bounds follow from the board it is sized around."""

    def get_bounds(self, params: Optional[Dict] = None) -> BoundingBox3D:
        """Outer envelope of the tray.

        One object, one envelope. It used to branch on a ``show`` parameter
        that selected between the tray and the cover, which is two parts
        wearing one name -- the cover is ``datum_cap``.
        """
        values = Params(**(params or {}))

        return BoundingBox3D(
            min_point=Vector3D(x=-values.outer_x / 2, y=-values.outer_y / 2, z=0),
            max_point=Vector3D(x=values.outer_x / 2, y=values.outer_y / 2, z=values.outer_z),
        )


def create(metadata_root: Path) -> DatumCorePart:
    scad = metadata_root / "parts" / "datum_core" / "datum_core.scad"
    return DatumCorePart(
        name="datum_core",
        source_file=scad,
        description=(
            "Enclosure tray for a 40 x 40 mm control-surface board: standoffs, "
            "connector cutout, antenna relief"
        ),
        params_model=Params,
        category="enclosure",
        tags=["datum", "enclosure", "case", "control-surface", "pcb"],
        readme_path=metadata_root / "parts" / "datum_core" / "README.md",
        # The house constants, so a slicer profile is not guesswork and the
        # part's own `walls`/`tolerence` are not a second opinion about them.
        print_settings=PrintSettings(
            nozzle_diameter=0.4, layer_height=0.2, wall_thickness=3.0, tolerance=0.4
        ),
        preview_color=Color.from_hex("#3E7CB1"),
        # Three numbers this project's own sources state differently. None is a
        # typo to be quietly corrected: each has a document behind it, and the
        # dashboard exists so the choice is made by looking rather than arguing.
        # `walls` and `tolerence` were contested only by parts/datum, the
        # single-piece tray this part supersedes. It carried 2.4 and 0.2 while
        # citing the enclosure record for values that record does not contain.
        # Retiring it settled both: the house constants stand unopposed, and a
        # part that wants to differ must now say why, as clause 3 requires.
        #
        # board_y is not settled and must not look settled. Two live sources
        # still disagree about how big the board is, and neither is the retired
        # part -- so the dissent is cited where it actually lives now.
        contested={
            "board_y": [
                ContestedValue(
                    value=40.0,
                    source="datum HANDOFF.md, WP-4",
                    note="Board outline is specified as at most 40 x 40 mm, so this is the "
                    "worst case an enclosure must accept.",
                ),
                ContestedValue(
                    value=30.0,
                    source="apothecary/shims/kicad.py, t1_core_stub",
                    note="The hand-entered envelope the black-box seam serves today: a "
                    "specific board rather than the bound. No schematic exists to "
                    "settle which is real.",
                ),
            ],
        },
    )


DEFAULT = create(ROOT)
