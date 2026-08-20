"""datum-core as a navigable assembly, not one opaque solid.

``parts/datum-core/`` is the printable article: two SCAD pieces that render to
two STLs. That is the right shape for printing and the wrong shape for reading
-- a reviewer asking "how tall is the standoff" or "where does the connector
come through" gets one 500 KB mesh and no answer.

This is the same enclosure expressed as an ``Assembly`` tree, so every feature
is addressable, navigable and separately renderable at any depth. The numbers
are the SCAD file's defaults, and `tests/test_datum_core_site.py` holds them to
that: two descriptions of one object drift the moment nothing compares them.

The geometry here is built from primitives rather than importing the STL,
because an imported mesh has no interior structure to navigate. It is a
*model* of the printable part, and the envelope check in the tests is what
keeps the model honest about the thing it describes.
"""

from __future__ import annotations

from typing import List

from .booleans import Hull
from .hierarchy import Assembly, Feature, LayoutReport, Site, Structure, Substructure
from .models.bounds import BoundingBox3D
from .models.vectors import Vector3D
from .primitives import Cylinder
from .transforms import Rotate, Translate

# --- the SCAD file's defaults, in one place ---------------------------------

BOARD_X = 40.0
BOARD_Y = 40.0
BOARD_T = 1.6
BOARD_CLEARANCE = 0.4

WALL = 2.4
FLOOR_T = 2.0
LID_T = 2.0
CORNER_R = 3.0
STANDOFF_H = 4.0
HEADROOM = 8.0

MOUNT_INSET = 3.5
BOSS_D = 5.0
SCREW_D = 2.2

CONNECTOR_W = 9.4
CONNECTOR_H = 3.6
CONNECTOR_MARGIN = 0.6

INDICATOR_D = 4.0
INDICATOR_X = 0.0
INDICATOR_Y = 14.0

CONTACT_D = 12.0
CONTACT_PITCH_X = 18.0
CONTACT_PITCH_Y = 18.0

LIP_H = 3.0
LIP_CLEARANCE = 0.25

EXPLODE_GAP = 12.0

# The SCAD file renders at $fn=64. Matching it matters for more than looks:
# at OpenSCAD's default facet count a hulled corner falls short of its own
# radius, and the model then reports an envelope 0.3 mm under the part's.
CURVE_FACETS = 64

# --- derived, exactly as the SCAD derives them ------------------------------

CAVITY_X = BOARD_X + 2 * BOARD_CLEARANCE
CAVITY_Y = BOARD_Y + 2 * BOARD_CLEARANCE
OUTER_X = CAVITY_X + 2 * WALL
OUTER_Y = CAVITY_Y + 2 * WALL

BOARD_Z = FLOOR_T + STANDOFF_H
TRAY_H = BOARD_Z + BOARD_T + HEADROOM
CONNECTOR_Z = BOARD_Z + BOARD_T + CONNECTOR_H / 2
LID_H = LID_T + LIP_H

_CORNERS = ((-1, -1), (-1, 1), (1, -1), (1, 1))
_CORNER_NAMES = {
    (-1, -1): "front-left",
    (-1, 1): "back-left",
    (1, -1): "front-right",
    (1, 1): "back-right",
}


def rounded_prism(x: float, y: float, height: float, radius: float) -> Hull:
    """A rounded rectangular prism, as the hull of its four corner cylinders.

    The same construction the SCAD file uses, so the corner radius the parts
    are fitted around is the radius this model reports.
    """
    radius = max(radius, 0.1)
    return Hull(
        children=[
            Translate(
                v=Vector3D(x=sx * (x / 2 - radius), y=sy * (y / 2 - radius), z=0),
                children=[Cylinder(h=height, r=radius, center=False, fn=CURVE_FACETS)],
            )
            for sx, sy in _CORNERS
        ]
    )


def _box(x: float, y: float, z_min: float, z_max: float) -> BoundingBox3D:
    return BoundingBox3D(
        min_point=Vector3D(x=-x / 2, y=-y / 2, z=z_min),
        max_point=Vector3D(x=x / 2, y=y / 2, z=z_max),
    )


# --- the tray ---------------------------------------------------------------


