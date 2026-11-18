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

**A second plane** registers a height. Marked again, four points of a plane ``height`` mm
above the bed (a flat piece of known thickness lying on it) and the pixels lighting them
fix a second mapping, and from the two follows the mapping of any plane between them or
a little beyond, under one assumption: the projector is a pinhole, with no lens
distortion. A pinhole projects ``(X, Y, Z, 1)`` by a 3 x 4 matrix ``P`` whose columns are
``p0 p1 p2 p3``: the plane ``Z = z`` is mapped by ``[p0 p1 (z p2 + p3)]``, linear in
``z``. The plane's mapping fixed by four points carries a scale of its own, so the two
are brought to one (``homography.scaled_like``: the multiple that makes their first
two columns, ``p0`` and ``p1``, agree) and the plane at ``z`` is ``(1 - t) H0 + t Hh``,
``t = z / height`` (``mapping_at``): exactly the pinhole's for exact points, through both
marked sets of pixels for any points, and the line through them beyond ``height``.
What the assumption leaves out is in ``docs/projector.md``.

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

from .homography import Degenerate, Matrix, Point, apply, blend, homography, invert, scaled_like
from .state_folder import state_dir, write_whole

FORMAT = "apothecary.projector/1"
RECORDS = "projectors.json"

# A site's or a node path's name, as a plan keeps one (machine_plans.NAME).
NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]{0,199}$")
# The largest output a projector is taken to have, in pixels along either side.
SIZE_MOST = 16384
# How far inside the volume's floor the points a calibration starts from stand, in mm.
INSET_MM = 20.0
# A second plane is at least this far above the first, in mm: nearer, a hand cannot mark
# two planes apart, and they are the same plane.
MIN_SPAN_MM = 1.0
# ... and at most this far, a height no flat piece on a bed stands at.
MAX_SPAN_MM = 500.0
# A plane is mapped from the bed plane up to this many times the second plane's height;
# past the second plane's own height it is extrapolated, and what a marking got wrong in
# the second plane is carried that many times over.
REACH = 2.0
# The two planes' first two columns differ by at most this fraction (homography.
# scaled_like). Two planes of one pinhole projector that held still differ by none; a
# hand marking each differs by several hundredths, and a projector moved or zoomed between
# them by about as much, so this tells only a gross mismatch -- points marked in another
# order, or of another plane -- and not a projector that moved a little.
AGREE = 0.5
# The second plane's mapping differs from the first's by less than this fraction of its
# largest entry (once scaled alike): the same pixels marked twice.
SAME_AS = 1e-9


class Refused(ValueError):
    """A calibration that cannot be kept, saying why."""


class Upper(BaseModel):
    """A second plane: four points ``height`` mm above the bed plane (in the bed's
    millimetres, so a bed that carries Y has them where it stood) and the pixels of the
    same output lighting them."""

    bed: List[Point]
    pixels: List[Point]  # in the first plane's output, scaled to it from the page's canvas
    height: float
    bed_offset: float = 0.0
    at: datetime


class Calibration(BaseModel):
    """Four points of a machine's bed and the four pixels of a projector's output that
    light them; and, once marked, a second plane."""

    format: str = FORMAT
    site: str
    path: str
    bed: List[Point]  # four points on the bed plane, in the bed's millimetres
    pixels: List[Point]  # the pixel lighting each, from the output's top left
    size: Tuple[int, int]  # the output's width and height, in pixels
    bed_offset: float = 0.0  # where a bed that carries Y stood along Y as they were marked
    at: datetime
    upper: Optional[Upper] = None  # a second plane, at a known height; None: the bed plane only


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


