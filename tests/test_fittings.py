"""A round part as a stack of sections: its solid, the interfaces its runs make, and
what would not print (apothecary/fittings.py, docs/connections.md)."""

import pytest

from apothecary.booleans import Difference
from apothecary.fittings import Profile, Section, sagitta


def adapter(**changes):
    """The stepped hose adapter's profile at its defaults, hose end on the bed."""
    sections = {
        "hose": dict(length=40, outer=(39, 41), bore=(35, 35)),
        "flare": dict(length=2.5, outer=(41, 46), bore=(35, 35)),
        "collar": dict(length=2.5, outer=(46, 46), bore=(35, 35)),
        "transition": dict(length=8, outer=(46, 32.6), bore=(35, 27.4)),
        "step_32": dict(length=25, outer=(32.6, 31.4), bore=(27.4, 27.4)),
        "shoulder": dict(length=3.5, outer=(31.4, 25.6), bore=(27.4, 20.4)),
        "tip_25": dict(length=20, outer=(25.6, 24.4), bore=(20.4, 20.4)),
    }
    for name, change in changes.items():
        sections[name] = {**sections[name], **change}
    return Profile(sections=[Section(name=n, **s) for n, s in sections.items()])


def tube(*sections):
    return Profile(sections=[Section(name=f"s{i}", **s) for i, s in enumerate(sections)])


# --- what would not print -------------------------------------------------------------


def test_the_adapter_prints_as_it_stands():
    assert adapter().problems() == []
    assert adapter().height == 101.5


def test_a_wall_under_the_minimum_is_named():
    (problem,) = adapter(tip_25={"outer": (25.6, 23.4)}).problems()
    assert problem.startswith("tip_25: the wall at its top is 1.50")


def test_an_outside_leaning_out_past_45_degrees_is_named():
    (problem,) = adapter(flare={"length": 2.0}, collar={"length": 3.0}).problems()
    assert problem == "flare: its outside leans out past 45 degrees"


def test_a_bore_closing_in_past_45_degrees_is_named():
    (problem,) = adapter(shoulder={"length": 3.0}, tip_25={"length": 20.5}).problems()
    assert problem == "shoulder: its bore closes in past 45 degrees"


def test_a_ledge_facing_down_and_a_flat_ceiling_are_named():
    ledge = tube(
        dict(length=5, outer=(30, 30), bore=(20, 20)), dict(length=5, outer=(40, 40), bore=(20, 20))
    )
    assert ledge.problems() == ["s1: a ledge over s0 faces down"]
    ceiling = tube(
        dict(length=5, outer=(40, 40), bore=(30, 30)), dict(length=5, outer=(40, 40), bore=(20, 20))
    )
    assert ceiling.problems() == ["s1: the bore below it ends in a flat ceiling"]


def test_too_few_facets_are_named():
    assert sagitta(46, 128) < 0.01 < sagitta(46, 64)
    (problem,) = adapter().model_copy(update={"fn": 64}).problems()
    assert problem.startswith("at $fn 64 a facet falls")


# --- the solid ------------------------------------------------------------------------


def test_the_solid_is_the_outside_less_the_bore_cut_clear_of_both_ends():
    solid = adapter().solid()
    assert isinstance(solid, Difference)
    scad = solid.render()
    assert scad.count("$fn=128") == 2 * 7
    # The hose end's bore starts below the bed; the tip's runs on above the top.
    assert "translate([0.0, 0.0, -1.0])" in scad
    assert "cylinder(h=21.01, r=10.2" in scad


def test_a_blind_bore_meets_the_solid_section_above_it_exactly():
    cup = tube(dict(length=10, outer=(40, 40), bore=(32, 32)), dict(length=3, outer=(40, 40)))
    scad = cup.solid().render()
    assert "cylinder(h=11.0, r=16.0" in scad  # 1 below the bed, none into the floor


# --- the interfaces a run of sections makes -------------------------------------------


def test_the_hose_end_is_a_spigot_pointing_down_out_of_the_bed_face():
    s = adapter().spigot("hose", "hose", up=False)
    assert (s.position.z, s.normal.z, s.d_base, s.d_tip, s.length) == (40, -1, 41, 39, 40)
    assert s.reach is None


def test_the_32_step_is_a_spigot_led_by_what_lies_above_it():
    s = adapter().spigot("fitting_32", "step_32")
    assert (s.position.z, s.normal.z, s.d_base, s.d_tip, s.length) == (53, 1, 32.6, 31.4, 25)
    assert (s.reach, s.lead_d) == (48.5, 31.4)


def test_a_bore_makes_a_socket_at_its_mouth():
    port = tube(dict(length=30, outer=(38, 38), bore=(32, 32)))
    s = port.socket("port")
    assert (s.position.z, s.normal.z, s.diameter, s.depth, s.floor) == (30, 1, 32, 30, None)


def test_a_bore_that_narrows_further_in_has_a_floor():
    port = tube(
        dict(length=10, outer=(38, 38), bore=(20, 20)),
        dict(length=30, outer=(38, 38), bore=(32, 32)),
    )
    s = port.socket("port")
    assert (s.diameter, s.depth, s.floor) == (32, 30, 20)
    blind = tube(dict(length=3, outer=(38, 38)), dict(length=30, outer=(38, 38), bore=(32, 32)))
    assert blind.socket("port").floor == 0.0


def test_a_socket_needs_a_bore_that_holds_at_its_mouth():
    with pytest.raises(ValueError, match="no bore"):
        tube(dict(length=3, outer=(38, 38))).socket("port")
    with pytest.raises(ValueError, match="tapers"):
        tube(dict(length=10, outer=(38, 38), bore=(30, 32))).socket("port")
