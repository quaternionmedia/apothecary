"""Rolling rotor -- a rotor that rolls round inside its stator instead of turning on a shaft.

The part is its SCAD, ``parts/rolling_rotor/rolling_rotor.scad``; this module mirrors its
outlines and its pose in the same degrees, for what Python has to know without OpenSCAD --
the envelope, the interfaces, and the gap -- and ``tests/test_rolling_rotor_part.py``
holds the two together through the SCAD's ``-D echo_shapes=true``.

The rotor is a disc of radius ``bore - eccentricity`` standing in a track of radius
``bore``. Its centre stands ``eccentricity`` from the axis at the angle ``orbit``, where it
touches the track; rolling on the track without slip, it has turned ``-orbit *
eccentricity / rotor radius`` of its own, so each orbit turns it back by that over 360
degrees. The no-slip roll is what the pose assumes: a track that slips turns the rotor
less, which only a bench can say. Above the track the stator's pole teeth stand back by
``gap``: the gap between the poles and the rotor is least where it touches the track and
goes round the stator with it.

What is measured here is geometry (``apothecary.gap_geometry``): the gap at every point of
the stator's poles for any orbit, its least and where that is, where the closest approach
travels through an orbit on the stator and on the rotor, that nothing but the track ever
touches the rotor, a slot's cross-section, and the volumes printed. Nothing here says how
hard the poles pull or how much torque the roll gives.

Units: mm and degrees.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from pydantic import BaseModel, Field, model_validator

from apothecary.fittings import WALL
from apothecary.gap_geometry import (
    GapProfile,
    Point,
    Pose,
    Travel,
    area,
    circle,
    clearance,
    follow,
    radial_gap,
)
from apothecary.models import BoundingBox3D, Color, Vector3D
from apothecary.models.interfaces import InterfaceBase, Socket

from .base import BasePart
from .skeleton import ROOT

MM = {"unit": "mm"}
DEG = {"unit": "deg"}

# Hidden in the SCAD: between the stator and the rotor as they print.
SPACING = 6.0


class Params(BaseModel):
    """The SCAD's top-level assignments, with its defaults."""

    bore: float = Field(
        30.0,
        ge=10,
        le=90,
        description="radius of the track the rotor rolls on",
        json_schema_extra=MM,
    )
    eccentricity: float = Field(
        1.0,
        ge=0.2,
        le=6,
        description="the track's radius less the rotor's: how far the rotor's centre "
        "stands off the axis",
        json_schema_extra=MM,
    )
    gap: float = Field(
        0.5,
        ge=0,
        le=5,
        description="how far the pole tips stand back from the track",
        json_schema_extra=MM,
    )
    stack: float = Field(
        12.0,
        ge=3,
        le=40,
        description="height of the rotor, and of the poles above the floor",
        json_schema_extra=MM,
    )
    orbit: float = Field(
        0.0,
        ge=0,
        le=360,
        description="where the rotor's centre stands about the axis, which is where it "
        "touches the track",
        json_schema_extra=DEG,
    )
    poles: int = Field(8, ge=3, le=24, description="pole teeth")
    pole_width: float = Field(
        8.0, ge=2, le=30, description="width of a tooth", json_schema_extra=MM
    )
    pole_depth: float = Field(
        10.0,
        ge=3,
        le=40,
        description="a tooth's depth from its tip to the yoke",
        json_schema_extra=MM,
    )
    yoke: float = Field(
        5.0, ge=2, le=20, description="the ring behind the teeth", json_schema_extra=MM
    )
    base: float = Field(
        2.0, ge=1, le=6, description="the floor the rotor stands on", json_schema_extra=MM
    )
    track_height: float = Field(
        2.0, ge=0.6, le=10, description="height of the track above the floor", json_schema_extra=MM
    )
    hole: float = Field(
        10.0,
        ge=0,
        le=60,
        description="diameter of the rotor's centre hole, 0 for none",
        json_schema_extra=MM,
    )
    outputs: int = Field(4, ge=0, le=12, description="holes an output's pins run in, 0 for none")
    output_pin: float = Field(
        4.0, ge=1, le=12, description="diameter of the output's pins", json_schema_extra=MM
    )
    output_circle: float = Field(
        16.0,
        ge=3,
        le=80,
        description="radius of the circle the holes stand on",
        json_schema_extra=MM,
    )
    facets: int = Field(180, ge=36, le=720, multiple_of=12, description="sides of a circle")

    @model_validator(mode="after")
    def _drawable(self) -> "Params":
        problems = problems_of(self)
        if problems:
            raise ValueError("; ".join(problems))
        return self

    # ---- derived, as the SCAD derives them ----

    @property
    def tip_r(self) -> float:
        return self.bore + self.gap

    @property
    def yoke_r(self) -> float:
        return self.tip_r + self.pole_depth

    @property
    def outer_r(self) -> float:
        return self.yoke_r + self.yoke

    @property
    def rotor_r(self) -> float:
        return self.bore - self.eccentricity

    @property
    def output_d(self) -> float:
        return self.output_pin + 2 * self.eccentricity

    @property
    def height(self) -> float:
        return self.base + self.stack


