"""Round fittings, built with the interfaces they make.

A round part -- a hose adapter, a tube, a reducer -- is a stack of sections along
+Z, each a frustum with a bore: its outer diameter at its bottom and its top, and
its bore's. ``Profile`` holds the stack. From the one stack it gives the solid
(``solid``: cylinders under a difference, the primitives every renderer already
draws), the interfaces a run of sections makes (``spigot``, ``socket``), and
what would not print (``problems``). The geometry and the interfaces are built
from the same numbers by one object, so they cannot disagree; that the solid
OpenSCAD renders is the one declared is held by ``apothecary parts verify``,
which measures each round interface on the STL.

+Z is up as the part prints: section 0 stands on the bed. An outer surface that
widens going up overhangs, and so does a bore that narrows going up; each is
held to ``OVERHANG`` from vertical, and a step that would leave a ledge facing
down is refused. docs/connections.md is the reference.
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field, model_validator

from .booleans import Difference, Union
from .core import OpenSCADObject
from .meshes import Triangle, section_radii
from .models.interfaces import EPSILON, InterfaceBase, Socket, Spigot
from .models.vectors import Vector3D
from .primitives import Cylinder
from .transforms import Translate

# Facets per circle. OpenSCAD draws a circle as a polygon with its corners on the
# circle; at 128 a flat falls under 0.01 mm inside a 46 mm circle (SAGITTA).
FN = 128
SAGITTA = 0.01

# The steepest a surface may lean out over nothing, in degrees from vertical.
OVERHANG = 45.0

# The thinnest wall, in mm: five lines of a 0.4 mm nozzle.
WALL = 2.0

# How far a bore runs past the solid at each open end, and past each joint
# between two sections, so the difference leaves no skin.
CLEAR = 1.0
OVERLAP = 0.01


class Section(BaseModel):
    """One frustum of a round part: ``outer`` and ``bore`` are (bottom, top)
    diameters in mm; a bore of None is solid."""

    name: str
    length: float = Field(..., gt=0)
    outer: Tuple[float, float]
    bore: Optional[Tuple[float, float]] = None

    @model_validator(mode="after")
    def _sizes(self) -> "Section":
        if min(self.outer) <= 0 or (self.bore is not None and min(self.bore) <= 0):
            raise ValueError(f"{self.name}: a diameter is more than zero")
        return self


def sagitta(diameter: float, fn: int = FN) -> float:
    """How far inside a circle of ``diameter`` the middle of a facet falls at ``fn``."""
    return diameter / 2 * (1 - math.cos(math.pi / fn))


def facets(diameter: float) -> int:
    """The facets a circle of ``diameter`` is drawn with: ``FN``, or more for a circle
    so wide that ``FN`` leaves a flat more than ``SAGITTA`` inside it (a 100 mm port),
    a multiple of four so the circle is as wide across x as across y."""
    n = FN
    while sagitta(diameter, n) > SAGITTA:
        n += 4
    return n


class Profile(BaseModel):
    """A round part as a stack of sections along +Z, section 0 on the bed."""

    sections: List[Section] = Field(..., min_length=1)
    fn: int = FN

    @model_validator(mode="after")
    def _names(self) -> "Profile":
        names = [s.name for s in self.sections]
        if len(set(names)) != len(names):
            raise ValueError("each section has a name of its own")
        return self

    # --- where things are ----------------------------------------------------------

    def index(self, name: str) -> int:
        for i, s in enumerate(self.sections):
            if s.name == name:
                return i
        raise KeyError(f"no section {name!r}: {', '.join(s.name for s in self.sections)}")

    def z(self, i: int) -> float:
        """The height of section ``i``'s bottom; ``z(len(sections))`` is the top."""
        return sum(s.length for s in self.sections[:i])

    @property
    def height(self) -> float:
        return self.z(len(self.sections))

    @property
    def widest(self) -> float:
        return max(max(s.outer) for s in self.sections)

    # --- what would not print --------------------------------------------------------

    def problems(self, wall: float = WALL, overhang: float = OVERHANG) -> List[str]:
        """What would not print as the profile stands, in words; empty when it all would."""
        found: List[str] = []
        limit = math.tan(math.radians(overhang))
        for i, s in enumerate(self.sections):
            bore = s.bore or (0.0, 0.0)
            for end, at in ((0, "bottom"), (1, "top")):
                thick = (s.outer[end] - bore[end]) / 2
                if s.bore is not None and thick < wall - EPSILON:
                    found.append(f"{s.name}: the wall at its {at} is {thick:.2f}, under {wall:g}")
            if (s.outer[1] - s.outer[0]) / 2 > limit * s.length + EPSILON:
                found.append(f"{s.name}: its outside leans out past {overhang:g} degrees")
            if s.bore is not None and (bore[0] - bore[1]) / 2 > limit * s.length + EPSILON:
                found.append(f"{s.name}: its bore closes in past {overhang:g} degrees")
            if i + 1 < len(self.sections):
                above = self.sections[i + 1]
                if above.outer[0] > s.outer[1] + EPSILON:
                    found.append(f"{above.name}: a ledge over {s.name} faces down")
                above_bore = above.bore or (0.0, 0.0)
                if s.bore is not None and above_bore[0] < bore[1] - EPSILON:
                    found.append(f"{above.name}: the bore below it ends in a flat ceiling")
        if sagitta(self.widest, self.fn) > SAGITTA:
            found.append(
                f"at $fn {self.fn} a facet falls {sagitta(self.widest, self.fn):.3f} inside "
                f"the {self.widest:g} circle, over {SAGITTA:g}"
            )
        return found

    # --- the solid -----------------------------------------------------------------

    def solid(self) -> OpenSCADObject:
        """The part: each section's outside a cylinder, its bore cut out of the whole."""
        outside: List[OpenSCADObject] = []
        bores: List[OpenSCADObject] = []
        last = len(self.sections) - 1
        for i, s in enumerate(self.sections):
            z0 = self.z(i)
            outside.append(_frustum(z0, s.length, s.outer, self.fn, s.name))
            if s.bore is None:
                continue
            # An open end is cleared past the solid, a joint with another bore overlapped,
            # and a joint with a solid section met exactly: that is a blind bore's end.
            below = CLEAR if i == 0 else (OVERLAP if self.sections[i - 1].bore else 0.0)
            above = CLEAR if i == last else (OVERLAP if self.sections[i + 1].bore else 0.0)
            bores.append(
                _frustum(
                    z0 - below,
                    s.length + below + above,
                    _run_on(s, below, above),
                    self.fn,
                    f"{s.name} bore",
                )
            )
        body = outside[0] if len(outside) == 1 else Union(children=outside)
        if not bores:
            return body
        return Difference(children=[body, bores[0] if len(bores) == 1 else Union(children=bores)])

    # --- the interfaces a run of sections makes -------------------------------------

    def spigot(
        self, name: str, first: str, last: Optional[str] = None, *, up: bool = True, **kw
    ) -> Spigot:
        """The spigot sections ``first`` to ``last`` make, pointing up (out of the top)
        or down (out of the bottom); what lies past its tip leads it."""
        i, j = self.index(first), self.index(last or first)
        lo, hi = self.z(i), self.z(j + 1)
        bottom, top = self.sections[i].outer[0], self.sections[j].outer[1]
        past = self.sections[j + 1 :] if up else self.sections[:i]
        reach = (self.height - lo) if up else hi
        return Spigot(
            name=name,
            position=Vector3D(z=lo if up else hi),
            normal=Vector3D(z=1 if up else -1),
            d_base=bottom if up else top,
            d_tip=top if up else bottom,
            length=hi - lo,
            reach=reach if past else None,
            lead_d=max(max(s.outer) for s in past) if past else None,
            **kw,
        )

    def socket(self, name: str, *, top: bool = True, **kw) -> Socket:
        """The socket the bore makes at the top (or the bottom) mouth: its diameter
        there, how far it holds at that, and the narrowest it gets further in."""
        order = self.sections[::-1] if top else self.sections
        if order[0].bore is None:
            raise ValueError(f"the {'top' if top else 'bottom'} of the part has no bore")
        diameter = order[0].bore[1 if top else 0]
        depth, beyond = 0.0, []
        for s in order:
            holds = s.bore is not None and all(abs(d - diameter) < EPSILON for d in s.bore)
            if holds and not beyond:
                depth += s.length
            else:
                beyond.append(min(s.bore) if s.bore is not None else 0.0)
        if depth == 0.0:
            raise ValueError(
                f"the bore at the {'top' if top else 'bottom'} tapers from its "
                "mouth: a socket's bore holds at one diameter"
            )
        narrowest = min(beyond) if beyond else None
        return Socket(
            name=name,
            position=Vector3D(z=self.height if top else 0.0),
            normal=Vector3D(z=1 if top else -1),
            diameter=diameter,
            depth=depth,
            floor=narrowest if narrowest is not None and narrowest < diameter else None,
            **kw,
        )


