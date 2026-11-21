"""A dust adapter between two round ends: its parameters are its two ends.

End ``a`` stands on the bed and points down; end ``b`` points up. Each is a spigot
that goes into what it meets (a hose's bore, a port's) or a socket that takes what
it meets in (a tool's outlet stub), and each is sized by what it meets: ``a_d``
and ``b_d`` are the bore a spigot goes into, or the outside a socket takes. A
spigot end straddles that bore, ``taper`` wider at its base than at its tip, so
it touches a rigid bore halfway in and wedges there; a socket end's bore is the
diameter it takes. That is the nominal rule (``NOMINAL``): no clearance is
added, so the first print says whether the printer draws a bore and an outside
true, and a hose's real give.

A spigot end ``a`` has a collar past its base, which a hose stops against and is
clamped before. Between the two ends a transition narrows, its bore closing in at
45 degrees or less; an optional ``step`` -- a spigot of its own diameter -- stands
between the transition and a spigot end ``b``, so one adapter goes into either of
two fittings, one at a time. The defaults are the stepped adapter for a 40 mm hose
onto a 32 mm or a 25 mm port, every end pushing in; its presets are that and the
plain 40 to 32. ``apothecary/adapters.py`` generates the parameters between any two
round ends. Built in Python from one profile (``apothecary.fittings``), so the
solid and its interfaces come from the same numbers;
parts/dust/hose_adapter/hose_adapter.scad is that solid at the defaults, rewritten
by ``apothecary parts render hose_adapter -o parts/dust/hose_adapter/hose_adapter.scad``.

It prints as it is drawn: end ``a`` on the bed, axis up. Every outside narrows
going up but the collar's underside, at 45 degrees, and every bore closes in at
45 degrees or less: nothing needs support. parts/dust/README.md says what each
number is and what a step costs in airflow.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from pydantic import BaseModel, Field, model_validator

from apothecary.core import OpenSCADObject
from apothecary.fittings import WALL, Profile, Section, facets
from apothecary.models import BoundingBox3D, Color, PrintSettings, Vector3D
from apothecary.models.interfaces import InterfaceBase
from apothecary.projects.parts.base import BasePart, Preset
from apothecary.projects.parts.skeleton import ROOT

MM = {"unit": "mm"}

# The nominal rule, in words: what a generated adapter says it applied.
NOMINAL = (
    "a spigot end straddles the bore it meets by half its taper either side, so it "
    "touches a rigid bore halfway in; a socket end's bore is the outside it takes, at "
    "that spigot's middle; no clearance is added"
)


class Params(BaseModel):
    """Each end sized by what it meets. A spigot end is its nominal bore, wider by half
    its taper at its base and narrower by half at its tip, its own bore leaving a wall
    of ``wall`` at the tip; a socket end's bore is its nominal, ``wall`` round it."""

    a_socket: bool = Field(
        False,
        description="end a, on the bed, takes what it meets in; off: it goes into it",
    )
    a_d: float = Field(
        40.0,
        gt=0,
        json_schema_extra=MM,
        description="what end a meets: the bore it goes into, or the outside it takes",
    )
    a_length: float = Field(40.0, gt=0, json_schema_extra=MM)
    a_taper: float = Field(
        2.0,
        ge=0,
        json_schema_extra=MM,
        description="how much wider a spigot end a is at its base than at its tip",
    )
    collar: float = Field(
        5.0,
        gt=0,
        json_schema_extra=MM,
        description="how much wider the collar past a spigot end a is than its base: what "
        "a hose stops against",
    )
    collar_length: float = Field(2.5, gt=0, json_schema_extra=MM)
    transition_length: float = Field(8.0, gt=0, json_schema_extra=MM)
    step: bool = Field(
        True,
        description="a stepped spigot between the transition and a spigot end b, so it goes "
        "into either of two fittings",
    )
    step_d: float = Field(
        32.0, gt=0, json_schema_extra=MM, description="the bore the step goes into"
    )
    step_length: float = Field(25.0, gt=0, json_schema_extra=MM)
    b_socket: bool = Field(
        False, description="end b, at the top, takes what it meets in; off: it goes into it"
    )
    b_d: float = Field(
        25.0,
        gt=0,
        json_schema_extra=MM,
        description="what end b meets: the bore it goes into, or the outside it takes",
    )
    b_length: float = Field(20.0, gt=0, json_schema_extra=MM)
    taper: float = Field(
        1.2,
        ge=0,
        json_schema_extra=MM,
        description="how much wider the step and a spigot end b are at their base than "
        "at their tip",
    )
    wall: float = Field(WALL, gt=0, json_schema_extra=MM)

    @model_validator(mode="after")
    def _prints(self) -> "Params":
        if self.step and self.b_socket:
            raise ValueError("a step leads a spigot end b into its fitting; end b is a socket")
        for end, socket, d, taper in self._ends():
            bore = d if socket else _spigot(d, taper)[1] - 2 * self.wall
            if bore <= 0:
                raise ValueError(
                    f"end {end}, a spigot into a {d:g} bore, leaves no bore inside a "
                    f"{self.wall:g} wall"
                )
        problems = profile(self).problems(wall=self.wall)
        if problems:
            raise ValueError("it would not print: " + "; ".join(problems))
        return self

    def _ends(self):
        yield "a", self.a_socket, self.a_d, self.a_taper
        if self.step:
            yield "step", False, self.step_d, self.taper
        yield "b", self.b_socket, self.b_d, self.taper


