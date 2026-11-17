"""The gap between two bodies in a plane, when it is not one number.

A conventional machine's gap is one number: a rigid rotor turning on its own axis inside
a rigid bore, two concentric circles. Here the gap is a function -- of where round the
machine it is read, and of the pose of what moves -- and the place where it is least
travels as the machine moves. This module describes that from geometry alone: closed
polygons, the poses that place them, and distances between them. It knows no field,
force, material or time, and says nothing of how hard a gap pulls.

A body is a closed polygon in its own frame: its edges join each point to the next and
the last to the first, in either sense. A ``Pose`` places a body in the plane: its own
origin moved to ``(x, y)`` and turned ``turn`` degrees counter-clockwise about it.

Two gaps are read between an outer body and an inner one:

- ``radial_gap``: along rays from a centre, the outer body's nearest crossing less the
  inner body's farthest. It is the gap a winding-function or permeance model reads,
  ``g(theta)``, and the one the airgap part's bore is solved by. It means what it says
  for bodies whose boundaries cross each ray once: star-shaped about the centre.
- ``clearance``: from each point of the outer boundary, the shortest distance to the
  inner body's boundary, negative where the point lies inside the inner body. It is
  what closes at a contact, and what a collision is. For star-shaped bodies it is never
  more than the radial gap on the same ray: the ray's segment is one path between the
  two boundaries, and the clearance is the shortest.

``approach`` finds where two bodies come closest at one pose, as a point on each in its
own frame; ``follow`` follows that point through a sequence of poses and says how far it
travels on each body, and so whether the motion sweeps, stands, rocks, rolls or slips
(``KINDS``).

Every distance here is between polygons. A circle drawn as a polygon of ``n`` sides is
off the true circle by at most its sagitta, ``r * (1 - cos(180 / n))``; ``sagitta``
gives it, and a tolerance a caller passes should be at least that.

Units are those of the points (mm in this repository) and degrees.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

Point = Tuple[float, float]
Polygon = Sequence[Point]

ORIGIN: Point = (0.0, 0.0)


# ---- poses and shapes ---------------------------------------------------------------------


@dataclass(frozen=True)
class Pose:
    """Where a body stands: its own origin at ``(x, y)``, turned ``turn`` degrees."""

    x: float = 0.0
    y: float = 0.0
    turn: float = 0.0

    def _cs(self) -> Tuple[float, float]:
        a = math.radians(self.turn)
        return math.cos(a), math.sin(a)

    def place(self, points: Polygon) -> List[Point]:
        """``points`` of the body's own frame, where this pose puts them."""
        c, s = self._cs()
        return [(self.x + c * px - s * py, self.y + s * px + c * py) for px, py in points]

    def local(self, point: Point) -> Point:
        """A point of the plane in the body's own frame: ``place`` undone."""
        c, s = self._cs()
        dx, dy = point[0] - self.x, point[1] - self.y
        return (c * dx + s * dy, -s * dx + c * dy)


def circle(r: float, n: int, centre: Point = ORIGIN, start: float = 0.0) -> List[Point]:
    """A circle of radius ``r`` as ``n`` points on it, the first at ``start`` degrees:
    what OpenSCAD's ``circle(r, $fn = n)`` draws when ``start`` is 0."""
    out = []
    for k in range(n):
        a = math.radians(start + 360.0 * k / n)
        out.append((centre[0] + r * math.cos(a), centre[1] + r * math.sin(a)))
    return out


def sagitta(r: float, n: int) -> float:
    """How far inside a circle of radius ``r`` the middle of an edge of its ``n``-gon lies."""
    return r * (1 - math.cos(math.pi / n))


def area(polygon: Polygon) -> float:
    """The area a closed polygon encloses, whichever way round its points run."""
    s = 0.0
    n = len(polygon)
    for i in range(n):
        x0, y0 = polygon[i]
        x1, y1 = polygon[(i + 1) % n]
        s += x0 * y1 - x1 * y0
    return abs(s) / 2


def angle_of(point: Point, centre: Point = ORIGIN) -> float:
    """The angle of ``point`` about ``centre``, in [0, 360)."""
    a = math.degrees(math.atan2(point[1] - centre[1], point[0] - centre[0]))
    return a % 360.0


