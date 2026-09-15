"""KiCad shim: board outlines and mounting holes, when a board exists.

This is a stub, and it is honest about which kind. It does not read
`.kicad_pcb` files yet. What it does is fix the *seam* — a
:class:`~apothecary.models.blackbox.BlackBoxProvider` — so that geometry code
written today against a hand-entered envelope keeps working unchanged when a
real reader lands behind it.

Why a stub is the right amount of work now: a board outline is four numbers and
a handful of hole positions. Parsing s-expressions to obtain four numbers, for
a board that is not laid out yet, buys nothing and commits this library to a
file format. The numbers below come from the reference board's records and are
marked `source="stub"`, so a scene can report how much of itself is guessed.

To replace this, implement `get()` against a real file and return
`source="kicad"`. Nothing else changes.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from apothecary.models import BoundingBox3D, Vector3D
from apothecary.models.blackbox import BlackBox, Keepout, MountPoint, StubProvider

# T1-Core: the datum project's reference board.
#
# 5 V USB-C bus power, full 16-pin receptacle, Wi-Fi module. Dimensions are a
# stub standing in for a layout that does not exist yet; the CONSTRAINTS are
# from that project's records and are what the geometry must respect:
#   - a USB-C receptacle on one edge, needing mating clearance
#   - a Wi-Fi module needing antenna keepout, so no ground plane and no metal
#   - signal-only: no mains, no line voltage anywhere near this part
_T1_CORE_W = 40.0
_T1_CORE_D = 30.0
_T1_CORE_H = 1.6  # standard board stack
_MOUNT_INSET = 3.5


def t1_core_stub() -> BlackBox:
    """The reference board as a hand-entered envelope."""
    return BlackBox(
        name="t1-core",
        envelope=BoundingBox3D(
            min_point=Vector3D(x=0, y=0, z=0),
            max_point=Vector3D(x=_T1_CORE_W, y=_T1_CORE_D, z=_T1_CORE_H),
        ),
        mounts=[
            MountPoint(name=f"m{i + 1}", position=Vector3D(x=x, y=y, z=0), hole_diameter=2.2)
            for i, (x, y) in enumerate(
                [
                    (_MOUNT_INSET, _MOUNT_INSET),
                    (_T1_CORE_W - _MOUNT_INSET, _MOUNT_INSET),
                    (_MOUNT_INSET, _T1_CORE_D - _MOUNT_INSET),
                    (_T1_CORE_W - _MOUNT_INSET, _T1_CORE_D - _MOUNT_INSET),
                ]
            )
        ],
        keepouts=[
            Keepout(
                name="usb-c-mating",
                box=BoundingBox3D(
                    min_point=Vector3D(x=_T1_CORE_W / 2 - 5, y=-9, z=0),
                    max_point=Vector3D(x=_T1_CORE_W / 2 + 5, y=0, z=4),
                ),
                reason="USB-C plug and strain relief need to arrive from outside the "
                "enclosure; the wall gets an opening here.",
            ),
            Keepout(
                name="antenna",
                box=BoundingBox3D(
                    min_point=Vector3D(x=0, y=_T1_CORE_D - 8, z=0),
                    max_point=Vector3D(x=_T1_CORE_W, y=_T1_CORE_D, z=8),
                ),
                reason="Wi-Fi module antenna. Keep printed material thin and metal "
                "absent; a boss here detunes it.",
            ),
        ],
        source="stub",
        notes="Envelope is provisional. Constraints (USB-C edge access, antenna "
        "keepout, signal-only) come from the datum project's records and hold "
        "regardless of final board size.",
    )


class KiCadProvider(StubProvider):
    """Provider that will read KiCad, and today does not.

    Subclasses :class:`StubProvider` so it is usable now: it serves the same
    hand-entered envelopes, and `get()` still reports `source="stub"` rather
    than implying a file was read. When `board_file` is given and parsing
    exists, `get()` returns `source="kicad"` and callers see the difference in
    the value rather than in their code.
    """

    def __init__(self, board_file: Optional[Path] = None) -> None:
        super().__init__({b.name: b for b in _default_boxes()})
        self.board_file = board_file

    def can_read_board(self) -> bool:
        """Whether a real outline is available. False until a reader exists."""
        return False

    def unresolved(self) -> List[str]:
        """Names still served from a stub — what a scene should report as guessed."""
        return [n for n in self.names() if self.get(n).is_stub]


def _default_boxes() -> List[BlackBox]:
    return [t1_core_stub()]