def _spigot(d: float, taper: float) -> Tuple[float, float]:
    """(base, tip) outer diameters of a spigot for a bore of ``d``."""
    return (d + taper / 2, d - taper / 2)


def flow_bore(socket: bool, d: float, taper: float, wall: float) -> float:
    """The bore through an end: a spigot's inside, ``wall`` in from its tip; past a
    socket's depth, a lip of ``wall`` that stops what it takes."""
    return (d if socket else _spigot(d, taper)[1]) - 2 * wall


def end_outer(socket: bool, d: float, taper: float, wall: float) -> float:
    """An end's widest outside: a socket's wall round its bore, a spigot's base."""
    return d + 2 * wall if socket else _spigot(d, taper)[0]


def profile(p: Params) -> Profile:
    """The adapter as a stack of sections, end a on the bed."""
    w = p.wall
    a_flow = flow_bore(p.a_socket, p.a_d, p.a_taper, w)
    if p.a_socket:
        a_outer = p.a_d + 2 * w
        # The socket's mouth is on the bed; its bore holds up to the transition.
        sections = [
            Section(name="a", length=p.a_length, outer=(a_outer, a_outer), bore=(p.a_d, p.a_d))
        ]
        top_outer, top_bore = a_outer, p.a_d
    else:
        a = _spigot(p.a_d, p.a_taper)
        collar = a[0] + p.collar
        sections = [
            # A spigot end a points down: its tip is on the bed and its base at the top.
            Section(name="a", length=p.a_length, outer=(a[1], a[0]), bore=(a_flow, a_flow)),
            Section(name="flare", length=p.collar / 2, outer=(a[0], collar), bore=(a_flow, a_flow)),
            Section(
                name="collar", length=p.collar_length, outer=(collar, collar), bore=(a_flow, a_flow)
            ),
        ]
        top_outer, top_bore = collar, a_flow
    # What stands on the transition: the step, else end b.
    if p.step:
        step = _spigot(p.step_d, p.taper)
        step_bore = step[1] - 2 * w
        next_outer, next_bore = step[0], step_bore
    elif p.b_socket:
        # Under a socket end b, a lip of the wall stops what it takes: the bore widens to
        # the socket's above it, a ledge facing up.
        next_outer, next_bore = p.b_d + 2 * w, flow_bore(True, p.b_d, p.taper, w)
    else:
        b = _spigot(p.b_d, p.taper)
        next_outer, next_bore = b[0], b[1] - 2 * w
    sections.append(
        Section(
            name="transition",
            length=p.transition_length,
            outer=(top_outer, next_outer),
            bore=(top_bore, next_bore),
        )
    )
    if p.step:
        sections.append(
            Section(name="step", length=p.step_length, outer=step, bore=(step_bore, step_bore))
        )
    if p.b_socket:
        outer = p.b_d + 2 * w
        sections.append(
            Section(name="b", length=p.b_length, outer=(outer, outer), bore=(p.b_d, p.b_d))
        )
    else:
        b = _spigot(p.b_d, p.taper)
        b_bore = b[1] - 2 * w
        if p.step:
            sections.append(
                # As short as a bore may close in, at 45 degrees.
                Section(
                    name="shoulder",
                    length=max((step_bore - b_bore) / 2, w),
                    outer=(step[1], b[0]),
                    bore=(step_bore, b_bore),
                )
            )
        sections.append(Section(name="b", length=p.b_length, outer=b, bore=(b_bore, b_bore)))
    widest = max(max(s.outer) for s in sections)
    return Profile(sections=sections, fn=facets(widest))


