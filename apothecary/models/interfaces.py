"""Interfaces: the places where one part meets another, and whether two meet.

An interface is a named place on a part where another part meets it: a spigot
that goes into something, a socket that takes something in, a bolt hole, a slot.
It is given in the part's own frame -- its SCAD's, the pose it prints in -- by a
``position`` on the part and a ``normal`` pointing out of the part, toward
whatever meets it. Its ``source`` says where its numbers came from, as a black
box's does (``models/blackbox.py``): a stub is guessed, measured is measured, a
standard is cited (``cite``) rather than copied (docs/fitting-a-part.md).

``fit(a, b)`` answers for two interfaces whether they meet and where, by the rule
for that pair of types. A spigot and a socket have one (``SPIGOT_SOCKET``); the
other types are declared and placed but have no rule yet, and say so.

The words are snowplow.yaml's, which declared interfaces before this module:
``name``, ``type``, ``version``, ``position``, ``normal``. docs/connections.md is
the reference for the whole seam: interfaces, fits, and the connections between
parts in an assembly.
"""

from __future__ import annotations

import math
from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, Field, TypeAdapter, field_validator, model_validator

from .vectors import Vector3D

Source = Literal["stub", "measured", "datasheet", "standard"]

# Within this, two lengths in millimetres are the same length.
EPSILON = 1e-6


def unit(v: Vector3D) -> Vector3D:
    """``v`` scaled to length one; ValueError for a zero vector, which points nowhere."""
    length = math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z)
    if length < EPSILON:
        raise ValueError("a normal of zero length points nowhere")
    return Vector3D(x=v.x / length, y=v.y / length, z=v.z / length)


class InterfaceBase(BaseModel):
    """What every interface says, whatever its type."""

    name: str = Field(..., min_length=1)
    version: str = Field("1", description="the interface's own revision, as snowplow.yaml's")
    position: Vector3D = Field(..., description="where it is, in the part's own frame")
    normal: Vector3D = Field(
        ..., description="out of the part, toward whatever meets it; kept as a unit vector"
    )
    source: Source = Field(
        "stub",
        description="where its numbers came from: stub (guessed), measured, datasheet, "
        "standard (then cite says which)",
    )
    cite: Optional[str] = Field(None, description="the standard or drawing its numbers are from")
    excludes: List[str] = Field(
        default_factory=list,
        description="interfaces of the same part that cannot be in use with this one",
    )
    notes: Optional[str] = None

    @field_validator("normal")
    @classmethod
    def _unit_normal(cls, value: Vector3D) -> Vector3D:
        return unit(value)

    @model_validator(mode="after")
    def _cites_its_standard(self) -> "InterfaceBase":
        if self.source == "standard" and not self.cite:
            raise ValueError(f"{self.name}: a standard's numbers name it in cite")
        if self.name in self.excludes:
            raise ValueError(f"{self.name}: an interface cannot exclude itself")
        return self

    @property
    def is_stub(self) -> bool:
        return self.source == "stub"


class Spigot(InterfaceBase):
    """Round, and goes into a socket. Its outer diameter runs from ``d_base`` at
    ``position`` to ``d_tip`` at ``position + normal * length``: a taper when the
    tip is narrower. Past its base the part widens (a shoulder or a collar), so
    it goes in no further than ``length``. ``reach`` is how far the part goes on
    past ``position`` along the normal, at least ``length``; what lies between
    the tip and the reach -- a narrower spigot beyond this one -- is ``lead``
    long and at most ``lead_d`` across, and goes into the socket first."""

    type: Literal["spigot"] = "spigot"
    d_base: float = Field(..., gt=0, description="outer diameter at position, mm")
    d_tip: float = Field(..., gt=0, description="outer diameter at the tip, mm")
    length: float = Field(..., gt=0, description="position to the tip along the normal, mm")
    reach: Optional[float] = Field(
        None,
        gt=0,
        description="how far the part goes past position along the normal; None: to the tip",
    )
    lead_d: Optional[float] = Field(
        None, gt=0, description="the widest diameter of what lies past the tip, mm"
    )

    @model_validator(mode="after")
    def _reach_past_the_tip(self) -> "Spigot":
        if self.reach is not None and self.reach < self.length - EPSILON:
            raise ValueError(
                f"{self.name}: reach {self.reach} stops short of the tip at {self.length}"
            )
        if self.lead > EPSILON and self.lead_d is None:
            raise ValueError(f"{self.name}: what lies past the tip says how wide it is (lead_d)")
        return self

    @property
    def lead(self) -> float:
        """How far the part goes on past the tip."""
        return 0.0 if self.reach is None else max(0.0, self.reach - self.length)

    @property
    def tip(self) -> Vector3D:
        return self.position + self.normal * self.length

    def diameter_at(self, inserted: float) -> float:
        """The outer diameter where the socket's mouth stands once the tip has gone
        ``inserted`` in: ``d_tip`` at 0, ``d_base`` at ``length``."""
        t = min(max(inserted / self.length, 0.0), 1.0)
        return self.d_tip + (self.d_base - self.d_tip) * t


