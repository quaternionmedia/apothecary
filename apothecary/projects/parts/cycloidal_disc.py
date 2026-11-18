"""Cycloidal disc -- a lobed disc that rolls round inside a ring of pins, the ratio set by its teeth.

The part is its SCAD, ``parts/cycloidal_disc/cycloidal_disc.scad``; this module mirrors its
outlines and its pose in the same degrees, for what Python has to know without OpenSCAD --
the envelope, the interfaces, what is bought and the gap -- and
``tests/test_cycloidal_disc_part.py`` holds the two together through the SCAD's
``-D echo_shapes=true``.

``pins`` pins stand on a circle of radius ``pin_circle`` in the stator's floor. The disc
has one lobe fewer. An eccentric crank carries the disc's centre round a circle of radius
``eccentricity``; at ``crank`` the disc's centre stands there and the disc has turned
``-crank / (pins - 1)``, so each turn of the crank turns it back one pin's pitch of a
lobe. The rolling rotor's turn back rests on its track not slipping; here the lobes on
the pins set it, and a disc turned any other way would stand in a pin.

The profile is constructed, not quoted. Seen from the disc, turning as the pose turns
it, each pin's centre runs round one closed curve,

    c(s) = (R cos s - E cos N s,  R sin s - E sin N s),   0 <= s < 360 degrees,

with ``R = pin_circle``, ``E = eccentricity`` and ``N = pins`` (put the pin at ``(R, 0)``
into the disc's frame at ``crank = (N - 1) s`` and this is what comes out). Every pin's
centre is on it at every pose: pin k is the same curve ``360 k / N`` further on. The
disc's flank is that curve's inner parallel at the pin's radius plus ``clearance``:
``c(s) - (pin / 2 + clearance) n(s)``, ``n`` its outward unit normal,

    n(s) ~ (R cos s - E N cos N s,  R sin s - E N sin N s).

So each pin stands exactly ``clearance`` from the flank, at every pose, where the curve
is a curtate trochoid (``R > E N``) and its parallel does not fold (the pin's radius plus
the clearance under the curve's least radius on its lobes); ``problems_of`` refuses a set
that is not. The disc is drawn as ``profile`` points of that parallel; ``profile_sagitta``
says how far the polygon's edges stand from the curve.

What is measured here is geometry (``apothecary.gap_geometry``): the gap from each pin to
the disc at any crank, its least and where; the turn at which the disc fits between the
pins at a crank, and how far it can turn either way before it meets one (its backlash as
drawn); where the pitch circles' contact and one pin's contact travel through a turn of
the crank; that each output pin stays in its hole. How hard anything pulls, the torque
the disc passes, how it wears and what its friction costs are not computed: no field, no
force, no material.

Units: mm and degrees.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, List, Literal, Mapping, Optional, Tuple

from pydantic import BaseModel, Field, model_validator

from apothecary.fittings import WALL
from apothecary.gap_geometry import (
    Point,
    Pose,
    Travel,
    circle,
    follow,
    inside,
    to_boundary,
)
from apothecary.models import BoundingBox3D, Color, Vector3D
from apothecary.models.bought import INSERT_FIT, Bought
from apothecary.models.interfaces import InterfaceBase, Socket
from apothecary.motion import Gap, Insert, Mark, Motion, Piece

from .base import BasePart
from .skeleton import ROOT

MM = {"unit": "mm"}
DEG = {"unit": "deg"}

# Hidden in the SCAD: between the stator and the disc as they print; between the pins'
# outsides and the housing's wall.
SPACING = 6.0
ROOM = 1.0


class Params(BaseModel):
    """The SCAD's top-level assignments, with its defaults."""

    pins: int = Field(11, ge=4, le=41, description="pins round the ring; the disc has one lobe fewer")
    pin_circle: float = Field(
        30.0,
        ge=10,
        le=120,
        description="radius of the circle the pins' centres stand on",
        json_schema_extra=MM,
    )
    pin: float = Field(5.0, ge=1, le=20, description="diameter of a pin", json_schema_extra=MM)
    eccentricity: float = Field(
        1.0,
        ge=0.2,
        le=6,
        description="how far the crank carries the disc's centre off the axis",
        json_schema_extra=MM,
    )
    clearance: float = Field(
        0.1,
        ge=0,
        le=1,
        description="how far the disc's flank stands back from each pin, as drawn",
        json_schema_extra=MM,
    )
    thickness: float = Field(7.0, ge=2, le=40, description="the disc's thickness", json_schema_extra=MM)
    crank: float = Field(
        0.0,
        ge=0,
        le=360,
        description="where the crank carries the disc's centre about the axis",
        json_schema_extra=DEG,
    )
    printed_pins: bool = Field(
        False, description="the pins printed with the floor instead of bought and pressed in"
    )
    base: float = Field(
        3.0, ge=1.5, le=10, description="the floor the pins stand in", json_schema_extra=MM
    )
    wall: float = Field(
        6.0, ge=2, le=30, description="the housing's wall outside the pins", json_schema_extra=MM
    )
    shaft: float = Field(
        8.0,
        ge=0,
        le=40,
        description="diameter of the hole in the floor the crank's shaft runs through, 0 for none",
        json_schema_extra=MM,
    )
    bearing: float = Field(
        22.0,
        ge=0,
        le=80,
        description="diameter of the disc's centre hole, for the bearing on the crank, 0 for none",
        json_schema_extra=MM,
    )
    outputs: int = Field(6, ge=0, le=12, description="holes an output's pins run in, 0 for none")
    output_pin: float = Field(
        4.0, ge=1, le=12, description="diameter of the output's pins", json_schema_extra=MM
    )
    output_circle: float = Field(
        18.0,
        ge=3,
        le=100,
        description="radius of the circle the output holes stand on",
        json_schema_extra=MM,
    )
    lobe_insert: float = Field(
        0.0,
        ge=0,
        le=20,
        description="diameter of a pocket from the top of each lobe for a bought insert, 0 for none",
        json_schema_extra=MM,
    )
    pole_insert: float = Field(
        0.0,
        ge=0,
        le=20,
        description="diameter of a pocket from the top of the wall between each two pins for a "
        "bought insert, 0 for none",
        json_schema_extra=MM,
    )
    insert_depth: float = Field(
        4.0,
        ge=1,
        le=40,
        description="depth of each insert's pocket from the top",
        json_schema_extra=MM,
    )
    profile: int = Field(
        720, ge=120, le=2880, multiple_of=12, description="points on the disc's profile"
    )
    facets: int = Field(180, ge=36, le=720, multiple_of=12, description="sides of a circle")
    piece: Literal["all", "stator", "disc"] = Field(
        "all",
        description="what to draw: both, or one alone -- the disc in its own frame, its "
        "centre on the axis and unturned, where assembled",
    )

    @model_validator(mode="after")
    def _drawable(self) -> "Params":
        problems = problems_of(self)
        if problems:
            raise ValueError("; ".join(problems))
        return self

    # ---- derived, as the SCAD derives them ----

    @property
    def lobes(self) -> int:
        return self.pins - 1

    @property
    def offset(self) -> float:
        """How far the flank stands inside the pins' centres' curve: a pin's radius and
        the clearance."""
        return self.pin / 2 + self.clearance

    @property
    def tip_r(self) -> float:
        """The lobes' tips' radius from the disc's centre: R + E less the offset."""
        return self.pin_circle + self.eccentricity - self.offset

    @property
    def root_r(self) -> float:
        """The lobes' roots' radius."""
        return self.pin_circle - self.eccentricity - self.offset

    @property
    def inner_r(self) -> float:
        """The housing's wall's inside."""
        return self.pin_circle + self.pin / 2 + ROOM

    @property
    def outer_r(self) -> float:
        return self.inner_r + self.wall

    @property
    def height(self) -> float:
        return self.base + self.thickness

    @property
    def output_d(self) -> float:
        return self.output_pin + 2 * self.eccentricity

    @property
    def pole_insert_r(self) -> float:
        return self.inner_r + self.wall / 2

    @property
    def lobe_insert_r(self) -> float:
        """The lobes' pockets stand on this circle, under the lobes' tips: a wall and the
        pocket's radius in from the lobes' roots, since a lobe is only twice the
        eccentricity deep."""
        return self.root_r - WALL - self.lobe_insert / 2


