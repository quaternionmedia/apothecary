"""What a slice is composed from beyond the slicer's own profiles: the start of a
print, the filament, and what a piece's word declares.

The start of a print is composed from modules as they are wanted; the filament is the printer's one, and choosing another is a
module; a word declaring print settings for the pieces made as it has the shape
a part's declaration has. Each is a ``Piece`` here, and each says what it does.

A **stub** is a piece that exists, says what it will do, and is not chosen: a
printer's profile that names one is refused, saying what it will do, before
anything is built. Building one is replacing its stub with what it does and
taking ``stub`` off -- the profile then names it, and nothing else changes.

A built piece may carry a **precondition** (``needs``): what must hold of the
printer's profile, or of its board's bed readings, for the piece to be chosen.
It is checked where a stub is refused -- before anything is read or built -- and
a piece whose precondition fails is refused with the reason. The two levelling
pieces each carry one. ``stored-mesh`` turns on the mesh the board stores
(``M420 S1``), and is chosen only while the newest bed reading of the printer's
board (``firmware.devices.leveling_records``, by the port the board is on) is a
probe whose range is under the bound the profile holds
(``measured.mesh_range_bound``): a reading of what the board stores (``M420 V``)
does not say the bed is that, and a bed further out than the bound is trammed,
not corrected, so a mesh the board stores is never turned on by a start piece
unless the bed was probed to under that bound. ``probe-each-print`` probes before
each print (``G29``), and needs the probe the bench measured
(``measured.probe_offset``). A start levels one way: not both.

Each levelling line follows the last ``G28`` of the start, since ``G28`` turns
levelling off in Marlin unless the firmware restores it; a probe also follows
the wait for the bed (``M190``) when one follows that ``G28``, so the bed is
probed at the temperature it prints at.

A printer's profile (``parts/ender3/slicer.json``) names the pieces its slices
use: ``"start": {"modules": [...], "source": ...}`` and ``"filament":
{"modules": [...], "source": ...}``. With neither, a printer's start is
``home`` and its filament ``printer``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Tuple

from .modules import SlicerError

if TYPE_CHECKING:
    from .profiles import PrinterProfile

START, FILAMENT, DECLARED = "start", "filament", "declared"

# A line of G-code that homes, X, Y and Z or all at once: what `home` stands on,
# and what the levelling pieces follow. The match ends at the word, so the line
# it is on is the one found.
_HOMES = re.compile(r"^[ \t]*G28(?=\s|;|$)", re.I | re.M)
# A line that waits for the bed to reach its temperature: a probe follows it.
_BED_WAIT = re.compile(r"^[ \t]*M190(?=\s|;|$)", re.I | re.M)

STORED_MESH_LINE = "M420 S1 ; use the bed mesh the printer stored"
PROBE_LINE = "G29 ; probe the bed"
LEVELLING = ("stored-mesh", "probe-each-print")


@dataclass(frozen=True)
class Piece:
    """One piece a slice can be composed from: what it does, or will do."""

    kind: str  # START, FILAMENT or DECLARED
    id: str
    does: str
    stub: bool = False
    # What must hold for a built piece to be chosen, given the printer's profile and
    # the port its board is on when known: raises SlicerError saying why it does not.
    needs: Optional[Callable[["PrinterProfile", Optional[str]], None]] = field(
        default=None, compare=False, repr=False
    )
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


def _last(pattern: re.Pattern, text: str, start: int = 0) -> Optional[re.Match]:
    found = None
    for match in pattern.finditer(text, start):
        found = match
    return found


def _after(text: str, match: re.Match, line: str) -> str:
    """``line`` on the line after the one ``match`` is on."""
    end = text.find("\n", match.end())
    if end == -1:
        return f"{text}\n{line}"
    return f"{text[:end]}\n{line}{text[end:]}"


def _after_homing(start: str, line: str) -> str:
    """``line`` after the last G28: G28 turns levelling off, so what levels follows it."""
    homed = _last(_HOMES, _homes(start))
    return _after(start, homed, line)


def _after_the_beds_wait(start: str, line: str) -> str:
    """``line`` after the last G28 and, when the start then waits for the bed (M190),
    after that wait: the bed is probed at the temperature it prints at."""
    homed = _last(_HOMES, _homes(start))
    waited = _last(_BED_WAIT, start, homed.end())
    return _after(start, waited or homed, line)


def _a_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _needs_a_probe_under_the_bound(profile: "PrinterProfile", port: Optional[str]) -> None:
    """``stored-mesh``: the newest bed reading of the printer's board is a probe whose
    range is under the bound the profile holds."""
    bound = profile.measured.get("mesh_range_bound")
    under = bound.value if bound is not None else None
    if not _a_number(under):
        raise SlicerError(
            f"{profile.file}: 'stored-mesh' turns a mesh on only under a bound on what a "
            "probe found, and the profile holds no bound (measured.mesh_range_bound), a "
            "value in mm with its source"
        )
    if not port:
        raise SlicerError(
            f"{profile.file}: 'stored-mesh' reads the newest bed reading of the printer's "
            f"board, and {profile.part}'s board is on no known port: slice for the printer "
            "where it stands (its site, with its board pinned and plugged in, or its port)"
        )
    from ..firmware import devices

    readings = devices.leveling_records(port)
    if not readings:
        raise SlicerError(
            f"{profile.file}: 'stored-mesh' needs a bed reading, and there is no bed reading "
            f"of the board on {port}: Probe bed first"
        )
    newest = readings[0]
    if newest.method != "probe":
        raise SlicerError(
            f"{profile.file}: the newest bed reading of the board on {port} ({newest.id}) is "
            "a read of what the board holds (M420 V), not a probe, and what it holds is not "
            "known to be the bed: Probe bed, store the mesh from the printer's screen, then "
            "choose 'stored-mesh'"
        )
    found = newest.stats.get("range")
    if not _a_number(found):
        raise SlicerError(
            f"{profile.file}: the newest probe of the board on {port} ({newest.id}) has no range"
        )
    if not found < under:
        raise SlicerError(
            f"{profile.file}: the newest probe of the board on {port} ({newest.id}) found a "
            f"range of {found:g} mm, not under the {under:g} mm the profile holds as the "
            "bound (measured.mesh_range_bound): tram the bed and probe again before a "
            "stored mesh is turned on"
        )


def _needs_the_probe(profile: "PrinterProfile", port: Optional[str]) -> None:
    """``probe-each-print``: the probe the bench measured, by its offset in the profile."""
    held = profile.measured.get("probe_offset")
    if held is None or not held.value:
        raise SlicerError(
            f"{profile.file}: 'probe-each-print' probes with the printer's probe, and the "
            "profile holds no probe offset the bench measured (measured.probe_offset)"
        )


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
        "follows the bed it last probed; chosen only while the newest bed reading of the "
        "printer's board is a probe whose range is under the profile's bound "
        "(measured.mesh_range_bound)",
        needs=_needs_a_probe_under_the_bound,
        compose=lambda start: _after_homing(start, STORED_MESH_LINE),
    ),
    Piece(
        START,
        "probe-each-print",
        "after G28, probe the bed before each print (G29), once the start has waited for "
        "the bed's temperature, and print on what it finds; needs the probe whose offset "
        "the profile holds (measured.probe_offset)",
        needs=_needs_the_probe,
        compose=lambda start: _after_the_beds_wait(start, PROBE_LINE),
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


def chosen(
    kind: str, named: List[str], profile: "PrinterProfile", port: Optional[str] = None
) -> List[Piece]:
    """The pieces of ``kind`` ``profile`` names, in its order. A stub named is refused,
    saying what it will do, and a built piece whose precondition fails is refused
    with the reason -- both before anything is read or built. ``port`` is the one
    the printer's board is on, when a slice knows it."""
    where = profile.file
    found = [piece(kind, name) for name in named]
    for p in found:
        if p.stub:
            raise SlicerError(
                f"{where}: the {kind} piece {p.id!r} is a stub, not built yet "
                f"(what it will do: {p.does})"
            )
    if len({p.id for p in found}) != len(found):
        raise SlicerError(f"{where}: a {kind} piece is named once")
    if kind == START and (not found or found[0].id != "home"):
        raise SlicerError(f"{where}: a start begins with 'home'; the others follow its homing")
    if kind == FILAMENT and len(found) != 1:
        raise SlicerError(f"{where}: a slice has one filament piece, not {len(found)}")
    if len([p for p in found if p.id in LEVELLING]) > 1:
        raise SlicerError(
            f"{where}: a start levels one way: 'stored-mesh' or 'probe-each-print', not both"
        )
    for p in found:
        if p.needs is not None:
            p.needs(profile, port)
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
