"""Sibling parts placed where their interfaces meet, and checked for fit
(apothecary/connections.py, hierarchy.Connection; docs/connections.md)."""

from __future__ import annotations

import math
import random

import pytest
from pydantic import ValidationError

from apothecary.connections import _world, check, place, turn_toward
from apothecary.hierarchy import Assembly, Connection
from apothecary.models import Vector3D
from apothecary.orbitals import turned
from apothecary.projects.assemblies.dust_hose import build, unplaced
from apothecary.projects.parts.skeleton import ROOT
from apothecary.projects.registry import part_named


def node(*children, connections=()):
    """A bench of parts side by side, each ``part`` or ``part@preset``."""

    def child(name, ref):
        part, _, preset = ref.partition("@")
        params = part_named(part, ROOT).preset(preset) if preset else None
        return Assembly(name=name, role="part", part_ref=part, params=params)

    return Assembly(
        name="bench",
        children=[child(n, ref) for n, ref in children],
        connections=[Connection(a=a, b=b) for a, b in connections],
    )


# --- a connection ---------------------------------------------------------------------


def test_a_connection_names_a_child_and_its_interface_at_each_end():
    c = Connection(a="hose.end", b="adapter.a")
    assert c.ends() == (("hose", "end"), ("adapter", "a"))
    with pytest.raises(ValidationError, match="child.interface"):
        Connection(a="hose", b="adapter.a")


# --- the smallest turn ----------------------------------------------------------------


@pytest.mark.parametrize(
    "start, finish, turn",
    [
        ((0, 0, 1), (0, 0, 1), (0, 0, 0)),
        ((0, 0, 1), (0, 0, -1), (180, 0, 0)),
        ((0, 0, 1), (1, 0, 0), (0, 90, 0)),
        ((1, 0, 0), (0, 1, 0), (0, 0, 90)),
    ],
)
def test_the_smallest_turn_between_two_directions(start, finish, turn):
    got = turn_toward(
        Vector3D(**dict(zip("xyz", start, strict=True))),
        Vector3D(**dict(zip("xyz", finish, strict=True))),
    )
    assert got.to_list() == pytest.approx(list(turn), abs=1e-9)


def test_a_turn_takes_its_start_to_its_finish_as_openscad_turns():
    """Held against orbitals.turned, OpenSCAD's rotate([x, y, z]), for directions at random."""
    rng = random.Random(7)

    def direction():
        v = [rng.gauss(0, 1) for _ in range(3)]
        size = math.sqrt(sum(c * c for c in v))
        return Vector3D(**dict(zip("xyz", (c / size for c in v), strict=True)))

    for _ in range(200):
        start, finish = direction(), direction()
        turn = turn_toward(start, finish)
        assert turned(turn.to_list(), start.to_list()) == pytest.approx(finish.to_list(), abs=1e-9)


# --- check ----------------------------------------------------------------------------


def test_parts_not_yet_placed_are_named_with_where_their_connection_puts_them():
    report = check(unplaced())
    assert not report.ok
    (adapter,) = report.joints[0].problems
    assert adapter.startswith("adapter stands 60.00 from where hose.end ↔ adapter.a puts it")
    assert "facing another way" in report.joints[1].problems[0]


def test_placed_by_their_connections_they_fit_and_stand_where_they_meet():
    placed, report = build("32")
    assert report.ok, report.lines()
    where = {c.name: (c.position.to_list(), c.turn) for c in placed.children}
    assert where["hose"] == ([0, 0, 0], None)
    assert where["adapter"] == ([0, 0, 60], None)
    assert where["port"][0] == pytest.approx([0, 0, 155.5])
    assert where["port"][1].to_list() == pytest.approx([180, 0, 0])
    assert [j.fit.seat for j in report.joints] == [40.0, 12.5]
    assert report.stubs == ["hose.end", "port.end"]