def _c(d: float) -> float:
    return math.cos(math.radians(d))


def _s(d: float) -> float:
    return math.sin(math.radians(d))


# ---- the curve and its parallel ----------------------------------------------------------


def pin_path(p: Params, s: float) -> Point:
    """Where every pin's centre runs in the disc's own frame: ``c(s)``, s in degrees."""
    R, E, N = p.pin_circle, p.eccentricity, p.pins
    return (R * _c(s) - E * _c(N * s), R * _s(s) - E * _s(N * s))


def _normal(p: Params, s: float) -> Point:
    R, E, N = p.pin_circle, p.eccentricity, p.pins
    nx, ny = R * _c(s) - E * N * _c(N * s), R * _s(s) - E * N * _s(N * s)
    length = math.hypot(nx, ny)
    return (nx / length, ny / length)


def flank_at(p: Params, s: float, offset: Optional[float] = None) -> Point:
    """The disc's flank at ``s``: the pins' centres' curve less ``offset`` along its
    outward normal, the pin's radius and the clearance unless told."""
    d = p.offset if offset is None else offset
    (cx, cy), (nx, ny) = pin_path(p, s), _normal(p, s)
    return (cx - d * nx, cy - d * ny)


def disc_outline(p: Params) -> List[Point]:
    """The disc's rim in its own frame, ``profile`` points of the flank, as the SCAD's
    ``profile_outline`` draws it."""
    return [flank_at(p, 360.0 * i / p.profile) for i in range(p.profile)]


