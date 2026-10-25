"""Comparing a geometry kernel with the reference, by numbers.

The question (``docs/plans/rust-geometry-kernels-2026-10-09.md``) is whether a
kernel other than OpenSCAD could render apothecary's scenes. This module is
the harness that answers it, and it holds no kernel: a corpus of scenes, the
reference (OpenSCAD with the Manifold backend), the measures of a mesh and of
two meshes against each other, and the protocol a kernel is wired in through.
Pure Python and no dependency, on ``apothecary.meshes``.

Nothing here states what the reference measures; ``apothecary kernel-reference``
prints it, and ``tests/test_kernel_comparison.py`` compares a kernel with it.
"""

from __future__ import annotations

import json
import math
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    runtime_checkable,
)

from . import meshes
from .booleans import Difference, Hull, Intersection, Union
from .meshes import Triangle
from .models.vectors import Vector3D
from .objects import SceneObject
from .primitives import Cube, Cylinder, Import, Sphere
from .scene import Scene
from .transforms import Rotate, Scale, Translate

Point = Tuple[float, float, float]

# ---------------------------------------------------------------- the corpus


@dataclass(frozen=True)
class Case:
    """One scene in the corpus. ``build`` takes a scratch folder because an
    import needs a file to name; everything else ignores it."""

    name: str
    group: str
    build: Callable[[Path], Scene]
    # What this case is there to catch, in a line.
    why: str = ""
    # True where the scene leaves ``fn`` to OpenSCAD's own rule (``$fa``/``$fs``),
    # so a kernel that does not copy that rule differs by tessellation, not by
    # a fault.
    openscad_facets: bool = False

    def scene(self, workdir: Path) -> Scene:
        return self.build(Path(workdir))


def v(x: float, y: float, z: float) -> Vector3D:
    return Vector3D(x=x, y=y, z=z)


def _scene(name: str, *objects: SceneObject) -> Callable[[Path], Scene]:
    return lambda _workdir: Scene(name=name, objects=list(objects))


def _box() -> List[Triangle]:
    """A closed 5 x 3 x 2 box, outward-wound, with its corner at the origin."""
    x, y, z = 5.0, 3.0, 2.0
    c = [(i * x, j * y, k * z) for i in (0, 1) for j in (0, 1) for k in (0, 1)]

    def quad(a: int, b: int, cc: int, d: int) -> List[Triangle]:
        return [(c[a], c[b], c[cc]), (c[a], c[cc], c[d])]

    # indices are 4*i + 2*j + k
    return (
        quad(0, 1, 3, 2)  # x = 0, facing -x
        + quad(4, 6, 7, 5)  # x = 5
        + quad(0, 4, 5, 1)  # y = 0
        + quad(2, 3, 7, 6)  # y = 3
        + quad(0, 2, 6, 4)  # z = 0
        + quad(1, 5, 7, 3)  # z = 2
    )


def _octahedron() -> List[Triangle]:
    """A closed octahedron of radius 4, outward-wound."""
    r = 4.0
    out: List[Triangle] = []
    for sx in (1, -1):
        for sy in (1, -1):
            for sz in (1, -1):
                a, b, c = (sx * r, 0.0, 0.0), (0.0, sy * r, 0.0), (0.0, 0.0, sz * r)
                out.append((a, b, c) if sx * sy * sz > 0 else (a, c, b))
    return out


def _import_case(name: str, mesh: Callable[[], List[Triangle]], wrap=None) -> Callable[[Path], Scene]:
    def build(workdir: Path) -> Scene:
        path = Path(workdir) / f"{name}.stl"
        meshes.write_stl(mesh(), path)
        node = Import(file=str(path.resolve()))
        return Scene(name=name, objects=[wrap(node) if wrap else node])

    return build


def _import_moved(workdir: Path) -> Scene:
    path = Path(workdir) / "import_moved.stl"
    meshes.write_stl(_box(), path)
    node = Import(file=str(path.resolve()), scale=2.0, rotate=v(90, 0, 30), translate=v(1, 2, 3))
    return Scene(name="import_moved", objects=[node])


def _rounded_box() -> SceneObject:
    """Four corner cylinders hulled: an enclosure shell's shape."""
    corners = [(1, 1), (9, 1), (1, 7), (9, 7)]
    return Hull(
        children=[
            Translate(v=v(x, y, 0), children=[Cylinder(h=4, r=1, fn=24)]) for x, y in corners
        ]
    )


