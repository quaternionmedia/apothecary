"""Where a point of a picture lies on the surface it shows: one mapping.

A point of a picture is two fractions, across from its left edge and down from
its top (``u``, ``v``). The surface it shows is a plane -- a host's top, or the
floor -- and a point on it is two millimetres from the place's origin. One
three-by-three matrix, a *homography*, takes the one to the other:
``(u, v, 1)`` multiplied out is ``(x * w, y * w, w)``. Everything that asks
where a picture lies asks it here: the mat's corners, a shape's outline, where
a piece made from it stands and how big it is, Why this, and re-sizing.

Two kinds of picture make two kinds of matrix, and nothing downstream tells
them apart:

- **Flat** (``flat``): a picture no camera took -- a file dropped or added, the
  floor's Add -- laid on its place as a rectangle ``W`` millimetres across and
  ``W`` times its height over its width deep, its right toward +x and its top
  toward +y (away from the front). Its last row is ``(0, 0, 1)``: no
  perspective.
- **Through a pinhole** (``pinhole``): a picture a camera took, its lens at
  ``eye`` (``eye.z`` above the plane), turned ``turn`` degrees about the
  vertical, tilted ``tilt`` degrees from straight down, seeing ``fov`` degrees
  across. Square pixels: what it sees down is ``fov``'s width times the
  picture's height over its width.

The camera's conventions are chosen so that one looking straight down at turn 0
takes exactly the flat picture: its right is +x, the picture's top is +y, and
its width on the plane is ``2 * h * tan(fov / 2)`` for a lens ``h`` above it.
Tilting turns the view toward the picture's top -- at turn 0, toward +y, the
far side -- so a camera at tilt 30 looks 30 degrees past straight down. Turning
is counterclockwise seen from above, as every turn in a site is: at turn 90 the
picture's top lies toward -x. A ray that runs along the plane or away from it
lands nowhere, and every function here says so with None rather than a point
behind the camera.

Written out in plain Python, as ``geometry.py`` is, so it depends on nothing.
"""

from __future__ import annotations

import math
from typing import Callable, Iterable, List, NamedTuple, Optional, Sequence, Tuple

Matrix = Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]
Point = Tuple[float, float]
Vec3 = Tuple[float, float, float]

# Below this, a ray runs along the plane, or away from it: it lands nowhere.
GRAZING = 1e-9

# A side is never thinner than this, as compose.MIN_THICKNESS has it.
LEAST_SIDE = 0.01

# The fields of view a lens may be taught, in degrees across: wider than a
# pinhole, narrower than a half-sphere.
FOV_LEAST = 0.01
FOV_MOST = 179.99

# The picture's four corners, as fractions: top left, top right, bottom right, bottom left.
CORNERS: Tuple[Point, ...] = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))


# --- the two kinds of matrix ------------------------------------------------------------


def flat(width: float, tallness: float, centre: Point = (0.0, 0.0)) -> Matrix:
    """A picture laid flat, ``width`` mm across and ``width * tallness`` deep, its
    middle at ``centre``: ``x = centre.x + (u - 0.5) * W``, ``y = centre.y + (0.5 - v) * D``."""
    depth = width * tallness
    return (
        (width, 0.0, centre[0] - width / 2),
        (0.0, -depth, centre[1] + depth / 2),
        (0.0, 0.0, 1.0),
    )


def axes(turn: float, tilt: float) -> Tuple[Vec3, Vec3, Vec3]:
    """A camera's right, its picture's down, and where it looks, as unit vectors in
    the site's frame. Straight down at turn 0: (1, 0, 0), (0, -1, 0), (0, 0, -1);
    tilted about its right, then turned about the vertical."""
    t, k = math.radians(tilt), math.radians(turn)
    ct, st, ck, sk = math.cos(t), math.sin(t), math.cos(k), math.sin(k)

    def turned(v: Vec3) -> Vec3:
        return (v[0] * ck - v[1] * sk, v[0] * sk + v[1] * ck, v[2])

    return turned((1.0, 0.0, 0.0)), turned((0.0, -ct, -st)), turned((0.0, st, -ct))