def curvature(p: Params, s: float) -> float:
    """The pins' centres' curve's curvature at ``s``, 1/mm, positive where it bends round
    toward the disc's centre (its lobes)."""
    R, E, N = p.pin_circle, p.eccentricity, p.pins
    a = math.radians(s)
    dx, dy = -R * math.sin(a) + E * N * math.sin(N * a), R * math.cos(a) - E * N * math.cos(N * a)
    ddx = -R * math.cos(a) + E * N * N * math.cos(N * a)
    ddy = -R * math.sin(a) + E * N * N * math.sin(N * a)
    return (dx * ddy - dy * ddx) / math.hypot(dx, dy) ** 3


def sharpest(p: Params, samples: int = 2000) -> float:
    """The curve's sharpest bend round toward the centre over a lobe, 1/mm: a lobe's tip.
    The flank folds where the offset passes its radius."""
    lobe = 360.0 / (p.pins - 1)
    return max(curvature(p, lobe * k / samples) for k in range(samples + 1))


def profile_sagitta(p: Params, between: int = 4) -> float:
    """How far the disc's polygon stands from the flank it is drawn from: the farthest
    any point of the curve between two corners stands from the edge joining them."""
    worst = 0.0
    step = 360.0 / p.profile
    lobe = 360.0 / (p.pins - 1)
    # The flank repeats every lobe, so one lobe's edges say it.
    for i in range(math.ceil(lobe / step) + 1):
        a, b = flank_at(p, i * step), flank_at(p, (i + 1) * step)
        ex, ey = b[0] - a[0], b[1] - a[1]
        length = math.hypot(ex, ey)
        for k in range(1, between):
            q = flank_at(p, (i + k / between) * step)
            worst = max(worst, abs((q[0] - a[0]) * ey - (q[1] - a[1]) * ex) / length)
    return worst