def _library_house(_workdir: Path) -> Scene:
    from .example import create_example_scene

    return create_example_scene()


def _library_snowplow(_workdir: Path) -> Scene:
    from .projects.parts.rc_snowplow import DEFAULT, Params

    geometry = DEFAULT.geometry(Params().model_dump())
    return Scene(name="snowplow", objects=[geometry])


CASES: Tuple[Case, ...] = (
    # Each primitive alone.
    Case("cube", "primitive", _scene("cube", Cube(size=10)), "the corner at the origin"),
    Case(
        "cube_centered",
        "primitive",
        _scene("cube_centered", Cube(size=v(10, 6, 4), center=True)),
        "a vector size, centred",
    ),
    Case(
        "sphere",
        "primitive",
        _scene("sphere", Sphere(r=5, fn=32)),
        "OpenSCAD's ring layout, not a geodesic sphere",
    ),
    Case(
        "sphere_default_facets",
        "primitive",
        _scene("sphere_default_facets", Sphere(r=5)),
        "fn left to OpenSCAD's $fa/$fs rule",
        openscad_facets=True,
    ),
    Case("cylinder", "primitive", _scene("cylinder", Cylinder(h=10, r=3, fn=32)), "r sets both"),
    Case(
        "cone",
        "primitive",
        _scene("cone", Cylinder(h=10, r1=4, r2=1, fn=32, center=True)),
        "two radii, centred",
    ),
    Case(
        "cone_point",
        "primitive",
        _scene("cone_point", Cylinder(h=8, r1=4, r2=0, fn=24)),
        "a radius of zero: an apex, not a cap",
    ),
    # Each boolean.
    Case(
        "union",
        "boolean",
        _scene(
            "union",
            Union(
                children=[
                    Cube(size=10),
                    Translate(v=v(5, 5, 5), children=[Cube(size=10)]),
                ]
            ),
        ),
        "two cubes that overlap",
    ),
    Case(
        "difference",
        "boolean",
        _scene(
            "difference",
            Difference(
                children=[
                    Cube(size=v(20, 20, 10)),
                    Translate(v=v(10, 10, -1), children=[Cylinder(h=12, r=4, fn=32)]),
                ]
            ),
        ),
        "a through hole",
    ),
    Case(
        "intersection",
        "boolean",
        _scene(
            "intersection",
            Intersection(
                children=[
                    Sphere(r=6, fn=32),
                    Cube(size=v(8, 8, 8), center=True),
                ]
            ),
        ),
        "a cube's corners cut by a sphere",
    ),
    Case(
        "union_touching",
        "boolean",
        _scene(
            "union_touching",
            Union(
                children=[
                    Cube(size=10),
                    Translate(v=v(10, 0, 0), children=[Cube(size=10)]),
                ]
            ),
        ),
        "two cubes sharing a whole face: coplanar, touching",
    ),
    Case(
        "difference_flush",
        "boolean",
        _scene(
            "difference_flush",
            Difference(
                children=[
                    Cube(size=10),
                    Translate(v=v(2, 2, 5), children=[Cube(size=v(6, 6, 5))]),
                ]
            ),
        ),
        "a cutter whose top is flush with the part's top: coincident faces",
    ),
    # Nested.
    Case(
        "nested",
        "nested",
        _scene(
            "nested",
            Difference(
                children=[
                    Union(
                        children=[
                            Cube(size=v(20, 20, 6)),
                            Translate(v=v(10, 10, 6), children=[Sphere(r=6, fn=24)]),
                        ]
                    ),
                    Translate(
                        v=v(10, 10, -1),
                        children=[Cylinder(h=20, r=2.5, fn=24)],
                    ),
                    Translate(v=v(-1, 8, 2), children=[Cube(size=v(30, 4, 2))]),
                ]
            ),
        ),
        "a union cut by two things, one of them across it",
    ),
    Case(
        "nested_intersection",
        "nested",
        _scene(
            "nested_intersection",
            Intersection(
                children=[
                    Union(children=[Cube(size=10), Translate(v=v(6, 6, 6), children=[Sphere(r=5, fn=24)])]),
                    Difference(
                        children=[
                            Cube(size=v(20, 20, 20), center=True),
                            Cylinder(h=40, r=2, fn=24, center=True),
                        ]
                    ),
                ]
            ),
        ),
        "an intersection of a union and a difference",
    ),
    # Hull.
    Case("hull_rounded_box", "hull", _scene("hull_rounded_box", _rounded_box()), "four cylinders"),
    Case(
        "hull_spheres",
        "hull",
        _scene(
            "hull_spheres",
            Hull(
                children=[
                    Sphere(r=3, fn=24),
                    Translate(v=v(10, 0, 4), children=[Sphere(r=2, fn=24)]),
                ]
            ),
        ),
        "a capsule-like solid from two spheres",
    ),
    Case(
        "hull_then_difference",
        "hull",
        _scene(
            "hull_then_difference",
            Difference(
                children=[
                    _rounded_box(),
                    Translate(v=v(2, 2, 1), children=[Cube(size=v(6, 4, 4))]),
                ]
            ),
        ),
        "a hulled shell hollowed",
    ),
    # Transforms.
    Case(
        "translate",
        "transform",
        _scene("translate", Translate(v=v(3, -4, 5), children=[Cube(size=2)])),
        "",
    ),
    Case(
        "rotate_euler",
        "transform",
        _scene(
            "rotate_euler",
            Rotate(a=v(30, 40, 50), children=[Cube(size=v(4, 3, 2))]),
        ),
        "OpenSCAD turns about X, then Y, then Z",
    ),
    Case(
        "rotate_axis_angle",
        "transform",
        _scene(
            "rotate_axis_angle",
            Rotate(a=35, v=v(1, 1, 0), children=[Cube(size=v(4, 3, 2))]),
        ),
        "an angle about an axis",
    ),
    Case(
        "scale_nonuniform",
        "transform",
        _scene(
            "scale_nonuniform",
            Scale(v=v(2, 1, 0.5), children=[Sphere(r=3, fn=24)]),
        ),
        "an ellipsoid from a sphere",
    ),
    # Import.
    Case(
        "import_box",
        "import",
        _import_case("import_box", _box),
        "a closed STL, on its own",
    ),
    Case(
        "import_moved",
        "import",
        _import_moved,
        "the import's scale, rotate, translate, in that order",
    ),
    Case(
        "import_then_difference",
        "import",
        _import_case(
            "import_then_difference",
            _octahedron,
            wrap=lambda node: Difference(
                children=[node, Translate(v=v(-1, -1, 0), children=[Cube(size=v(2, 2, 6))])]
            ),
        ),
        "an imported mesh in a boolean",
    ),
    # Real parts, where a scene form exists.
    Case("library_house", "library", _library_house, "the example scene: a cone roof, a door cut"),
    Case(
        "library_snowplow",
        "library",
        _library_snowplow,
        "rc_snowplow's Python geometry: a rotated blade, a drilled mount",
    ),
)