def looking(turn: float, tilt: float) -> Vec3:
    """Where a camera's centre ray runs: its forward axis."""
    return axes(turn, tilt)[2]


def pinhole(eye: Vec3, turn: float, tilt: float, fov: float, tallness: float) -> Matrix:
    """A picture a camera took, onto the plane ``z = 0``: the lens at ``eye``,
    turned and tilted, ``fov`` degrees across, the picture ``tallness`` as deep
    as it is wide.

    A picture point's ray runs ``forward + (2u - 1) * T * right + (2v - 1) * T *
    tallness * down``, with ``T = tan(fov / 2)``, and lands where it reaches
    ``z = 0``. Written so the third coordinate is positive where a ray lands."""
    right, down, forward = axes(turn, tilt)
    half = math.tan(math.radians(fov) / 2)
    deep = half * tallness
    a = [2 * half * r for r in right]
    b = [2 * deep * d for d in down]
    c = [f - half * r - deep * d for f, r, d in zip(forward, right, down, strict=True)]
    ex, ey, ez = eye
    return (
        (ez * a[0] - ex * a[2], ez * b[0] - ex * b[2], ez * c[0] - ex * c[2]),
        (ez * a[1] - ey * a[2], ez * b[1] - ey * b[2], ez * c[1] - ey * c[2]),
        (-a[2], -b[2], -c[2]),
    )


def moved(matrix: Matrix, dx: float, dy: float) -> Matrix:
    """The same mapping, every point landing ``(dx, dy)`` further on."""
    (a, b, c), (d, e, f), (g, h, i) = matrix
    return ((a + dx * g, b + dx * h, c + dx * i), (d + dy * g, e + dy * h, f + dy * i), (g, h, i))


def as_lists(matrix: Matrix) -> List[List[float]]:
    return [list(row) for row in matrix]


def as_matrix(rows: Sequence[Sequence[float]]) -> Matrix:
    (a, b, c), (d, e, f), (g, h, i) = rows
    return ((a, b, c), (d, e, f), (g, h, i))


# --- where a point lands ----------------------------------------------------------------


def onto(matrix: Matrix, u: float, v: float) -> Optional[Point]:
    """Where the picture's point ``(u, v)`` lands, in mm; None where its ray never does."""
    (a, b, c), (d, e, f), (g, h, i) = matrix
    w = g * u + h * v + i
    if w <= GRAZING:
        return None
    return ((a * u + b * v + c) / w, (d * u + e * v + f) / w)


def apart(matrix: Matrix, p: Point, q: Point) -> Optional[float]:
    """How far apart two picture points land, in mm; None unless both do."""
    landed_p, landed_q = onto(matrix, *p), onto(matrix, *q)
    if landed_p is None or landed_q is None:
        return None
    return math.hypot(landed_q[0] - landed_p[0], landed_q[1] - landed_p[1])


def across(matrix: Matrix) -> Optional[float]:
    """The picture's width across its centre line, in mm: a flat picture's ``W``.
    A camera's centre line lands whenever its centre does, since its right is level."""
    return apart(matrix, (0.0, 0.5), (1.0, 0.5))


def down_the_middle(matrix: Matrix) -> Optional[float]:
    """The picture's depth down its middle, in mm; None when its top does not land."""
    return apart(matrix, (0.5, 0.0), (0.5, 1.0))


def corners(matrix: Matrix) -> List[Optional[Point]]:
    """Where the picture's four corners land (``CORNERS``' order), each None where it does not."""
    return [onto(matrix, u, v) for u, v in CORNERS]


# --- a shape as it lies on the surface -----------------------------------------------------


class Laid(NamedTuple):
    """Where one found shape lies on its surface, and how big it is there.

    ``centre`` is where its middle lands; ``width`` and ``depth`` are its two
    sides as a piece is built with them (its own long and short side when the
    finder measured them, else its upright box across and down); and
    ``turned_degrees`` is counted as ``FoundShape`` counts it, so a build turns
    by minus it."""

    centre: Point
    width: float
    depth: float
    turned_degrees: float