def problems_of(p: Params) -> List[str]:
    """What keeps a set of values from drawing a disc that runs on its pins and prints:
    a curve that loops, a flank that folds, pins that meet, holes that break through."""
    out = []
    R, E, N = p.pin_circle, p.eccentricity, p.pins
    if R <= E * N:
        out.append(
            f"pins on a {R:g} circle with {E:g} of eccentricity and {N} pins make a curve that "
            f"loops (it needs more than eccentricity times pins, {E * N:g})"
        )
        return out
    folds_at = 1 / sharpest(p)
    if p.offset >= 0.95 * folds_at:
        out.append(
            f"a {p.pin:g} pin and {p.clearance:g} of clearance fold the flank at the lobes' tips, "
            f"which bend on a {folds_at:.3g} radius"
        )
    pitch = 2 * R * math.sin(math.pi / N)
    if pitch - p.pin < WALL:
        out.append(f"{N} pins of {p.pin:g} on a {R:g} circle stand less than {WALL:g} apart")
    reach = p.tip_r + E
    if reach > p.inner_r - 0.5:
        out.append(f"the disc's lobes reach {reach:.3g}, into the housing's wall at {p.inner_r:g}")
    floor_r = p.root_r
    if p.bearing > 0 and p.bearing / 2 + WALL > floor_r:
        out.append(f"the centre hole leaves less than {WALL:g} of disc")
    if p.shaft > 0 and p.shaft / 2 + WALL > R - p.pin / 2:
        out.append(f"the shaft's hole reaches the pins' holes")
    if p.outputs:
        r = p.output_d / 2
        if p.output_circle + r + WALL > floor_r:
            out.append(
                f"the output holes ({p.output_d:g} across on a {p.output_circle:g} circle) "
                f"leave less than {WALL:g} of disc outside them"
            )
        if p.output_circle - r - WALL < p.bearing / 2:
            out.append(f"the output holes leave less than {WALL:g} round the centre hole")
        if p.outputs > 1 and 2 * p.output_circle * math.sin(math.pi / p.outputs) - p.output_d < WALL:
            out.append(f"the {p.outputs} output holes leave less than {WALL:g} between them")
    if p.lobe_insert > 0:
        out += _lobe_problems(p)
    if p.pole_insert > 0:
        if p.pole_insert / 2 + WALL > p.wall / 2:
            out.append(f"a {p.pole_insert:g} pocket leaves less than {WALL:g} of a {p.wall:g} wall")
        if p.insert_depth > p.height - 1:
            out.append(f"a pocket {p.insert_depth:g} deep leaves less than 1 of wall under it")
    return out


def _lobe_problems(p: Params) -> List[str]:
    """What keeps the lobes' pockets from fitting: the flank, the holes, a floor under."""
    out = []
    centres = lobe_insert_centres(p)
    half = p.lobe_insert / 2
    flank = disc_outline(p)
    if any(d < half + WALL for d, _ in to_boundary(centres, flank)):
        out.append(f"a {p.lobe_insert:g} pocket leaves less than {WALL:g} of a lobe round it")
    holes = [((0.0, 0.0), p.bearing / 2)] if p.bearing > 0 else []
    holes += [(c, p.output_d / 2) for c in output_centres(p)]
    if any(math.dist(c, h) - half - r < WALL for c in centres for h, r in holes):
        out.append(f"the lobes' pockets leave less than {WALL:g} round the disc's holes")
    if p.insert_depth > p.thickness - 1:
        out.append(f"a pocket {p.insert_depth:g} deep leaves less than 1 of disc under it")
    return out


# ---- where things stand ------------------------------------------------------------------


def pin_centres(p: Params) -> List[Point]:
    """The pins, in the stator's frame, the first on +x."""
    return [(p.pin_circle * _c(360 * k / p.pins), p.pin_circle * _s(360 * k / p.pins)) for k in range(p.pins)]


def output_centres(p: Params) -> List[Point]:
    """The output holes' centres in the disc's own frame."""
    n = p.outputs
    return [(p.output_circle * _c(360 * k / n), p.output_circle * _s(360 * k / n)) for k in range(n)]


def lobe_insert_centres(p: Params) -> List[Point]:
    """The lobes' pockets in the disc's own frame, one under each lobe's tip."""
    n = p.lobes
    return [(p.lobe_insert_r * _c(180 * (2 * k + 1) / n), p.lobe_insert_r * _s(180 * (2 * k + 1) / n)) for k in range(n)]


def pole_insert_centres(p: Params) -> List[Point]:
    """The wall's pockets, halfway between each two pins."""
    n = p.pins
    return [(p.pole_insert_r * _c(180 * (2 * k + 1) / n), p.pole_insert_r * _s(180 * (2 * k + 1) / n)) for k in range(n)]


def turn(p: Params, crank: Optional[float] = None) -> float:
    """The disc's own turn when the crank stands at ``crank``: back by one pin's pitch of a
    lobe each turn of the crank, ``-crank / (pins - 1)``."""
    crank = p.crank if crank is None else crank
    return -crank / (p.pins - 1)


