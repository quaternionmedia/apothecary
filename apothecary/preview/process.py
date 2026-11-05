"""What a move means, for each way of making a part: the core's two instantiations.

The interpreter (``moves.py``) and the preview it builds (``core.py``) are the same for
every machine. A ``Process`` is all that differs: what each move is, how moves group
into what a person scrubs through, what a pause's words mean and how fast a rapid goes.
A new way of making something is one more ``Process`` here and nothing else.

Additive, on a printer: a move that pushes filament lays material, any other travels,
and moves group into layers. Subtractive, on a router: a G0 is a rapid, a feed straight
down a plunge and any other feed a cut, and moves group into the passes the toolpath
names (``apothecary.cam``) or, in a CAM post's file, the depths it goes to.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Protocol, Tuple

from .moves import Move

# A comment that names the operation the lines after it belong to, as apothecary.cam
# writes one: `(op 2/4 pass 1/6: hole 3 mm at 110,36.667 plunged to z -2)`.
OPERATION_COMMENT = re.compile(r"^op \d+/\d+\b")
_TO_Z = re.compile(r"\bto z (-?\d+(?:\.\d+)?)")
# A slicer's mark of a new layer: OrcaSlicer and PrusaSlicer's, and Cura's.
LAYER_COMMENT = re.compile(r"^(LAYER_CHANGE|LAYER:\s*-?\d+)$", re.IGNORECASE)
_EPSILON = 1e-6

Group = Tuple[str, Optional[float]]  # a new group's label, and its height if it has one


class GroupRule(Protocol):
    """When a new group of moves begins: told each comment, then asked at each move."""

    def comment(self, text: str) -> None: ...

    def move(self, move: Move, kind: str) -> Optional[Group]: ...


@dataclass(frozen=True)
class Process:
    name: str
    machine: str  # the kind of machine that works this way (apothecary/jobs.py)
    word: str  # what a group of moves is called: a layer, a pass
    kinds: Tuple[str, ...]  # what a move can be; the first is what makes the part
    classify: Callable[[Move], str]
    groups: Callable[[], GroupRule]
    dwell: Callable[[Optional[float], Optional[float]], float]  # P and S, to seconds
    rapid: Optional[float] = None  # mm/min of a G0, when the file's feed does not set it


def _is_flat(move: Move) -> bool:
    return move.start[0] == move.end[0] and move.start[1] == move.end[1]


# --- additive -------------------------------------------------------------------------


def _additive_kind(move: Move) -> str:
    return "extrude" if move.extruded > 0 else "travel"


class _Layers:
    """A slicer's own marks, where it writes them: a spiral rises on every move and is
    still one layer to its slicer. A file with none starts a layer at each higher Z
    that lays material."""

    def __init__(self) -> None:
        self.count = 0
        self.marked = False
        self.pending = False
        self.z: Optional[float] = None

    def comment(self, text: str) -> None:
        if LAYER_COMMENT.match(text):
            self.marked = self.pending = True

    def _next(self, z: float) -> Group:
        self.count += 1
        self.z = z
        return (f"layer {self.count}", z)

    def move(self, move: Move, kind: str) -> Optional[Group]:
        if self.marked:
            if not self.pending:
                return None
            self.pending = False
            return self._next(move.end[2])
        if kind == "extrude" and (self.z is None or move.end[2] > self.z + _EPSILON):
            return self._next(move.end[2])
        return None


def _additive_dwell(p: Optional[float], s: Optional[float]) -> float:
    """Marlin: P in milliseconds, S in seconds."""
    return (s or 0.0) + (p or 0.0) / 1000.0


ADDITIVE = Process(
    name="additive",
    machine="printer",
    word="layer",
    kinds=("extrude", "travel"),
    classify=_additive_kind,
    groups=_Layers,
    dwell=_additive_dwell,
)


# --- subtractive ----------------------------------------------------------------------


def _subtractive_kind(move: Move) -> str:
    if move.rapid:
        return "rapid"
    return "plunge" if _is_flat(move) and move.end[2] < move.start[2] else "cut"


class _Passes:
    """The toolpath's own names, where it writes them. A CAM post's file has none: it
    starts a pass at each plunge to another depth."""

    def __init__(self) -> None:
        self.named = False
        self.pending: Optional[str] = None
        self.z: Optional[float] = None

    def comment(self, text: str) -> None:
        if OPERATION_COMMENT.match(text):
            self.named = True
            self.pending = text

    def move(self, move: Move, kind: str) -> Optional[Group]:
        if self.pending is not None:
            label, self.pending = self.pending, None
            found = _TO_Z.search(label)
            return (label, float(found.group(1)) if found else None)
        if self.named or kind != "plunge":
            return None
        z = move.end[2]
        if self.z is not None and abs(z - self.z) < _EPSILON:
            return None
        self.z = z
        return (f"depth {z:g}", z)


def _subtractive_dwell(p: Optional[float], s: Optional[float]) -> float:
    """Grbl: P in seconds."""
    return p if p is not None else (s or 0.0)


SUBTRACTIVE = Process(
    name="subtractive",
    machine="router",
    word="pass",
    kinds=("cut", "plunge", "rapid"),
    classify=_subtractive_kind,
    groups=_Passes,
    dwell=_subtractive_dwell,
    rapid=4000.0,  # the maker's figure; tests/test_preview.py holds it to grbl.FEED_MAX
)


# --- by machine -----------------------------------------------------------------------

BY_MACHINE: Dict[str, Process] = {p.machine: p for p in (ADDITIVE, SUBTRACTIVE)}


def for_machine(machine: str) -> Process:
    """The process of a kind of machine; KeyError for one that has none."""
    return BY_MACHINE[machine]
