"""A theatre as a navigable site: its shell, a lighting rig, and scenery.

The site's pieces are its subsystems, as the garage's are:

- ``theatre``, the shell, is the building's walls (category ``wall``): drawn faded,
  a click passing through it to what hangs inside. It is the ``theatre`` part
  (parts/theatre/theatre.scad), stood at the site's origin: Part › Edit on it sizes
  the stage, walls, opening and pit with sliders.
- ``lighting`` holds the rig by its hanging positions -- ``foh``, ``1st_electric``
  and so on, each the fixtures whose label names it ("FOH 3" hangs on ``foh``) --
  so a step into it shows the positions and a step into one its fixtures.
- ``scenery`` holds the scenic elements the rig patches (a ``Scenic`` type).
The rig is a folder of a lighting console's two exports, ``patches.csv`` and
``fixture-parameters.csv`` (apothecary/lighting.py reads them): the folder
``APOTHECARY_THEATRE_RIG`` names, else the example rig in examples/theatre-rig/,
made up for this example. Any console's exports in those two files stand in for it.

Frame: millimetres, as every site is; the origin is the plaster line's centre on
the stage floor; +x is to the right as the house sees the stage, +y upstage, +z up.
The rig's own numbers are in metres, in the same frame.

The rig hangs where its exports place it; a shell resized by its sliders does not
move it, and the site's check names a fixture the shell at its defaults does not
hold (docs/lighting.md says what a rig that follows the shell would take).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from .hierarchy import Assembly, LayoutReport, LayoutViolation, Site, Structure, Substructure
from .lighting import LightingRig, Patch, load_rig, validate_rig
from .models.bounds import BoundingBox3D
from .models.vectors import Vector3D
from .primitives import Cube
from .projects.parts import theatre
from .projects.parts.skeleton import ROOT

SITE = "theatre"
RIG_ENV = "APOTHECARY_THEATRE_RIG"
EXAMPLE_RIG = ROOT / "examples" / "theatre-rig"
PATCHES_CSV = "patches.csv"
PARAMS_CSV = "fixture-parameters.csv"

MOVER_MM = 400
FIXTURE_MM = 300
SCENIC_MM = 1000

# Fixture types drawn larger: moving heads.
MOVERS = {"Mac_III_Performance_16B", "VL3500_Spot"}


def rig_dir() -> Path:
    """The rig's folder: ``APOTHECARY_THEATRE_RIG``, else the example."""
    named = os.environ.get(RIG_ENV, "").strip()
    return Path(named) if named else EXAMPLE_RIG


def rig_present() -> bool:
    return (rig_dir() / PATCHES_CSV).exists() and (rig_dir() / PARAMS_CSV).exists()


def load_theatre_rig() -> Optional[LightingRig]:
    if not rig_present():
        return None
    return load_rig(rig_dir() / PATCHES_CSV, rig_dir() / PARAMS_CSV)


def _name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")


def _shell() -> Assembly:
    return Structure(
        "theatre",
        position=Vector3D(),
        footprint=theatre.DEFAULT.get_bounds(),
        category="wall",
        part_ref="theatre",
    )


def _cube(name: str, mm: float) -> Assembly:
    half = mm / 2
    return Substructure(
        name,
        base=Cube(size=mm, center=True),
        footprint=BoundingBox3D(
            min_point=Vector3D(x=-half, y=-half, z=-half),
            max_point=Vector3D(x=half, y=half, z=half),
        ),
    )


def _fixture(p: Patch) -> Assembly:
    loc = p.location
    mm = MOVER_MM if p.fixture_type in MOVERS else FIXTURE_MM
    half = mm / 2
    return Substructure(
        f"ch{p.channel}_{_name(p.label or p.fixture_type)}",
        position=Vector3D(x=loc.x * 1000, y=loc.y * 1000, z=loc.z * 1000),
        footprint=BoundingBox3D(
            min_point=Vector3D(x=-half, y=-half, z=-half),
            max_point=Vector3D(x=half, y=half, z=half),
        ),
        children=[_cube("housing", mm)],
    )


def _scenic(p: Patch) -> Assembly:
    loc = p.location
    half = SCENIC_MM / 2
    return Substructure(
        f"ch{p.channel}_{_name(p.label or p.fixture_type)}",
        position=Vector3D(x=loc.x * 1000, y=loc.y * 1000, z=loc.z * 1000 + half),
        footprint=BoundingBox3D(
            min_point=Vector3D(x=-half, y=-half, z=-half),
            max_point=Vector3D(x=half, y=half, z=half),
        ),
        children=[_cube("element", SCENIC_MM)],
    )


def hanging_position(p: Patch) -> str:
    """The position a fixture hangs on: its label without its number ("FOH 3" hangs on
    ``foh``, "3rd Electric Cyc 2" on ``3rd_electric_cyc``), else its type's name."""
    words = re.sub(r"\s*\d+\s*$", "", p.label or "").strip() or p.fixture_type
    return _name(words).lower()


def _subsystem(name: str, category: str, children: List[Assembly]) -> Assembly:
    """A subsystem at the site's origin, in the site's frame, so what it holds stands
    where the rig's exports place it."""
    return Structure(name, position=Vector3D(), category=category, substructures=children)


def create_theatre_site() -> Assembly:
    """The shell; the rig's every located fixture on its hanging position, under
    ``lighting``; and its located scenic elements, under ``scenery``."""
    children: List[Assembly] = [_shell()]
    rig = load_theatre_rig()
    positions: Dict[str, List[Assembly]] = {}
    scenery: List[Assembly] = []
    for p in rig.patches if rig else []:
        if p.location is None:
            continue  # listed by the lighting route; there is no place for it in the room
        if p.fixture_type.startswith("Scenic"):
            scenery.append(_scenic(p))
        else:
            positions.setdefault(hanging_position(p), []).append(_fixture(p))
    if positions:
        hung = [Substructure(name, children=fixtures) for name, fixtures in positions.items()]
        children.append(_subsystem("lighting", "lighting", hung))
    if scenery:
        children.append(_subsystem("scenery", "scenic", scenery))
    return Site(SITE, structures=children)


def validate_theatre(site: Assembly) -> LayoutReport:
    """The rig's own checks -- DMX maps against their address spans, address clashes --
    and a located fixture the shell, at its defaults, does not hold."""
    rig = load_theatre_rig()
    if rig is None:
        return LayoutReport()
    violations = [
        LayoutViolation(kind=v.kind, message=v.message, structures=v.structures)
        for v in validate_rig(rig).violations
    ]
    shell = theatre.DEFAULT.get_bounds()
    for p in rig.patches:
        if p.location is None:
            continue
        at = (p.location.x * 1000, p.location.y * 1000, p.location.z * 1000)
        lo, hi = shell.min_point, shell.max_point
        if not (lo.x <= at[0] <= hi.x and lo.y <= at[1] <= hi.y and lo.z <= at[2] <= hi.z):
            where = f"ch{p.channel} {p.label or p.fixture_type}"
            violations.append(
                LayoutViolation(
                    kind="outside_the_theatre",
                    structures=[where],
                    message=f"{where} hangs outside the theatre's shell",
                )
            )
    return LayoutReport(violations=violations)