def pose(p: Params, crank: Optional[float] = None) -> Pose:
    """Where the disc stands, assembled, at ``crank``."""
    crank = p.crank if crank is None else crank
    return Pose(p.eccentricity * _c(crank), p.eccentricity * _s(crank), turn(p, crank))


def output_pose(p: Params, crank: Optional[float] = None) -> Pose:
    """Where the output stands: turned with the disc, on the axis."""
    return Pose(0.0, 0.0, turn(p, crank))


def print_offset(p: Params) -> float:
    """How far along x the disc's centre stands from the stator's as they print."""
    return p.outer_r + SPACING + p.tip_r


# ---- what is measured --------------------------------------------------------------------


def pin_marks(p: Params, crank: Optional[float] = None, placed: Optional[Pose] = None) -> List[Mark]:
    """Each pin's gap to the disc at ``crank`` (or with the disc where ``placed`` puts it),
    least first: its centre's distance to the disc's rim less its radius, negative where
    it stands in the disc, with the point on the pin and the point on the disc."""
    at = placed if placed is not None else pose(p, crank)
    rim = at.place(disc_outline(p))
    r = p.pin / 2
    marks = []
    for c, (d, foot) in zip(pin_centres(p), to_boundary(pin_centres(p), rim), strict=True):
        into = inside(c, rim)
        ux, uy = (foot[0] - c[0]) / d, (foot[1] - c[1]) / d
        sign = -1 if into else 1
        marks.append(Mark(d - r if not into else -(d + r), (c[0] + sign * r * ux, c[1] + sign * r * uy), foot))
    return sorted(marks, key=lambda m: m.gap)


def least_gap(p: Params, crank: Optional[float] = None, placed: Optional[Pose] = None) -> float:
    return pin_marks(p, crank, placed)[0].gap


def free_turn(p: Params, crank: Optional[float] = None, reach: float = 2.0, tol: float = 1e-7) -> Tuple[float, float]:
    """How far the disc can turn about its own centre either way from where ``pose`` puts
    it at ``crank`` before it meets a pin, in degrees: (back, on), the first not above 0
    and the second not below. Halved toward each touch from as far as ``reach``
    degrees. Its width is the disc's backlash as drawn, at its centre; its middle, where
    the pins would centre it, is 0 when the pose turns it as the teeth do."""
    crank = p.crank if crank is None else crank
    at = pose(p, crank)

    def fits(delta: float) -> bool:
        return least_gap(p, placed=Pose(at.x, at.y, at.turn + delta)) >= 0

    out = []
    for way in (-1.0, 1.0):
        lo, hi = 0.0, way * reach
        if not fits(lo):
            # The pose itself stands in a pin: find the nearest turn either way that fits.
            return (math.nan, math.nan)
        while abs(hi - lo) > tol:
            mid = (lo + hi) / 2
            if fits(mid):
                lo = mid
            else:
                hi = mid
        out.append(lo)
    return out[0], out[1]


def cranks(step: float = 5.0) -> List[float]:
    """One turn of the crank in steps, both ends included."""
    n = round(360 / step)
    return [360.0 * k / n for k in range(n + 1)]


def pitch_travel(p: Params, step: float = 5.0) -> Travel:
    """Where the pitch circles touch through a turn of the crank: the ring's, ``E N`` about
    the axis, and the disc's, ``E (N - 1)`` about its own centre. They roll, by the pose."""
    n = 720
    ring = circle(p.eccentricity * p.pins, n)
    disc = circle(p.eccentricity * p.lobes, n)
    return follow(ring, disc, [pose(p, a) for a in cranks(step)])


def pin_travel(p: Params, step: float = 5.0, k: int = 0) -> Travel:
    """Where pin ``k`` and the disc come closest through a turn of the crank, the pin the
    outer body: on the pin, and along the disc's flank."""
    c = pin_centres(p)[k]
    poses = [pose(p, a) for a in cranks(step)]
    # The pin drawn fine enough that its corners move the contact well under a degree.
    pin = circle(p.pin / 2, 1440)
    return follow(pin, disc_outline(p), poses, [Pose(c[0], c[1], 0.0)] * len(poses))


# ---- the motion ------------------------------------------------------------------------