def wrap(angle: float) -> float:
    """``angle`` brought into (-180, 180]."""
    a = math.fmod(angle, 360.0)
    if a > 180:
        a -= 360
    elif a <= -180:
        a += 360
    return a


# ---- distances between boundaries ------------------------------------------------------------


def _foot(px: float, py: float, ax: float, ay: float, bx: float, by: float):
    """The squared distance from (px, py) to segment ab, and the nearest point on it."""
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 == 0 else ((px - ax) * dx + (py - ay) * dy) / length2
    if t < 0:
        t = 0.0
    elif t > 1:
        t = 1.0
    qx, qy = ax + t * dx, ay + t * dy
    return (px - qx) ** 2 + (py - qy) ** 2, qx, qy


class _Edges:
    """A polygon's edges sorted by their least x, so that those within a distance of a
    point are found without reading the rest."""

    def __init__(self, polygon: Polygon):
        n = len(polygon)
        rows = []
        for i in range(n):
            ax, ay = polygon[i]
            bx, by = polygon[(i + 1) % n]
            rows.append((min(ax, bx), max(ax, bx), min(ay, by), max(ay, by), ax, ay, bx, by))
        rows.sort()
        self.rows = rows
        self.xmins = [r[0] for r in rows]
        self.width = max((r[1] - r[0] for r in rows), default=0.0)

    def near(self, px: float, py: float, bound: float = math.inf):
        """The distance from (px, py) to the nearest edge no farther than ``bound``, and
        the point on it; None when no edge is that near."""
        lim = bound * (1 + 1e-9) + 1e-12
        best, bq = lim * lim, None
        lo = bisect.bisect_left(self.xmins, px - lim - self.width) if lim < math.inf else 0
        hi = bisect.bisect_right(self.xmins, px + lim) if lim < math.inf else len(self.rows)
        rows = self.rows
        for k in range(lo, hi):
            x0, x1, y0, y1, ax, ay, bx, by = rows[k]
            if x1 < px - lim or y0 > py + lim or y1 < py - lim:
                continue
            d2, qx, qy = _foot(px, py, ax, ay, bx, by)
            if d2 < best:
                best, bq = d2, (qx, qy)
                lim = math.sqrt(d2)
        return None if bq is None else (math.sqrt(best), bq)


def _to_boundary(points: Polygon, polygon: Polygon) -> List[Tuple[float, Point]]:
    """For each of ``points``, the distance to ``polygon``'s boundary and the point there.
    Each point's distance is at most the last one's plus the step between them, which
    bounds the edges read for it."""
    edges = _Edges(polygon)
    out: List[Tuple[float, Point]] = []
    prev: Optional[Point] = None
    for p in points:
        bound = math.inf if prev is None else out[-1][0] + math.dist(p, prev)
        found = edges.near(p[0], p[1], bound) or edges.near(p[0], p[1])
        out.append(found)
        prev = p
    return out


def _closest(a: Polygon, b: Polygon) -> Tuple[float, Point, Point]:
    """The closest pair of points of the two boundaries: from each point of either to
    the other's edges, reading only edges nearer than the best pair found so far."""
    best: Tuple[float, Point, Point] = (math.inf, (0.0, 0.0), (0.0, 0.0))
    for points, polygon, flip in ((a, b, False), (b, a, True)):
        edges = _Edges(polygon)
        for p in points:
            found = edges.near(p[0], p[1], best[0])
            if found is not None and found[0] < best[0]:
                best = (found[0], found[1], p) if flip else (found[0], p, found[1])
    return best


def inside(point: Point, polygon: Polygon) -> bool:
    """Whether ``point`` lies inside ``polygon`` (even-odd rule; a point on an edge may
    fall either way)."""
    x, y = point
    n = len(polygon)
    hit = False
    for i in range(n):
        x0, y0 = polygon[i]
        x1, y1 = polygon[(i + 1) % n]
        if (y0 > y) != (y1 > y):
            xc = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
            if xc > x:
                hit = not hit
    return hit


def _orient(ax, ay, bx, by, cx, cy) -> float:
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)


