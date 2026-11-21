"""A part's motion: its pieces moved through one of its parameters, as a table the page plays.

A part whose pieces move against one another as one of its parameters goes -- a rotor's
orbit, a hub's swing, a disc's crank -- declares a ``Motion`` (``BasePart.motion``): the
parameter and its range, the piece that stands still and the pieces that move, each
drawn once by the part's SCAD in its own frame, and the wrapper's own pose function,
which says where each moving piece stands at a value. ``table`` samples that function
at the motion's step and says it as one document, ``motion/1``, which the page plays:
it draws each piece once and moves it rigidly from row to row, with no OpenSCAD run
while it plays and no second copy of a part's maths in the page.

A motion is planar. Each pose is a ``gap_geometry.Pose``: the piece's own origin moved
across the part's xy plane and turned about the part's z axis, which is how each part
here moves -- a rotor rolling in its stator, a hub swinging on its leaves, a disc on its
pins. A piece that bends instead of moving rigidly, a leaf, is ``Bent``: drawn from the
model's own outlines at each sample and extruded, which is the drawing's geometry at
that pose and not a simulation of the bending.

Each row carries the gaps the wrapper names, measured here with ``gap_geometry`` at that
pose: the least, and the point on each body where it is, in the part's frame. The page
computes none of them; between two rows it shows the nearer row's, and says which.

Between two rows the page takes each of x, y and turn in proportion (``interpolate``;
``apothecary/static/part_motion.js`` is its copy, and tests/test_part_motion_js.py holds
the two together). ``interpolation_error`` is how far that puts any point of a piece
from where the wrapper's pose function puts it, the worst over the middle of every
step, and the table says it.

Units: mm and degrees, or the parameter's own unit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from .gap_geometry import Point, Polygon, Pose

FORMAT = "motion/1"

# The most rows a table is made of: a step that would make more is refused, so a
# declaration cannot ask the server for a table it would take minutes to measure.
MOST_ROWS = 2001


@dataclass(frozen=True)
class Insert:
    """A bought insert where it sits in a piece, in that piece's own frame: an upright
    cylinder ``diameter`` across from ``z0`` to ``z1``, named as the part's bought list
    names it."""

    name: str
    at: Point
    z0: float
    z1: float
    diameter: float


@dataclass(frozen=True)
class Piece:
    """One piece the part's SCAD draws alone, with the value of its piece parameter that
    draws it, in its own frame: where its pose's origin is, unturned. ``reach`` is how
    far its farthest point stands from that origin, which bounds what a turn moves. A
    piece that is not ``drawn`` is what is bought and nothing printed -- an output's
    pins -- and carries only its inserts."""

    name: str
    label: str
    reach: float = 0.0
    inserts: Tuple[Insert, ...] = ()
    drawn: bool = True


@dataclass(frozen=True)
class Bent:
    """A piece drawn from the model's outlines at each pose rather than moved: each
    outline, in the part's frame, extruded from ``z0`` to ``z1``. ``outlines(value)``
    gives them; each value must give as many, each of as many points."""

    name: str
    label: str
    z0: float
    z1: float
    outlines: Callable[[float], List[Polygon]]


@dataclass(frozen=True)
class Mark:
    """A gap at one pose: its value, and the point on each body where it is, in the
    part's frame: ``on`` on what stands still, ``to`` on what moves."""

    gap: float
    on: Point
    to: Point


@dataclass(frozen=True)
class Gap:
    """A gap the motion follows: ``measure(value)`` its marks at a pose, the least
    first, one for each place it is followed (a pin each, where there are pins)."""

    name: str
    label: str
    z: float
    measure: Callable[[float], List[Mark]]