def motion_of(p: Params, step: float = 2.0) -> Motion:
    """A turn of the crank: the stator and its pins still, the disc carried round and
    turned back by its lobes, the output's pins turning with it, each pin's gap to the
    disc followed at each sample."""
    top = p.height
    # Bought pins are drawn as what is bought; printed ones are the stator's own.
    pins = () if p.printed_pins else tuple(Insert("pin", c, 0.0, top, p.pin) for c in pin_centres(p))
    poles = tuple(
        Insert("pole insert", c, top - p.insert_depth, top, p.pole_insert - INSERT_FIT)
        for c in (pole_insert_centres(p) if p.pole_insert > 0 else [])
    )
    lobes = tuple(
        Insert("lobe insert", c, top - p.insert_depth, top, p.lobe_insert - INSERT_FIT)
        for c in (lobe_insert_centres(p) if p.lobe_insert > 0 else [])
    )
    outputs = tuple(Insert("output pin", c, p.base, top + 3.0, p.output_pin) for c in output_centres(p))
    moving = [Piece("disc", "the disc", reach=p.tip_r, inserts=lobes)]
    if outputs:
        moving.append(
            Piece("output", "the output's pins", reach=p.output_circle + p.output_pin / 2, inserts=outputs, drawn=False)
        )
    return Motion(
        param="crank",
        label="crank",
        unit="deg",
        lo=0.0,
        hi=360.0,
        step=step,
        cyclic=True,
        piece_param="piece",
        still=Piece("stator", "the stator and its pins", reach=p.outer_r, inserts=pins + poles),
        moving=tuple(moving),
        pose=lambda crank: {"disc": pose(p, crank), "output": output_pose(p, crank)},
        gaps=(Gap("pins", "each pin to the disc", p.base + p.thickness / 2, lambda crank: pin_marks(p, crank)),),
        note=f"The lobes on the pins turn the disc back one pin's pitch each turn of the crank: "
        f"{p.pins - 1} turns of the crank turn the output once. Each fixed pin's contact slides "
        "along the flank of a lobe; nothing here says how hard it presses or what that costs.",
    )


# ---- the part ------------------------------------------------------------------------------


