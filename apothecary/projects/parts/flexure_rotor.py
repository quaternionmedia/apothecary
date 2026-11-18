"""Flexure rotor -- a rotor carried on leaves printed with its stator, in one piece.

The part is its SCAD, ``parts/flexure_rotor/flexure_rotor.scad``; this module mirrors its
outlines in the same degrees, for what Python has to know without OpenSCAD -- the
envelope, the pockets, the gaps, the stop and the leaves' bending -- and
``tests/test_flexure_rotor_part.py`` holds the two together through the SCAD's ``-D
echo_shapes=true``.

A hub with lobes stands inside a ring with posts, joined to it by leaves. The hub turns
about the axis by bending the leaves: the drawing turns it rigidly by ``swing`` and bends
each leaf as a cubic from the hub's rim to the ring, leaving each square to it -- the
shape of a beam built in at both ends, for a small turn. Each lobe has a post ``stop``
degrees round from it: turned that way, the gap between their flanks closes, and is
``post_r * sin(stop - swing)`` while the post's corner is nearer the lobe's flank than its
end, until they touch. That is the hub's stop; the other way, only the leaves stop it.

What is measured here is geometry (``apothecary.gap_geometry``): the gap between each lobe
and its post, the clearance between the hub and the ring's posts and between each leaf and
the lobes and posts it passes, at any swing; where the hub first touches; and the strain a
leaf's surface takes bent to a swing, ``thickness / 2`` times its sharpest curvature -- the
bending of a beam whose sections stay plane, its stretch along its length left out. How
stiff the leaves are, how fast the hub rings, and whether a leaf survives that strain
belong to the filament and the print, which this module does not know.

The motion (``motion``) is the swing, from ``-stop`` to the stop: the ring and its posts
stand still, the hub and its lobes turn rigidly, and each leaf is drawn at each sampled
swing from ``leaf_outline``, the model's own cubic, which is the drawing's shape and not
a simulation of the bending. What goes in the pockets is listed by ``bought``, a disc for
each, its material the owner's to choose.

Units: mm and degrees.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, List, Literal, Mapping, Optional, Sequence

from pydantic import BaseModel, Field, model_validator

from apothecary.fittings import WALL
from apothecary.gap_geometry import (
    GapProfile,
    Point,
    Pose,
    Travel,
    area,
    circle,
    clearance_in,
    follow,
    nearest,
    radial_gap,
    separation,
)
from apothecary.models import BoundingBox3D, Color, Vector3D
from apothecary.models.bought import INSERT_FIT, Bought
from apothecary.models.interfaces import InterfaceBase, Socket
from apothecary.motion import Bent, Gap, Insert, Mark, Motion, Piece

from .base import BasePart
from .skeleton import ROOT

MM = {"unit": "mm"}
DEG = {"unit": "deg"}

# Hidden in the SCAD: straight pieces a leaf is drawn in.
LEAF_STEPS = 24
# The least the part draws between pieces that move against each other.
PRINT_GAP = 0.5


class Params(BaseModel):
    """The SCAD's top-level assignments, with its defaults."""

    hub: float = Field(
        10.0,
        ge=4,
        le=40,
        description="radius of the hub, where the leaves start",
        json_schema_extra=MM,
    )
    lobes: int = Field(2, ge=1, le=6, description="lobes on the hub, evenly spaced")
    lobe_r: float = Field(
        22.0, ge=6, le=80, description="radius of the lobes' tips", json_schema_extra=MM
    )
    lobe_arc: float = Field(
        40.0, ge=5, le=120, description="each lobe's width", json_schema_extra=DEG
    )
    swing: float = Field(
        0.0, ge=-20, le=20, description="the hub's turn as drawn", json_schema_extra=DEG
    )
    ring: float = Field(
        34.0,
        ge=8,
        le=100,
        description="inner radius of the ring, where the leaves end",
        json_schema_extra=MM,
    )
    wall: float = Field(5.0, ge=2, le=20, description="the ring's wall", json_schema_extra=MM)
    post_r: float = Field(
        14.0, ge=4, le=80, description="radius of the posts' tips", json_schema_extra=MM
    )
    post_arc: float = Field(
        30.0, ge=5, le=120, description="each post's width", json_schema_extra=DEG
    )
    stop: float = Field(
        8.0,
        ge=1,
        le=45,
        description="how far the hub turns before each lobe's flank meets its post's",
        json_schema_extra=DEG,
    )
    leaves: int = Field(2, ge=1, le=4, description="leaves between each post and the next lobe")
    leaf: float = Field(0.8, ge=0.4, le=3, description="a leaf's thickness", json_schema_extra=MM)
    height: float = Field(
        8.0, ge=2, le=30, description="height of the whole piece", json_schema_extra=MM
    )
    pocket: float = Field(
        6.2,
        ge=0,
        le=15,
        description="diameter of a pocket in each lobe and each post, 0 for none",
        json_schema_extra=MM,
    )
    pocket_depth: float = Field(
        3.0, ge=0.5, le=20, description="depth of a pocket from the top", json_schema_extra=MM
    )
    facets: int = Field(180, ge=36, le=720, multiple_of=12, description="sides of a circle")
    piece: Literal["all", "ring", "hub"] = Field(
        "all",
        description="what to draw: the piece, or one part of it alone without the leaves -- "
        "the ring and its posts, or the hub and its lobes unturned",
    )

    @model_validator(mode="after")
    def _drawable(self) -> "Params":
        problems = problems_of(self)
        if problems:
            raise ValueError("; ".join(problems))
        return self

    @property
    def span(self) -> float:
        """A leaf's length, from the hub's rim to the ring."""
        return self.ring - self.hub

    @property
    def free(self) -> float:
        """The degrees of room for leaves after each post, before the next lobe."""
        return 360 / self.lobes - self.lobe_arc - self.stop - self.post_arc


