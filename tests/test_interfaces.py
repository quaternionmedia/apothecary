"""Interfaces, and the rule that says whether a spigot seats in a socket
(apothecary/models/interfaces.py, docs/connections.md)."""

import pytest
from pydantic import ValidationError

from apothecary.models import Vector3D
from apothecary.models.interfaces import (
    BoltHole,
    Socket,
    Spigot,
    fit,
    read_interfaces,
    seated_frame,
)

UP = {"z": 1}
DOWN = {"z": -1}


def hose_spigot(**kw):
    """The adapter's hose end: 41 at its base, 39 at its tip, 40 long, pointing down."""
    return Spigot(
        **{
            "name": "hose",
            "position": {"z": 40},
            "normal": DOWN,
            "d_base": 41.0,
            "d_tip": 39.0,
            "length": 40.0,
            **kw,
        }
    )


def step_32(**kw):
    """The adapter's 32 step, with the 25 tip leading it."""
    return Spigot(
        **{
            "name": "fitting_32",
            "position": {"z": 53},
            "normal": UP,
            "d_base": 32.6,
            "d_tip": 31.4,
            "length": 25.0,
            "reach": 45.0,
            "lead_d": 25.6,
            **kw,
        }
    )


def socket(**kw):
    return Socket(
        **{"name": "port", "position": {}, "normal": UP, "diameter": 32.0, "depth": 30.0, **kw}
    )


# --- what an interface is -------------------------------------------------------------


def test_a_normal_is_kept_as_a_unit_vector():
    s = socket(normal={"x": 0, "y": 3, "z": 4})
    assert (s.normal.y, s.normal.z) == pytest.approx((0.6, 0.8))


def test_a_normal_of_zero_length_is_refused():
    with pytest.raises(ValidationError, match="points nowhere"):
        socket(normal={})


def test_a_standards_numbers_name_the_standard():
    with pytest.raises(ValidationError, match="cite"):
        socket(source="standard")
    assert socket(source="standard", cite="ISO 7-1").cite == "ISO 7-1"


def test_reach_cannot_stop_short_of_the_tip():
    with pytest.raises(ValidationError, match="stops short"):
        step_32(reach=20.0)


def test_what_leads_the_tip_says_how_wide_it_is():
    with pytest.raises(ValidationError, match="lead_d"):
        step_32(lead_d=None)


def test_a_list_reads_each_type_by_its_name():
    read = read_interfaces(
        [
            {
                "name": "a",
                "type": "spigot",
                "position": {},
                "normal": UP,
                "d_base": 10,
                "d_tip": 9,
                "length": 5,
            },
            {
                "name": "b",
                "type": "socket",
                "position": {},
                "normal": UP,
                "diameter": 10,
                "depth": 5,
            },
            {"name": "c", "type": "bolt_hole", "position": {}, "normal": UP, "diameter": 3},
            {"name": "d", "type": "slot", "position": {}, "normal": UP, "width": 2, "length": 9},
        ]
    )
    assert [type(i).__name__ for i in read] == ["Spigot", "Socket", "BoltHole", "Slot"]


def test_a_type_it_does_not_know_is_refused():
    with pytest.raises(ValidationError):
        read_interfaces([{"name": "a", "type": "barb", "position": {}, "normal": UP}])


def test_names_are_one_per_part_and_excludes_name_the_parts_own():
    one = {"name": "a", "type": "bolt_hole", "position": {}, "normal": UP, "diameter": 3}
    with pytest.raises(ValueError, match="one per part"):
        read_interfaces([one, one])
    with pytest.raises(ValueError, match="does not have"):
        read_interfaces([{**one, "excludes": ["b"]}])
    with pytest.raises(ValidationError, match="cannot exclude itself"):
        read_interfaces([{**one, "excludes": ["a"]}])


# --- the rule for a spigot in a socket ------------------------------------------------


def test_a_tapered_spigot_seats_in_a_hose_by_stretching_it():
    """A 40 rubber hose, 5% stretch, takes the whole 39-to-41 spigot: at the
    shoulder the spigot is 1 mm wider than the bore, 2.5%."""
    hose = socket(name="hose_end", diameter=40.0, depth=200.0, stretch=0.05)
    f = fit(hose_spigot(), hose)
    assert f.verdict == "seats"
    assert (f.seat, f.gap, f.interference, f.stretch) == (40.0, 0.0, 1.0, 0.025)
    assert "shoulder" in f.reason


def test_a_rigid_socket_takes_a_taper_to_where_it_is_as_wide_as_the_bore():
    """A 32.0 bore takes the 31.4-to-32.6 step halfway, 12.5 of its 25."""
    f = fit(step_32(), socket())
    assert f.verdict == "seats"
    assert (f.seat, f.gap, f.interference) == (12.5, 12.5, 0.0)


def test_the_order_of_the_pair_does_not_change_the_fit():
    one, other = fit(step_32(), socket()), fit(socket(), step_32())
    assert (one.verdict, one.seat, one.spigot, one.socket) == (
        other.verdict,
        other.seat,
        other.spigot,
        other.socket,
    )
    assert (other.a, other.b) == ("port", "fitting_32")


def test_a_tip_wider_than_the_bore_will_not_enter():
    f = fit(step_32(), socket(diameter=25.0))
    assert f.verdict == "will not enter"
    assert "31.4" in f.reason


def test_a_spigot_narrower_than_the_bore_is_loose():
    f = fit(step_32(), socket(diameter=33.0))
    assert f.verdict == "loose"


def test_a_socket_too_shallow_to_reach_the_taper():
    """The step touches a 32.0 bore 12.5 in; a bore 5 deep holds over none of that."""
    f = fit(step_32(), socket(depth=5.0))
    assert f.verdict == "shallow"


def test_what_leads_the_tip_can_stop_it_before_it_touches():
    """The 25 tip goes in first, 20 ahead of the step: a floor of 20 at 30 deep stops
    it with the step 10 in, short of the 12.5 where it would touch."""
    f = fit(step_32(), socket(floor=20.0))
    assert f.verdict == "tip blocked"
    assert f.seat == 10.0
    assert "leads" in f.reason


def test_a_floor_wider_than_what_leads_lets_it_through():
    f = fit(step_32(), socket(floor=26.0))
    assert (f.verdict, f.seat) == ("seats", 12.5)


def test_a_straight_spigot_the_size_of_the_bore_goes_in_to_its_shoulder():
    straight = step_32(d_base=32.0, d_tip=32.0, reach=None, lead_d=None)
    f = fit(straight, socket())
    assert (f.verdict, f.seat, f.gap) == ("seats", 25.0, 0.0)


def test_two_spigots_do_not_mate_and_a_bolt_hole_has_no_rule_yet():
    assert fit(step_32(), hose_spigot()).verdict == "do not mate"
    hole = BoltHole(name="m3", position={}, normal=UP, diameter=3.0)
    assert fit(step_32(), hole).verdict == "no rule"


def test_a_seated_spigot_points_into_the_socket_with_its_tip_past_the_mouth():
    """seat 12.5 of a 25 spigot: its base stands 12.5 out of the mouth, pointing in."""
    port = socket(position={"x": 5, "y": 0, "z": 100})
    position, normal = seated_frame(step_32(), port, 12.5)
    assert position.to_list() == pytest.approx([5, 0, 112.5])
    assert normal.to_list() == pytest.approx([0, 0, -1])
    tip = position + normal * 25.0
    assert tip.to_list() == pytest.approx((port.position - Vector3D(z=12.5)).to_list())