class CycloidalDiscPart(BasePart):
    """The stator and the disc side by side as they print; at rest, assembled."""

    def get_bounds(self, params: Optional[Dict] = None) -> BoundingBox3D:
        """The pieces as they print: the disc's by its own polygon's extent, which its
        lobes' tips need not reach along an axis."""
        p = Params(**(params or {}))
        rim = disc_outline(p)
        x0 = print_offset(p)
        xs, ys = [x0 + x for x, _ in rim], [y for _, y in rim]
        if p.piece == "disc":
            return BoundingBox3D(
                min_point=Vector3D(x=min(xs), y=min(ys), z=0.0),
                max_point=Vector3D(x=max(xs), y=max(ys), z=p.thickness),
            )
        right = p.outer_r if p.piece == "stator" else max(xs)
        return BoundingBox3D(
            min_point=Vector3D(x=-p.outer_r, y=-p.outer_r, z=0.0),
            max_point=Vector3D(x=right, y=p.outer_r, z=p.height),
        )

    def interfaces(self, params: Optional[Mapping[str, Any]] = None) -> List[InterfaceBase]:
        """Where what is bought goes, in the print pose: each pin's hole through the floor,
        the shaft's, the pockets in the wall; the disc's centre hole for the crank's
        bearing, the holes an output's pins run in (a pin's diameter and twice the
        eccentricity), the pockets in its lobes. Of the pieces drawn."""
        p = Params(**(params or {}))
        up = Vector3D(x=0.0, y=0.0, z=1.0)
        kw: Dict[str, Any] = {"normal": up, "source": "drawn"}
        found: List[InterfaceBase] = []
        if p.piece != "disc":
            for k, (x, y) in enumerate([] if p.printed_pins else pin_centres(p)):
                found.append(
                    Socket(name=f"pin_{k + 1}", position=Vector3D(x=x, y=y, z=p.base), diameter=p.pin,
                           depth=p.base, notes="a pin pressed down through the floor", **kw)
                )
            if p.shaft > 0:
                found.append(
                    Socket(name="shaft", position=Vector3D(x=0.0, y=0.0, z=p.base), diameter=p.shaft,
                           depth=p.base, notes="the crank's shaft, through the floor", **kw)
                )
            for k, (x, y) in enumerate(pole_insert_centres(p) if p.pole_insert > 0 else []):
                found.append(
                    Socket(name=f"pole_{k + 1}", position=Vector3D(x=x, y=y, z=p.height), diameter=p.pole_insert,
                           depth=p.insert_depth, floor=0.0, notes="a pocket from the top of the wall for a bought insert", **kw)
                )
        if p.piece == "stator":
            return found
        x0 = print_offset(p)
        if p.bearing > 0:
            found.append(
                Socket(name="bearing", position=Vector3D(x=x0, y=0.0, z=p.thickness), diameter=p.bearing,
                       depth=p.thickness, notes="the bearing on the crank's eccentric", **kw)
            )
        for k, (x, y) in enumerate(output_centres(p) if p.outputs else []):
            found.append(
                Socket(name=f"output_{k + 1}", position=Vector3D(x=x0 + x, y=y, z=p.thickness),
                       diameter=round(p.output_d, 6), depth=p.thickness,
                       notes=f"a {p.output_pin:g} pin of the output runs round in it", **kw)
            )
        for k, (x, y) in enumerate(lobe_insert_centres(p) if p.lobe_insert > 0 else []):
            found.append(
                Socket(name=f"lobe_{k + 1}", position=Vector3D(x=x0 + x, y=y, z=p.thickness), diameter=p.lobe_insert,
                       depth=p.insert_depth, floor=0.0, notes="a pocket from the top of a lobe for a bought insert", **kw)
            )
        return found

    def bought(self, params: Optional[Mapping[str, Any]] = None) -> List[Bought]:
        """The pins, the crank's bearing, the output's pins and an insert for each pocket,
        sized here; the inserts' material the owner's."""
        p = Params(**(params or {}))
        out = [] if p.printed_pins else [
            Bought(name="pin", count=p.pins, diameter=p.pin, length=p.height,
                   goes_in=[f"pin_{k + 1}" for k in range(p.pins)],
                   notes="a dowel or ground rod, at least as long as the floor and the disc; "
                   "the disc's lobes run on them")
        ]
        if p.bearing > 0:
            out.append(Bought(name="bearing", count=1, diameter=p.bearing, length=p.thickness, goes_in=["bearing"],
                              notes="a ball bearing no wider than the disc, on the crank's eccentric, "
                              f"{p.eccentricity:g} off its shaft"))
        if p.outputs:
            out.append(Bought(name="output pin", count=p.outputs, diameter=p.output_pin,
                              goes_in=[f"output_{k + 1}" for k in range(p.outputs)],
                              notes="on an output disc that turns on the axis; each runs round the wall "
                              "of its hole once a turn of the crank"))
        for name, d, places in (
            ("lobe insert", p.lobe_insert, [f"lobe_{k + 1}" for k in range(p.lobes)]),
            ("pole insert", p.pole_insert, [f"pole_{k + 1}" for k in range(p.pins)]),
        ):
            if d > 0:
                out.append(Bought(name=name, count=len(places), diameter=round(d - INSERT_FIT, 6),
                                  length=p.insert_depth, goes_in=places,
                                  notes="a round insert for a pocket from the top: what carries the flux "
                                  "the plastic does not, of a material the bench chooses"))
        return out

    def motion(self, params: Optional[Mapping[str, Any]] = None) -> Motion:
        return motion_of(Params(**(params or {})))


def create(metadata_root: Path) -> CycloidalDiscPart:
    folder = metadata_root / "parts" / "cycloidal_disc"
    return CycloidalDiscPart(
        name="cycloidal_disc",
        source_file=folder / "cycloidal_disc.scad",
        description=(
            "A lobed disc that rolls round inside a ring of pins, one lobe fewer than pins: "
            "each turn of the crank turns it back a pin's pitch, set by its teeth"
        ),
        params_model=Params,
        category="electromechanical",
        tags=["motor", "reducer", "cycloidal", "eccentric", "parametric"],
        readme_path=folder / "README.md",
        rest={"print": False},
        preview_color=Color.from_hex("#D9925A"),
    )


DEFAULT = create(ROOT)