def problems_of(p: Params) -> List[str]:
    """What keeps a set of values from drawing a piece that prints and moves: pieces that
    meet, no room for the leaves, a pocket that breaks out, a swing past the stop."""
    out = []
    if p.post_r >= p.lobe_r:
        out.append(
            f"posts reaching in only to {p.post_r:g} pass over lobes reaching out to "
            f"{p.lobe_r:g}: no flank meets a flank, so nothing stops the hub"
        )
    if p.post_r - p.hub < PRINT_GAP:
        out.append(f"the posts' tips stand less than {PRINT_GAP:g} from the hub")
    if p.ring - p.lobe_r < PRINT_GAP:
        out.append(f"the lobes' tips stand less than {PRINT_GAP:g} from the ring")
    free = 360 / p.lobes - p.lobe_arc - p.stop - p.post_arc
    room = 2 * p.hub * math.sin(math.radians(max(free, 0.0) / (p.leaves + 1)) / 2)
    if free <= 0 or room < p.leaf + 1.0:
        out.append(
            f"{p.lobes} lobes of {p.lobe_arc:g} and posts of {p.post_arc:g} at {p.stop:g} "
            f"leave no room on the hub for {p.leaves} leaves each"
        )
    if p.pocket > 0:
        for what, r0, r1, arc in (
            ("lobe", p.hub, p.lobe_r, p.lobe_arc),
            ("post", p.post_r, p.ring, p.post_arc),
        ):
            mid = (r0 + r1) / 2
            room_across = mid * math.sin(math.radians(arc / 2))
            if (r1 - r0) / 2 < p.pocket / 2 + WALL or room_across < p.pocket / 2 + WALL:
                out.append(
                    f"a {p.pocket:g} pocket leaves less than {WALL:g} of each {what} round it"
                )
        if p.pocket_depth > p.height - 1:
            out.append(f"a pocket {p.pocket_depth:g} deep leaves less than 1 under it")
    if p.swing >= p.stop:
        out.append(
            f"a swing of {p.swing:g} is at or past the stop at {p.stop:g}: a lobe stands in its post"
        )
    return out


# ---- the mirror ----------------------------------------------------------------------------


def _cos(d: float) -> float:
    return math.cos(math.radians(d))


def _sin(d: float) -> float:
    return math.sin(math.radians(d))


