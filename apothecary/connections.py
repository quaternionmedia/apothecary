"""Connections: sibling parts placed where their interfaces meet, and checked for fit.

A node's ``connections`` (``hierarchy.Connection``) each pair an interface of one
child with an interface of another, both registered parts. Composition
(``composition.py``) says what a part is built from; a connection says how two
parts that stand side by side meet, and changes no depth or shell.

``check(node)`` answers, for each connection, how its two interfaces fit
(``models.interfaces.fit``) and whether the two children stand where that fit
puts them, and for the node as a whole, whether an interface is in two
connections or two that exclude each other are in use together. It names every
interface whose numbers are a stub's, since a fit is as good as its numbers.

``place(node)`` puts the children where their connections say. The first child
of each connected group stays where it stands; each child joined to a placed one
by a connection that seats is turned so its interface faces the other's (the
smallest turn that does: a round interface has no clocking) and moved so its
interface stands where the fit puts it. A connection between two children
already placed closes a loop and is checked, not solved again. docs/connections.md
is the reference.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from .hierarchy import Assembly
from .models.interfaces import Fit, InterfaceBase, Spigot, fit
from .models.vectors import Vector3D
from .orbitals import turn_matrix, turned

# Within these, two interfaces stand where their connection puts them: mm, and the
# cosine of the angle between one's normal and the reverse of the other's.
PLACED_WITHIN = 0.01
FACING_WITHIN = 1e-6

Matrix = Tuple[Tuple[float, float, float], ...]


class Joint(BaseModel):
    """One connection's answer: how its interfaces fit, and what is wrong with it."""

    connection: str
    fit: Optional[Fit] = None
    stubs: List[str] = Field(default_factory=list)
    problems: List[str] = Field(default_factory=list)