def problems_of(p: Params) -> List[str]:
    """What keeps a set of values from drawing a part that prints: teeth that meet, a
    hole that breaks through, a wall under ``fittings.WALL``."""
    out = []
    tip_r = p.bore + p.gap
    rotor_r = p.bore - p.eccentricity
    pitch = 360 / p.poles
    half = math.degrees(math.asin(min(1.0, p.pole_width / 2 / tip_r)))
    if p.pole_width / 2 >= tip_r or 2 * half >= pitch:
        out.append(
            f"{p.poles} teeth {p.pole_width:g} wide meet at their tips on a {tip_r:g} radius"
        )
    output_r = (p.output_pin + 2 * p.eccentricity) / 2
    if p.outputs:
        if p.output_circle + output_r + WALL > rotor_r:
            out.append(
                f"the output holes ({2 * output_r:g} across on a {p.output_circle:g} circle) "
                f"leave less than {WALL:g} of rotor outside them"
            )
        if p.output_circle - output_r - WALL < p.hole / 2:
            out.append(f"the output holes leave less than {WALL:g} round the centre hole")
        if p.outputs > 1:
            between = 2 * p.output_circle * math.sin(math.pi / p.outputs) - 2 * output_r
            if between < WALL:
                out.append(f"the {p.outputs} output holes leave less than {WALL:g} between them")
    if p.hole / 2 + WALL > rotor_r:
        out.append(f"the centre hole leaves less than {WALL:g} of rotor")
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


def bore_outline(p: Params) -> List[Point]:
    """The free space the poles leave, as the SCAD's ``bore_outline``: each tooth's tip,
    its straight sides, the slot's bottom to the next tooth."""
    pitch = 360 / p.poles
    bt = math.degrees(math.asin(p.pole_width / 2 / p.tip_r))
    by = math.degrees(math.asin(p.pole_width / 2 / p.yoke_r))
    out: List[Point] = []
    for k in range(p.poles):
        c = k * pitch
        out += arc(p, p.tip_r, c - bt, c + bt) + arc(p, p.yoke_r, c + by, c + pitch - by)
    return out


def hole_outline(p: Params, d: float, centre: Point = (0.0, 0.0)) -> List[Point]:
    """A hole as the SCAD's ``round_hole`` draws it: round its circle."""
    return circle(d / 2 / math.cos(math.pi / p.facets), p.facets, centre)


def track_outline(p: Params) -> List[Point]:
    """The track's inside, the circle the rotor rolls on, drawn as a hole is."""
    return hole_outline(p, 2 * p.bore)


def rotor_outline(p: Params) -> List[Point]:
    """The rotor's rim in its own frame, its centre at the origin."""
    return circle(p.rotor_r, p.facets)


def turn(p: Params, orbit: Optional[float] = None) -> float:
    """The rotor's own turn when its centre stands at ``orbit``: rolled on the track
    without slip, ``-orbit * eccentricity / rotor radius``."""
    orbit = p.orbit if orbit is None else orbit
    return -orbit * p.eccentricity / p.rotor_r


def pose(p: Params, orbit: Optional[float] = None) -> Pose:
    """Where the rotor stands, assembled, at ``orbit``."""
    orbit = p.orbit if orbit is None else orbit
    return Pose(p.eccentricity * _cos(orbit), p.eccentricity * _sin(orbit), turn(p, orbit))


def output_centres(p: Params) -> List[Point]:
    """The output holes' centres in the rotor's own frame."""
    return [
        (p.output_circle * _cos(360 * k / p.outputs), p.output_circle * _sin(360 * k / p.outputs))
        for k in range(p.outputs)
    ]


def print_offset(p: Params) -> float:
    """How far along x the rotor's centre stands from the stator's as they print."""
    return p.outer_r + SPACING + p.rotor_r


# ---- what is measured --------------------------------------------------------------------


def pole_gap(p: Params, orbit: Optional[float] = None) -> GapProfile:
    """At each point of the poles' outline, how far the rotor is: least at the tip
    nearest where the rotor touches the track."""
    return clearance(bore_outline(p), pose(p, orbit).place(rotor_outline(p)))


def pole_radial_gap(p: Params, orbit: Optional[float] = None, n: int = 360) -> GapProfile:
    """The gap along rays from the axis: what a permeance model reads, slots and all."""
    return radial_gap(bore_outline(p), pose(p, orbit).place(rotor_outline(p)), n)


