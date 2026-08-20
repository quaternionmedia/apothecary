"""A datum iteration, placed in a scene, with its integration stubs named.

This is the scaffold the datum project needs from apothecary: generate an
enclosure for a given board, put it somewhere, and be explicit about every
place a real artifact will later replace a guess.

What is real here: the enclosure geometry, the board envelope's effect on it,
and the printer settings.

What is stubbed, and says so: the board outline (hand-entered, not read from
KiCad), the module and connector envelopes, and the mounting surface. Each is
a :class:`~apothecary.models.blackbox.BlackBox` from a provider, so replacing
one is a provider change rather than an edit here.

:meth:`Assembly.report` lists what is still guessed, so a review can start from
what nobody has measured rather than from what looks finished.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

from apothecary.core import OpenSCADObject
from apothecary.models import BoundingBox3D, Vector3D
from apothecary.models.blackbox import BlackBox, BlackBoxProvider, Keepout, StubProvider
from apothecary.primitives import Cube
from apothecary.projects.parts.datum import DatumParams, params_for
from apothecary.scene import Scene
from apothecary.shims.kicad import KiCadProvider
from apothecary.transforms import Translate


class Placement(BaseModel):
    """Where an artifact sits in the scene, and what it is."""

    name: str
    position: Vector3D = Field(default_factory=Vector3D)
    stub: bool = True
    note: Optional[str] = None


class Assembly(BaseModel):
    """A datum iteration and everything placed around it."""

    board_name: str
    params: DatumParams
    placements: List[Placement] = Field(default_factory=list)

    def report(self) -> str:
        """What is guessed, in the order a reviewer should ask about it."""
        stubs = [p for p in self.placements if p.stub]
        lines = [
            f"datum iteration for board {self.board_name!r}",
            f"  enclosure  {self.params.outer_w:.1f} x {self.params.outer_d:.1f} "
            f"x {self.params.outer_h:.1f} mm",
            f"  fits board {self.params.board_w:.1f} x {self.params.board_d:.1f} mm, "
            f"{len(self.placements)} placed artifact(s)",
        ]
        if stubs:
            lines.append(f"  {len(stubs)} still stubbed — nothing has measured these:")
            lines += [f"    - {p.name}: {p.note or 'no note'}" for p in stubs]
        else:
            lines.append("  no stubs remain")
        return "\n".join(lines)


def mounting_surface_stub(width: float = 120.0, depth: float = 120.0) -> BlackBox:
    """Whatever the enclosure ends up attached to.

    A wall plate, a desk, a panel. Modelled because an enclosure that fits its
    board and not its mounting is only half designed, and stubbed because which
    surface it is has not been decided.
    """
    return BlackBox(
        name="mounting-surface",
        envelope=BoundingBox3D(
            min_point=Vector3D(x=0, y=0, z=-3),
            max_point=Vector3D(x=width, y=depth, z=0),
        ),
        keepouts=[
            Keepout(
                name="fastener-access",
                box=BoundingBox3D(
                    min_point=Vector3D(x=0, y=0, z=-3),
                    max_point=Vector3D(x=width, y=depth, z=0),
                ),
                reason="A driver has to reach the fasteners. Which fasteners, and from "
                "which side, is undecided.",
            )
        ],
        source="stub",
        notes="Placeholder surface. Signal-only: if this becomes a wall box, the listed "
        "box is the barrier and this part is cosmetic.",
    )


def build(
    provider: Optional[BlackBoxProvider] = None,
    board_name: str = "t1-core",
    at: Optional[Vector3D] = None,
    surfaces: Optional[BlackBoxProvider] = None,
) -> tuple[Scene, Assembly]:
    """Generate a datum iteration and place it in a scene.

    `provider` defaults to the KiCad shim, which today serves hand-entered
    envelopes. Pass any other provider satisfying the protocol — including a
    real KiCad reader, when one exists — and nothing below changes.

    `surfaces` is the same seam for whatever the enclosure mounts to, so a
    caller can supply a real wall plate without editing this function.
    """
    provider = provider or KiCadProvider()
    origin = at or Vector3D()

    board = provider.get(board_name)
    params = params_for(board)

    surfaces = surfaces or StubProvider().register(mounting_surface_stub())
    surface = surfaces.get("mounting-surface")

    def at(position: Vector3D, size: Vector3D, comment: str) -> OpenSCADObject:
        """Place a block.

        Cube carries no position of its own, so a bare Cube renders at the
        origin however carefully you fill in coordinates. An earlier version of
        this function did exactly that: every object in the scene sat on top of
        every other one, and the Python model looked correct throughout.
        """
        return Translate(v=position, comment=comment, children=[Cube(size=size, center=False)])

    surface_pos = Vector3D(x=origin.x - 40, y=origin.y - 40, z=origin.z - 3)
    objects: List[OpenSCADObject] = [
        # The enclosure's envelope. The printable geometry is parts/datum/datum.scad;
        # this is the block a scene needs for placement and collision.
        at(
            origin,
            Vector3D(x=params.outer_w, y=params.outer_d, z=params.outer_h),
            "datum enclosure envelope",
        ),
        # The board, seated on its standoffs inside the enclosure.
        at(
            Vector3D(
                x=origin.x + params.wall + params.tol,
                y=origin.y + params.wall + params.tol,
                z=origin.z + params.wall + params.standoff,
            ),
            Vector3D(x=params.board_w, y=params.board_d, z=params.board_h),
            f"board: {board.name} ({board.source})",
        ),
        # What it mounts to.
        at(
            surface_pos,
            Vector3D(
                x=surface.envelope.width,
                y=surface.envelope.height,
                z=surface.envelope.depth,
            ),
            f"mounting surface ({surface.source})",
        ),
    ]

    scene = Scene(name=f"datum-{board_name}", objects=objects)
    assembly = Assembly(
        board_name=board_name,
        params=params,
        placements=[
            Placement(
                name="datum-enclosure",
                position=origin,
                stub=False,
                note="generated from parts/datum/datum.scad",
            ),
            Placement(
                name=f"board:{board.name}",
                position=origin,
                stub=board.is_stub,
                note=board.notes or f"envelope source: {board.source}",
            ),
            Placement(
                name="mounting-surface",
                position=surface_pos,
                stub=surface.is_stub,
                note=surface.notes,
            ),
        ],
    )
    return scene, assembly


def write(out_dir: Path, board_name: str = "t1-core") -> Path:
    """Render an iteration to a .scad file and return its path."""
    scene, _ = build(board_name=board_name)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{scene.name}.scad"
    target.write_text(scene.render(), encoding="utf-8")
    return target
