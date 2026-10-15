"""El Camino HS Performing Arts Center as a navigable site: shell, lighting rig, scenery.

The venue's files are read where they are: ``APOTHECARY_ECHS_PAC_DIR``, else
``<repo>/ECHS-PAC``. Nothing from them is copied into the repository. When they
are not on this machine the site is not registered and the lighting routes
answer 404, so a clean clone and CI are unaffected.

Units: the site is in millimetres, as every site is; the rig's data and the
lighting panel are in metres.

The shell is traced by eye from AV1.0 (orchestra pit level, 72 dpi, so 1 px =
1 pt). It is a few boxes, not the outline: ``shortcut: boxes for the envelope
and pit, the house and tower not traced, upgrade by tracing AV1.1 and adding a
polygon primitive``.

Coordinates: +x runs down the sheet, +y upstage (left on the sheet), z up from
the stage floor. The plaster line is the origin. Sheet scale is 0.039 m per pt,
from the drawing's own scale note; not pinned to a known dimension yet.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Optional

from .hierarchy import Assembly, LayoutReport, LayoutViolation, Site, Structure, Substructure
from .lighting import LightingRig, Patch, load_rig, validate_rig
from .models.bounds import BoundingBox3D
from .models.vectors import Vector3D
from .primitives import Cube

VENUE_DIR_ENV = "APOTHECARY_ECHS_PAC_DIR"
PATCHES_CSV = "ECHS-PAC-patches.csv"
PARAMS_CSV = "ECHS-PAC-fixture-parameters.csv"

# AV1.0, traced at 72 dpi. The plaster line centre at stage floor level is the origin.
M_PER_PT = 0.039
PLASTER_LINE_PT = (890, 597)
SHELL_H_MM = 9000  # no section on the sheets; the highest fixture is at 8.5 m
MOVER_MM = 400
FIXTURE_MM = 300
SCENIC_MM = 1000

# (name, sheet box (x0, y0, x1, y1) in pt, z0 mm, z1 mm)
SHELL = [
    ("upstage_wall", (165, 192, 265, 925), 0, SHELL_H_MM),
    ("north_wall", (265, 265, 1170, 300), 0, SHELL_H_MM),
    ("south_wall", (265, 890, 1170, 925), 0, SHELL_H_MM),
    ("proscenium", (886, 405, 894, 790), 0, SHELL_H_MM),
    ("stage_floor", (265, 300, 890, 890), -200, 0),
    ("orchestra_pit", (560, 330, 920, 862), -1400, -200),
]

MOVERS = {"Mac_III_Performance_16B", "VL3500_Spot"}


def venue_dir() -> Path:
    env = os.environ.get(VENUE_DIR_ENV)
    return Path(env) if env else Path(__file__).resolve().parent.parent / "ECHS-PAC"


def venue_present() -> bool:
    return (venue_dir() / PATCHES_CSV).exists() and (venue_dir() / PARAMS_CSV).exists()


def load_echs_rig() -> Optional[LightingRig]:
    if not venue_present():
        return None
    return load_rig(venue_dir() / PATCHES_CSV, venue_dir() / PARAMS_CSV)


def _sheet_to_site_mm(px: float, py: float) -> tuple[float, float]:
    """A point on AV1.0 to (x, y) in mm, with +y upstage."""
    ox, oy = PLASTER_LINE_PT
    return (py - oy) * M_PER_PT * 1000, (ox - px) * M_PER_PT * 1000


def _name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")


def _shell_piece(name: str, box: tuple, z0: float, z1: float) -> Assembly:
    px0, py0, px1, py1 = box
    x0, y0 = _sheet_to_site_mm(px1, py1)  # the sheet's y is site x, its x is site -y
    x1, y1 = _sheet_to_site_mm(px0, py0)
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    size = Vector3D(x=x1 - x0, y=y1 - y0, z=z1 - z0)
    return Structure(
        name,
        position=Vector3D(x=x0, y=y0, z=z0),
        footprint=BoundingBox3D(min_point=Vector3D(), max_point=size),
        category="architecture",
        substructures=[Substructure(name, base=Cube(size=size))],
    )


def _fixture(p: Patch) -> Assembly:
    loc = p.location
    mm = MOVER_MM if p.fixture_type in MOVERS else FIXTURE_MM
    half = mm / 2
    return Structure(
        f"ch{p.channel}_{_name(p.label or p.fixture_type)}",
        position=Vector3D(x=loc.x * 1000, y=loc.y * 1000, z=loc.z * 1000),
        footprint=BoundingBox3D(
            min_point=Vector3D(x=-half, y=-half, z=-half),
            max_point=Vector3D(x=half, y=half, z=half),
        ),
        category="lighting",
        substructures=[Substructure("housing", base=Cube(size=mm, center=True))],
    )


def _scenic(p: Patch) -> Assembly:
    loc = p.location
    half = SCENIC_MM / 2
    return Structure(
        f"ch{p.channel}_{_name(p.label or p.fixture_type)}",
        position=Vector3D(x=loc.x * 1000, y=loc.y * 1000, z=loc.z * 1000 + half),
        footprint=BoundingBox3D(
            min_point=Vector3D(x=-half, y=-half, z=-half),
            max_point=Vector3D(x=half, y=half, z=half),
        ),
        category="scenic",
        substructures=[Substructure("element", base=Cube(size=SCENIC_MM, center=True))],
    )


def create_echs_pac_site() -> Assembly:
    """The shell, every located fixture, and every located scenic element."""
    rig = load_echs_rig()
    if rig is None:
        raise FileNotFoundError(f"ECHS-PAC export not found in {venue_dir()}")
    children: List[Assembly] = [_shell_piece(*piece) for piece in SHELL]
    for p in rig.patches:
        if p.location is None:
            continue  # listed by the lighting route; there is no place for it in the room
        if p.fixture_type.startswith("Scenic"):
            children.append(_scenic(p))
        else:
            children.append(_fixture(p))
    return Site("echs_pac", structures=children)


def validate_echs_pac(site: Assembly) -> LayoutReport:
    """The rig's own checks: DMX maps against their address spans, and address clashes."""
    rig = load_echs_rig()
    if rig is None:
        return LayoutReport()
    return LayoutReport(
        violations=[
            LayoutViolation(kind=v.kind, message=v.message, structures=v.structures)
            for v in validate_rig(rig).violations
        ]
    )