def arc(p: Params, r: float, a0: float, a1: float) -> List[Point]:
    """As the SCAD's ``arc``: both ends, a point about every 360/facets degrees."""
    n = max(1, math.ceil(abs(a1 - a0) * p.facets / 360))
    return [
        (r * _cos(a0 + (a1 - a0) * i / n), r * _sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)
    ]


def lobe_at(p: Params, k: int) -> float:
    return 360 * k / p.lobes


def post_from(p: Params, k: int) -> float:
    """A post's flank nearest its lobe."""
    return lobe_at(p, k) + p.lobe_arc / 2 + p.stop


def leaf_angles(p: Params) -> List[float]:
    """Where each leaf meets the ring, as the SCAD's ``leaf_angles``."""
    return [
        post_from(p, k) + p.post_arc + p.free * (j + 1) / (p.leaves + 1)
        for k in range(p.lobes)
        for j in range(p.leaves)
    ]


def hub_outline(p: Params, swing: Optional[float] = None) -> List[Point]:
    """The hub and its lobes, turned by ``swing``."""
    swing = p.swing if swing is None else swing
    h = p.lobe_arc / 2
    out: List[Point] = []
    for k in range(p.lobes):
        c = lobe_at(p, k) + swing
        out += arc(p, p.lobe_r, c - h, c + h) + arc(p, p.hub, c + h, c - h + 360 / p.lobes)
    return out


def cavity_outline(p: Params) -> List[Point]:
    """The free space inside the ring and its posts."""
    out: List[Point] = []
    for k in range(p.lobes):
        a = post_from(p, k)
        b = a + p.post_arc
        out += arc(p, p.post_r, a, b) + arc(p, p.ring, b, a + 360 / p.lobes)
    return out


def lobe_outline(p: Params, k: int, swing: Optional[float] = None) -> List[Point]:
    """One lobe alone, from the hub's rim to its tip."""
    swing = p.swing if swing is None else swing
    c, h = lobe_at(p, k) + swing, p.lobe_arc / 2
    return arc(p, p.lobe_r, c - h, c + h) + arc(p, p.hub, c + h, c - h)


def post_outline(p: Params, k: int) -> List[Point]:
    """One post alone, from its tip to the ring."""
    a = post_from(p, k)
    return arc(p, p.post_r, a, a + p.post_arc) + arc(p, p.ring, a + p.post_arc, a)


def _hermite(p0, t0, p1, t1, u):
    h = (2 * u**3 - 3 * u**2 + 1, u**3 - 2 * u**2 + u, -2 * u**3 + 3 * u**2, u**3 - u**2)
    return tuple(h[0] * p0[i] + h[1] * t0[i] + h[2] * p1[i] + h[3] * t1[i] for i in range(2))


def _hermite_d(p0, t0, p1, t1, u):
    h = (6 * u**2 - 6 * u, 3 * u**2 - 4 * u + 1, -6 * u**2 + 6 * u, 3 * u**2 - 2 * u)
    return tuple(h[0] * p0[i] + h[1] * t0[i] + h[2] * p1[i] + h[3] * t1[i] for i in range(2))


def _hermite_dd(p0, t0, p1, t1, u):
    h = (12 * u - 6, 6 * u - 4, -12 * u + 6, 6 * u - 2)
    return tuple(h[0] * p0[i] + h[1] * t0[i] + h[2] * p1[i] + h[3] * t1[i] for i in range(2))


def _leaf_ends(p: Params, angle: float, swing: float):
    u0 = (_cos(angle + swing), _sin(angle + swing))
    u1 = (_cos(angle), _sin(angle))
    p0 = (p.hub * u0[0], p.hub * u0[1])
    p1 = (p.ring * u1[0], p.ring * u1[1])
    t0 = (p.span * u0[0], p.span * u0[1])
    t1 = (p.span * u1[0], p.span * u1[1])
    return u0, u1, p0, t0, p1, t1


