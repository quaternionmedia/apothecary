"""A projector aimed at a machine's bed: which of its pixels lands where on the bed.

The light goes the other way from a camera's. A camera's picture is read back onto the
surface it shows (``vision/projection.py``); a projector's output is drawn so that what
it lights lands on the bed where it is meant. Four points fix where: four points of the
bed, marked by a person, and the four pixels of the output that light each of them --
one mapping (``apothecary/homography.py``) from the bed's millimetres to the output's
pixels, and its way back.

**The bed's millimetres** are a machine's working volume as a file counts it, X and Y
from the volume's low corner (api.machine_frame's ``volume``, standing where its
``origin`` has it), on the bed plane, at the frame's ``bed_z``. **Where the bed stands**
is how far along Y a bed that carries Y stands from where the frame's ``origin`` has it
(``bed_offset``: frames.js's ``bedOffsetAt``, ``bed_moves_y`` less the work's Y under
the tool); 0 for a bed that stays. A projector stands still in the room, so the mapping
is of the room: a point ``(x, y)`` of a bed standing ``offset`` along Y lies at ``(x, y
+ offset)`` of the frame, and the four points are kept with where the bed stood when
they were marked.

What it registers, and what it does not: the four points lie on the bed plane, so a
point of that plane lands true, and a point above it -- the top of a part, the stock's
face, a clamp -- is lit where its ray meets the bed plane, displaced away from the
projector's axis by its height. The picture is of intent, never a measurement.

A calibration is kept per machine node of a site in the state folder,
``projectors.json``, written whole under one lock, as a camera's record is.

A prototype: no ratified record governs it.
"""

from __future__ import annotations

import json
import math
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from pydantic import BaseModel, ValidationError

from .homography import Degenerate, Matrix, Point, apply, homography, invert
from .state_folder import state_dir, write_whole

FORMAT = "apothecary.projector/1"
RECORDS = "projectors.json"

# A site's or a node path's name, as a plan keeps one (machine_plans.NAME).
NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]{0,199}$")
# The largest output a projector is taken to have, in pixels along either side.
SIZE_MOST = 16384
# How far inside the volume's floor the points a calibration starts from stand, in mm.
INSET_MM = 20.0


class Refused(ValueError):
    """A calibration that cannot be kept, saying why."""


class Calibration(BaseModel):
    """Four points of a machine's bed and the four pixels of a projector's output that
    light them."""

    format: str = FORMAT
    site: str
    path: str
    bed: List[Point]  # four points on the bed plane, in the bed's millimetres
    pixels: List[Point]  # the pixel lighting each, from the output's top left
    size: Tuple[int, int]  # the output's width and height, in pixels
    bed_offset: float = 0.0  # where a bed that carries Y stood along Y as they were marked
    at: datetime


def _finite(points: Sequence[Sequence[float]], what: str) -> List[Point]:
    if len(points) != 4:
        raise Refused(f"a calibration is four {what}, not {len(points)}")
    out: List[Point] = []
    for point in points:
        numbers = all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in point)
        if len(point) != 2 or not numbers:
            raise Refused(f"each of the {what} is two numbers, not {list(point)!r}")
        x, y = float(point[0]), float(point[1])
        if not (math.isfinite(x) and math.isfinite(y)):
            raise Refused(f"each of the {what} is two finite numbers, not {list(point)!r}")
        out.append((x, y))
    return out


def checked(
    site: str,
    path: str,
    bed: Sequence[Sequence[float]],
    pixels: Sequence[Sequence[float]],
    size: Sequence[int],
    bed_offset: float = 0.0,
) -> Calibration:
    """A calibration that fixes one mapping, or ``Refused`` saying why not: four finite
    points of each, every pixel within the output, an output of a size a projector
    has, and no three of either four on one line."""
    if not (NAME.match(site) and NAME.match(path)):
        raise Refused(f"no calibration can be kept for {site!r}, {path!r}")
    marked = _finite(bed, "points of the bed")
    lit = _finite(pixels, "pixels of the output")
    if len(size) != 2 or not all(isinstance(s, int) and 0 < s <= SIZE_MOST for s in size):
        raise Refused(f"an output is two whole numbers of pixels, 1 to {SIZE_MOST}: not {size!r}")
    wide, high = size
    for u, v in lit:
        if not (0 <= u <= wide and 0 <= v <= high):
            raise Refused(f"pixel {u:g}, {v:g} is outside the {wide} by {high} output")
    if not math.isfinite(bed_offset):
        raise Refused("where the bed stood is a finite number of millimetres")
    try:
        homography(_in_the_room(marked, bed_offset), lit)
    except Degenerate as exc:
        raise Refused(f"the calibration fixes no mapping: {exc}") from None
    return Calibration(
        site=site,
        path=path,
        bed=marked,
        pixels=lit,
        size=(wide, high),
        bed_offset=float(bed_offset),
        at=datetime.now(timezone.utc),
    )