class Socket(InterfaceBase):
    """Round, and takes a spigot in. Its bore is ``diameter`` at the mouth
    (``position``) and holds over ``depth``; the normal points out of the mouth.
    ``floor`` is the narrowest opening past ``depth``: anything wider stops
    there. None: nothing stops a spigot past the depth (a hose, a duct that
    widens). ``stretch`` is the fraction the bore opens when pushed: 0 for
    something rigid, a hose's own for a hose."""

    type: Literal["socket"] = "socket"
    diameter: float = Field(..., gt=0, description="bore at the mouth, mm")
    depth: float = Field(..., gt=0, description="how far in the bore holds, mm")
    floor: Optional[float] = Field(
        None, ge=0, description="narrowest opening past depth, mm; None: nothing stops"
    )
    stretch: float = Field(
        0.0, ge=0, lt=1, description="the fraction the bore opens when pushed; 0: rigid"
    )

    @property
    def widest(self) -> float:
        """The widest spigot the bore takes, stretched as far as it goes."""
        return self.diameter * (1 + self.stretch)


class BoltHole(InterfaceBase):
    """A hole a bolt passes through along the normal. Declared and placed; no fit rule yet."""

    type: Literal["bolt_hole"] = "bolt_hole"
    diameter: float = Field(..., gt=0)


class Slot(InterfaceBase):
    """A slot an edge goes into along the normal. Declared and placed; no fit rule yet."""

    type: Literal["slot"] = "slot"
    width: float = Field(..., gt=0)
    length: float = Field(..., gt=0)


Interface = Annotated[Union[Spigot, Socket, BoltHole, Slot], Field(discriminator="type")]

INTERFACES = TypeAdapter(List[Interface])


def read_interfaces(data) -> List[InterfaceBase]:
    """A list of interfaces from plain data (a part.json's, a request's); a
    pydantic ValidationError names what is wrong. Names are one per part, and
    ``excludes`` names only interfaces of the same part."""
    interfaces = INTERFACES.validate_python(data or [])
    names = [i.name for i in interfaces]
    doubled = sorted({n for n in names if names.count(n) > 1})
    if doubled:
        raise ValueError(f"interface names are one per part: {', '.join(doubled)} more than once")
    for i in interfaces:
        unknown = sorted(set(i.excludes) - set(names))
        if unknown:
            raise ValueError(
                f"{i.name} excludes {', '.join(unknown)}, which the part does not have"
            )
    return interfaces


Verdict = Literal[
    "seats", "loose", "will not enter", "shallow", "tip blocked", "do not mate", "no rule"
]


class Fit(BaseModel):
    """What the rule for a pair of interfaces says. ``seat`` is how far the
    spigot's tip goes past the socket's mouth, ``gap`` how far its shoulder then
    stands from the mouth, ``interference`` how much wider than the bore the
    spigot is where the mouth meets it (mm across), and ``stretch`` that as a
    fraction of the bore: what a compliant socket opens by."""

    verdict: Verdict
    a: str
    b: str
    spigot: Optional[str] = None
    socket: Optional[str] = None
    seat: Optional[float] = None
    gap: Optional[float] = None
    interference: Optional[float] = None
    stretch: Optional[float] = None
    reason: str

    @property
    def seats(self) -> bool:
        return self.verdict == "seats"