def leaf_outline(
    p: Params, angle: float, swing: Optional[float] = None, ext: float = 0.0
) -> List[Point]:
    """The leaf meeting the ring at ``angle``, bent by ``swing``, as the SCAD's
    ``leaf_outline``; ``ext`` carries it on straight into the hub and the ring, as the
    drawing does so that it joins them."""
    swing = p.swing if swing is None else swing
    u0, u1, p0, t0, p1, t1 = _leaf_ends(p, angle, swing)
    h = p.leaf / 2
    left, right = [], []
    for i in range(LEAF_STEPS + 1):
        u = i / LEAF_STEPS
        m = _hermite(p0, t0, p1, t1, u)
        d = _hermite_d(p0, t0, p1, t1, u)
        length = math.hypot(d[0], d[1])
        side = (-d[1] / length, d[0] / length)
        left.append((m[0] + h * side[0], m[1] + h * side[1]))
        right.append((m[0] - h * side[0], m[1] - h * side[1]))
    n0, n1 = (-u0[1], u0[0]), (-u1[1], u1[0])
    start = [(p0[0] - ext * u0[0] + h * n0[0], p0[1] - ext * u0[1] + h * n0[1])] if ext > 0 else []
    end = (
        [
            (p1[0] + ext * u1[0] + h * n1[0], p1[1] + ext * u1[1] + h * n1[1]),
            (p1[0] + ext * u1[0] - h * n1[0], p1[1] + ext * u1[1] - h * n1[1]),
        ]
        if ext > 0
        else []
    )
    finish = [(p0[0] - ext * u0[0] - h * n0[0], p0[1] - ext * u0[1] - h * n0[1])] if ext > 0 else []
    return start + left + end + right[::-1] + finish


def pocket_centres(p: Params, swing: Optional[float] = None) -> List[Point]:
    """Each lobe's pocket, then each post's, as the SCAD places them."""
    swing = p.swing if swing is None else swing
    r_lobe, r_post = (p.hub + p.lobe_r) / 2, (p.post_r + p.ring) / 2
    out = []
    for k in range(p.lobes):
        a = lobe_at(p, k) + swing
        out.append((r_lobe * _cos(a), r_lobe * _sin(a)))
    for k in range(p.lobes):
        a = post_from(p, k) + p.post_arc / 2
        out.append((r_post * _cos(a), r_post * _sin(a)))
    return out


# ---- what is measured --------------------------------------------------------------------


def flank_gap(p: Params, swing: Optional[float] = None) -> float:
    """The least gap between a lobe and its post at ``swing``, negative once they overlap."""
    return min(separation(lobe_outline(p, k, swing), post_outline(p, k)) for k in range(p.lobes))


def flank_gap_closed_form(p: Params, swing: Optional[float] = None) -> float:
    """``post_r * sin(stop - swing)``: from the post's corner square to the lobe's flank,
    which is where they are nearest while ``post_r * cos(stop - swing)`` is beyond the hub."""
    swing = p.swing if swing is None else swing
    return p.post_r * math.sin(math.radians(p.stop - swing))


def clearances(p: Params, swing: Optional[float] = None) -> Dict[str, float]:
    """How far each moving thing stands from what it could meet at ``swing``: the hub and
    its lobes from the ring and its posts, each leaf from the lobes and from the posts."""
    swing = p.swing if swing is None else swing
    leaves = [leaf_outline(p, a, swing) for a in leaf_angles(p)]
    lobes = [lobe_outline(p, k, swing) for k in range(p.lobes)]
    posts = [post_outline(p, k) for k in range(p.lobes)]
    return {
        "hub_to_ring": clearance_in(hub_outline(p, swing), cavity_outline(p)),
        "leaves_to_lobes": min(separation(f, g) for f in leaves for g in lobes),
        "leaves_to_posts": min(separation(f, g) for f in leaves for g in posts),
    }


def leaf_curvature(p: Params, swing: Optional[float] = None, samples: int = 200) -> float:
    """The sharpest curvature along any leaf bent to ``swing``, in 1/mm."""
    swing = p.swing if swing is None else swing
    worst = 0.0
    for angle in leaf_angles(p):
        _, _, p0, t0, p1, t1 = _leaf_ends(p, angle, swing)
        for i in range(samples + 1):
            u = i / samples
            d = _hermite_d(p0, t0, p1, t1, u)
            dd = _hermite_dd(p0, t0, p1, t1, u)
            k = abs(d[0] * dd[1] - d[1] * dd[0]) / math.hypot(d[0], d[1]) ** 3
            worst = max(worst, k)
    return worst