@dataclass(frozen=True)
class Motion:
    """What a part declares of its motion. ``pose(value)`` is the wrapper's own: where
    each of ``moving`` stands at ``value`` of ``param``. Each piece is drawn by the
    part's SCAD with ``piece_param`` set to its name, in its own frame, which does not
    read ``param``."""

    param: str
    label: str
    unit: str
    lo: float
    hi: float
    step: float
    piece_param: str
    still: Piece
    moving: Tuple[Piece, ...]
    pose: Callable[[float], Mapping[str, Pose]]
    cyclic: bool = False
    bent: Tuple[Bent, ...] = ()
    gaps: Tuple[Gap, ...] = ()
    note: str = ""

    def __post_init__(self):
        if not self.hi > self.lo:
            raise ValueError(f"a motion runs from low to high: {self.lo} to {self.hi}")
        if not self.step > 0:
            raise ValueError(f"a motion's step is more than nothing: {self.step}")
        if (self.hi - self.lo) / self.step + 1 > MOST_ROWS:
            raise ValueError(
                f"{self.lo} to {self.hi} in steps of {self.step} is more than {MOST_ROWS} rows"
            )
        names = [self.still.name, *(p.name for p in self.moving), *(b.name for b in self.bent)]
        if len(set(names)) != len(names):
            raise ValueError(f"each piece is named once: {names}")

    def samples(self) -> List[float]:
        """The values the table is sampled at: from ``lo`` to ``hi``, both included, at
        ``step`` or a little less, so the last falls on ``hi``."""
        n = max(1, math.ceil((self.hi - self.lo) / self.step - 1e-9))
        return [self.lo + (self.hi - self.lo) * k / n for k in range(n + 1)]

    def summary(self) -> Dict[str, Any]:
        """What a part's metadata says of it: enough to offer it, nothing measured."""
        return {
            "param": self.param,
            "label": self.label,
            "unit": self.unit,
            "range": [self.lo, self.hi],
            "step": self.step,
            "cyclic": self.cyclic,
        }


# ---- between two rows ------------------------------------------------------------------


def bracket(samples: Sequence[float], value: float) -> Tuple[int, float]:
    """The row at or before ``value`` and how far toward the next it stands, 0 to 1;
    a value outside the samples is held at the nearer end."""
    last = len(samples) - 1
    if value <= samples[0] or last == 0:
        return 0, 0.0
    if value >= samples[last]:
        return max(0, last - 1), 1.0
    lo, hi = 0, last
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if samples[mid] <= value:
            lo = mid
        else:
            hi = mid
    return lo, (value - samples[lo]) / (samples[lo + 1] - samples[lo])


def interpolate(samples: Sequence[float], rows: Sequence[Sequence[float]], value: float) -> List[float]:
    """A row at ``value``, each of its numbers taken in proportion between the two rows
    either side: the page's way between samples, which ``part_motion.js`` mirrors."""
    i, t = bracket(samples, value)
    if len(rows) == 1:
        return list(rows[0])
    a, b = rows[i], rows[i + 1]
    return [x + t * (y - x) for x, y in zip(a, b, strict=True)]


def nearest(samples: Sequence[float], value: float) -> int:
    """The row nearest ``value``: the one whose gaps the page shows there."""
    i, t = bracket(samples, value)
    return i + 1 if t > 0.5 and i + 1 < len(samples) else i


def _row(pose: Pose) -> List[float]:
    return [pose.x, pose.y, pose.turn]


def _moved_by(a: Sequence[float], b: Sequence[float], reach: float) -> float:
    """How far apart two poses put a point at most ``reach`` from the piece's origin:
    the shift between them, plus the chord the turn between them sweeps at ``reach``."""
    shift = math.hypot(a[0] - b[0], a[1] - b[1])
    return shift + 2 * reach * abs(math.sin(math.radians(a[2] - b[2]) / 2))