def orbits(step: float = 5.0) -> List[float]:
    """One orbit in steps, both ends included."""
    n = round(360 / step)
    return [360.0 * k / n for k in range(n + 1)]


def pole_travel(p: Params, step: float = 5.0) -> Travel:
    """Where the poles and the rotor come closest, through one orbit."""
    return follow(bore_outline(p), rotor_outline(p), [pose(p, a) for a in orbits(step)])


def track_travel(p: Params, step: float = 5.0) -> Travel:
    """Where the rotor touches the track, through one orbit: a roll, by construction of
    the pose, which the measure reads back from the outlines."""
    return follow(track_outline(p), rotor_outline(p), [pose(p, a) for a in orbits(step)])


def slot_outline(p: Params) -> List[Point]:
    """One slot's cross-section, between the first tooth and the next, out from the
    circle of the tips: the room the coils share."""
    pitch = 360 / p.poles
    bt = math.degrees(math.asin(p.pole_width / 2 / p.tip_r))
    by = math.degrees(math.asin(p.pole_width / 2 / p.yoke_r))
    return arc(p, p.yoke_r, by, pitch - by) + arc(p, p.tip_r, pitch - bt, bt)


def slot_area(p: Params) -> float:
    return area(slot_outline(p))


def volumes(p: Params) -> Dict[str, float]:
    """The volume of each piece as drawn, in mm^3: solid, so a print's mass is this times
    the filament's density times how full the slicer fills it."""
    outer = area(circle(p.outer_r, p.facets))
    track_hole = area(track_outline(p))
    stator = (
        p.base * outer
        + p.track_height * (outer - track_hole)
        + (p.stack - p.track_height) * (outer - area(bore_outline(p)))
    )
    holes = (area(hole_outline(p, p.hole)) if p.hole > 0 else 0.0) + p.outputs * area(
        hole_outline(p, p.output_d)
    )
    rotor = p.stack * (area(rotor_outline(p)) - holes)
    return {"stator": stator, "rotor": rotor}


# ---- the part ------------------------------------------------------------------------------


class RollingRotorPart(BasePart):
    """The stator and the rotor side by side as they print; at rest, assembled."""

    def get_bounds(self, params: Optional[Dict] = None) -> BoundingBox3D:
        p = Params(**(params or {}))
        return BoundingBox3D(
            min_point=Vector3D(x=-p.outer_r, y=-p.outer_r, z=0.0),
            max_point=Vector3D(x=print_offset(p) + p.rotor_r, y=p.outer_r, z=p.height),
        )

    def interfaces(self, params: Optional[Mapping[str, Any]] = None) -> List[InterfaceBase]:
        """The rotor's holes, where what it drives meets it, in the print pose: its centre
        hole, and the holes an output's pins run in, each a pin's diameter plus twice the
        eccentricity, so the pin goes round its wall once an orbit and stays loose."""
        p = Params(**(params or {}))
        x0 = print_offset(p)
        drawn: Dict[str, Any] = {"source": "drawn", "version": "1"}
        up = Vector3D(x=0.0, y=0.0, z=1.0)
        found: List[InterfaceBase] = []
        if p.hole > 0:
            found.append(
                Socket(
                    name="centre",
                    position=Vector3D(x=x0, y=0.0, z=p.stack),
                    normal=up,
                    diameter=p.hole,
                    depth=p.stack,
                    notes="through the rotor: a bearing on an eccentric, when a crank "
                    "drives the orbit instead of the poles",
                    **drawn,
                )
            )
        for k, (cx, cy) in enumerate(output_centres(p) if p.outputs else []):
            found.append(
                Socket(
                    name=f"output_{k + 1}",
                    position=Vector3D(x=x0 + cx, y=cy, z=p.stack),
                    normal=up,
                    diameter=round(p.output_d, 6),
                    depth=p.stack,
                    notes=f"a {p.output_pin:g} pin of the output disc runs round in it",
                    **drawn,
                )
            )
        return found


def create(metadata_root: Path) -> RollingRotorPart:
    folder = metadata_root / "parts" / "rolling_rotor"
    return RollingRotorPart(
        name="rolling_rotor",
        source_file=folder / "rolling_rotor.scad",
        description=(
            "A rotor that rolls round inside its stator instead of turning on a shaft: "
            "the gap to the poles closes where it touches the track and travels with it"
        ),
        params_model=Params,
        category="electromechanical",
        tags=["motor", "rotor", "stator", "rolling", "eccentric", "parametric"],
        readme_path=folder / "README.md",
        rest={"print": False},
        preview_color=Color.from_hex("#D9925A"),
    )


DEFAULT = create(ROOT)
