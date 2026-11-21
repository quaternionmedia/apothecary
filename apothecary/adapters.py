"""The adapter between two round ends, generated from their interfaces.

An end is a round interface of a part at its parameters: ``dust_port@hose_40.end``
names the part, the preset its parameters start from, and the interface; a person's
own numbers go over the preset (a caliper's reading of the real end). ``between(x,
y)`` reads each end's interface and derives the parameters of the one adapter part,
``hose_adapter``, whose parameters are its two ends:

- an end that is a socket (a hose's bore, a port's) is met by a spigot end into
  that bore; a hose's -- a socket that opens when pushed -- by a long spigot of a
  hose's taper (``HOSE``), a rigid bore's by a short one of a fitting's
  (``FITTING``), never longer than twice the depth the bore holds over, so it
  touches the bore within it;
- an end that is a spigot (a tool's outlet stub) is met by a socket end whose bore
  is that spigot's diameter at its middle, as deep as the spigot is long;
- the end whose outside is the wider stands on the bed as end ``a``, so every
  outside narrows going up, and the transition between them is as long as its bore
  needs to close in at 45 degrees (``fittings.OVERHANG``), and no shorter than the
  adapter's own.

That is ``hose_adapter.NOMINAL``: no clearance is added, so what only a print shows
-- whether the printer draws a bore and an outside true, a hose's real give -- is
the first print's to say, and a person's to measure.

It is refused, saying why, when an end is not round; when the two ends meet each
other already; when an end would leave no bore inside the wall; when the adapter
would not print without support; and when the adapter it derives does not seat on
both ends by ``models.interfaces.fit``. That last is the round trip: an adapter is
never answered that does not fit the two ends it was made from. Given the adapter's
own parameters instead (``params``), it derives nothing and answers how those fit
the two ends: an adapter adjusted and checked again. docs/connections.md is the
reference.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Tuple

from pydantic import BaseModel, ValidationError

from .connections import ConnectionReport, place
from .fittings import OVERHANG, WALL
from .hierarchy import Assembly, Connection
from .models.interfaces import Fit, InterfaceBase, Socket, Spigot, fit

# The one adapter part generated between two ends.
ADAPTER = "hose_adapter"

# The spigot end a socket is met by: (taper, length) -- a hose's, which opens when
# pushed and is clamped over a long one, and a rigid fitting's.
HOSE = (2.0, 40.0)
FITTING = (1.2, 25.0)


class Refused(ValueError):
    """Two ends that are not joined, saying why."""


class End(BaseModel):
    """One end: a part, the parameters it stands at, and its round interface there."""

    part: str
    preset: Optional[str] = None
    # Every parameter it stands at; ``set``, those a person gave over the preset.
    params: Dict[str, Any] = {}
    set: Dict[str, Any] = {}
    interface: InterfaceBase

    @property
    def label(self) -> str:
        """``part@preset.interface``, then any number a person set over the preset."""
        named = self.part + (f"@{self.preset}" if self.preset else "")
        given = ", ".join(f"{k}={_shown(v)}" for k, v in self.set.items())
        return f"{named}.{self.interface.name}" + (f" ({given})" if given else "")


def _shown(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).lower() if isinstance(value, bool) else str(value)


def _round(interfaces: List[InterfaceBase]) -> List[InterfaceBase]:
    return [i for i in interfaces if isinstance(i, (Spigot, Socket))]


def end(
    part,
    preset: Optional[str] = None,
    interface: Optional[str] = None,
    overrides: Optional[Mapping[str, Any]] = None,
) -> End:
    """An end of ``part`` (a ``BasePart``): its preset's parameters with ``overrides``
    over them, and the interface named, or its one round interface. KeyError for a
    preset or an interface it has not got; ValueError for parameters it refuses;
    Refused for an interface that is not round, or a part with several and none named."""
    params = dict(part.preset(preset)) if preset else {}
    given = part.validate_overrides(dict(overrides)) if overrides else {}
    params.update(given)
    found = part.interfaces(params or None)
    if interface is not None:
        chosen = part.interface(interface, params or None)
        if chosen not in _round([chosen]):
            raise Refused(
                f"{part.name}.{chosen.name} is a {chosen.type.replace('_', ' ')}: an adapter "
                "is generated between round ends, a spigot or a socket"
            )
    else:
        round_ones = _round(found)
        if len(round_ones) != 1:
            names = ", ".join(i.name for i in round_ones) or "none"
            raise Refused(
                f"{part.name} has {len(round_ones)} round interfaces ({names}): name the one "
                f"meant, {part.name}.<interface>"
            )
        chosen = round_ones[0]
    return End(part=part.name, preset=preset, params=params, set=given, interface=chosen)


def _meets(mate: InterfaceBase) -> Dict[str, Any]:
    """What an adapter end is to meet ``mate``: (socket, d, length, taper)."""
    if isinstance(mate, Socket):
        taper, length = HOSE if mate.stretch > 0 else FITTING
        # It touches the bore halfway along itself: within the depth the bore holds over.
        return {"socket": False, "d": mate.diameter, "length": min(length, 2 * mate.depth), "taper": taper}
    middle = (mate.d_base + mate.d_tip) / 2
    return {"socket": True, "d": middle, "length": mate.length, "taper": FITTING[0]}


def _outer(end: Dict[str, Any], wall: float) -> float:
    from .projects.parts.hose_adapter import end_outer

    return end_outer(end["socket"], end["d"], end["taper"], wall)


def derive(x: End, y: End, wall: float = WALL) -> Tuple[Dict[str, Any], bool]:
    """The adapter's parameters between ``x`` and ``y`` by the nominal rule, and whether
    ``y`` is the end its ``a`` meets (the wider stands on the bed). Nothing is checked
    here."""
    from .projects.parts.hose_adapter import Params, end_outer, flow_bore

    ends = [_meets(x.interface), _meets(y.interface)]
    # The wider outside stands on the bed; a spigot end a has its collar too.
    first = 0 if _outer(ends[0], wall) >= _outer(ends[1], wall) else 1
    a, b = ends[first], ends[1 - first]
    defaults = Params.model_fields
    params = {
        "a_socket": a["socket"],
        "a_d": round(a["d"], 3),
        "a_length": round(a["length"], 3),
        "a_taper": a["taper"],
        "step": False,
        "b_socket": b["socket"],
        "b_d": round(b["d"], 3),
        "b_length": round(b["length"], 3),
        "taper": b["taper"],
        "wall": wall,
    }
    # The transition's bore closes from end a's to what stands on it at OVERHANG or less.
    a_bore = a["d"] if a["socket"] else flow_bore(False, a["d"], a["taper"], wall)
    b_bore = flow_bore(b["socket"], b["d"], b["taper"], wall)
    a_top = end_outer(a["socket"], a["d"], a["taper"], wall) + (
        0 if a["socket"] else defaults["collar"].default
    )
    b_base = end_outer(b["socket"], b["d"], b["taper"], wall)
    steep = math.tan(math.radians(OVERHANG))
    needed = max((a_bore - b_bore) / 2, (b_base - a_top) / 2, 0.0) / steep
    least = defaults["transition_length"].default
    params["transition_length"] = max(least, math.ceil(needed * 10) / 10)
    return params, first == 1


class Adapter(BaseModel):
    """An adapter between two ends: its parameters, which end meets which, and how each
    fits. ``derived`` says whether its parameters were derived or given."""

    part: str = ADAPTER
    params: Dict[str, Any]
    a: End
    b: End
    fits: List[Fit]
    interfaces: List[InterfaceBase]
    derived: bool
    rule: str

    @property
    def seats(self) -> bool:
        return all(f.seats for f in self.fits)

    @property
    def stubs(self) -> List[str]:
        """The ends whose numbers are a guess: a fit is as good as its numbers."""
        return [e.label for e in (self.a, self.b) if e.interface.is_stub]

    def assembly(self) -> Assembly:
        """The two ends and the adapter standing side by side, each at its parameters,
        and the two connections that say how they meet: the end ``a`` meets stays where
        it is, and ``placed`` stands the others where their interfaces meet."""

        def node(name: str, e: End) -> Assembly:
            return Assembly(name=name, role="part", part_ref=e.part, params=e.params or None)

        return Assembly(
            name=f"{self.part}_between",
            role="assembly",
            children=[
                node("end_a", self.a),
                Assembly(name="adapter", role="part", part_ref=self.part, params=self.params),
                node("end_b", self.b),
            ],
            connections=[
                Connection(a=f"end_a.{self.a.interface.name}", b="adapter.a"),
                Connection(a="adapter.b", b=f"end_b.{self.b.interface.name}"),
            ],
        )

    def placed(self) -> Tuple[Assembly, ConnectionReport]:
        """``assembly`` placed by its connections, and what ``connections.check`` says."""
        return place(self.assembly())

    def lines(self) -> List[str]:
        """What the command line and the page say of it, a line each."""
        out = [f"{self.part} between {self.a.label} and {self.b.label}"]
        for name, other, f in (("a", self.a, self.fits[0]), ("b", self.b, self.fits[1])):
            seat = "" if f.seat is None else f", {f.seat:g} in"
            out.append(f"  {name} ↔ {other.label}: {f.verdict}{seat} ({f.reason})")
        if self.stubs:
            out.append(f"  stub numbers: {', '.join(self.stubs)}")
        return out


def _part(name: str):
    from .projects.parts.skeleton import ROOT
    from .projects.registry import part_named

    return part_named(name, ROOT)


def between(x: End, y: End, params: Optional[Mapping[str, Any]] = None) -> Adapter:
    """The adapter between ``x`` and ``y``: derived, and refused when it cannot be made
    or does not seat on both; or, given ``params``, those checked against them, ``x``
    the end its ``a`` meets and ``y`` its ``b``'s."""
    adapter = _part(ADAPTER)
    derived = params is None
    a_side, b_side = x, y
    if derived:
        already = fit(x.interface, y.interface)
        if already.seats:
            raise Refused(
                f"{x.label} and {y.label} meet without an adapter: {already.reason}"
            )
        params, swapped = derive(x, y)
        if swapped:
            a_side, b_side = y, x
    try:
        params = adapter.validate_overrides(dict(params))
    except ValueError as exc:
        why = (
            "; ".join(e["msg"].removeprefix("Value error, ") for e in exc.errors())
            if isinstance(exc, ValidationError)
            else str(exc)
        )
        raise Refused(f"no adapter between {x.label} and {y.label}: {why}") from None
    interfaces = adapter.interfaces(params)
    ours = {i.name: i for i in interfaces}
    fits = [fit(ours["a"], a_side.interface), fit(ours["b"], b_side.interface)]
    made = Adapter(
        params=params,
        a=a_side,
        b=b_side,
        fits=fits,
        interfaces=interfaces,
        derived=derived,
        rule=_rule(),
    )
    if derived and not made.seats:
        unfit = next(f for f in fits if not f.seats)
        raise Refused(
            f"the adapter derived between {x.label} and {y.label} does not seat: "
            f"{unfit.a} {unfit.verdict} ({unfit.reason})"
        )
    return made


def _rule() -> str:
    from .projects.parts.hose_adapter import NOMINAL

    return NOMINAL


__all__ = [
    "ADAPTER",
    "Adapter",
    "End",
    "FITTING",
    "HOSE",
    "Refused",
    "between",
    "derive",
    "end",
]