def _ends(cx: float, cy: float, half: float, direction: Point, tallness: float):
    """The two picture points ``half`` (a fraction of the width) either side of a
    centre along ``direction`` (across, down; down counted in widths too)."""
    du, dv = direction[0] * half, direction[1] * half / tallness
    return (cx - du, cy - dv), (cx + du, cy + dv)


def _heading(p: Point, q: Point) -> float:
    """The angle from ``p`` to ``q`` on the surface, counterclockwise from +x, degrees."""
    return math.degrees(math.atan2(q[1] - p[1], q[0] - p[0]))


def _as_counted(degrees: float) -> float:
    """An angle as a shape counts it: from 0 up to but not including 180, and a
    turn the arithmetic left a nanodegree short of a whole one read as that one."""
    return round(degrees, 9) % 180.0


def lay(matrix: Matrix, shape, tallness: float) -> Optional[Laid]:
    """Where ``shape`` lies on the surface ``matrix`` maps its picture onto; None
    when its middle, or an end of a side it is measured by, lands nowhere.

    A shape whose own sides were measured is measured along them: its long side
    from end to end along its ``turned_degrees``, its short side across that,
    and its turn is the way its long side runs on the surface. A shape known
    only by its upright box is measured across and down the picture, and turned
    by its own ``turned_degrees`` plus however far the picture's across is
    turned where it lies. On a flat picture that is the shape's sides times
    ``W`` and its own turn, as they always were."""
    cx = (shape.min_point.x + shape.max_point.x) / 2
    cy = (shape.min_point.y + shape.max_point.y) / 2
    centre = onto(matrix, cx, cy)
    if centre is None:
        return None
    if shape.measured_sides:
        turn = math.radians(shape.turned_degrees)
        along = (math.cos(turn), math.sin(turn))
        aside = (-math.sin(turn), math.cos(turn))
        long_ends = _ends(cx, cy, shape.long_side / 2, along, tallness)
        short_ends = _ends(cx, cy, shape.short_side / 2, aside, tallness)
    else:
        long_ends = ((shape.min_point.x, cy), (shape.max_point.x, cy))
        short_ends = ((cx, shape.min_point.y), (cx, shape.max_point.y))
    ends = [onto(matrix, *end) for end in (*long_ends, *short_ends)]
    if any(end is None for end in ends):
        return None
    p1, p2, q1, q2 = ends
    width = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    depth = math.hypot(q2[0] - q1[0], q2[1] - q1[1])
    if shape.measured_sides:
        # A picture counts its angles the other way round from a build: the
        # surface's heading of the long side is minus the shape's turn.
        turned = _as_counted(-_heading(p1, p2))
    else:
        turned = _as_counted(shape.turned_degrees - _heading(p1, p2))
    return Laid(centre, max(width, LEAST_SIDE), max(depth, LEAST_SIDE), turned)


def box_of(matrix: Matrix, shape) -> Optional[Tuple[float, float]]:
    """The upright box, in mm, that the shape's own upright box covers on the
    surface; None when a corner of it lands nowhere."""
    lo, hi = shape.min_point, shape.max_point
    landed = [
        onto(matrix, u, v) for u, v in ((lo.x, lo.y), (hi.x, lo.y), (hi.x, hi.y), (lo.x, hi.y))
    ]
    if any(p is None for p in landed):
        return None
    xs, ys = [p[0] for p in landed], [p[1] for p in landed]
    return (max(xs) - min(xs), max(ys) - min(ys))