def interpolation_error(motion: Motion, samples: Optional[Sequence[float]] = None) -> Tuple[float, float]:
    """The farthest any point of a moving piece, or of a bent one's outline, stands from
    where the wrapper puts it, when the page takes it in proportion between two rows:
    the worst over the middle of every step, in mm, and the value where it is."""
    samples = list(samples if samples is not None else motion.samples())
    poses = [motion.pose(v) for v in samples]
    outlines = [[b.outlines(v) for v in samples] for b in motion.bent]
    worst, where = 0.0, samples[0]
    for i in range(len(samples) - 1):
        mid = (samples[i] + samples[i + 1]) / 2
        truth = motion.pose(mid)
        for piece in motion.moving:
            a, b = _row(poses[i][piece.name]), _row(poses[i + 1][piece.name])
            between = [x + 0.5 * (y - x) for x, y in zip(a, b, strict=True)]
            off = _moved_by(between, _row(truth[piece.name]), piece.reach)
            if off > worst:
                worst, where = off, mid
        for k, bent in enumerate(motion.bent):
            true_shapes = bent.outlines(mid)
            for s0, s1, st in zip(outlines[k][i], outlines[k][i + 1], true_shapes, strict=True):
                for p0, p1, pt in zip(s0, s1, st, strict=True):
                    off = math.dist(((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2), pt)
                    if off > worst:
                        worst, where = off, mid
    return worst, where


# ---- the table ---------------------------------------------------------------------------


def _point(p: Point, digits: int = 6) -> List[float]:
    return [round(p[0], digits), round(p[1], digits)]


def _insert(i: Insert) -> Dict[str, Any]:
    return {"name": i.name, "at": _point(i.at), "z": [i.z0, i.z1], "diameter": i.diameter}


def table(motion: Motion, params: Mapping[str, Any]) -> Dict[str, Any]:
    """The motion as one document, ``motion/1``: its samples, each moving piece's pose
    at each, each bent piece's outlines at each, each gap's marks at each, and how far
    the page's way between two rows can stray. ``params`` are the part's values; the
    pieces are drawn with them, the motion's parameter and the piece parameter left out."""
    samples = motion.samples()
    poses = [motion.pose(v) for v in samples]
    error, error_at = interpolation_error(motion, samples)
    drawn = {k: v for k, v in params.items() if k not in (motion.param, motion.piece_param)}
    pieces = []
    for piece in motion.moving:
        rows = [[round(x, 9) for x in _row(p[piece.name])] for p in poses]
        pieces.append(
            {
                "piece": piece.name,
                "label": piece.label,
                "reach": piece.reach,
                "drawn": piece.drawn,
                "poses": rows,
                "inserts": [_insert(i) for i in piece.inserts],
                # Where a whole cycle leaves it: what the page adds to its turn each time
                # round, for a motion that goes round again.
                "per_cycle": round(rows[-1][2] - rows[0][2], 9) if motion.cyclic else 0.0,
            }
        )
    gaps = []
    for gap in motion.gaps:
        marks = [gap.measure(v) for v in samples]
        gaps.append(
            {
                "name": gap.name,
                "label": gap.label,
                "unit": "mm",
                "z": gap.z,
                "least": [round(m[0].gap, 6) for m in marks],
                "marks": [
                    [{"gap": round(k.gap, 6), "on": _point(k.on), "to": _point(k.to)} for k in m]
                    for m in marks
                ],
            }
        )
    return {
        "format": FORMAT,
        **motion.summary(),
        "samples": [round(v, 9) for v in samples],
        "piece_param": motion.piece_param,
        "params": drawn,
        "still": {
            "piece": motion.still.name,
            "label": motion.still.label,
            "inserts": [_insert(i) for i in motion.still.inserts],
        },
        "pieces": pieces,
        "bent": [
            {
                "name": b.name,
                "label": b.label,
                "z": [b.z0, b.z1],
                "outlines": [[[_point(p) for p in shape] for shape in b.outlines(v)] for v in samples],
            }
            for b in motion.bent
        ],
        "gaps": gaps,
        "interpolation": {
            "how": "x, y and turn each taken in proportion between the two rows either side; "
            "an outline point by point",
            "error_mm": round(error, 6),
            "at": round(error_at, 6),
        },
        "note": motion.note,
    }


__all__ = [
    "FORMAT",
    "MOST_ROWS",
    "Bent",
    "Gap",
    "Insert",
    "Mark",
    "Motion",
    "Piece",
    "bracket",
    "interpolate",
    "interpolation_error",
    "nearest",
    "table",
]