def checked_upper(
    calibration: Calibration,
    pixels: Sequence[Sequence[float]],
    size: Sequence[int],
    height: float,
    bed: Optional[Sequence[Sequence[float]]] = None,
    bed_offset: float = 0.0,
) -> Calibration:
    """``calibration`` with a second plane, or ``Refused`` saying why it fixes none: a
    height not finite or within ``MIN_SPAN_MM`` of the bed plane (the same plane) or
    past ``MAX_SPAN_MM``, four points or pixels of either that fix no mapping, the
    pixels marked where the bed plane's were (no height told), or a plane the first does
    not agree with (``AGREE``: a gross mismatch only). ``bed`` is the first's four points when none are given, and
    ``pixels`` of a canvas ``size`` are scaled to the first's output as the page scales."""
    if isinstance(height, bool) or not isinstance(height, (int, float)) or not math.isfinite(height):
        raise Refused("the second plane's height is a finite number of millimetres")
    if height < MIN_SPAN_MM:
        raise Refused(
            f"a second plane {height:g} mm above the bed is within {MIN_SPAN_MM:g} mm of the "
            "bed plane: the two are one plane to a hand's marking, and fix no height"
        )
    if height > MAX_SPAN_MM:
        raise Refused(f"a second plane {height:g} mm above the bed is past {MAX_SPAN_MM:g} mm")
    marked = _finite(bed if bed is not None else calibration.bed, "points of the second plane")
    lit = _finite(pixels, "pixels of the second plane")
    if len(size) != 2 or not all(isinstance(s, int) and 0 < s <= SIZE_MOST for s in size):
        raise Refused(f"an output is two whole numbers of pixels, 1 to {SIZE_MOST}: not {size!r}")
    if not math.isfinite(bed_offset):
        raise Refused("where the bed stood is a finite number of millimetres")
    wide, high = size
    for u, v in lit:
        if not (0 <= u <= wide and 0 <= v <= high):
            raise Refused(f"pixel {u:g}, {v:g} is outside the {wide} by {high} output")
    scaled = [(u * calibration.size[0] / wide, v * calibration.size[1] / high) for u, v in lit]
    upper = Upper(
        bed=marked,
        pixels=scaled,
        height=float(height),
        bed_offset=float(bed_offset),
        at=datetime.now(timezone.utc),
    )
    try:
        _two_planes(calibration, upper)
    except Degenerate as exc:
        raise Refused(f"the second plane fixes no mapping: {exc}") from None
    return calibration.model_copy(update={"upper": upper})


def _two_planes(calibration: Calibration, upper: Upper) -> Tuple[Matrix, Matrix]:
    """The bed plane's mapping and the second plane's, brought to one scale; ``Degenerate``
    when the second fixes none, lies where the first does, or does not agree with it."""
    first = mapping(calibration)
    second = homography(_in_the_room(upper.bed, upper.bed_offset), upper.pixels)
    scaled, misfit = scaled_like(second, first)
    if misfit > AGREE:
        raise Degenerate(
            f"it does not agree with the bed plane's, by {misfit:.0%} of it (at most "
            f"{AGREE:.0%}): the four points are marked in another order than the bed "
            "plane's, or are not of a plane over the bed, or the projector moved between"
        )
    gap = max(abs(a - b) for ra, rb in zip(scaled, first, strict=True) for a, b in zip(ra, rb, strict=True))
    if gap < SAME_AS * max(abs(v) for row in first for v in row):
        raise Degenerate(
            "its pixels are the bed plane's: a plane above the bed lights the same points "
            "elsewhere, and nothing of its height is told"
        )
    return first, scaled


def mapping_at(
    calibration: Calibration, z: float, over: Sequence[Point] = ()
) -> Matrix:
    """The mapping of the plane ``z`` mm above the bed: the frame's point on that plane
    (the room's X and Y, as ``mapping`` takes them) to the output's pixel. Exact for a
    pinhole projector between and beyond the two planes, up to ``REACH`` times the second's
    height; ``Refused`` for a height below the bed, for any above the bed plane while
    no second plane is marked, for one past that reach, and for a plane at which a point
    of ``over`` (and each of the calibration's own) reaches the projector's lens plane,
    where a pinhole's picture turns inside out."""
    if isinstance(z, bool) or not isinstance(z, (int, float)) or not math.isfinite(z):
        raise Refused("a height is a finite number of millimetres")
    first = mapping(calibration)
    if abs(z) < 1e-9:
        return first
    if z < 0:
        raise Refused(f"{z:g} mm is below the bed plane, which is as low as a picture is drawn")
    upper = calibration.upper
    if upper is None:
        raise Refused(
            f"only the bed plane is calibrated: a plane {z:g} mm above it needs a second "
            "calibration at a known height"
        )
    if z > REACH * upper.height + 1e-9:
        raise Refused(
            f"{z:g} mm is past {REACH:g} times the second plane's {upper.height:g} mm: "
            "beyond that the line through the two planes is not trusted"
        )
    _, second = _two_planes(calibration, upper)
    at = blend(first, second, z / upper.height)
    points = [*_in_the_room(calibration.bed, calibration.bed_offset), *over]
    for x, y in points:
        w0 = first[2][0] * x + first[2][1] * y + first[2][2]
        w = at[2][0] * x + at[2][1] * y + at[2][2]
        if w * w0 <= 0.0:
            raise Refused(
                f"a plane {z:g} mm above the bed reaches the projector's lens plane over "
                f"{x:g}, {y:g}: the two planes do not describe a projector that high"
            )
    return at


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
    "MAX_SPAN_MM",
    "MIN_SPAN_MM",
    "REACH",
    "Refused",
    "Upper",
    "bed_to_projector",
    "checked",
    "checked_upper",
    "clear",
    "load",
    "mapping",
    "mapping_at",
    "projector_to_bed",
    "records",
    "save",
    "starting_points",
]