def test_the_seated_tip_is_past_the_mouth_by_its_seat():
    """The adapter's 32 step, placed: its tip 12.5 past the port's mouth, facing in."""
    placed, _ = build("32")
    adapter, port = placed.children[1], placed.children[2]
    step = part_named("hose_adapter", ROOT).interface("step")
    mouth, inward = _world(port, part_named("dust_port", ROOT).interface("end", port.params))
    base, out = _world(adapter, step)
    tip = base + out * step.length
    assert (tip - mouth).to_list() == pytest.approx((-inward * 12.5).to_list(), abs=1e-9)


def test_the_25_end_goes_into_the_25_port():
    placed, report = build("25")
    assert report.ok, report.lines()
    assert placed.children[2].position.to_list() == pytest.approx([0, 0, 176.5])
    assert report.joints[1].fit.seat == 10.0


def test_the_first_part_keeps_its_turn_and_the_rest_follow_it():
    """The hose lying along x: the adapter and the port are turned to meet it."""
    laid = unplaced()
    laid.children[0].turn = Vector3D(y=90)
    placed, report = place(laid)
    assert report.ok, report.lines()
    assert placed.children[0].turn == Vector3D(y=90)
    assert placed.children[1].turn.to_list() == pytest.approx([0, 90, 0])


def test_two_ends_that_exclude_each_other_are_not_both_in_use():
    both = node(
        ("adapter", "hose_adapter"),
        ("big", "dust_port@port_32"),
        ("small", "dust_port@port_25"),
        connections=[("adapter.step", "big.end"), ("adapter.b", "small.end")],
    )
    report = place(both)[1]
    assert report.problems == ["adapter.b and adapter.step exclude each other and are both in use"]


def test_an_interface_is_in_one_connection_at_a_time():
    twice = node(
        ("adapter", "hose_adapter"),
        ("one", "dust_port@port_32"),
        ("two", "dust_port@port_32"),
        connections=[("adapter.step", "one.end"), ("adapter.step", "two.end")],
    )
    (problem,) = check(twice).problems
    assert problem.startswith("adapter.step is in two connections")


def test_a_connection_that_does_not_seat_says_why_and_is_not_placed():
    wrong = node(
        ("adapter", "hose_adapter"),
        ("port", "dust_port@port_25"),
        connections=[("adapter.step", "port.end")],
    )
    placed, report = place(wrong)
    assert report.joints[0].problems == ["step and end do not seat: will not enter"]
    assert placed.children[1].position == Vector3D()


def test_what_a_connection_names_that_is_not_there_is_named():
    report = check(
        node(
            ("adapter", "hose_adapter"),
            ("port", "dust_port@port_32"),
            connections=[
                ("adapter.barb", "port.end"),
                ("nothing.end", "port.end"),
                ("port.end", "port.end"),
            ],
        )
    )
    problems = [p for j in report.joints for p in j.problems]
    assert "hose_adapter has no interface 'barb'" in problems[0]
    assert problems[1] == "bench has no child 'nothing'"
    assert problems[2].startswith("port meets itself")


def test_joined_parts_overlap_by_design_and_nothing_else_may():
    placed, _ = build("32")
    assert placed.validate().is_valid
    placed.connections = []
    overlaps = {tuple(v.structures) for v in placed.validate().violations}
    assert overlaps == {("hose", "adapter"), ("adapter", "port")}


# --- the problems index ---------------------------------------------------------------


def test_a_stub_interface_is_an_open_question_for_a_measurement():
    from apothecary.spaces import MEASUREMENT, _interface_problems

    (problem,) = _interface_problems(part_named("dust_port", ROOT))
    assert (problem.kind, problem.owner) == ("unmeasured", MEASUREMENT)
    assert problem.summary == "dust_port.end: its numbers are a stub's"
    assert _interface_problems(part_named("hose_adapter", ROOT)) == []


def test_a_site_whose_connections_do_not_hold_is_a_misfit_for_apothecary():
    from apothecary.spaces import APOTHECARY, _connection_problems

    found = _connection_problems("garage", Assembly(name="garage", children=[unplaced()]))
    assert {(p.kind, p.owner) for p in found} == {("misfit", APOTHECARY)}
    assert len(found) == 2
    assert _connection_problems("garage", Assembly(name="garage", children=[build()[0]])) == []