class ConnectionReport(BaseModel):
    """What ``check`` found: a joint per connection and the node's own problems."""

    node: str
    joints: List[Joint] = Field(default_factory=list)
    problems: List[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems and all(not j.problems for j in self.joints)

    @property
    def stubs(self) -> List[str]:
        return sorted({s for j in self.joints for s in j.stubs})

    def lines(self) -> List[str]:
        """The report in words, a line each: what the command line and the page print."""
        out = []
        for j in self.joints:
            if j.fit is not None:
                seat = "" if j.fit.seat is None else f", {j.fit.seat:g} in"
                out.append(f"{j.connection}: {j.fit.verdict}{seat} ({j.fit.reason})")
            out.extend(f"  {p}" for p in j.problems if j.fit is None or p != _unfit(j))
        out.extend(self.problems)
        if self.stubs:
            out.append(f"stub numbers: {', '.join(self.stubs)}")
        return out


def _unfit(j: Joint) -> str:
    return f"{j.fit.a} and {j.fit.b} do not seat: {j.fit.verdict}"


def _part(ref: str):
    # The registry is layer 2's, as this module is; imported here, where it is used.
    from .projects.parts.skeleton import ROOT
    from .projects.registry import part_named

    return part_named(ref, ROOT)


def _end(
    node: Assembly, end: Tuple[str, str]
) -> Tuple[Optional[Assembly], Optional[InterfaceBase], str]:
    """The child and the interface one end of a connection names, or why not."""
    child_name, interface_name = end
    child = next((c for c in node.children if c.name == child_name), None)
    if child is None:
        return None, None, f"{node.name} has no child {child_name!r}"
    if child.part_ref is None:
        return child, None, f"{child_name} is no registered part, so it has no interfaces"
    try:
        return child, _part(child.part_ref).interface(interface_name, child.params), ""
    except KeyError as exc:
        return child, None, str(exc.args[0])
    except Exception as exc:  # a part that does not load says why, as the registry does
        return child, None, f"{child.part_ref}: {exc}"


def _world(child: Assembly, interface: InterfaceBase) -> Tuple[Vector3D, Vector3D]:
    """Where an interface of a placed child stands, and which way it faces, in the
    node's frame: turned with the child, then moved with it."""
    turn = child.turn.to_list() if child.turn is not None else (0.0, 0.0, 0.0)
    p = turned(turn, interface.position.to_list())
    n = turned(turn, interface.normal.to_list())
    return (
        Vector3D(x=p[0], y=p[1], z=p[2]) + child.position,
        Vector3D(x=n[0], y=n[1], z=n[2]),
    )


def _meets(here: InterfaceBase, there: InterfaceBase, f: Fit) -> float:
    """How far past ``here``'s position, along its normal, ``there``'s position
    stands when the two are seated: the spigot's length less its seat."""
    spigot = here if isinstance(here, Spigot) else there
    return spigot.length - f.seat


def check(node: Assembly) -> ConnectionReport:
    """How each of ``node``'s connections fits, and what is wrong with them."""
    report = ConnectionReport(node=node.name)
    in_use: Dict[Tuple[str, str], str] = {}
    interfaces: Dict[Tuple[str, str], InterfaceBase] = {}
    for c in node.connections:
        joint = Joint(connection=str(c))
        report.joints.append(joint)
        ends = c.ends()
        if ends[0][0] == ends[1][0]:
            joint.problems.append(f"{ends[0][0]} meets itself: a connection joins two children")
            continue
        found = []
        for end in ends:
            child, interface, why = _end(node, end)
            if interface is None:
                joint.problems.append(why)
                continue
            found.append((child, interface))
            interfaces[end] = interface
            if end in in_use:
                report.problems.append(
                    f"{'.'.join(end)} is in two connections: {in_use[end]} and {c}"
                )
            in_use[end] = str(c)
            if interface.is_stub:
                joint.stubs.append(".".join(end))
        if len(found) < 2:
            continue
        (child_a, a), (child_b, b) = found
        joint.fit = fit(a, b)
        if not joint.fit.seats:
            joint.problems.append(_unfit(joint))
            continue
        pa, na = _world(child_a, a)
        pb, nb = _world(child_b, b)
        want = pa + na * _meets(a, b, joint.fit)
        off = math.dist(want.to_list(), pb.to_list())
        facing = -(na.x * nb.x + na.y * nb.y + na.z * nb.z)
        if off > PLACED_WITHIN or facing < 1 - FACING_WITHIN:
            joint.problems.append(
                f"{child_b.name} stands {off:.2f} from where {c} puts it"
                + ("" if facing >= 1 - FACING_WITHIN else ", facing another way")
                + "; connections.place puts it there"
            )
    named = set()
    for (child, name), interface in sorted(interfaces.items()):
        for other in interface.excludes:
            pair = (child, *sorted((name, other)))
            if (child, other) in in_use and pair not in named:
                named.add(pair)
                report.problems.append(
                    f"{child}.{pair[1]} and {child}.{pair[2]} exclude each other and are both "
                    "in use"
                )
    return report


# --- placing ----------------------------------------------------------------------------


def _matrix_to_turn(m: Matrix) -> Vector3D:
    """The OpenSCAD ``rotate([rx, ry, rz])`` that makes the rotation ``m`` (about x, then
    y, then z: ``orbitals.turn_matrix``'s order)."""
    sy = -m[2][0]
    sy = max(-1.0, min(1.0, sy))
    ry = math.asin(sy)
    if abs(math.cos(ry)) > 1e-9:
        rx = math.atan2(m[2][1], m[2][2])
        rz = math.atan2(m[1][0], m[0][0])
    else:  # straight up or down: x and z turn about the same axis, so x takes none
        rx = 0.0
        rz = math.atan2(-m[0][1], m[1][1])
    return Vector3D(**{k: _clean(math.degrees(v)) for k, v in zip("xyz", (rx, ry, rz), strict=True)})


def _clean(angle: float) -> float:
    angle = round(angle, 9)
    return 0.0 if angle == 0 else angle


def _rotation(axis: Tuple[float, float, float], angle: float) -> Matrix:
    x, y, z = axis
    c, s, t = math.cos(angle), math.sin(angle), 1 - math.cos(angle)
    return (
        (t * x * x + c, t * x * y - s * z, t * x * z + s * y),
        (t * x * y + s * z, t * y * y + c, t * y * z - s * x),
        (t * x * z - s * y, t * y * z + s * x, t * z * z + c),
    )


def _multiply(a: Matrix, b: Matrix) -> Matrix:
    return tuple(
        tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3)
    )


