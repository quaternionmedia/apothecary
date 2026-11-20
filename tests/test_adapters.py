"""The adapter between two round ends, generated from their interfaces
(apothecary/adapters.py; docs/connections.md, The adapter between two ends).

The round trip is the guard: an adapter generated between two ends, read back from
its parameters alone, fits both ends it was made from. Each pair of the port's
presets, and ends measured across a span of sizes of either kind, go round it."""

from __future__ import annotations

from itertools import combinations_with_replacement

import pytest

from apothecary import adapters
from apothecary.adapters import Refused, between, derive, end
from apothecary.hierarchy import Assembly
from apothecary.models.interfaces import BoltHole, Socket, Spigot, fit
from apothecary.models.vectors import Vector3D
from apothecary.projects.parts import dust_port, hose_adapter
from apothecary.projects.parts.base import BasePart

PORT, ADAPTER = dust_port.DEFAULT, hose_adapter.DEFAULT
SIZES = ("hose_40", "port_32", "port_25")


def at(preset=None, **over):
    return end(PORT, preset, None, over or None)


def round_trip(made) -> list:
    """Each of the adapter's ends, read back from its parameters alone, fitted to the end
    it was made for."""
    ours = {i.name: i for i in ADAPTER.interfaces(made.params)}
    return [fit(ours["a"], made.a.interface), fit(ours["b"], made.b.interface)]


# --- what is derived --------------------------------------------------------------------


@pytest.mark.parametrize(
    "x, y", [(x, y) for x, y in combinations_with_replacement(SIZES, 2)], ids="-".join
)
def test_each_pair_of_the_three_sizes_is_joined_and_the_adapter_fits_both(x, y):
    made = between(at(x), at(y))
    assert made.derived and made.seats
    assert all(f.seats for f in round_trip(made)), made.lines()
    # The wider end stands on the bed; nothing is stepped.
    assert made.params["a_d"] >= made.params["b_d"] and made.params["step"] is False


def test_the_hose_and_the_32_port_make_the_plain_40_to_32():
    made = between(at("hose_40"), at("port_32"))
    plain = ADAPTER.validate_overrides({**ADAPTER.preset("plain_40_32")})
    assert {k: made.params[k] for k in plain} == plain
    assert ADAPTER.interfaces(made.params) == ADAPTER.interfaces(ADAPTER.preset("plain_40_32"))
    assert [f.seat for f in made.fits] == [40.0, 12.5]


def test_the_order_given_does_not_matter_the_wider_end_is_a():
    one, two = between(at("port_25"), at("hose_40")), between(at("hose_40"), at("port_25"))
    assert one.params == two.params
    assert (one.a.label, one.b.label) == ("dust_port@hose_40.end", "dust_port@port_25.end")


def test_a_spigot_end_is_met_by_a_socket_its_middle_across():
    made = between(at("hose_40"), at("outlet_35", taper=1.0))
    assert (made.params["b_socket"], made.params["b_d"], made.params["b_length"]) == (True, 35.5, 30.0)
    assert [f.verdict for f in made.fits] == ["seats", "seats"]
    assert made.fits[1].seat == 15.0  # halfway along a tapered stub, as a spigot end into a bore


def test_a_hose_is_met_by_a_hose_s_spigot_and_a_rigid_bore_by_a_fitting_s():
    made = between(at("hose_40"), at("port_25"))
    assert (made.params["a_taper"], made.params["a_length"]) == adapters.HOSE
    assert (made.params["taper"], made.params["b_length"]) == adapters.FITTING
    # A rigid bore that holds over 10 takes a spigot no longer than 20: it touches within.
    shallow = between(at("hose_40"), at("port_25", length=10.0))
    assert shallow.params["b_length"] == 20.0 and shallow.seats


def test_the_transition_is_as_long_as_its_bore_needs_to_close_at_45_degrees():
    made = between(at("port_32", diameter=120.0), at("hose_40"))
    p = hose_adapter.Params(**made.params)
    assert hose_adapter.profile(p).problems() == []
    assert made.params["transition_length"] > 8.0
    (a_bore, b_bore) = (120 - 0.6 - 4, 40 - 1.0 - 4)
    assert made.params["transition_length"] == pytest.approx((a_bore - b_bore) / 2, abs=0.11)


