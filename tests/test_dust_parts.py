"""The stepped hose adapter and the stand-ins it fits (parts/dust/): its tracked
SCAD is its code, it prints as it stands, its interfaces are its profile's, and
each pair it is made for fits as parts/dust/README.md says."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from rendered_parts import built_stl_fixture, registered_parts  # noqa: F401

from apothecary.fittings import readings
from apothecary.meshes import read_mesh
from apothecary.models.interfaces import fit
from apothecary.projects.parts.hose_adapter import DEFAULT, Params, profile
from apothecary.projects.parts.skeleton import ROOT
from apothecary.projects.parts.stl_renderer import geometry_scad
from apothecary.projects.registry import part_named

STUBS = ("dust_hose_40", "dust_port_32", "dust_port_25")

DECLARING_INTERFACES = [
    pytest.param(part, id=name)
    for name, part in registered_parts()
    if part is not None and part.has_interfaces
]


def interface(part: str, name: str):
    return part_named(part, ROOT).interface(name)


# --- the adapter ----------------------------------------------------------------------


def test_the_tracked_scad_is_the_code_at_its_defaults():
    """`apothecary parts render hose_adapter -o parts/dust/hose_adapter/hose_adapter.scad`
    rewrites it."""
    assert DEFAULT.source_file.read_text(encoding="utf-8") == geometry_scad(DEFAULT, {})


def test_it_prints_as_it_stands_and_its_box_is_its_profile():
    shape = profile(Params())
    assert shape.problems() == []
    box = DEFAULT.get_bounds()
    assert (box.size.x, box.size.y, box.size.z) == (46.0, 46.0, 101.5)


def test_parameters_that_would_not_print_are_refused():
    with pytest.raises(ValidationError, match="transition: its bore closes in past 45"):
        Params(transition_length=2.0)


def test_its_interfaces_are_its_drawing_and_the_two_fitting_ends_exclude_each_other():
    found = {i.name: i for i in DEFAULT.interfaces()}
    assert list(found) == ["hose", "fitting_32", "fitting_25"]
    assert {i.source for i in found.values()} == {"drawn"}
    assert found["fitting_32"].excludes == ["fitting_25"]
    assert found["fitting_25"].excludes == ["fitting_32"]
    assert found["hose"].normal.z == -1 and found["fitting_32"].normal.z == 1


def test_without_its_tip_it_is_a_plain_40_to_32():
    found = DEFAULT.interfaces({"tip": False})
    assert [(i.name, i.excludes, i.lead) for i in found] == [
        ("hose", [], 0.0),
        ("fitting_32", [], 0.0),
    ]
    assert DEFAULT.get_bounds({"tip": False}).size.z == 78.0


# --- the stand-ins --------------------------------------------------------------------


@pytest.mark.parametrize("name", STUBS)
def test_each_stand_in_is_a_stub_and_says_so_of_its_interface(name):
    part = part_named(name, ROOT)
    assert "stub" in part.tags
    assert [i.source for i in part.interfaces()] == ["stub"]


# --- the fits parts/dust/README.md states ---------------------------------------------


def test_the_hose_takes_the_whole_hose_end_opened_two_and_a_half_percent():
    f = fit(interface("hose_adapter", "hose"), interface("dust_hose_40", "end"))
    assert (f.verdict, f.seat, f.gap, f.stretch) == ("seats", 40.0, 0.0, 0.025)


def test_each_port_takes_its_step_part_way_in():
    f32 = fit(interface("hose_adapter", "fitting_32"), interface("dust_port_32", "port"))
    f25 = fit(interface("hose_adapter", "fitting_25"), interface("dust_port_25", "port"))
    assert (f32.verdict, f32.seat, f25.verdict, f25.seat) == ("seats", 12.5, "seats", 10.0)


def test_the_wrong_step_for_a_port_says_why():
    assert (
        fit(interface("hose_adapter", "fitting_32"), interface("dust_port_25", "port")).verdict
        == "will not enter"
    )
    assert (
        fit(interface("hose_adapter", "fitting_25"), interface("dust_port_32", "port")).verdict
        == "loose"
    )


# --- every part that declares interfaces, on its render -------------------------------


def test_the_dust_parts_are_among_the_parts_that_declare_interfaces():
    names = {p.id for p in DECLARING_INTERFACES}
    assert {"hose_adapter", *STUBS} <= names


@pytest.mark.slow
@pytest.mark.parametrize("part", DECLARING_INTERFACES)
def test_each_declared_round_interface_is_on_the_render(part, built_stl):
    """`apothecary parts verify`'s reading, for every part that declares interfaces."""
    mesh = read_mesh(built_stl(part))
    read = [r for i in part.interfaces() for r in readings(i, mesh)]
    assert read, part.name
    assert all(r.holds() for r in read), [r for r in read if not r.holds()]