def crosses(a: Polygon, b: Polygon) -> bool:
    """Whether an edge of ``a`` crosses an edge of ``b`` outright: two edges that only
    touch, end on the other or run along it, do not cross."""
    na, nb = len(a), len(b)
    for i in range(na):
        (p0x, p0y), (p1x, p1y) = a[i], a[(i + 1) % na]
        lo_x, hi_x = min(p0x, p1x), max(p0x, p1x)
        lo_y, hi_y = min(p0y, p1y), max(p0y, p1y)
        for j in range(nb):
            (q0x, q0y), (q1x, q1y) = b[j], b[(j + 1) % nb]
            if max(q0x, q1x) < lo_x or min(q0x, q1x) > hi_x:
                continue
            if max(q0y, q1y) < lo_y or min(q0y, q1y) > hi_y:
                continue
            d1 = _orient(p0x, p0y, p1x, p1y, q0x, q0y)
            d2 = _orient(p0x, p0y, p1x, p1y, q1x, q1y)
            d3 = _orient(q0x, q0y, q1x, q1y, p0x, p0y)
            d4 = _orient(q0x, q0y, q1x, q1y, p1x, p1y)
            if d1 * d2 < 0 and d3 * d4 < 0:
                return True
    return False


@dataclass(frozen=True)
class Nearest:
    """Where two boundaries come closest: the distance, and the point on each."""

    distance: float
    on_a: Point
    on_b: Point


def nearest(a: Polygon, b: Polygon) -> Nearest:
    """The closest two points of the boundaries of ``a`` and ``b``: from every point of
    each to the other's edges, which finds the closest pair of any two polygons whose
    boundaries do not cross."""
    return Nearest(*_closest(a, b))


def overlaps(a: Polygon, b: Polygon) -> bool:
    """Whether two solid bodies share any area: an edge of one crossing the other's, or
    a point of one inside the other."""
    if crosses(a, b):
        return True
    return any(inside(p, b) for p in a) or any(inside(p, a) for p in b)


def separation(a: Polygon, b: Polygon) -> float:
    """The distance between two solid bodies' boundaries, negative where they overlap."""
    d = nearest(a, b).distance
    return -d if overlaps(a, b) else d


def contained(body: Polygon, cavity: Polygon) -> bool:
    """Whether a solid body lies within a cavity (the free space a closed outline
    encloses, such as a bore): every point of it inside, and no edge crossing out."""
    return all(inside(p, cavity) for p in body) and not crosses(body, cavity)


def clearance_in(body: Polygon, cavity: Polygon) -> float:
    """How far a solid body stands from the walls of the cavity it lies in, negative
    where it does not lie within it."""
    d = nearest(body, cavity).distance
    return d if contained(body, cavity) else -d


# ---- gap profiles ------------------------------------------------------------------------


@dataclass(frozen=True)
class GapProfile:
    """A gap read at a set of angles about a centre: ``gaps[i]`` at ``angles[i]``."""

    angles: Tuple[float, ...]
    gaps: Tuple[float, ...]

    @property
    def minimum(self) -> float:
        return min(self.gaps)

    @property
    def maximum(self) -> float:
        return max(self.gaps)

    @property
    def mean(self) -> float:
        """The mean over the samples: over angle when they are evenly spaced in angle,
        as ``radial_gap``'s are."""
        return sum(self.gaps) / len(self.gaps)

    @property
    def spread(self) -> float:
        return self.maximum - self.minimum

    @property
    def where(self) -> float:
        """The angle of the least gap (the first, where several tie)."""
        return self.angles[self.gaps.index(self.minimum)]

    def is_uniform(self, tol: float) -> bool:
        """Whether the gap is one number, to within ``tol``."""
        return self.spread <= tol

    def minima(self, tol: float) -> List[float]:
        """The angle of each run of samples within ``tol`` of the least gap, at the
        middle of its run: one for an eccentric circle, two for an ellipse in a round
        bore, one per pole for a toothed stator whose every tooth stands as near."""
        n = len(self.gaps)
        low = [g <= self.minimum + tol for g in self.gaps]
        if all(low):
            return []
        start = next(i for i in range(n) if not low[i])
        out = []
        run: List[int] = []
        for k in range(1, n + 1):
            i = (start + k) % n
            if low[i]:
                run.append(i)
            elif run:
                a0 = self.angles[run[0]]
                span = sum(wrap(self.angles[j] - self.angles[j - 1]) for j in run[1:])
                out.append((a0 + span / 2) % 360.0)
                run = []
        return sorted(out)