def _round(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(value, 3)


def _inserted_at(spigot: Spigot, diameter: float, *, past: bool = False) -> float:
    """How far the tip has gone in when the spigot's diameter at the mouth reaches
    ``diameter`` -- or, ``past``, goes beyond it -- capped at its length. A straight
    spigot reaches a diameter it is as wide as at once, and never goes beyond it."""
    rise = spigot.d_base - spigot.d_tip
    if abs(rise) < EPSILON:
        if past:
            return 0.0 if spigot.d_tip > diameter + EPSILON else spigot.length
        return 0.0 if spigot.d_tip >= diameter - EPSILON else spigot.length
    return min(max((diameter - spigot.d_tip) / rise * spigot.length, 0.0), spigot.length)


def spigot_socket(spigot: Spigot, socket: Socket) -> Fit:
    """The rule for a spigot in a socket.

    The spigot goes in tip first. It touches the bore where its diameter at the
    mouth reaches the bore (``contact``), and goes on, opening a compliant
    socket, until its diameter reaches the widest the bore opens to, its
    shoulder reaches the mouth, or something past the socket's depth stops its
    tip or what leads it. It seats where it stops, if it touched the bore
    within the socket's depth before then.
    """
    names = {"a": spigot.name, "b": socket.name, "spigot": spigot.name, "socket": socket.name}
    bore, widest = socket.diameter, socket.widest
    if spigot.d_tip > widest + EPSILON:
        return Fit(
            verdict="will not enter",
            reason=f"its tip is {spigot.d_tip:g} across and the bore opens to {widest:g}",
            **names,
        )
    if spigot.lead > EPSILON and spigot.lead_d > widest + EPSILON:
        return Fit(
            verdict="will not enter",
            reason=f"what leads its tip is {spigot.lead_d:g} across and the bore opens to "
            f"{widest:g}",
            **names,
        )
    if spigot.d_base < bore - EPSILON:
        return Fit(
            verdict="loose",
            reason=f"it is {spigot.d_base:g} across at its widest and the bore is {bore:g}: "
            "nothing touches",
            **names,
        )
    contact = _inserted_at(spigot, bore)
    wedged = _inserted_at(spigot, widest, past=True)
    stops = [(spigot.length, "its shoulder reaches the mouth")]
    if socket.floor is not None:
        if spigot.d_tip > socket.floor + EPSILON:
            stops.append((socket.depth, f"its tip meets the {socket.floor:g} past the depth"))
        if spigot.lead > EPSILON and spigot.lead_d > socket.floor + EPSILON:
            stops.append(
                (
                    socket.depth - spigot.lead,
                    f"what leads its tip, {spigot.lead_d:g} across, meets the "
                    f"{socket.floor:g} past the depth",
                )
            )
    stop, why = min(stops, key=lambda s: s[0])
    if contact > socket.depth + EPSILON:
        return Fit(
            verdict="shallow",
            seat=_round(min(stop, spigot.length)),
            reason=f"it touches the bore {contact:.1f} in, past the {socket.depth:g} the bore "
            "holds over",
            **names,
        )
    if stop < contact - EPSILON:
        return Fit(
            verdict="tip blocked",
            seat=_round(max(stop, 0.0)),
            reason=f"it stops {max(stop, 0.0):.1f} in, before it touches the bore at "
            f"{contact:.1f}: {why}",
            **names,
        )
    seat = min(wedged, stop)
    at_mouth = spigot.diameter_at(seat)
    interference = max(0.0, at_mouth - bore)
    if wedged <= stop + EPSILON and wedged < spigot.length - EPSILON:
        why = (
            f"its diameter reaches {at_mouth:.2f}, the widest the bore opens to"
            if socket.stretch
            else f"its diameter reaches the bore's {bore:g}"
        )
    return Fit(
        verdict="seats",
        seat=_round(seat),
        gap=_round(spigot.length - seat),
        interference=_round(interference),
        stretch=_round(interference / bore),
        reason=f"it goes {seat:.1f} in and stops: {why}",
        **names,
    )


# The rules, keyed by the pair of types in the order the rule takes them.
RULES = {("spigot", "socket"): spigot_socket}

# Pairs of types that have no rule because they do not mate at all.
UNMATED = {("spigot", "spigot"), ("socket", "socket")}


def fit(a: InterfaceBase, b: InterfaceBase) -> Fit:
    """Whether ``a`` and ``b`` meet, and where, by the rule for their pair of types,
    in either order. A pair that cannot mate says so; a pair with no rule yet too."""
    key = (a.type, b.type)
    if key in RULES:
        result = RULES[key](a, b)
    elif key[::-1] in RULES:
        result = RULES[key[::-1]](b, a)
    elif key in UNMATED:
        return Fit(
            verdict="do not mate",
            a=a.name,
            b=b.name,
            reason=f"a {a.type} meets a {'socket' if a.type == 'spigot' else 'spigot'}, "
            f"not another {b.type}",
        )
    else:
        return Fit(
            verdict="no rule",
            a=a.name,
            b=b.name,
            reason=f"no rule says how a {a.type} meets a {b.type} yet",
        )
    return result.model_copy(update={"a": a.name, "b": b.name})


def seated_frame(spigot: Spigot, socket: Socket, seat: float) -> tuple[Vector3D, Vector3D]:
    """Where a spigot seated ``seat`` into a socket has its position and normal, in
    the socket's frame: it points into the socket, its tip ``seat`` past the mouth."""
    position = socket.position + socket.normal * (spigot.length - seat)
    return position, -socket.normal


__all__ = [
    "BoltHole",
    "Fit",
    "INTERFACES",
    "Interface",
    "InterfaceBase",
    "RULES",
    "Slot",
    "Socket",
    "Source",
    "Spigot",
    "fit",
    "read_interfaces",
    "seated_frame",
    "spigot_socket",
    "unit",
]