CASE_NAMES: Tuple[str, ...] = tuple(case.name for case in CASES)


def case_named(name: str) -> Case:
    for case in CASES:
        if case.name == name:
            return case
    raise KeyError(f"no case {name!r}; the corpus has {', '.join(CASE_NAMES)}")


# --------------------------------------------------------------- the measures


@dataclass(frozen=True)
class Measures:
    """What is measured of one mesh."""

    triangles: int
    volume: float
    area: float
    bbox_min: Point
    bbox_max: Point
    watertight: bool
    manifold: bool
    degenerate: int = 0

    @property
    def size(self) -> Point:
        return tuple(high - low for low, high in zip(self.bbox_min, self.bbox_max, strict=True))  # type: ignore[return-value]

    @property
    def diagonal(self) -> float:
        return math.sqrt(sum(d * d for d in self.size))


def signed_volume(triangles: Iterable[Triangle]) -> float:
    """The volume a closed, outward-wound mesh encloses (the divergence theorem).
    Negative for an inside-out mesh, which is how a flipped one shows."""
    total = 0.0
    for a, b, c in triangles:
        total += (
            a[0] * (b[1] * c[2] - b[2] * c[1])
            - a[1] * (b[0] * c[2] - b[2] * c[0])
            + a[2] * (b[0] * c[1] - b[1] * c[0])
        )
    return total / 6.0