def _cavity() -> Assembly:
    """The volume the board sits in. Subtracted from the shell."""
    return Assembly(
        name="cavity",
        role="feature",
        base=Translate(
            v=Vector3D(x=0, y=0, z=FLOOR_T),
            children=[rounded_prism(CAVITY_X, CAVITY_Y, TRAY_H, CORNER_R - WALL)],
        ),
        footprint=_box(CAVITY_X, CAVITY_Y, FLOOR_T, TRAY_H),
        comment="Board clearance volume",
    )


def _connector_opening() -> Assembly:
    """The slot the edge connector comes through, in the +Y wall."""
    half = CONNECTOR_W / 2 - CONNECTOR_H / 2
    radius = (CONNECTOR_H + 2 * CONNECTOR_MARGIN) / 2
    # The slot lies along +Y, through the wall. A cylinder is Z-aligned, so
    # each end is rotated -90 about X to point along +Y before hulling -- the
    # same construction as the SCAD file's connector_cut().
    slot = Hull(
        children=[
            Translate(
                v=Vector3D(x=sx * half, y=0, z=0),
                children=[
                    Rotate(
                        a=Vector3D(x=-90, y=0, z=0),
                        children=[Cylinder(h=WALL + 1.5, r=radius, center=False, fn=CURVE_FACETS)],
                    )
                ],
            )
            for sx in (-1, 1)
        ]
    )
    return Assembly(
        name="connector-opening",
        role="feature",
        base=Translate(
            v=Vector3D(x=0, y=CAVITY_Y / 2 - 0.5, z=CONNECTOR_Z),
            children=[slot],
        ),
        footprint=_box(CONNECTOR_W, WALL + 1.5, CONNECTOR_Z - radius, CONNECTOR_Z + radius),
        comment="Edge connector clearance, sized with margin on every side",
    )


def _standoffs() -> List[Assembly]:
    """Four bosses the board screws down onto, each with its own pilot hole."""
    standoffs = []
    for sx, sy in _CORNERS:
        position = Vector3D(
            x=sx * (BOARD_X / 2 - MOUNT_INSET),
            y=sy * (BOARD_Y / 2 - MOUNT_INSET),
            z=FLOOR_T,
        )
        boss = Feature.boss(
            f"boss-{_CORNER_NAMES[(sx, sy)]}",
            position=Vector3D(x=0, y=0, z=0),
            diameter=BOSS_D,
            height=STANDOFF_H,
        )
        boss.position = position
        boss.footprint = BoundingBox3D(
            min_point=Vector3D(x=-BOSS_D / 2, y=-BOSS_D / 2, z=0),
            max_point=Vector3D(x=BOSS_D / 2, y=BOSS_D / 2, z=STANDOFF_H),
        )
        # The pilot hole is a subtraction on the boss, so it is navigable in
        # its own right rather than being folded into anonymous geometry.
        boss.subtractions = [
            Assembly(
                name="pilot-hole",
                role="feature",
                base=Translate(
                    v=Vector3D(x=0, y=0, z=-0.1),
                    children=[
                        Cylinder(
                            h=STANDOFF_H + 0.2, r=SCREW_D / 2, center=False, fn=CURVE_FACETS
                        )
                    ],
                ),
                comment=f"Pilot hole, {SCREW_D} mm",
            )
        ]
        standoffs.append(boss)
    return standoffs


def _tray() -> Assembly:
    shell = Substructure(
        "shell",
        base=rounded_prism(OUTER_X, OUTER_Y, TRAY_H, CORNER_R),
        subtractions=[_cavity(), _connector_opening()],
        footprint=_box(OUTER_X, OUTER_Y, 0, TRAY_H),
    )
    mounting = Substructure(
        "mounting",
        additions=_standoffs(),
        footprint=_box(BOARD_X, BOARD_Y, FLOOR_T, FLOOR_T + STANDOFF_H),
    )
    return Structure(
        "tray",
        category="enclosure",
        material="PETG",
        footprint=_box(OUTER_X, OUTER_Y, 0, TRAY_H),
        substructures=[shell, mounting],
    )


# --- the lid ----------------------------------------------------------------