def long_side_on(matrix: Matrix, shape, tallness: float) -> Optional[float]:
    """A shape's long side on the surface, in mm, as ``ScaleReference`` reads it off a
    flat picture: its own long side when measured, else its upright box's longer side."""
    if shape.measured_sides:
        laid = lay(matrix, shape, tallness)
        return laid.width if laid is not None else None
    cx = (shape.min_point.x + shape.max_point.x) / 2
    cy = (shape.min_point.y + shape.max_point.y) / 2
    if shape.width >= shape.height * tallness:
        return apart(matrix, (shape.min_point.x, cy), (shape.max_point.x, cy))
    return apart(matrix, (cx, shape.min_point.y), (cx, shape.max_point.y))


# --- the lens, taught ------------------------------------------------------------------


def solve_fov(
    measure: Callable[[float], Optional[float]],
    target: float,
    least: float = FOV_LEAST,
    most: float = FOV_MOST,
) -> Optional[float]:
    """The field of view, in degrees, at which ``measure`` comes to ``target``.

    By bisection: ``measure`` grows with the field of view, and is None where a
    ray it measures by no longer lands, which counts as further than any
    target. None when no field of view between ``least`` and ``most`` reaches it."""

    def reach(fov: float) -> float:
        got = measure(fov)
        return math.inf if got is None else got

    low, high = least, most
    if not reach(low) <= target <= reach(high):
        return None
    for _ in range(200):
        middle = (low + high) / 2
        if reach(middle) < target:
            low = middle
        else:
            high = middle
        if high - low < 1e-12:
            break
    return (low + high) / 2


# --- where a camera's centre ray lands ----------------------------------------------------


class Box(NamedTuple):
    """A root structure's bounds, as the ray reads them."""

    name: str
    low: Vec3
    high: Vec3


class Hit(NamedTuple):
    """What a ray reached first: a top (``name``), the floor (``""``), or a side of
    something (``side`` true), and the point, in the site's frame."""

    name: str
    point: Vec3
    side: bool = False


def _entry(eye: Vec3, ray: Vec3, box: Box) -> Optional[Tuple[float, int]]:
    """How far along the ray it enters the box, and across which axis; None when
    it misses, or starts inside it."""
    near, far, axis = -math.inf, math.inf, -1
    for k in range(3):
        if abs(ray[k]) < GRAZING:
            if not box.low[k] <= eye[k] <= box.high[k]:
                return None
            continue
        t1, t2 = (box.low[k] - eye[k]) / ray[k], (box.high[k] - eye[k]) / ray[k]
        if t1 > t2:
            t1, t2 = t2, t1
        if t1 > near:
            near, axis = t1, k
        far = min(far, t2)
    if near > far or near <= 0 or axis < 0:
        return None
    return near, axis


def first_surface(eye: Vec3, ray: Vec3, boxes: Iterable[Box]) -> Optional[Hit]:
    """What a ray from ``eye`` reaches first: the top of one of ``boxes``, the floor
    (``z = 0``), or a box's side or underside; None when it reaches none of them
    (the sky). A box it starts inside is passed through."""
    best: Optional[Tuple[float, Hit]] = None
    for box in boxes:
        entered = _entry(eye, ray, box)
        if entered is None:
            continue
        t, axis = entered
        point = (eye[0] + t * ray[0], eye[1] + t * ray[1], eye[2] + t * ray[2])
        top = axis == 2 and ray[2] < 0
        hit = Hit(box.name, point, side=not top)
        if best is None or t < best[0]:
            best = (t, hit)
    if ray[2] < -GRAZING and eye[2] > 0:
        t = -eye[2] / ray[2]
        if best is None or t < best[0]:
            best = (t, Hit("", (eye[0] + t * ray[0], eye[1] + t * ray[1], 0.0)))
    return best[1] if best is not None else None


__all__ = [
    "Box",
    "CORNERS",
    "FOV_LEAST",
    "FOV_MOST",
    "GRAZING",
    "Hit",
    "Laid",
    "Matrix",
    "across",
    "apart",
    "as_lists",
    "as_matrix",
    "axes",
    "box_of",
    "corners",
    "down_the_middle",
    "first_surface",
    "flat",
    "lay",
    "long_side_on",
    "looking",
    "moved",
    "onto",
    "pinhole",
    "solve_fov",
]