def surface_area(triangles: Iterable[Triangle]) -> float:
    return sum(_triangle_area(t) for t in triangles)


def _triangle_area(t: Triangle) -> float:
    a, b, c = t
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    return 0.5 * math.sqrt(nx * nx + ny * ny + nz * nz)


def edge_report(triangles: Sequence[Triangle], digits: int = 5) -> Tuple[bool, bool, int]:
    """(watertight, manifold, degenerate) of a triangle soup.

    Corners are welded by rounding to ``digits`` decimals (an STL repeats every
    vertex once per triangle). **Watertight**: every edge belongs to exactly
    two triangles. **Manifold**, here: watertight and consistently wound, so
    every edge is used once in each direction, which is what a slicer needs of
    an STL. (Vertex-manifoldness, two cones meeting at a point, is not tested.)
    A triangle with two corners welded together is degenerate: counted, and left
    out of the edges.
    """
    ids: Dict[Point, int] = {}

    def vid(p: Point) -> int:
        key = (round(p[0], digits) + 0.0, round(p[1], digits) + 0.0, round(p[2], digits) + 0.0)
        return ids.setdefault(key, len(ids))

    directed: Dict[Tuple[int, int], int] = {}
    degenerate = 0
    for a, b, c in triangles:
        i, j, k = vid(a), vid(b), vid(c)
        if i == j or j == k or i == k:
            degenerate += 1
            continue
        for edge in ((i, j), (j, k), (k, i)):
            directed[edge] = directed.get(edge, 0) + 1
    if not directed:
        return False, False, degenerate
    undirected: Dict[Tuple[int, int], int] = {}
    for (i, j), n in directed.items():
        key = (i, j) if i < j else (j, i)
        undirected[key] = undirected.get(key, 0) + n
    watertight = all(n == 2 for n in undirected.values())
    manifold = watertight and all(n == 1 for n in directed.values())
    return watertight, manifold, degenerate


def measure(triangles: Sequence[Triangle]) -> Measures:
    watertight, manifold, degenerate = edge_report(triangles)
    lo, hi = meshes.bounds(triangles)
    return Measures(
        triangles=len(triangles),
        volume=signed_volume(triangles),
        area=surface_area(triangles),
        bbox_min=lo,
        bbox_max=hi,
        watertight=watertight,
        manifold=manifold,
        degenerate=degenerate,
    )


def relative_error(value: float, reference: float) -> float:
    """``|value - reference| / |reference|``; the absolute difference when the
    reference is zero."""
    if reference == 0:
        return abs(value)
    return abs(value - reference) / abs(reference)


def bbox_error(a: Measures, b: Measures) -> float:
    """The largest distance any face of one box is from the same face of the other."""
    return max(
        max(abs(p - q) for p, q in zip(a.bbox_min, b.bbox_min, strict=True)),
        max(abs(p - q) for p, q in zip(a.bbox_max, b.bbox_max, strict=True)),
    )


# ---- the distance between two surfaces