def turn_toward(start: Vector3D, finish: Vector3D) -> Vector3D:
    """The turn, as OpenSCAD's ``rotate([rx, ry, rz])`` degrees, that takes ``start``
    -- a unit direction in a part's own frame -- to ``finish``: the smallest that
    does. Half a turn is about the axis square to ``start`` nearest x."""
    first = turn_matrix((0.0, 0.0, 0.0))
    s, f = start.to_list(), finish.to_list()
    cos = max(-1.0, min(1.0, sum(s[i] * f[i] for i in range(3))))
    cross = (s[1] * f[2] - s[2] * f[1], s[2] * f[0] - s[0] * f[2], s[0] * f[1] - s[1] * f[0])
    size = math.sqrt(sum(v * v for v in cross))
    if size < 1e-12:
        if cos > 0:
            return _matrix_to_turn(first)
        # Half a turn: about the axis square to start nearest x.
        x = (1.0, 0.0, 0.0) if abs(s[0]) < 0.9 else (0.0, 1.0, 0.0)
        along = sum(x[i] * s[i] for i in range(3))
        axis = tuple(x[i] - along * s[i] for i in range(3))
        size = math.sqrt(sum(v * v for v in axis))
        axis = tuple(v / size for v in axis)
        return _matrix_to_turn(_multiply(_rotation(axis, math.pi), first))
    axis = tuple(v / size for v in cross)
    return _matrix_to_turn(_multiply(_rotation(axis, math.acos(cos)), first))


def place(node: Assembly) -> Tuple[Assembly, ConnectionReport]:
    """``node`` with its connected children placed where their connections say, and
    ``check``'s report on the result. Each placed child's ``footprint`` is its part's
    bounds, in its own frame, where it had none."""
    placed = node.model_copy(deep=True)
    children = {c.name: c for c in placed.children}
    done = set()
    pending = list(placed.connections)
    # Each connected group is anchored at its first child, in the node's order.
    order = [c.name for c in placed.children]
    groups: List[set] = []
    for c in placed.connections:
        (a, _), (b, _) = c.ends()
        joined = [g for g in groups if a in g or b in g]
        merged = set().union(*joined, {a, b}) if joined else {a, b}
        groups = [g for g in groups if g not in joined] + [merged]
    for g in groups:
        anchor = min((n for n in g if n in children), key=order.index, default=None)
        if anchor is not None:
            done.add(anchor)
    moving = True
    while moving:
        moving = False
        for c in pending:
            ends = c.ends()
            here = [e for e in ends if e[0] in done]
            if len(here) != 1:
                continue
            there = ends[1] if here[0] == ends[0] else ends[0]
            anchor_child, a, _ = _end(placed, here[0])
            child, b, _ = _end(placed, there)
            if a is None or b is None or child is None:
                continue
            f = fit(a, b)
            if not f.seats:
                continue
            pa, na = _world(anchor_child, a)
            child.turn = turn_toward(b.normal, -na)
            if child.turn == Vector3D():
                child.turn = None
            at = turned(child.turn.to_list() if child.turn else (0, 0, 0), b.position.to_list())
            target = pa + na * _meets(a, b, f)
            child.position = Vector3D(
                **{k: round(getattr(target, k) - at[i], 9) + 0.0 for i, k in enumerate("xyz")}
            )
            if child.footprint is None and child.part_ref is not None:
                child.footprint = _part(child.part_ref).get_bounds(child.params)
            done.add(there[0])
            moving = True
    for child in placed.children:
        if child.name in done and child.footprint is None and child.part_ref is not None:
            child.footprint = _part(child.part_ref).get_bounds(child.params)
    return placed, check(placed)


__all__ = [
    "ConnectionReport",
    "Joint",
    "PLACED_WITHIN",
    "check",
    "place",
    "turn_toward",
]