def _in_the_room(bed: Sequence[Point], offset: float) -> List[Point]:
    """Points of a bed standing ``offset`` along Y, where they lie in the frame."""
    return [(x, y + offset) for x, y in bed]


def mapping(calibration: Calibration) -> Matrix:
    """The frame's point on the bed plane (a point of the bed with it standing where the
    frame's ``origin`` has it) to the output's pixel."""
    return homography(_in_the_room(calibration.bed, calibration.bed_offset), calibration.pixels)


def bed_to_projector(
    calibration: Calibration, x: float, y: float, bed_offset: float = 0.0
) -> Point:
    """The pixel that lights the bed's point ``(x, y)``, the bed standing ``bed_offset``
    along Y."""
    return apply(mapping(calibration), x, y + bed_offset)


def projector_to_bed(
    calibration: Calibration, u: float, v: float, bed_offset: float = 0.0
) -> Point:
    """The bed's point the pixel ``(u, v)`` lights, the bed standing ``bed_offset`` along Y."""
    x, y = apply(invert(mapping(calibration)), u, v)
    return (x, y - bed_offset)


def starting_points(volume: Sequence[float]) -> List[Point]:
    """The bed's points a calibration starts from: the volume's floor, ``INSET_MM`` in
    from each side (a fifth of a side, for a side shorter than five insets), front left,
    front right, back right, back left."""
    vx, vy = float(volume[0]), float(volume[1])
    ix, iy = min(INSET_MM, vx / 5), min(INSET_MM, vy / 5)
    return [(ix, iy), (vx - ix, iy), (vx - ix, vy - iy), (ix, vy - iy)]


# --- the records, in the state folder ---------------------------------------------------

# One read-modify-write at a time; a write lands whole, so a reader never sees half a file.
_LOCK = threading.Lock()


def _records_file() -> Path:
    return state_dir() / RECORDS


def _load() -> List[Calibration]:
    """Every machine's calibration; a file missing or unreadable holds none, and a
    record that does not read is left out rather than taking the rest with it."""
    try:
        data = json.loads(_records_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = data.get("projectors", []) if isinstance(data, dict) else []
    kept: List[Calibration] = []
    for row in rows if isinstance(rows, list) else []:
        try:
            kept.append(Calibration.model_validate(row))
        except ValidationError:
            continue
    return kept


def records(site: Optional[str] = None) -> List[Calibration]:
    """The calibrations of one site's machines (every site's with none named)."""
    return [c for c in _load() if site is None or c.site == site]


def load(site: str, path: str) -> Optional[Calibration]:
    return next((c for c in _load() if c.site == site and c.path == path), None)


def save(calibration: Calibration) -> Calibration:
    """Keep a machine's calibration in place of the one it had."""
    with _LOCK:
        kept = [
            c for c in _load() if (c.site, c.path) != (calibration.site, calibration.path)
        ]
        kept.append(calibration)
        write_whole(
            _records_file(),
            json.dumps({"projectors": [c.model_dump(mode="json") for c in kept]}, indent=2),
        )
    return calibration


def clear(site: str, path: str) -> bool:
    """Forget a machine's calibration; whether it had one."""
    with _LOCK:
        everything = _load()
        kept = [c for c in everything if (c.site, c.path) != (site, path)]
        if len(kept) == len(everything):
            return False
        write_whole(
            _records_file(),
            json.dumps({"projectors": [c.model_dump(mode="json") for c in kept]}, indent=2),
        )
    return True


__all__ = [
    "Calibration",
    "FORMAT",
    "INSET_MM",
    "Refused",
    "bed_to_projector",
    "checked",
    "clear",
    "load",
    "mapping",
    "projector_to_bed",
    "records",
    "save",
    "starting_points",
]