# How far in from each end of an interface its diameter is read, in mm: clear of the
# joint with the next section, where a cut would catch both.
READ_IN = 0.5

# The most a diameter read on a render may differ from the one declared, mm across.
# A 0.6 mm taper over 25 mm moves its seat 2 mm for each 0.05 here; a flat of the
# 128-gon reads under 0.01 inside the circle.
INTERFACE_TOLERANCE = 0.05


class Reading(BaseModel):
    """One diameter of a round interface, as declared and as read on a mesh."""

    interface: str
    where: str
    declared: float
    measured: Optional[float] = None

    @property
    def drift(self) -> Optional[float]:
        return None if self.measured is None else abs(self.measured - self.declared)

    def holds(self, tolerance: float = INTERFACE_TOLERANCE) -> bool:
        return self.drift is not None and self.drift <= tolerance + EPSILON


def readings(interface: InterfaceBase, triangles: Sequence[Triangle]) -> List[Reading]:
    """A round interface's diameters read across the mesh, near each end: a spigot's
    outside at its base and its tip, a socket's bore at its mouth and its depth. Cut
    square to the normal about the line through the position along it, so a part
    drawn off its declared axis reads wrong too. Empty for a type that is not round."""
    n, at = interface.normal, interface.position
    if isinstance(interface, Spigot):
        m = min(READ_IN, interface.length / 4)
        ends = (("base", m, interface.length - m), ("tip", interface.length - m, m))
        out = []
        for where, along, from_tip in ends:
            cut = section_radii(triangles, (at + n * along).to_list(), n.to_list())
            out.append(
                Reading(
                    interface=interface.name,
                    where=where,
                    declared=round(interface.diameter_at(from_tip), 4),
                    measured=None if cut is None else round(2 * cut[1], 4),
                )
            )
        return out
    if isinstance(interface, Socket):
        m = min(READ_IN, interface.depth / 4)
        out = []
        for where, along in (("mouth", m), ("depth", interface.depth - m)):
            cut = section_radii(triangles, (at - n * along).to_list(), n.to_list())
            out.append(
                Reading(
                    interface=interface.name,
                    where=where,
                    declared=interface.diameter,
                    measured=None if cut is None else round(2 * cut[0], 4),
                )
            )
        return out
    return []


def _run_on(s: Section, below: float, above: float) -> Tuple[float, float]:
    """A bore's diameters carried on along its own slope ``below`` and ``above`` its section."""
    slope = (s.bore[1] - s.bore[0]) / s.length
    return (s.bore[0] - slope * below, s.bore[1] + slope * above)


def _frustum(z0: float, h: float, d: Tuple[float, float], fn: int, label: str) -> OpenSCADObject:
    r1, r2 = round(d[0] / 2, 6), round(d[1] / 2, 6)
    cyl = Cylinder(h=round(h, 6), r1=r1, r2=r2, fn=fn, comment=label)
    if abs(z0) < EPSILON:
        return cyl
    return Translate(v=Vector3D(z=round(z0, 6)), children=[cyl])


__all__ = [
    "CLEAR",
    "FN",
    "INTERFACE_TOLERANCE",
    "OVERHANG",
    "Profile",
    "READ_IN",
    "Reading",
    "SAGITTA",
    "Section",
    "WALL",
    "facets",
    "readings",
    "sagitta",
]
