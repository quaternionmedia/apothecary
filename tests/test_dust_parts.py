"""The dust parts (parts/dust/): one port part whose parameters say which end it is,
its sizes its presets, and the adapter whose parameters are its two ends. Each tracked
SCAD is its code at its defaults, each prints as it stands, each interface is its
profile's, at every preset, and each pair the stepped adapter is made for fits as
parts/dust/README.md says."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from rendered_parts import built_stl_fixture, registered_parts  # noqa: F401

from apothecary.fittings import facets, readings
from apothecary.meshes import read_mesh
from apothecary.models.interfaces import Socket, Spigot, fit
from apothecary.projects.parts import dust_port, hose_adapter
from apothecary.projects.parts.skeleton import ROOT
from apothecary.projects.parts.stl_renderer import geometry_scad
from apothecary.projects.registry import part_names, part_named

ADAPTER, PORT = hose_adapter.DEFAULT, dust_port.DEFAULT
PRESETS = tuple(dust_port.PRESETS)

DECLARING_INTERFACES = [
    pytest.param(part, id=name)
    for name, part in registered_parts()
    if part is not None and part.has_interfaces
]


def end(preset: str, **over):
    return PORT.interfaces({**PORT.preset(preset), **over})[0]


# --- the one port part ------------------------------------------------------------------


@pytest.mark.parametrize("part", [ADAPTER, PORT], ids=["hose_adapter", "dust_port"])
def test_the_tracked_scad_is_the_code_at_its_defaults(part):
    """`apothecary parts render NAME -o parts/dust/NAME/NAME.scad` rewrites it."""
    assert part.source_file.read_text(encoding="utf-8") == geometry_scad(part, {})


def test_a_port_is_one_part_and_its_sizes_are_its_presets():
    names = set(part_names(ROOT))
    assert "dust_port" in names
    assert not {"dust_hose_40", "dust_port_32", "dust_port_25"} & names
    assert PRESETS == ("hose_40", "port_32", "port_25", "outlet_35")
    # Its defaults are a 32 port's.
    assert PORT.interfaces() == PORT.interfaces(PORT.preset("port_32"))


@pytest.mark.parametrize("preset", PRESETS)
def test_its_interface_at_each_preset_is_what_its_parameters_say(preset):
    p = dust_port.Params(**PORT.preset(preset))
    (i,) = PORT.interfaces(PORT.preset(preset))
    assert i.name == "end" and i.source == "stub"
    box = PORT.get_bounds(PORT.preset(preset)).size
    assert box.z == p.length
    if p.socket:
        assert isinstance(i, Socket)
        assert (i.diameter, i.depth, i.stretch, i.floor) == (p.diameter, p.length, p.stretch / 100, None)
        assert (i.position.z, i.normal.z) == (p.length, 1.0)
        assert box.x == p.diameter + 2 * p.wall
    else:
        assert isinstance(i, Spigot)
        assert (i.d_tip, i.d_base, i.length) == (p.diameter, p.diameter + p.taper, p.length)
        assert (i.position.z, i.normal.z) == (0.0, 1.0)
        assert box.x == p.diameter + p.taper


def test_a_caliper_reading_goes_over_a_preset_and_measured_says_so():
    i = end("port_32", diameter=31.6, measured=True)
    assert (i.diameter, i.source, i.notes) == (31.6, "measured", "Measured.")
    assert "measure the bore at the mouth" in end("port_32").notes
    assert "measure the outside at the tip" in end("outlet_35").notes


def test_a_wide_port_is_drawn_with_more_facets_not_refused():
    """A 100 mm port: at 128 facets a flat falls more than 0.01 inside its circle."""
    assert facets(46.0) == 128
    wide = dust_port.profile(dust_port.Params(diameter=100.0))
    assert wide.fn > 128 and wide.fn % 4 == 0 and wide.problems() == []


def test_a_port_that_would_not_print_is_refused():
    with pytest.raises(ValidationError, match="the wall at its bottom is 1.00, under 2"):
        dust_port.Params(wall=1.0)
    with pytest.raises(ValidationError, match="a spigot 5 across leaves no bore inside a 3 wall"):
        dust_port.Params(socket=False, diameter=5.0)


def test_a_preset_that_names_what_the_part_has_not_got_is_refused_when_it_loads():
    with pytest.raises(ValidationError, match="preset bad: unknown parameter"):
        dust_port.DustPortPart(
            name="dust_port",
            source_file=PORT.source_file,
            params_model=dust_port.Params,
            presets={"bad": {"params": {"bore": 3}}},
        )
    with pytest.raises(ValidationError, match="preset 'a.b': a preset's name is letters"):
        dust_port.DustPortPart(
            name="dust_port",
            source_file=PORT.source_file,
            params_model=dust_port.Params,
            presets={"a.b": {"params": {}}},
        )
    with pytest.raises(KeyError, match="dust_port has no preset 'nope'; its presets: hose_40"):
        PORT.preset("nope")


# --- the adapter, its parameters its two ends --------------------------------------------


def test_the_adapter_prints_as_it_stands_and_its_box_is_its_profile():
    shape = hose_adapter.profile(hose_adapter.Params())
    assert shape.problems() == []
    box = ADAPTER.get_bounds()
    assert (box.size.x, box.size.y, box.size.z) == (46.0, 46.0, 101.5)


def test_parameters_that_would_not_print_are_refused():
    with pytest.raises(ValidationError, match="transition: its bore closes in past 45"):
        hose_adapter.Params(transition_length=2.0)
    with pytest.raises(ValidationError, match="a step leads a spigot end b into its fitting"):
        hose_adapter.Params(b_socket=True)
    with pytest.raises(ValidationError, match="end b, a spigot into a 4 bore, leaves no bore"):
        hose_adapter.Params(step=False, b_d=4.0)


def test_its_interfaces_are_its_drawing_and_the_step_and_end_b_exclude_each_other():
    found = {i.name: i for i in ADAPTER.interfaces()}
    assert list(found) == ["a", "step", "b"]
    assert {i.source for i in found.values()} == {"drawn"}
    assert found["step"].excludes == ["b"]
    assert found["b"].excludes == ["step"]
    assert found["a"].normal.z == -1 and found["step"].normal.z == 1


def test_its_presets_are_the_stepped_adapter_and_the_plain_40_to_32():
    assert list(ADAPTER.presets) == ["stepped_40_32_25", "plain_40_32"]
    assert ADAPTER.preset("stepped_40_32_25") == {}
    plain = ADAPTER.preset("plain_40_32")
    found = ADAPTER.interfaces(plain)
    assert [(i.name, i.excludes, i.lead, i.d_tip) for i in found] == [
        ("a", [], 0.0, 39.0),
        ("b", [], 0.0, 31.4),
    ]
    assert ADAPTER.get_bounds(plain).size.z == 78.0


def test_a_socket_end_takes_what_it_meets_and_stops_it_on_a_lip():
    p = {"step": False, "b_socket": True, "b_d": 35.0, "b_length": 30.0}
    (a, b) = ADAPTER.interfaces(p)
    assert isinstance(b, Socket)
    assert (b.diameter, b.depth, b.floor, b.normal.z) == (35.0, 30.0, 31.0, 1.0)
    assert hose_adapter.profile(hose_adapter.Params(**p)).problems() == []


# --- the fits parts/dust/README.md states ---------------------------------------------


def test_the_hose_takes_the_whole_of_end_a_opened_two_and_a_half_percent():
    f = fit(ADAPTER.interface("a"), end("hose_40"))
    assert (f.verdict, f.seat, f.gap, f.stretch) == ("seats", 40.0, 0.0, 0.025)


def test_each_port_takes_its_step_part_way_in():
    f32 = fit(ADAPTER.interface("step"), end("port_32"))
    f25 = fit(ADAPTER.interface("b"), end("port_25"))
    assert (f32.verdict, f32.seat, f25.verdict, f25.seat) == ("seats", 12.5, "seats", 10.0)


def test_the_wrong_end_for_a_port_says_why():
    assert fit(ADAPTER.interface("step"), end("port_25")).verdict == "will not enter"
    assert fit(ADAPTER.interface("b"), end("port_32")).verdict == "loose"


# --- every part that declares interfaces, on its render -------------------------------


def test_the_dust_parts_are_among_the_parts_that_declare_interfaces():
    names = {p.id for p in DECLARING_INTERFACES}
    assert {"hose_adapter", "dust_port"} <= names


@pytest.mark.slow
@pytest.mark.parametrize("part", DECLARING_INTERFACES)
def test_each_declared_round_interface_is_on_the_render(part, built_stl):
    """`apothecary parts verify`'s reading, for every part that declares interfaces."""
    mesh = read_mesh(built_stl(part))
    read = [r for i in part.interfaces() for r in readings(i, mesh)]
    assert read, part.name
    assert all(r.holds() for r in read), [r for r in read if not r.holds()]


@pytest.mark.slow
@pytest.mark.parametrize("preset", PRESETS)
def test_the_port_renders_at_each_preset_and_its_interface_is_on_the_render(preset, tmp_path):
    """The port drawn at each of its sizes, read as `apothecary parts verify` reads it."""
    from apothecary.projects.parts.stl_renderer import get_renderer, render_part

    if not get_renderer().is_available:
        pytest.skip("OpenSCAD not installed")
    params = PORT.preset(preset)
    out = tmp_path / f"{preset}.stl"
    result = render_part(PORT, out, params)
    assert result.success, result.error_message
    mesh = read_mesh(out)
    read = [r for i in PORT.interfaces(params) for r in readings(i, mesh)]
    assert read and all(r.holds() for r in read), read


def test_registered_by_name():
    assert part_named("dust_port", ROOT).presets == PORT.presets
