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
- **Which** point is its (``seat``): the pieces of one category take neighbouring
  points, a cluster; a piece built into one on an outer shell takes the point of its
  cluster nearest under that one, and its cluster gathers under the pieces its members
  are built into. The shells are seated from the outside in, so a piece's place
  follows the pieces outside it that it is built into and nothing else outside it.
- A piece's **turn** stands its up (+z) along the ray from the centre, in OpenSCAD's
  ``rotate([rx, ry, rz])`` order and degrees.
"""

from __future__ import annotations

import math
from typing import Dict, Iterable, List, Mapping, NamedTuple, Optional, Sequence, Set, Tuple

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


def _direction(vector: Sequence[float]) -> Optional[Point]:
    length = math.sqrt(sum(c * c for c in vector))
    if length == 0.0:
        return None
    return (vector[0] / length, vector[1] / length, vector[2] / length)


def least_cost_assignment(cost: Sequence[Sequence[float]]) -> List[int]:
    """For a square matrix, the column each row takes, every column once, at the least
    total cost: the Hungarian method, in its shortest-augmenting-path form. The rows
    and columns are walked in order, so the same matrix gives the same answer."""
    n = len(cost)
    infinity = math.inf
    u = [0.0] * (n + 1)
    v = [0.0] * (n + 1)
    row_at = [0] * (n + 1)  # row_at[j]: the row column j holds, counted from 1; 0 none
    way = [0] * (n + 1)
    for row in range(1, n + 1):
        row_at[0] = row
        column = 0
        least = [infinity] * (n + 1)
        used = [False] * (n + 1)
        while True:
            used[column] = True
            here, delta, nxt = row_at[column], infinity, 0
            for j in range(1, n + 1):
                if used[j]:
                    continue
                reduced = cost[here - 1][j - 1] - u[here] - v[j]
                if reduced < least[j]:
                    least[j], way[j] = reduced, column
                if least[j] < delta:
                    delta, nxt = least[j], j
            for j in range(n + 1):
                if used[j]:
                    u[row_at[j]] += delta
                    v[j] -= delta
                else:
                    least[j] -= delta
            column = nxt
            if row_at[column] == 0:
                break
        while column:
            before = way[column]
            row_at[column] = row_at[before]
            column = before
    taken = [0] * n
    for j in range(1, n + 1):
        taken[row_at[j] - 1] = j - 1
    return taken


def seat(
    names: Iterable[str],
    lattice: Sequence[Point],
    category_of: Mapping[str, Optional[str]],
    toward: Mapping[str, Point],
) -> Dict[str, int]:
    """Which point of ``lattice`` (unit directions) each of ``names`` takes on one shell.

    The names of one category (``category_of``; one with none is a category of its own)
    take neighbouring points, a region about the category's **centre**:

    - a member that ``toward`` gives a direction (the piece it is built into, on a
      shell outside) pulls its category's centre to the middle of every such pull;
    - a category nothing pulls is centred on the lattice point farthest from every
      centre already chosen, so clusters spread over the sphere (the first on a shell
      nothing pulls starts at the lattice's first point);
    - the points are shared out so that each category holds as many as it has members
      and the points stand, all told, as near their categories' centres as they can
      (the least sum of squared chords: ``least_cost_assignment``), which makes each
      region one piece of the sphere.

    Within its region a pulled member takes the point nearest its pull, and the others
    take what is left, nearest the centre first. Categories go pulled first, then the
    larger first, then by name; members by name; a tie between points goes to the
    lower index. The same input gives the same seats, whatever order it came in."""
    groups: Dict[Optional[str], List[str]] = {}
    for name in sorted(set(names)):
        groups.setdefault(category_of.get(name), []).append(name)

    def pulled(members: Sequence[str]) -> List[str]:
        return [m for m in members if m in toward]

    order = sorted(
        groups,
        key=lambda c: (not pulled(groups[c]), -len(groups[c]), c is None, c or ""),
    )
    centres: List[Point] = []
    for category in order:
        pulls = [toward[m] for m in pulled(groups[category])]
        if pulls:
            centres.append(_direction([sum(p[i] for p in pulls) for i in range(3)]) or pulls[0])
        elif centres:
            far = max(
                range(len(lattice)),
                key=lambda i: (min(_distance(lattice[i], c) for c in centres), -i),
            )
            centres.append(lattice[far])
        else:
            centres.append(lattice[0])

    # A slot for each member: category k's, as many as it has members.
    slots = [k for k, category in enumerate(order) for _ in groups[category]]
    cost = [[_distance(point, centres[k]) ** 2 for k in slots] for point in lattice]
    held: List[List[int]] = [[] for _ in order]
    for i, slot in enumerate(least_cost_assignment(cost)):
        held[slots[slot]].append(i)

    taken: Dict[str, int] = {}
    for k, category in enumerate(order):
        members, left = groups[category], list(held[k])
        for member in pulled(members):
            point = min(left, key=lambda i: (_distance(lattice[i], toward[member]), i))
            taken[member] = point
            left.remove(point)
        left.sort(key=lambda i: (_distance(lattice[i], centres[k]), i))
        rest = [m for m in members if m not in toward]
        for member, point in zip(rest, left, strict=True):
            taken[member] = point
    return taken


def lay_out(
    shell_of: Mapping[str, int],
    size_of: Mapping[str, float],
    gap: float = GAP,
    category_of: Optional[Mapping[str, Optional[str]]] = None,
    parent_of: Optional[Mapping[str, str]] = None,
) -> Dict[str, Placement]:
    """A placement for each name of ``shell_of``, a shell being any integer rank.

    ``size_of`` is each name's bounding-sphere radius; ``category_of`` each name's
    category, whose pieces sit together on their shell; ``parent_of`` the name each
    stands under, a piece on a shell outside it that it is built into (a name on its own
    shell or inside it is not one). The points are seated from the outermost shell in
    (``seat``), each shell's pieces by name, so the same input gives the same layout;
    the radii are then found from the inside out (``shell_radii``), so a shell's radius
    depends on the shells inside it and on its own pieces, never on one outside. A piece
    added to the outermost shell that no piece inside is built into moves nothing
    inside it."""
    category_of = category_of or {}
    parent_of = parent_of or {}
    ranks = sorted(set(shell_of.values()))
    phase = {rank: index * GOLDEN_ANGLE for index, rank in enumerate(ranks)}
    direction: Dict[str, Point] = {}
    laid: Dict[int, List[str]] = {}
    for rank in reversed(ranks):
        names = sorted(n for n, s in shell_of.items() if s == rank)
        lattice = fibonacci_sphere(len(names), 1.0, phase[rank])
        # Only the shells outside this one are seated yet: a parent on this shell or
        # inside it has no direction to pull toward.
        toward = {
            name: direction[parent_of[name]] for name in names if parent_of.get(name) in direction
        }
        seated = seat(names, lattice, category_of, toward)
        at = {index: name for name, index in seated.items()}
        laid[rank] = [at[index] for index in range(len(names))]
        for name, index in seated.items():
            direction[name] = lattice[index]
    radii = shell_radii([[size_of[n] for n in laid[rank]] for rank in ranks], gap)
    placed: Dict[str, Placement] = {}
    for rank, radius in zip(ranks, radii, strict=True):
        for name in laid[rank]:
            point = tuple(radius * c for c in direction[name])
            placed[name] = Placement(rank, radius, point, outward_turn(point))
    return placed
