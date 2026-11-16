"""Orbitals of complexity: pieces on nested spherical shells, by what they are built from.

Pure arithmetic over names and sizes; nothing here reads the registry, a site or a
viewer. The universe (``universe.py``) feeds it each part's children and footprint
and draws what comes back.

- **Depth** is composition depth: a name built from no other is 0, any other is one
  more than the deepest it is built from. A cycle ends where it closes, and a child
  that is not a name given is dropped.
- A **shell** is a rank among the depths that occur, dense: a depth no name has leaves
  no empty shell.
- A shell's **radius** is the smallest that keeps its pieces' bounding spheres
  (half a footprint's diagonal, with a gap) clear of each other and clear of the shell
  inside.
- A piece's **point** on its shell is one of a Fibonacci lattice, each shell turned a
  golden angle from the one inside so points do not line up along a ray.
- A piece's **turn** stands its up (+z) along the ray from the centre, in OpenSCAD's
  ``rotate([rx, ry, rz])`` order and degrees.
"""

from __future__ import annotations

import math
from typing import Dict, Iterable, List, Mapping, NamedTuple, Sequence, Set, Tuple

Point = Tuple[float, float, float]

# Clear space kept between two neighbouring pieces' bounding spheres, and between
# a shell's and the next one's (mm).
GAP = 20.0

GOLDEN_ANGLE = math.pi * (3.0 - math.sqrt(5.0))


def composition_depths(children: Mapping[str, Iterable[str]]) -> Dict[str, int]:
    """Each name's depth: 0 for one built from nothing, else 1 + its deepest child's.

    A name in ``children`` that names itself, or closes a loop through others, counts
    the child that would close it as nothing, so the walk ends and the same input gives
    the same depths. A child that is not a key of ``children`` is dropped."""
    known = set(children)
    depth: Dict[str, int] = {}

    def visit(name: str, walking: Set[str]) -> int:
        if name in depth:
            return depth[name]
        walking = walking | {name}
        below = [
            visit(child, walking)
            for child in sorted(set(children[name]))
            if child in known and child not in walking
        ]
        depth[name] = 1 + max(below) if below else 0
        return depth[name]

    for name in sorted(known):
        visit(name, set())
    return depth


def dense_shells(depths: Mapping[str, int]) -> Dict[str, int]:
    """Each name's shell: its depth's rank among the depths that occur."""
    rank = {d: i for i, d in enumerate(sorted(set(depths.values())))}
    return {name: rank[d] for name, d in depths.items()}


def fibonacci_sphere(n: int, radius: float = 1.0, phase: float = 0.0) -> List[Point]:
    """``n`` points spread evenly over a sphere of ``radius`` about the origin, the
    lattice turned ``phase`` radians about z. None for ``n`` of 0."""
    points: List[Point] = []
    for i in range(n):
        z = 1.0 - (2.0 * i + 1.0) / n
        ring = math.sqrt(max(0.0, 1.0 - z * z))
        angle = i * GOLDEN_ANGLE + phase
        points.append(
            (radius * ring * math.cos(angle), radius * ring * math.sin(angle), radius * z)
        )
    return points


def _distance(a: Point, b: Point) -> float:
    return math.dist(a, b)


def outward_turn(point: Point) -> Tuple[float, float, float]:
    """The turn, as OpenSCAD ``rotate([rx, ry, rz])`` degrees, that takes +z to the
    direction of ``point`` from the origin: ``[0, polar angle, azimuth]``. The origin
    itself has no direction and turns nothing."""
    x, y, z = point
    length = math.sqrt(x * x + y * y + z * z)
    if length == 0.0:
        return (0.0, 0.0, 0.0)
    polar = math.degrees(math.acos(max(-1.0, min(1.0, z / length))))
    azimuth = math.degrees(math.atan2(y, x)) if (x or y) else 0.0
    return (0.0, polar, azimuth)


def turn_matrix(turn: Sequence[float]) -> Tuple[Point, Point, Point]:
    """The rows of the rotation OpenSCAD's ``rotate([rx, ry, rz])`` makes: about x,
    then y, then z."""
    rx, ry, rz = (math.radians(a) for a in turn)
    cx, sx, cy, sy, cz, sz = (
        math.cos(rx),
        math.sin(rx),
        math.cos(ry),
        math.sin(ry),
        math.cos(rz),
        math.sin(rz),
    )
    return (
        (cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx),
        (sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx),
        (-sy, cy * sx, cy * cx),
    )


def turned(turn: Sequence[float], point: Sequence[float]) -> Point:
    """``point`` turned about the origin by ``turn``."""
    m = turn_matrix(turn)
    return (
        m[0][0] * point[0] + m[0][1] * point[1] + m[0][2] * point[2],
        m[1][0] * point[0] + m[1][1] * point[1] + m[1][2] * point[2],
        m[2][0] * point[0] + m[2][1] * point[1] + m[2][2] * point[2],
    )


class Placement(NamedTuple):
    """Where a piece stands: its shell, that shell's radius, its point and its turn."""

    shell: int
    radius: float
    point: Point
    turn: Tuple[float, float, float]


def shell_radii(sizes: Sequence[Sequence[float]], gap: float = GAP) -> List[float]:
    """The radius of each shell, inside out, given each shell's pieces' sizes (the
    radius of each one's bounding sphere), in the order they are laid on the shell.

    A shell's radius is the least at which the lattice's neighbours clear one another
    by ``gap`` and which clears the shell inside by ``gap`` plus both shells' largest
    pieces. Chords scale with the radius, so each pair's least radius is exact."""
    radii: List[float] = []
    previous = 0.0
    previous_largest = None
    for index, shell in enumerate(sizes):
        n = len(shell)
        unit = fibonacci_sphere(n, 1.0, index * GOLDEN_ANGLE)
        largest = max(shell, default=0.0)
        least = largest + gap
        if previous_largest is not None:
            least = max(least, previous + previous_largest + largest + gap)
        for i in range(n):
            for j in range(i + 1, n):
                chord = _distance(unit[i], unit[j])
                if chord > 0:
                    least = max(least, (shell[i] + shell[j] + gap) / chord)
        radii.append(least)
        previous, previous_largest = least, largest
    return radii


def lay_out(
    shell_of: Mapping[str, int], size_of: Mapping[str, float], gap: float = GAP
) -> Dict[str, Placement]:
    """A placement for each name of ``shell_of``, a shell being any integer rank.

    ``size_of`` is each name's bounding-sphere radius. Shells are taken in rank order,
    their pieces by name, so the same input gives the same layout, and a shell's
    pieces and radius depend on the shells inside it and on its own pieces, never on
    one outside: a piece added to the outermost shell moves nothing inside it."""
    ranks = sorted(set(shell_of.values()))
    members = [sorted(n for n, s in shell_of.items() if s == rank) for rank in ranks]
    sizes = [[size_of[n] for n in names] for names in members]
    radii = shell_radii(sizes, gap)
    placed: Dict[str, Placement] = {}
    for index, (rank, names) in enumerate(zip(ranks, members, strict=True)):
        points = fibonacci_sphere(len(names), radii[index], index * GOLDEN_ANGLE)
        for name, point in zip(names, points, strict=True):
            placed[name] = Placement(rank, radii[index], point, outward_turn(point))
    return placed