def _crossings(polygon: Polygon, theta: float, centre: Point) -> List[float]:
    """How far along the ray from ``centre`` at ``theta`` degrees it crosses ``polygon``."""
    ux, uy = math.cos(math.radians(theta)), math.sin(math.radians(theta))
    cx, cy = centre
    n = len(polygon)
    out = []
    for i in range(n):
        ax, ay = polygon[i][0] - cx, polygon[i][1] - cy
        bx, by = polygon[(i + 1) % n][0] - cx, polygon[(i + 1) % n][1] - cy
        ex, ey = bx - ax, by - ay
        denom = ux * ey - uy * ex
        if abs(denom) <= 1e-9 * math.hypot(ex, ey):
            continue  # along the ray: the edges either side cross it at its ends
        t = (ax * ey - ay * ex) / denom  # along the ray
        s = (ax * uy - ay * ux) / denom  # along the edge
        if t >= 0 and -1e-12 <= s <= 1 + 1e-12:
            out.append(t)
    return out


def radial_gap(outer: Polygon, inner: Polygon, n: int = 360, centre: Point = ORIGIN) -> GapProfile:
    """The gap along ``n`` rays from ``centre``, evenly spaced from 0 degrees: the
    outer boundary's nearest crossing less the inner body's farthest. A ray that misses
    either reads ``nan``."""
    angles, gaps = [], []
    for k in range(n):
        theta = 360.0 * k / n
        out_hits = _crossings(outer, theta, centre)
        in_hits = _crossings(inner, theta, centre)
        g = min(out_hits) - max(in_hits) if out_hits and in_hits else math.nan
        angles.append(theta)
        gaps.append(g)
    return GapProfile(tuple(angles), tuple(gaps))


def clearance(outer: Polygon, inner: Polygon, centre: Point = ORIGIN) -> GapProfile:
    """At each point of ``outer``, the shortest distance to ``inner``'s boundary, and
    negative where that point lies inside ``inner``; read at the point's angle about
    ``centre``."""
    angles, gaps = [], []
    for p, (d, _) in zip(outer, _to_boundary(outer, inner), strict=True):
        angles.append(angle_of(p, centre))
        gaps.append(-d if inside(p, inner) else d)
    return GapProfile(tuple(angles), tuple(gaps))


# ---- the closest approach, and where it travels ---------------------------------------------


@dataclass(frozen=True)
class Approach:
    """Where two bodies come closest at one pose: the gap there, and the point on each,
    in that body's own frame and as an angle about its own origin."""

    gap: float
    on_outer: Point
    on_inner: Point

    @property
    def outer_angle(self) -> float:
        return angle_of(self.on_outer)

    @property
    def inner_angle(self) -> float:
        return angle_of(self.on_inner)


def approach(
    outer: Polygon,
    inner: Polygon,
    pose: Pose,
    outer_pose: Optional[Pose] = None,
    tol: float = 1e-9,
) -> Optional[Approach]:
    """Where ``inner`` (its own frame, placed by ``pose``) comes closest to ``outer``
    (placed by ``outer_pose``), or None when there is no one place: points spread round
    each body (``SPREAD`` of them) all stand within ``tol`` of the least distance, as
    on two concentric circles."""
    outer_pose = outer_pose or Pose()
    a = outer_pose.place(outer)
    b = pose.place(inner)
    d, on_a, on_b = _closest(a, b)
    spread = [x for x, _ in _to_boundary(_spread(a), b)]
    spread += [x for x, _ in _to_boundary(_spread(b), a)]
    if max(spread) - d <= tol:
        return None
    return Approach(d, outer_pose.local(on_a), pose.local(on_b))


SPREAD = 48