def leaf_strain(p: Params, swing: Optional[float] = None) -> float:
    """The strain at a leaf's surface where it bends sharpest: half its thickness times
    its curvature, a beam's bending with its sections staying plane."""
    return p.leaf / 2 * leaf_curvature(p, swing)


def leaf_strain_small(p: Params, swing: Optional[float] = None) -> float:
    """``leaf * a * (2 L + 3 hub) / L^2`` for a turn of ``a`` radians: the cubic of a beam
    of length L built in at the ring and turned with its root at the hub's rim, sharpest
    at that root, for a small turn."""
    swing = p.swing if swing is None else swing
    a = math.radians(abs(swing))
    return p.leaf * a * (2 * p.span + 3 * p.hub) / p.span**2


def stop_reached(p: Params, tol: float = 1e-6) -> float:
    """The swing at which a lobe first touches its post, found from the outlines by
    halving: the measured stop, which the drawing places at ``stop``."""
    lo, hi = p.swing if p.swing < p.stop else 0.0, p.stop + 5.0
    while hi - lo > tol:
        mid = (lo + hi) / 2
        if flank_gap(p, mid) > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def hub_gap(p: Params, swing: Optional[float] = None, n: int = 360) -> GapProfile:
    """The gap along rays from the axis between the hub with its lobes and the ring with
    its posts, leaves left out: what a permeance model reads of this piece."""
    swing = p.swing if swing is None else swing
    return radial_gap(cavity_outline(p), hub_outline(p, swing), n)


def swings(amplitude: float, step: float = 1.0) -> List[float]:
    """Out to ``amplitude`` and back, both ways, starting and ending at rest."""
    n = max(1, round(amplitude / step))
    out = [amplitude * i / n for i in range(n + 1)]
    out += [amplitude * i / n for i in range(n - 1, -n - 1, -1)]
    out += [amplitude * i / n for i in range(-n + 1, 1)]
    return out


def hub_travel(p: Params, amplitude: float, step: float = 1.0) -> Travel:
    """Where the hub comes closest to the ring and its posts as it swings out to
    ``amplitude`` and back, both ways."""
    return follow(
        cavity_outline(p), hub_outline(p, 0.0), [Pose(0.0, 0.0, s) for s in swings(amplitude, step)]
    )


def volume(p: Params) -> float:
    """The volume of the piece as drawn at swing 0, in mm^3: solid, so a print's mass is
    this times the filament's density times how full the slicer fills it."""
    flat = (
        area(circle(p.ring + p.wall, p.facets))
        - area(cavity_outline(p))
        + area(hub_outline(p, 0.0))
        + sum(area(leaf_outline(p, a, 0.0)) for a in leaf_angles(p))
    )
    pockets = 2 * p.lobes * area(circle(p.pocket / 2 / math.cos(math.pi / p.facets), p.facets))
    return flat * p.height - (pockets * p.pocket_depth if p.pocket > 0 else 0.0)


# ---- the motion ------------------------------------------------------------------------


def flank_marks(p: Params, swing: float) -> List[Mark]:
    """Where each lobe comes closest to its post at ``swing``, the least first: on the
    post, and on the lobe as it stands."""
    marks = []
    for k in range(p.lobes):
        found = nearest(lobe_outline(p, k, swing), post_outline(p, k))
        marks.append(Mark(found.distance, found.on_b, found.on_a))
    return sorted(marks, key=lambda m: m.gap)