def _contact_openings() -> List[Assembly]:
    """Four openings, one per contact, on the documented 2 x 2 grid."""
    openings = []
    for sx, sy in _CORNERS:
        openings.append(
            Assembly(
                name=f"contact-{_CORNER_NAMES[(sx, sy)]}",
                role="feature",
                base=Translate(
                    v=Vector3D(x=sx * CONTACT_PITCH_X / 2, y=sy * CONTACT_PITCH_Y / 2, z=-0.1),
                    children=[
                        Cylinder(
                            h=LID_H + 0.2, r=CONTACT_D / 2, center=False, fn=CURVE_FACETS
                        )
                    ],
                ),
                footprint=BoundingBox3D(
                    min_point=Vector3D(
                        x=sx * CONTACT_PITCH_X / 2 - CONTACT_D / 2,
                        y=sy * CONTACT_PITCH_Y / 2 - CONTACT_D / 2,
                        z=0,
                    ),
                    max_point=Vector3D(
                        x=sx * CONTACT_PITCH_X / 2 + CONTACT_D / 2,
                        y=sy * CONTACT_PITCH_Y / 2 + CONTACT_D / 2,
                        z=LID_T,
                    ),
                ),
                comment="Contact opening",
            )
        )
    return openings


def _indicator_pipe() -> Assembly:
    return Assembly(
        name="indicator-light-pipe",
        role="feature",
        base=Translate(
            v=Vector3D(x=INDICATOR_X, y=INDICATOR_Y, z=-0.1),
            children=[Cylinder(h=LID_H + 0.2, r=INDICATOR_D / 2, center=False, fn=CURVE_FACETS)],
        ),
        footprint=BoundingBox3D(
            min_point=Vector3D(
                x=INDICATOR_X - INDICATOR_D / 2, y=INDICATOR_Y - INDICATOR_D / 2, z=0
            ),
            max_point=Vector3D(
                x=INDICATOR_X + INDICATOR_D / 2, y=INDICATOR_Y + INDICATOR_D / 2, z=LID_T
            ),
        ),
        comment="Light pipe for the indicator",
    )


def _lid() -> Assembly:
    plate = Substructure(
        "plate",
        base=rounded_prism(OUTER_X, OUTER_Y, LID_T, CORNER_R),
        subtractions=[*_contact_openings(), _indicator_pipe()],
        footprint=_box(OUTER_X, OUTER_Y, 0, LID_T),
    )
    lip = Substructure(
        "lip",
        position=Vector3D(x=0, y=0, z=LID_T),
        base=rounded_prism(
            CAVITY_X - 2 * LIP_CLEARANCE,
            CAVITY_Y - 2 * LIP_CLEARANCE,
            LIP_H,
            CORNER_R - WALL,
        ),
        footprint=_box(CAVITY_X - 2 * LIP_CLEARANCE, CAVITY_Y - 2 * LIP_CLEARANCE, 0, LIP_H),
    )
    return Structure(
        "lid",
        # Sitting above the tray with the documented gap, so the assembly reads
        # as an exploded view rather than two pieces occupying one volume.
        position=Vector3D(x=0, y=0, z=TRAY_H + EXPLODE_GAP),
        category="enclosure",
        material="PETG",
        footprint=_box(OUTER_X, OUTER_Y, 0, LID_H),
        substructures=[plate, lip],
    )


# --- the site ---------------------------------------------------------------


def create_datum_core_site() -> Assembly:
    """datum-core, decomposed far enough to answer questions about it."""
    return Site("datum-core", structures=[_tray(), _lid()])


def validate_datum_core(site: Assembly) -> LayoutReport:
    """The tray and the lid must not occupy the same space.

    A real constraint, unlike the parts catalog's: these two are one object in
    an exploded view, and a gap that goes negative means the model is claiming
    the lid passes through the tray.
    """
    report = LayoutReport()
    tray = next((s for s in site.children if s.name == "tray"), None)
    lid = next((s for s in site.children if s.name == "lid"), None)
    if tray is None or lid is None:
        return report

    tray_top = tray.position.z + TRAY_H
    lid_bottom = lid.position.z
    if lid_bottom < tray_top:
        from .hierarchy import LayoutViolation

        report.violations.append(
            LayoutViolation(
                kind="overlap",
                message=(
                    f"lid sits {tray_top - lid_bottom:.1f} mm inside the tray: "
                    f"lid bottom {lid_bottom:.1f} mm, tray top {tray_top:.1f} mm"
                ),
                structures=["tray", "lid"],
            )
        )
    return report


__all__ = [
    "create_datum_core_site",
    "validate_datum_core",
    "rounded_prism",
    "TRAY_H",
    "LID_H",
    "OUTER_X",
    "OUTER_Y",
]