def closest_distance_to_triangle(p: Point, tri: Triangle) -> float:
    """The distance from ``p`` to the nearest point of the triangle (Ericson,
    *Real-Time Collision Detection*, 5.1.5)."""
    a, b, c = tri
    ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    ap = (p[0] - a[0], p[1] - a[1], p[2] - a[2])

    def dot(u, w):
        return u[0] * w[0] + u[1] * w[1] + u[2] * w[2]

    def at(origin, u, s, w=None, t=0.0):
        x = origin[0] + u[0] * s + (w[0] * t if w else 0.0)
        y = origin[1] + u[1] * s + (w[1] * t if w else 0.0)
        z = origin[2] + u[2] * s + (w[2] * t if w else 0.0)
        return (x, y, z)

    def dist(q):
        return math.sqrt((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2)

    d1, d2 = dot(ab, ap), dot(ac, ap)
    if d1 <= 0 and d2 <= 0:
        return dist(a)
    bp = (p[0] - b[0], p[1] - b[1], p[2] - b[2])
    d3, d4 = dot(ab, bp), dot(ac, bp)
    if d3 >= 0 and d4 <= d3:
        return dist(b)
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        return dist(at(a, ab, d1 / (d1 - d3)))
    cp = (p[0] - c[0], p[1] - c[1], p[2] - c[2])
    d5, d6 = dot(ab, cp), dot(ac, cp)
    if d6 >= 0 and d5 <= d6:
        return dist(c)
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        return dist(at(a, ac, d2 / (d2 - d6)))
    va = d3 * d6 - d5 * d4
    if va <= 0 and (d4 - d3) >= 0 and (d5 - d6) >= 0:
        bc = (c[0] - b[0], c[1] - b[1], c[2] - b[2])
        return dist(at(b, bc, (d4 - d3) / ((d4 - d3) + (d5 - d6))))
    denom = 1.0 / (va + vb + vc) if (va + vb + vc) else 0.0
    return dist(at(a, ab, vb * denom, ac, vc * denom))


class SurfaceIndex:
    """Triangles in a uniform grid, to find the nearest one to a point without
    looking at them all."""

    def __init__(self, triangles: Sequence[Triangle]):
        self.triangles = list(triangles)
        lo, hi = meshes.bounds(self.triangles)
        self.lo = lo
        extent = max(max(high - low for low, high in zip(lo, hi, strict=True)), 1e-9)
        per_axis = max(1, min(64, round(len(self.triangles) ** (1 / 3))))
        self.cell = extent / per_axis
        self.n = per_axis + 1
        self.cells: Dict[Tuple[int, int, int], List[int]] = {}
        for index, tri in enumerate(self.triangles):
            tlo = [min(p[axis] for p in tri) for axis in range(3)]
            thi = [max(p[axis] for p in tri) for axis in range(3)]
            ranges = [
                range(self._cell(tlo[axis], axis), self._cell(thi[axis], axis) + 1)
                for axis in range(3)
            ]
            for i in ranges[0]:
                for j in ranges[1]:
                    for k in ranges[2]:
                        self.cells.setdefault((i, j, k), []).append(index)

    def _cell(self, value: float, axis: int) -> int:
        return int((value - self.lo[axis]) // self.cell)

    def distance(self, p: Point) -> float:
        """From ``p`` to the nearest triangle, searched in growing shells of
        cells and stopped once no unsearched cell can hold a nearer one."""
        centre = [self._cell(p[axis], axis) for axis in range(3)]
        best = math.inf
        seen: set = set()
        # Far enough to cover the grid from wherever p is.
        reach = max(self.n, *(abs(c) for c in centre)) + max(self.n, 1)
        for ring in range(reach + 1):
            if best <= (ring - 1) * self.cell:
                break
            for i in range(centre[0] - ring, centre[0] + ring + 1):
                for j in range(centre[1] - ring, centre[1] + ring + 1):
                    for k in range(centre[2] - ring, centre[2] + ring + 1):
                        if max(abs(i - centre[0]), abs(j - centre[1]), abs(k - centre[2])) != ring:
                            continue
                        for index in self.cells.get((i, j, k), ()):
                            if index in seen:
                                continue
                            seen.add(index)
                            best = min(best, closest_distance_to_triangle(p, self.triangles[index]))
        return best


def sample_surface(triangles: Sequence[Triangle], count: int, seed: int = 0) -> List[Point]:
    """``count`` points on the surface, area-weighted, the same every run."""
    rng = random.Random(seed)
    areas = [_triangle_area(t) for t in triangles]
    chosen = rng.choices(range(len(triangles)), weights=areas, k=count)
    points: List[Point] = []
    for index in chosen:
        a, b, c = triangles[index]
        r1, r2 = math.sqrt(rng.random()), rng.random()
        wa, wb, wc = 1 - r1, r1 * (1 - r2), r1 * r2
        points.append(tuple(wa * a[i] + wb * b[i] + wc * c[i] for i in range(3)))  # type: ignore[arg-type]
    return points


@dataclass(frozen=True)
class SurfaceDistance:
    """Both ways, since one way hides a missing piece: ``mean`` is the average
    of the two directions' means, ``worst`` the larger of their maxima (the
    sampled Hausdorff distance, a lower bound on the true one)."""

    mean: float
    worst: float


def surface_distance(
    a: Sequence[Triangle], b: Sequence[Triangle], samples: int = 1500, seed: int = 0
) -> SurfaceDistance:
    if not a or not b:
        return SurfaceDistance(math.inf, math.inf)
    index_b = SurfaceIndex(b)
    from_a = [index_b.distance(p) for p in sample_surface(a, samples, seed)]
    index_a = SurfaceIndex(a)
    from_b = [index_a.distance(p) for p in sample_surface(b, samples, seed + 1)]
    return SurfaceDistance(
        mean=(sum(from_a) / len(from_a) + sum(from_b) / len(from_b)) / 2,
        worst=max(max(from_a), max(from_b)),
    )


@dataclass(frozen=True)
class Comparison:
    """A kernel's mesh against the reference's."""

    volume_error: float
    area_error: float
    bbox_error: float
    distance: SurfaceDistance
    watertight: bool
    manifold: bool
    triangle_ratio: float
    seconds_ratio: Optional[float]


def compare(
    candidate: Sequence[Triangle],
    reference: Sequence[Triangle],
    candidate_seconds: Optional[float] = None,
    reference_seconds: Optional[float] = None,
    samples: int = 1500,
) -> Comparison:
    got, want = measure(candidate), measure(reference)
    ratio = (
        candidate_seconds / reference_seconds
        if candidate_seconds is not None and reference_seconds
        else None
    )
    return Comparison(
        volume_error=relative_error(got.volume, want.volume),
        area_error=relative_error(got.area, want.area),
        bbox_error=bbox_error(got, want),
        distance=surface_distance(candidate, reference, samples),
        watertight=got.watertight,
        manifold=got.manifold,
        triangle_ratio=got.triangles / want.triangles if want.triangles else math.inf,
        seconds_ratio=ratio,
    )


# What a kernel has to be within, to count as rendering the same part. These
# are where the first comparison starts, not findings: the first real run says
# which are too tight or too loose, and they change in the commit that records
# why. Lengths are relative to the reference's bounding-box diagonal.
TOLERANCES = {
    "volume_error": 1e-3,
    "area_error": 1e-2,
    "bbox_error": 1e-3,  # of the diagonal
    "mean_distance": 1e-3,  # of the diagonal
    "worst_distance": 1e-2,  # of the diagonal
}


def violations(comparison: Comparison, reference: Measures, tolerances=TOLERANCES) -> List[str]:
    """What is outside ``tolerances``, each as a sentence; empty when none is."""
    diag = reference.diagonal or 1.0
    found = []
    if comparison.volume_error > tolerances["volume_error"]:
        found.append(f"volume differs by {comparison.volume_error:.2e} (relative)")
    if comparison.area_error > tolerances["area_error"]:
        found.append(f"surface area differs by {comparison.area_error:.2e} (relative)")
    if comparison.bbox_error > tolerances["bbox_error"] * diag:
        found.append(f"bounding box is off by {comparison.bbox_error:.3g}")
    if comparison.distance.mean > tolerances["mean_distance"] * diag:
        found.append(f"mean surface distance is {comparison.distance.mean:.3g}")
    if comparison.distance.worst > tolerances["worst_distance"] * diag:
        found.append(f"worst surface distance is {comparison.distance.worst:.3g}")
    if not comparison.watertight:
        found.append("not watertight")
    elif not comparison.manifold:
        found.append("watertight but not consistently wound")
    return found


# -------------------------------------------------------------- the adapters


@runtime_checkable
class KernelAdapter(Protocol):
    """What a kernel is wired in through: one adapter, nothing else.

    ``render`` turns a scene into an STL at ``out`` and returns it. A Rust
    kernel is a command that reads the scene's JSON (``scene.model_dump_json()``,
    the format in ``docs/scene-json.md``) and writes the file, so its adapter is
    a ``subprocess`` call and a ``Path``. ``available`` says whether this
    machine can run it, and why not if it cannot; a test skips with that reason.
    """

    name: str

    def available(self) -> Tuple[bool, str]: ...

    def render(self, scene: Scene, out: Path) -> Path: ...


# Registered kernels, by name. Empty on purpose: wiring a kernel in is adding
# its adapter here (or having its module do so on import), and the comparison
# tests then run for it.
KERNELS: Dict[str, KernelAdapter] = {}


def register(adapter: KernelAdapter) -> KernelAdapter:
    KERNELS[adapter.name] = adapter
    return adapter


def timed(adapter: KernelAdapter, scene: Scene, out: Path) -> Tuple[List[Triangle], float]:
    """A kernel's triangles and the seconds its ``render`` took, wall clock."""
    start = time.monotonic()
    path = adapter.render(scene, out)
    seconds = time.monotonic() - start
    return meshes.read_stl(Path(path).read_bytes()), seconds


# ------------------------------------------------------------- the reference


class ReferenceUnavailable(RuntimeError):
    """No OpenSCAD with the Manifold backend here."""


def reference_openscad(explicit: Optional[str] = None) -> Path:
    """The OpenSCAD the reference runs on: one that has Manifold, since the
    reference is OpenSCAD with that backend. Raises ``ReferenceUnavailable``,
    saying what was found, when there is none (OpenSCAD 2021.01, the release
    most distributions package, has only CGAL)."""
    from .openscad_installer import MANIFOLD_SINCE
    from .projects.parts.stl_renderer import find_openscad, has_manifold, openscad_version

    if explicit:
        path = Path(explicit)
        if path.exists() and has_manifold(path):
            return path
        found = openscad_version(path) if path.exists() else None
        raise ReferenceUnavailable(f"{explicit} is not an OpenSCAD with Manifold ({found})")
    floor = ".".join(f"{n:02d}" if i else str(n) for i, n in enumerate(MANIFOLD_SINCE))
    path, why = find_openscad(floor)
    if path is None:
        raise ReferenceUnavailable(
            "the reference needs OpenSCAD with the Manifold backend "
            f"(a development snapshot from {floor}). {why}"
        )
    if not has_manifold(path):
        raise ReferenceUnavailable(f"{path} is new enough but does not report Manifold")
    return path


@dataclass(frozen=True)
class Reference:
    """The reference's mesh for a case and what it took to make."""

    case: Case
    triangles: List[Triangle]
    seconds: float


def render_reference(scene: Scene, out: Path, openscad: Path) -> Tuple[Path, float]:
    """The scene as SCAD, rendered by ``openscad`` with ``--backend=manifold``
    (``OpenSCADRenderer.render_stl`` passes it for a snapshot that has it).
    Returns the STL and OpenSCAD's own seconds, process start included."""
    from .projects.parts.stl_renderer import OpenSCADRenderer

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    scad = out.with_suffix(".scad")
    scad.write_text(scene.render(), encoding="utf-8")
    result = OpenSCADRenderer(str(openscad)).render_stl(scad, out, timeout=120.0)
    if not result.success:
        raise RuntimeError(f"{scene.name}: {result.error_message}\n{result.stderr or ''}")
    return out, result.render_time_seconds


def run_reference(cases: Sequence[Case], workdir: Path, openscad: Path) -> List[Reference]:
    refs = []
    for case in cases:
        scene = case.scene(workdir)
        stl, seconds = render_reference(scene, Path(workdir) / "reference" / f"{case.name}.stl", openscad)
        refs.append(Reference(case, meshes.read_stl(stl.read_bytes()), seconds))
    return refs


def reference_table(references: Sequence[Reference], as_json: bool = False) -> str:
    """The reference's numbers for the corpus, as a table (or JSON lines)."""
    rows = []
    for ref in references:
        m = measure(ref.triangles)
        rows.append((ref, m))
    if as_json:
        return "\n".join(
            json.dumps(
                {
                    "case": r.case.name,
                    "group": r.case.group,
                    "triangles": m.triangles,
                    "volume": m.volume,
                    "area": m.area,
                    "bbox_min": m.bbox_min,
                    "bbox_max": m.bbox_max,
                    "watertight": m.watertight,
                    "manifold": m.manifold,
                    "seconds": r.seconds,
                }
            )
            for r, m in rows
        )
    head = (
        f"{'case':<24}{'group':<11}{'tris':>7}{'volume':>12}{'area':>12}"
        f"{'bbox x':>9}{'y':>9}{'z':>9}  {'watertight':<11}{'manifold':<9}{'s':>7}"
    )
    lines = [head, "-" * len(head)]
    for r, m in rows:
        sx, sy, sz = m.size
        lines.append(
            f"{r.case.name:<24}{r.case.group:<11}{m.triangles:>7}{m.volume:>12.3f}{m.area:>12.3f}"
            f"{sx:>9.3f}{sy:>9.3f}{sz:>9.3f}  {'yes' if m.watertight else 'NO':<11}"
            f"{'yes' if m.manifold else 'NO':<9}{r.seconds:>7.2f}"
        )
    return "\n".join(lines) + "\n"