def motion_of(p: Params, step: float = 0.25) -> Motion:
    """The swing, from ``-stop`` to the stop: the ring still, the hub turning, the leaves
    drawn from the model's cubic at each sample, and each lobe's flank gap to its post."""
    centres = pocket_centres(p, 0.0)
    top = p.height
    disc = p.pocket - INSERT_FIT

    def seated(points):
        return tuple(Insert("pocket insert", at, top - p.pocket_depth, top, disc) for at in points)

    lobes = seated(centres[: p.lobes] if p.pocket > 0 else [])
    posts = seated(centres[p.lobes :] if p.pocket > 0 else [])
    return Motion(
        param="swing",
        label="swing",
        unit="deg",
        lo=-p.stop,
        hi=p.stop,
        step=step,
        piece_param="piece",
        still=Piece("ring", "the ring and its posts", reach=p.ring + p.wall, inserts=posts),
        moving=(Piece("hub", "the hub and its lobes", reach=p.lobe_r, inserts=lobes),),
        pose=lambda swing: {"hub": Pose(0.0, 0.0, swing)},
        bent=(
            Bent(
                "leaves",
                "the leaves, drawn from the model's cubic",
                0.0,
                p.height,
                lambda swing: [leaf_outline(p, a, swing) for a in leaf_angles(p)],
            ),
        ),
        gaps=(Gap("flank", "a lobe's flank to its post", p.height / 2, lambda swing: flank_marks(p, swing)),),
        note="The hub turns rigidly on its leaves. Each leaf is drawn at each swing as the "
        "model's cubic of a beam built in at both ends: the drawing's shape, not a simulation "
        "of the bending, and nothing here says how far a pull swings it.",
    )


# ---- the part ------------------------------------------------------------------------------


class FlexureRotorPart(BasePart):
    """One piece: the ring and its posts, the leaves, the hub and its lobes."""

    def motion(self, params: Optional[Mapping[str, Any]] = None) -> Motion:
        return motion_of(Params(**(params or {})))

    def bought(self, params: Optional[Mapping[str, Any]] = None) -> List[Bought]:
        """A disc for each pocket, sized here, its material the owner's: a magnet in one
        and steel in the other is how the bench first tries it."""
        p = Params(**(params or {}))
        if p.pocket <= 0:
            return []
        places = [i.name for i in self.interfaces(p.model_dump())]
        return [
            Bought(
                name="pocket insert",
                count=len(places),
                diameter=round(p.pocket - INSERT_FIT, 6),
                length=p.pocket_depth,
                goes_in=places,
                notes="a disc for a pocket from the top, in each lobe and each post: what "
                "carries the flux the plastic does not, of a material the bench chooses",
            )
        ]

    def get_bounds(self, params: Optional[Dict] = None) -> BoundingBox3D:
        p = Params(**(params or {}))
        r = p.lobe_r if p.piece == "hub" else p.ring + p.wall
        return BoundingBox3D(
            min_point=Vector3D(x=-r, y=-r, z=0.0), max_point=Vector3D(x=r, y=r, z=p.height)
        )

    def interfaces(self, params: Optional[Mapping[str, Any]] = None) -> List[InterfaceBase]:
        """The pockets, where what is bought goes in: one in each lobe, turning with it,
        and one in each post, standing still."""
        p = Params(**(params or {}))
        if p.pocket <= 0:
            return []
        names: Sequence[str] = [f"lobe_{k + 1}" for k in range(p.lobes)] + [
            f"post_{k + 1}" for k in range(p.lobes)
        ]
        keep = {"all": names, "hub": names[: p.lobes], "ring": names[p.lobes :]}[p.piece]
        return [
            Socket(
                name=name,
                position=Vector3D(x=x, y=y, z=p.height),
                normal=Vector3D(x=0.0, y=0.0, z=1.0),
                diameter=p.pocket,
                depth=p.pocket_depth,
                floor=0.0,
                source="drawn",
                notes="a pocket from the top for a disc magnet or a steel slug, as the bench chooses",
            )
            for name, (x, y) in zip(names, pocket_centres(p, 0.0 if p.piece == "hub" else None), strict=True)
            if name in keep
        ]


def create(metadata_root: Path) -> FlexureRotorPart:
    folder = metadata_root / "parts" / "flexure_rotor"
    return FlexureRotorPart(
        name="flexure_rotor",
        source_file=folder / "flexure_rotor.scad",
        description=(
            "A rotor carried on leaves printed with its stator, in one piece: the hub turns "
            "a few degrees by bending them, until a lobe's flank meets its post's"
        ),
        params_model=Params,
        category="electromechanical",
        tags=["motor", "rotor", "stator", "flexure", "compliant", "parametric"],
        readme_path=folder / "README.md",
        preview_color=Color.from_hex("#D9925A"),
    )


DEFAULT = create(ROOT)