@pytest.mark.parametrize("d", [8.0, 12.5, 19.0, 25.4, 31.6, 38.0, 50.0, 63.0, 76.2, 100.0, 127.0])
def test_measured_ends_across_a_span_of_sizes_go_round_the_trip(d):
    """A hose's end to a port of each size, to an outlet stub of each, and back."""
    for other in (at("port_32", diameter=d), at("outlet_35", diameter=d + 6.5, taper=0.8)):
        made = between(at("hose_40"), other)
        assert all(f.seats for f in round_trip(made)), made.lines()


# --- what is refused ---------------------------------------------------------------------


def test_two_ends_that_meet_already_are_refused():
    with pytest.raises(Refused, match="meet without an adapter: it goes 30.0 in"):
        between(at("outlet_35"), at("port_32", diameter=35.0))


def test_an_end_that_leaves_no_bore_inside_the_wall_is_refused():
    with pytest.raises(Refused, match="end b, a spigot into a 4 bore, leaves no bore inside a 2 wall"):
        between(at("hose_40"), at("port_25", diameter=4.0))


def test_an_adapter_too_steep_to_print_is_refused_saying_what():
    made = between(at("hose_40"), at("port_25"))
    with pytest.raises(Refused, match="transition: its bore closes in past 45 degrees"):
        between(made.a, made.b, {**made.params, "transition_length": 2.0})


def test_an_end_that_is_not_round_or_not_named_is_refused():
    holed = BasePart.model_construct(name="plate", presets={})
    holed.__class__ = type(
        "Plate",
        (BasePart,),
        {
            "interfaces": lambda self, params=None: [
                BoltHole(name="m5", position=Vector3D(), normal=Vector3D(z=1), diameter=5.5)
            ],
            "validate_overrides": lambda self, params, scad_text=None: dict(params or {}),
        },
    )
    with pytest.raises(Refused, match="plate.m5 is a bolt hole: an adapter is generated between round ends"):
        end(holed, None, "m5")
    with pytest.raises(Refused, match="hose_adapter has 3 round interfaces"):
        end(ADAPTER)


def test_a_preset_or_an_interface_it_has_not_got_is_a_key_error():
    with pytest.raises(KeyError, match="no preset 'port_99'"):
        end(PORT, "port_99")
    with pytest.raises(KeyError, match="no interface 'mouth'"):
        end(PORT, None, "mouth")


# --- adjusted, and placed -----------------------------------------------------------------


def test_its_own_parameters_given_are_checked_not_derived():
    made = between(at("hose_40"), at("port_32"))
    loose = between(made.a, made.b, {**made.params, "b_d": 30.0})
    assert not loose.derived and not loose.seats
    assert loose.fits[1].verdict == "loose"


def test_the_two_ends_and_the_adapter_are_placed_where_they_meet():
    made = between(at("hose_40"), at("outlet_35"))
    placed, report = made.placed()
    assert report.ok, report.lines()
    assert isinstance(placed, Assembly)
    where = {c.name: (c.position.to_list(), c.turn and c.turn.to_list()) for c in placed.children}
    assert where["end_a"] == ([0, 0, 0], None)
    assert where["adapter"] == ([0, 0, 60], None)
    assert where["end_b"][1] == pytest.approx([180, 0, 0])
    assert [c.params is not None for c in placed.children] == [True, True, True]


def test_the_rule_applied_is_said_with_it():
    made = between(at("hose_40"), at("port_32"))
    assert made.rule == hose_adapter.NOMINAL
    assert "no clearance is added" in made.rule


def test_derive_says_which_end_stands_on_the_bed():
    params, swapped = derive(at("port_25"), at("hose_40"))
    assert swapped and params["a_d"] == 40.0
    assert isinstance(at("hose_40").interface, Socket)
    assert isinstance(at("outlet_35").interface, Spigot)
