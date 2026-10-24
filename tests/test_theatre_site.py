"""The theatre as a site: its shell the theatre part, the example rig hung in it by its
positions, the scenery beside it, another rig in its place, and the shell's sliders as
the SCAD draws them."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from apothecary import theatre_site
from apothecary.api import app
from apothecary.meshes import bounds, read_mesh
from apothecary.projects.parts import theatre
from apothecary.projects.parts.stl_renderer import get_renderer

client = TestClient(app)


def _subsystem(site, name):
    (node,) = [c for c in site.children if c.name == name]
    return node


def test_the_shell_is_the_theatre_part_at_its_defaults_and_its_walls():
    """The shell is the building's walls, as the garage's are: drawn faded, a click
    passing through it to what hangs inside."""
    site = theatre_site.create_theatre_site()
    shell = _subsystem(site, "theatre")
    assert (shell.part_ref, shell.category) == ("theatre", "wall")
    assert shell.footprint == theatre.DEFAULT.get_bounds()


def test_the_example_rig_hangs_on_its_positions_and_checks_clean():
    """The site's pieces are its subsystems: the shell, the lighting by its hanging
    positions, the scenery; every located patch is in one of them, and it checks clean."""
    site = theatre_site.create_theatre_site()
    assert [(c.name, c.category) for c in site.children] == [
        ("theatre", "wall"),
        ("lighting", "lighting"),
        ("scenery", "scenic"),
    ]
    lighting, scenery = _subsystem(site, "lighting"), _subsystem(site, "scenery")
    assert [position.name for position in lighting.children] == [
        "foh",
        "1st_electric",
        "2nd_electric",
        "3rd_electric_cyc",
        "groundrow",
        "house",
    ]
    rig = theatre_site.load_theatre_rig()
    located = [p for p in rig.patches if p.location is not None]
    hung = [f for position in lighting.children for f in position.children]
    assert len(hung) + len(scenery.children) == len(located)
    assert all(f.name.startswith("ch") for f in hung + scenery.children)
    foh = next(position for position in lighting.children if position.name == "foh")
    assert {f.name for f in foh.children} == {
        f"ch{p.channel}_FOH_{p.label.split()[-1]}" for p in located if p.label.startswith("FOH")
    }
    assert theatre_site.validate_theatre(site).violations == []


def test_site_units_are_millimetres_and_the_rig_is_in_metres():
    """A fixture stands where the rig's exports place it, in the site's frame: its
    subsystem and its position stand at the site's origin."""
    site = theatre_site.create_theatre_site()
    first = next(p for p in theatre_site.load_theatre_rig().patches if p.location is not None)
    lighting = _subsystem(site, "lighting")
    assert lighting.position == lighting.children[0].position == type(lighting.position)()
    node = next(
        f
        for position in lighting.children
        for f in position.children
        if f.name.startswith(f"ch{first.channel}_")
    )
    assert (node.position.x, node.position.y) == pytest.approx(
        (first.location.x * 1000, first.location.y * 1000)
    )


PARAMS = "FIXTURE_TYPE_NAME,FIXTURE_TYPE_MANUFACTURER,PARAMETER_TYPE,PARAMETER_TYPE_TEXT_SHORT\nDimmer,Generic,0,Intens\n"
PATCHES = (
    "CHANNEL,FIXTURE_TYPE,MANUFACTURER,ADDRESS,LABEL,LOCATION_X,LOCATION_Y,LOCATION_Z,"
    "ORIENTATION_X,ORIENTATION_Y,ORIENTATION_Z\n"
    "1,Dimmer,Generic,1/1,Over the stage,0,5,8,0,0,0\n"
    "2,Dimmer,Generic,1/2,In the car park,0,90,8,0,0,0\n"
)


def test_another_rig_stands_in_and_one_hung_outside_is_named(monkeypatch, tmp_path):
    (tmp_path / "patches.csv").write_text(PATCHES, encoding="utf-8")
    (tmp_path / "fixture-parameters.csv").write_text(PARAMS, encoding="utf-8")
    monkeypatch.setenv(theatre_site.RIG_ENV, str(tmp_path))
    site = theatre_site.create_theatre_site()
    assert [c.name for c in site.children] == ["theatre", "lighting"]
    # Labels with no number: each its own position.
    assert [
        (position.name, [f.name for f in position.children])
        for position in _subsystem(site, "lighting").children
    ] == [
        ("over_the_stage", ["ch1_Over_the_stage"]),
        ("in_the_car_park", ["ch2_In_the_car_park"]),
    ]
    report = theatre_site.validate_theatre(site)
    assert [(v.kind, v.structures) for v in report.violations] == [
        ("outside_the_theatre", ["ch2 In the car park"])
    ]


def test_with_no_rig_the_theatre_is_its_shell(monkeypatch, tmp_path):
    monkeypatch.setenv(theatre_site.RIG_ENV, str(tmp_path / "nowhere"))
    assert theatre_site.load_theatre_rig() is None
    assert [c.name for c in theatre_site.create_theatre_site().children] == ["theatre"]


def test_the_theatre_answers_over_http():
    assert client.get("/sites/theatre").status_code == 200
    body = client.get("/sites/theatre/lighting").json()
    assert len(body["rig"]["patches"]) == len(theatre_site.load_theatre_rig().patches)
    assert body["violations"] == []
    assert client.get("/sites/theatre/lighting/state").json()["seq"] == 0


# `name = default; // [min:step:max] words` -- the SCAD's sliders.
SLIDER = re.compile(r"^(\w+)\s*=\s*([-\d.]+);\s*//\s*\[([-\d.]+):([-\d.]+):([-\d.]+)\]", re.M)


def test_the_sliders_are_the_scads():
    """The page's sliders come from the part's parameters; the SCAD's customizer has the
    same names, defaults and ranges, so a value the page offers is one the SCAD takes."""
    scad = theatre.DEFAULT.source_file.read_text(encoding="utf-8")
    sliders = {m[0]: tuple(float(v) for v in (m[1], m[2], m[4])) for m in SLIDER.findall(scad)}
    fields = theatre.Params.model_fields
    assert set(sliders) == set(fields)
    for name, (default, low, high) in sliders.items():
        meta = {type(m).__name__: m for m in fields[name].metadata}
        assert (fields[name].default, meta["Ge"].ge, meta["Le"].le) == (default, low, high), name


@pytest.mark.skipif(not get_renderer().is_available, reason="OpenSCAD not installed")
def test_a_resized_shell_is_where_its_bounds_say(tmp_path):
    """Slid smaller, with no pit and no house: the rendered shell is the declared one."""
    resized = {"stage_width": 12000, "stage_depth": 10000, "house_depth": 0, "pit_width": 0}
    out = tmp_path / "theatre.stl"
    done = get_renderer().render_stl(theatre.DEFAULT.source_file, out, params=resized)
    assert done.success, done.error_message
    lo, hi = bounds(read_mesh(out))
    declared = theatre.DEFAULT.get_bounds(resized)
    assert lo == pytest.approx(
        [declared.min_point.x, declared.min_point.y, declared.min_point.z], abs=1
    )
    assert hi == pytest.approx(
        [declared.max_point.x, declared.max_point.y, declared.max_point.z], abs=1
    )
