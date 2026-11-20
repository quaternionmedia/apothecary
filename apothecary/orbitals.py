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
  points, a cluster in one piece of the shell; a piece built into one on an outer shell
  takes the point of its
  cluster nearest under that one, and its cluster gathers under the pieces its members
  are built into. The shells are seated from the outside in, so a piece's place
  follows the pieces outside it that it is built into and nothing else outside it.
- A piece's **turn** stands its up (+z) along the ray from the centre, in OpenSCAD's
  ``rotate([rx, ry, rz])`` order and degrees.
"""

from __future__ import annotations

import math
from typing import (
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    NamedTuple,
    Optional,
    Sequence,
    Set,
    Tuple,
)

Point = Tuple[float, float, float]

# Clear space kept between two neighbouring pieces' bounding spheres, and between
# a shell's and the next one's (mm).
GAP = 20.0

# How many nearest points a point of a shell's lattice is joined to, where it is among
# theirs too: the neighbours a point of the lattice has about it.
NEIGHBOURS = 6

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


def lattice_neighbours(lattice: Sequence[Point], count: int = NEIGHBOURS) -> List[List[int]]:
    """For each point of ``lattice``, the points it is joined to, by index: each of its
    ``count`` nearest that has it among its own ``count`` nearest (of equally near, the
    lower index first). The joins go both ways, so points in one piece on this graph are
    in one piece on the graph of each point's nearest whichever of them it is walked
    from; and a Fibonacci lattice is one piece on it (tests/test_orbitals.py)."""
    nearest = [
        set(
            sorted(
                (j for j in range(len(lattice)) if j != i),
                key=lambda j: (_distance(lattice[i], lattice[j]), j),
            )[:count]
        )
        for i in range(len(lattice))
    ]
    return [sorted(j for j in nearest[i] if i in nearest[j]) for i in range(len(lattice))]


def _piece(start: int, free: Set[int], joined: Sequence[Sequence[int]]) -> Set[int]:
    """The points of ``free`` that ``start`` reaches through points of ``free``."""
    piece, stack = {start}, [start]
    while stack:
        for j in joined[stack.pop()]:
            if j in free and j not in piece:
                piece.add(j)
                stack.append(j)
    return piece


def _pieces(free: Set[int], joined: Sequence[Sequence[int]]) -> List[Set[int]]:
    """``free`` in its pieces, the one with the lowest index first."""
    rest, pieces = set(free), []
    while rest:
        piece = _piece(min(rest), rest, joined)
        pieces.append(piece)
        rest -= piece
    return pieces


def _cut_off(point: int, free: Set[int], joined: Sequence[Sequence[int]]) -> Set[int]:
    """What taking ``point`` cuts off from the piece of ``free`` it is in: every piece of
    the rest of that piece but the largest (of equals, the one with the lowest index)."""
    pieces = _pieces(_piece(point, free, joined) - {point}, joined)
    if len(pieces) < 2:
        return set()
    kept = max(pieces, key=lambda p: (len(p), -min(p)))
    return set().union(*(p for p in pieces if p is not kept))


def _grow(
    seed: int,
    size: int,
    free: Set[int],
    joined: Sequence[Sequence[int]],
    rank: Callable[[int], tuple],
    keep_free_whole: bool,
) -> Optional[List[int]]:
    """``size`` points of ``free`` that are one piece, from ``seed``: each next point the
    first by ``rank`` of those joined to a point already taken. With ``keep_free_whole``,
    a point that would cut free points off the rest is taken only while there is room
    to take them too, and they are taken before anything else, so what is left free is
    one piece; None where no way on keeps to that. Without it, None only where the
    piece of ``free`` the seed is in is smaller than ``size``."""
    free = set(free)
    owed = _cut_off(seed, free, joined)
    if keep_free_whole and len(owed) > size - 1:
        return None
    region = [seed]
    free.discard(seed)
    while len(region) < size:
        room = size - len(region) - 1
        within = owed or free
        frontier = {j for i in region for j in joined[i] if j in within}
        if not frontier:
            return None
        fits = [j for j in frontier if j in owed or len(_cut_off(j, free, joined)) <= room]
        if not fits:
            if keep_free_whole:
                return None
            fits = list(frontier)
        point = min(fits, key=rank)
        if point not in owed:
            owed |= _cut_off(point, free, joined)
        owed.discard(point)
        region.append(point)
        free.discard(point)
    return region


def seat(
    names: Iterable[str],
    lattice: Sequence[Point],
    category_of: Mapping[str, Optional[str]],
    toward: Mapping[str, Point],
) -> Dict[str, int]:
    """Which point of ``lattice`` (unit directions) each of ``names`` takes on one shell.

    The names of one category (``category_of``; those with none are one category) take
    a region of the lattice that is one piece on its graph of neighbours
    (``lattice_neighbours``), grown from a seed a point at a time, each next point
    joined to one already taken and the first of those by nearness to the region's
    **centre**:

    - a category whose members ``toward`` gives a direction (the piece each is built
      into, on a shell outside) is centred on the middle of every such pull, and its
      seed is the free point nearest that centre;
    - a category nothing pulls is seeded at the free point most hemmed in by points
      already held (the largest share of its neighbours held), and centred there, so
      the regions fill the shell from those already laid and what is left free is not
      worn to a ring about each of them (the first on a shell nothing pulls starts at
      the lattice's first point);
    - a region takes no point that would cut free points off from the rest unless it
      has room to take those too, and then takes them first, so what is left free is
      one piece and every category after it has room for a region in one piece; where
      no seed allows that, the first seed by the same order grows one anyway, and where
      no piece of what is free holds the category it takes the free points nearest its
      centre.

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

    def nearer(point: Point) -> Callable[[int], tuple]:
        return lambda i: (_distance(lattice[i], point), i)

    joined = lattice_neighbours(lattice)
    free = set(range(len(lattice)))
    taken: Dict[str, int] = {}
    for category in order:
        members = groups[category]
        size = len(members)
        roomy = sorted(i for piece in _pieces(free, joined) if len(piece) >= size for i in piece)
        pulls = [toward[m] for m in pulled(members)]
        # Each seed a region may grow from, with the centre it grows nearest to.
        if pulls:
            centre = _direction([sum(p[i] for p in pulls) for i in range(3)]) or pulls[0]
            starts = [(seed, centre) for seed in sorted(roomy, key=nearer(centre))]
        else:
            hemmed = {
                i: sum(j not in free for j in joined[i]) / max(len(joined[i]), 1) for i in roomy
            }
            starts = [
                (seed, lattice[seed]) for seed in sorted(roomy, key=lambda i: (-hemmed[i], i))
            ]
        region = None
        for seed, middle in starts:
            region = _grow(seed, size, free, joined, nearer(middle), True)
            if region is not None:
                break
        else:
            if starts:
                seed, middle = starts[0]
                region = _grow(seed, size, free, joined, nearer(middle), False)
        if region is None:
            middle = centre if pulls else lattice[min(free)]
            region = sorted(free, key=nearer(middle))[:size]
        free -= set(region)

        left = list(region)
        for member in pulled(members):
            point = min(left, key=lambda i: (_distance(lattice[i], toward[member]), i))
            taken[member] = point
            left.remove(point)
        left.sort(key=nearer(middle))
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