class HoseAdapterPart(BasePart):
    """The adapter, built from its profile."""

    def geometry(self, params: Mapping[str, Any]) -> OpenSCADObject:
        return profile(Params(**params)).solid()

    def interfaces(self, params: Optional[Mapping[str, Any]] = None) -> List[InterfaceBase]:
        p = Params(**(params or {}))
        shape = profile(p)
        drawn = {"source": "drawn", "version": "1"}
        if p.a_socket:
            found = [shape.socket("a", top=False, **drawn)]
        else:
            found = [
                shape.spigot(
                    "a",
                    "a",
                    up=False,
                    notes="a hose pushes on to the collar and is clamped over it",
                    **drawn,
                )
            ]
        if p.step:
            found.append(shape.spigot("step", "step", excludes=["b"], **drawn))
        if p.b_socket:
            found.append(shape.socket("b", top=True, **drawn))
        else:
            found.append(shape.spigot("b", "b", excludes=["step"] if p.step else [], **drawn))
        return found

    def get_bounds(self, params: Optional[Dict] = None) -> BoundingBox3D:
        shape = profile(Params(**(params or {})))
        r = shape.widest / 2
        return BoundingBox3D(
            min_point=Vector3D(x=-r, y=-r, z=0.0),
            max_point=Vector3D(x=r, y=r, z=shape.height),
        )


PRESETS = {
    "stepped_40_32_25": Preset(
        description="a 40 mm hose onto a 32 mm or a 25 mm port, one at a time: its defaults",
        params={},
        label="40 → 32/25",
    ),
    "plain_40_32": Preset(
        description="a 40 mm hose onto a 32 mm port, no step: the stepped one sawn at the shoulder",
        params={"step": False, "b_d": 32.0, "b_length": 25.0},
        label="40 → 32",
    ),
}


def create(metadata_root: Path) -> HoseAdapterPart:
    folder = metadata_root / "parts" / "dust" / "hose_adapter"
    return HoseAdapterPart(
        name="hose_adapter",
        source_file=folder / "hose_adapter.scad",
        description="A dust adapter between two round ends, its parameters its two ends; "
        "at its defaults a 40 mm hose onto a 32 mm or a 25 mm port (Python parametric)",
        params_model=Params,
        category="dust",
        tags=["dust", "hose", "adapter", "python"],
        readme_path=metadata_root / "parts" / "dust" / "README.md",
        preview_color=Color(r=0.85, g=0.45, b=0.1),
        # printer_1's nozzle and layers; a wall of five lines.
        print_settings=PrintSettings(
            nozzle_diameter=0.4, layer_height=0.2, wall_thickness=WALL, tolerance=0.2
        ),
        presets=PRESETS,
    )


DEFAULT = create(ROOT)

__all__ = [
    "DEFAULT",
    "HoseAdapterPart",
    "NOMINAL",
    "PRESETS",
    "Params",
    "create",
    "end_outer",
    "flow_bore",
    "profile",
]
