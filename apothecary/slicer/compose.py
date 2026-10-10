"""What a slice is composed from beyond the slicer's own profiles: the start of a
print, the filament, and what a piece's word declares.

The owner's decision of 2026-10-10 (docs/plans/slicer-2026-10-10.md, *Decided
after the server side*): the start of a print is composed from modules as they
are wanted; the filament is the printer's one, and choosing another is a
module; a word declaring print settings for the pieces made as it has the shape
a part's declaration has. Each is a ``Piece`` here, and each says what it does.

A **stub** is a piece that exists, says what it will do, and is not chosen: a
printer's profile that names one is refused, saying what it will do, before
anything is built. Building one is replacing its stub with what it does and
taking ``stub`` off -- the profile then names it, and nothing else changes.

A printer's profile (``parts/ender3/slicer.json``) names the pieces its slices
use: ``"start": {"modules": [...], "source": ...}`` and ``"filament":
{"modules": [...], "source": ...}``. With neither, a printer's start is
``home`` and its filament ``printer``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from .modules import SlicerError

START, FILAMENT, DECLARED = "start", "filament", "declared"

# A line of G-code that homes, X, Y and Z or all at once: what `home` stands on,
# and what the levelling pieces will follow.
_HOMES = re.compile(r"^\s*G28(?:\s|;|$)", re.I | re.M)


@dataclass(frozen=True)
class Piece:
    """One piece a slice can be composed from: what it does, or will do."""

    kind: str  # START, FILAMENT or DECLARED
    id: str
    does: str
    stub: bool = False
    # What it does to the start G-code, for a start piece that is built.
    compose: Optional[Callable[[str], str]] = field(default=None, compare=False, repr=False)

    def as_json(self) -> dict:
        return {"kind": self.kind, "id": self.id, "does": self.does, "stub": self.stub}


def _homes(start: str) -> str:
    """The printer's own start, as its slicer profile has it: it must home."""
    if not _HOMES.search(start or ""):
        raise SlicerError(
            "the printer's start G-code does not home (no G28): `home` is the profile's own "
            "start, and every other piece of a start follows its homing"
        )
    return start


PIECES: Tuple[Piece, ...] = (
    Piece(
        START,
        "home",
        "the printer's own start, as its slicer profile has it: heat, home every axis (G28) "
        "and prime the nozzle; no levelling",
        compose=_homes,
    ),
    Piece(
        START,
        "stored-mesh",
        "after G28, turn on the bed mesh the printer stored (M420 S1), so the firmware "
        "follows the bed it last probed",
        stub=True,
    ),
    Piece(
        START,
        "probe-each-print",
        "after G28, probe the bed before each print (G29) and print on what it finds",
        stub=True,
    ),
    Piece(
        START,
        "first-layer-offset",
        "raise or lower the first layer by an offset measured at the bench (the paper test), "
        "added to every Z the slicer writes",
        stub=True,
    ),
    Piece(FILAMENT, "printer", "the printer's one filament, named in its profile"),
    Piece(
        FILAMENT,
        "choose",
        "a slice names another filament the printer has loaded, from the slicer's profiles "
        "of its vendor, and the start heats for it",
        stub=True,
    ),
    Piece(
        DECLARED,
        "word-print-settings",
        "a word declares print settings for the pieces made as it, in the shape a part "
        "declares them (PrintSettings), and a piece's slice uses them as a part's does",
        stub=True,
    ),
)

DEFAULTS: Dict[str, List[str]] = {START: ["home"], FILAMENT: ["printer"]}


def pieces(kind: Optional[str] = None) -> List[Piece]:
    """Every piece, or every piece of one kind, built ones first."""
    found = [p for p in PIECES if kind is None or p.kind == kind]
    return sorted(found, key=lambda p: p.stub)


def piece(kind: str, piece_id: str) -> Piece:
    for p in PIECES:
        if p.kind == kind and p.id == piece_id:
            return p
    names = ", ".join(p.id for p in pieces(kind))
    raise SlicerError(f"no {kind} piece {piece_id!r} (there are: {names})")


def chosen(kind: str, named: List[str], where: str) -> List[Piece]:
    """The pieces of ``kind`` a profile names, in its order; a stub named is refused,
    saying what it will do."""
    found = [piece(kind, name) for name in named]
    for p in found:
        if p.stub:
            raise SlicerError(
                f"{where}: the {kind} piece {p.id!r} is a stub, not built yet "
                f"(what it will do: {p.does})"
            )
    if kind == START and (not found or found[0].id != "home"):
        raise SlicerError(f"{where}: a start begins with 'home'; the others follow its homing")
    if kind == FILAMENT and len(found) != 1:
        raise SlicerError(f"{where}: a slice has one filament piece, not {len(found)}")
    return found


def compose_start(base: str, start: List[Piece]) -> str:
    """The start G-code: the slicer profile's own, through each chosen piece in turn."""
    text = base
    for p in start:
        if p.compose is not None:
            text = p.compose(text)
    return text


def describe(chosen_pieces: List[Piece]) -> str:
    return "; ".join(f"{p.id}: {p.does}" for p in chosen_pieces)