def _spread(points: Polygon) -> List[Point]:
    step = max(1, len(points) // SPREAD)
    return list(points[::step])


UNIFORM = "uniform"
STILL = "still"
ROCKING = "rocking"
SWEEPING = "sweeping"
STANDING = "standing"
ROLLING = "rolling"
SLIPPING = "slipping"

KINDS = {
    UNIFORM: "no one place is closest: the gap is one number at every pose",
    STILL: "the closest approach stays at one place on each body",
    ROCKING: "it moves back and forth and goes round neither body",
    SWEEPING: "it goes round the outer body and stays at one place on the inner: a cam, "
    "or an eccentric turning rigidly about the axis",
    STANDING: "it stays at one place on the outer body and goes round the inner: a body "
    "turning about a centre of its own, off the axis",
    ROLLING: "it goes round both, the same distance along each: rolling without slip",
    SLIPPING: "it goes round both, a different distance along each: the surfaces slide "
    "past one another there",
}


@dataclass(frozen=True)
class Travel:
    """The closest approach followed through a sequence of poses, first to last.

    ``travel_*`` is how far round each body's own origin the point goes, in degrees,
    signed and unwrapped step by step; ``path_*`` how far along each body's boundary,
    as the sum of the steps' chords. A step must be small enough that the point moves
    less than half a turn round either body between two poses. A cycle is given with
    its end: the poses of one orbit run from 0 to 360 degrees, both included.

    The point followed is wherever the gap is least at each pose. Where several
    places come nearly as close -- a rotor with lobes in a toothed bore -- it jumps
    between them, and ``kind`` describes that jumping point's path, not a contact
    sliding: a rigid rotor of three lobes turning in a toothed bore can read as
    slipping."""

    approaches: Tuple[Optional[Approach], ...]
    travel_outer: float
    travel_inner: float
    path_outer: float
    path_inner: float
    kind: str

    @property
    def turns_outer(self) -> float:
        return self.travel_outer / 360.0

    @property
    def turns_inner(self) -> float:
        return self.travel_inner / 360.0

    @property
    def slip(self) -> float:
        """The path on the outer body less the path on the inner: none for a roll."""
        return self.path_outer - self.path_inner

    @property
    def gaps(self) -> Tuple[Optional[float], ...]:
        return tuple(None if a is None else a.gap for a in self.approaches)


def follow(
    outer: Polygon,
    inner: Polygon,
    poses: Sequence[Pose],
    outer_poses: Optional[Sequence[Pose]] = None,
    tol: float = 1e-6,
    round_tol: float = 1.0,
    slip: float = 0.02,
) -> Travel:
    """The closest approach between ``outer`` and ``inner`` at each of ``poses`` (and
    ``outer_poses``, where the outer body moves too), and how it travels.

    A path within ``tol`` is none; the point goes round a body when its travel there is
    more than ``round_tol`` degrees; a roll's two paths agree within ``slip`` of the
    longer. On polygons the closest point steps between edges and corners, so a point
    that stands still on a body can still trace a short path there: whether it goes
    round is read from its travel, which such steps cancel, and not from its path."""
    outer_poses = list(outer_poses) if outer_poses is not None else [Pose()] * len(poses)
    found = tuple(
        approach(outer, inner, p, q, tol) for p, q in zip(poses, outer_poses, strict=True)
    )
    seen = [a for a in found if a is not None]
    if not seen:
        return Travel(found, 0.0, 0.0, 0.0, 0.0, UNIFORM)
    t_out = t_in = p_out = p_in = 0.0
    for a0, a1 in zip(seen, seen[1:], strict=False):
        t_out += wrap(a1.outer_angle - a0.outer_angle)
        t_in += wrap(a1.inner_angle - a0.inner_angle)
        p_out += math.dist(a0.on_outer, a1.on_outer)
        p_in += math.dist(a0.on_inner, a1.on_inner)
    round_out, round_in = abs(t_out) > round_tol, abs(t_in) > round_tol
    if p_out <= tol and p_in <= tol:
        kind = STILL
    elif not round_out and not round_in:
        kind = ROCKING
    elif round_out and not round_in:
        kind = SWEEPING
    elif round_in and not round_out:
        kind = STANDING
    elif abs(p_out - p_in) <= slip * max(p_out, p_in):
        kind = ROLLING
    else:
        kind = SLIPPING
    return Travel(found, t_out, t_in, p_out, p_in, kind)


__all__ = [
    "Approach",
    "GapProfile",
    "KINDS",
    "Nearest",
    "ORIGIN",
    "Pose",
    "ROCKING",
    "ROLLING",
    "SLIPPING",
    "STANDING",
    "STILL",
    "SWEEPING",
    "Travel",
    "UNIFORM",
    "angle_of",
    "approach",
    "area",
    "circle",
    "clearance",
    "clearance_in",
    "contained",
    "crosses",
    "follow",
    "inside",
    "nearest",
    "overlaps",
    "radial_gap",
    "sagitta",
    "separation",
    "wrap",
]
