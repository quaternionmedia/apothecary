"""A part without a Python model gets controls from its SCAD's own parameters,
as OpenSCAD's customizer lists them (apothecary/projects/parts/customizer.py),
and a staged set is checked against that list.

Most of these use a scripted OpenSCAD (tests/scripted_openscad.py) that lists
parameters as a snapshot does, or refuses as 2021.01 does; the last ones use a
real OpenSCAD that lists them, where this machine has one, and are skipped
where it has none.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from scripted_openscad import calls, renders, scripted_openscad, stl_names

from apothecary import api
from apothecary.api import app
from apothecary.projects.parts import customizer, stl_renderer
from apothecary.projects.parts.base import BasePart, scad_variables
from apothecary.projects.parts.calibration_cube import DEFAULT as CUBE
from apothecary.projects.parts.customizer import (
    customizer_spec,
    customizer_values,
    lists_parameters,
    scad_fields,
    without_initial,
)
from apothecary.projects.parts.params import params_spec
from apothecary.projects.parts.stl_renderer import OpenSCADRenderer

# What OpenSCAD 2026.09.27 lists for this SCAD, as it printed it:
#
#   /* [Size] */
#   // The width of it
#   width = 34; // [10:100]
#   height = 5.5; // [1:0.5:20]
#   // a toggle
#   hollow = true;
#   label = "hello"; // 20
#   shape = "round"; // [round, square, hex]
#   count = 3; // [1, 2, 3, 5]
#   named = 2; // [1:one, 2:two]
#   vec = [1, 2, 3];
#   neg = -4;
#   /* [Hidden] */
#   secret = 9;
LISTED = [
    {
        "caption": "The width of it",
        "group": "Size",
        "initial": 34.0,
        "max": 100.0,
        "min": 10.0,
        "name": "width",
        "step": 1.0,
        "type": "number",
    },
    {
        "group": "Size",
        "initial": 5.5,
        "max": 20.0,
        "min": 1.0,
        "name": "height",
        "step": 0.5,
        "type": "number",
    },
    {"caption": "a toggle", "group": "Size", "initial": True, "name": "hollow", "type": "boolean"},
    {"group": "Size", "initial": "hello", "maxLength": 20, "name": "label", "type": "string"},
    {
        "group": "Size",
        "initial": "round",
        "name": "shape",
        "options": [
            {"name": "round", "value": "round"},
            {"name": "square", "value": "square"},
            {"name": "hex", "value": "hex"},
        ],
        "type": "string",
    },
    {
        "group": "Size",
        "initial": 3.0,
        "name": "count",
        "options": [
            {"name": "1", "value": 1.0},
            {"name": "2", "value": 2.0},
            {"name": "3", "value": 3.0},
            {"name": "5", "value": 5.0},
        ],
        "type": "number",
    },
    {
        "group": "Size",
        "initial": 2.0,
        "name": "named",
        "options": [{"name": "one", "value": 1.0}, {"name": "two", "value": 2.0}],
        "type": "number",
    },
    {"group": "Size", "initial": [1.0, 2.0, 3.0], "name": "vec", "type": "number"},
    {"group": "Size", "initial": -4.0, "name": "neg", "step": 1.0, "type": "number"},
]


class TestFieldsFromTheListing:
    def test_each_kind_becomes_a_control_surfaces_field(self):
        fields = {f.name: f for f in scad_fields(LISTED)}
        assert list(fields) == [p["name"] for p in LISTED]
        width = fields["width"]
        assert (width.type, width.default, width.min, width.max, width.step) == (
            "number",
            34.0,
            10.0,
            100.0,
            1.0,
        )
        assert (width.group, width.description) == ("Size", "The width of it")
        assert (fields["height"].min, fields["height"].max, fields["height"].step) == (1, 20, 0.5)
        assert (fields["hollow"].type, fields["hollow"].default) == ("boolean", True)
        assert (fields["label"].type, fields["label"].default) == ("text", "hello")
        assert fields["vec"].type == "vector" and fields["vec"].default == [1.0, 2.0, 3.0]

    def test_choices_are_an_enum_with_their_options(self):
        fields = {f.name: f for f in scad_fields(LISTED)}
        shape, named = fields["shape"], fields["named"]
        assert shape.type == named.type == fields["count"].type == "enum"
        assert [(o.value, o.label) for o in named.options] == [(1.0, "one"), (2.0, "two")]
        assert [o.value for o in shape.options] == ["round", "square", "hex"]
        # A page that reads an enum's words from its pattern still can.
        assert shape.pattern == "^(round|square|hex)$"
        assert fields["count"].pattern == "^(1|2|3|5)$"

    def test_a_number_with_no_range_gets_one_to_drag_over(self):
        """As a model's field without bounds does: around its value, either side of zero."""
        fields = {f.name: f for f in scad_fields(LISTED)}
        neg = fields["neg"]
        assert neg.min < -4 < neg.max <= 0
        zero = scad_fields([{"name": "z", "type": "number", "initial": 0.0, "step": 1.0}])[0]
        assert zero.min < 0 < zero.max


class TestAStagedSetCheckedAgainstTheListing:
    def test_values_come_back_as_their_parameters_take_them(self):
        values, errors = customizer_values(
            LISTED,
            {
                "width": "40",
                "height": 2,
                "hollow": "false",
                "shape": "hex",
                "count": "5",
                "vec": [1, "2", 3.5],
            },
        )
        assert errors == []
        assert values == {
            "width": 40.0,
            "height": 2.0,
            "hollow": False,
            "shape": "hex",
            "count": 5.0,
            "vec": [1.0, 2.0, 3.5],
        }

    @pytest.mark.parametrize(
        "name, value, said",
        [
            ("width", 101, "at most 100"),
            ("width", 9.5, "at least 10"),
            ("width", "wide", "not a number"),
            ("width", True, "not true or false"),
            ("hollow", 1, "true or false"),
            ("shape", "oval", "one of round, square, hex"),
            ("named", 3, "one of 1, 2"),
            ("label", "x" * 21, "at most 20 characters"),
            ("vec", [1, 2], "a list of 3 numbers"),
            ("nope", 1, "no such parameter"),
        ],
    )
    def test_a_value_it_does_not_take_is_named(self, name, value, said):
        values, errors = customizer_values(LISTED, {name: value})
        assert values == {} and [e.field for e in errors] == [name]
        assert said in errors[0].message

    def test_a_number_with_no_stated_range_is_held_to_none(self):
        values, errors = customizer_values(LISTED, {"neg": 1000})
        assert errors == [] and values == {"neg": 1000.0}

    def test_a_value_the_scad_assigns_itself_is_no_override(self):
        values, _ = customizer_values(LISTED, {"width": 34, "height": 2})
        assert without_initial(LISTED, values) == {"height": 2.0}


def test_a_special_variable_the_scad_assigns_is_a_parameter():
    """``$fn = 64;`` at the top of a SCAD is reached by -D like any other."""
    assert scad_variables(Path("x.scad"), text="$fn = 64;\nx = 1;\n") == {"$fn", "x"}


# --- which OpenSCAD can list ------------------------------------------------------------


def test_a_snapshot_lists_and_2021_01_does_not(tmp_path):
    assert lists_parameters(scripted_openscad(tmp_path / "new" / "openscad"))
    assert not lists_parameters(
        scripted_openscad(tmp_path / "old" / "openscad", "2021.01", lists=False)
    )
    assert not lists_parameters(None) and not lists_parameters(tmp_path / "missing")


# --- the routes -------------------------------------------------------------------------

SCAD = """// A block.
width = 34; // [10:100]
depth = 20;
hollow = true;
module block() { cube([width, depth, 3]); }
block();
"""


@pytest.fixture
def openscad(tmp_path, monkeypatch):
    """``openscad(version, lists)``: the scripted OpenSCAD every call in the test
    uses; the variant cache is the test's own."""
    monkeypatch.setenv("APOTHECARY_CACHE_DIR", str(tmp_path / "cache"))

    def install(version: str = "2026.09.27", lists: bool = True) -> Path:
        exe = scripted_openscad(tmp_path / "bin" / version / "openscad", version, lists)
        monkeypatch.setenv("APOTHECARY_OPENSCAD", str(exe))
        monkeypatch.setattr(stl_renderer, "_renderer", None)
        return exe

    return install


@pytest.fixture
def block(tmp_path, monkeypatch):
    """A part with no Python model, at ``/parts/block``; its STL is the test's own."""
    scad = tmp_path / "parts" / "block" / "block.scad"
    scad.parent.mkdir(parents=True)
    scad.write_text(SCAD)
    part = BasePart(name="block", source_file=scad)
    real = api._load_part_wrapper
    monkeypatch.setattr(
        api, "_load_part_wrapper", lambda name: part if name == "block" else real(name)
    )
    return part


class TestTheParamsRoute:
    def test_a_part_without_a_model_answers_its_scads_own(self, openscad, block):
        exe = openscad()
        r = TestClient(app).get("/parts/block/params")
        assert r.status_code == 200, r.text
        body = r.json()
        assert (body["source"], body["openscad"]) == ("customizer", "OpenSCAD version 2026.09.27")
        fields = {f["name"]: f for f in body["fields"]}
        assert list(fields) == ["width", "depth", "hollow"]
        assert (fields["width"]["min"], fields["width"]["max"]) == (10.0, 100.0)
        assert fields["hollow"]["type"] == "boolean"
        # Listed once; asked again, the same SCAD is not listed again.
        TestClient(app).get("/parts/block/params")
        listings = [c for c in calls(exe) if c["format"] == "param"]
        assert len(listings) == 1 and listings[0]["cwd"] == str(block.part_dir)

    def test_2021_01_says_it_cannot_list_them(self, openscad, block):
        openscad("2021.01", lists=False)
        r = TestClient(app).get("/parts/block/params")
        assert r.status_code == 404
        detail = r.json()["detail"]
        assert detail["lists"] is False and detail["openscad"] == "OpenSCAD version 2021.01"
        assert "cannot list its SCAD's parameters" in detail["message"]
        assert "apothecary openscad install" in detail["message"]

    def test_a_scad_that_declares_none_says_so(self, openscad, block):
        openscad()
        block.source_file.write_text("cube(10);\n")
        detail = TestClient(app).get("/parts/block/params").json()["detail"]
        assert detail["lists"] is True and "declares no parameters" in detail["message"]

    def test_a_scad_openscad_cannot_read_says_where(self, openscad, block):
        openscad()
        block.source_file.write_text("x = 1;\ncube(x) SYNTAX ERROR\n")
        detail = TestClient(app).get("/parts/block/params").json()["detail"]
        assert "could not read its SCAD" in detail["message"]
        where = [(m["level"], m["line"]) for m in detail["messages"]]
        assert where == [("error", 2)]

    def test_a_part_with_a_model_answers_the_model_and_runs_nothing(self, openscad):
        exe = openscad()
        body = TestClient(app).get("/parts/calibration_cube/params").json()
        assert body["source"] == "model" and body == params_spec(CUBE).model_dump(mode="json")
        assert calls(exe) == []

    def test_a_models_tick_box_is_left_as_the_page_draws_it_today(self):
        """A model's boolean stays a number until the page has a tick-box to draw
        it with: a "boolean" there now would take its control away."""
        fields = {f.name: f for f in params_spec(CUBE).fields}
        assert fields["show_axes"].type == "number"


class TestTheCheckAndTheRender:
    def test_validate_checks_against_the_listing(self, openscad, block):
        openscad()
        client = TestClient(app)
        good = client.post("/parts/block/validate", json={"params": {"width": "50"}}).json()
        assert good["valid"] is True and good["params"] == {"width": 50.0}
        bad = client.post("/parts/block/validate", json={"params": {"width": 500}}).json()
        assert bad["valid"] is False and bad["errors"][0]["field"] == "width"

    def test_without_a_listing_validate_checks_the_names(self, openscad, block):
        openscad("2021.01", lists=False)
        client = TestClient(app)
        assert client.post("/parts/block/validate", json={"params": {"depth": 9}}).json()["valid"]
        refused = client.post("/parts/block/validate", json={"params": {"deep": 9}}).json()
        assert refused["valid"] is False and "unknown parameter" in refused["errors"][0]["message"]

    def test_generate_renders_what_the_listing_takes(self, openscad, block, tmp_path, monkeypatch):
        exe = openscad()
        monkeypatch.setattr(BasePart, "get_stl_output_path", lambda self: tmp_path / "block.stl")
        client = TestClient(app)
        r = client.post("/parts/block/stl/generate", json={"params": {"width": "50", "depth": 20}})
        assert r.status_code == 200, r.text
        body = r.json()
        # A number as a number, and depth, which the SCAD assigns itself, no override.
        assert body["params"] == {"width": 50.0}
        assert '"width=50.0"' in stl_names(client.get(body["stl_url"]).content)
        assert len(renders(exe)) == 1
        refused = client.post("/parts/block/stl/generate", json={"params": {"hollow": 3}})
        assert refused.status_code == 422 and "hollow" in refused.json()["detail"]
        assert len(renders(exe)) == 1


# --- the library's parts, with a real OpenSCAD that lists them ---------------------------


def _a_listing_openscad():
    """An OpenSCAD on this machine that lists a SCAD's parameters, or None."""
    for path in stl_renderer._openscad_candidates():
        if lists_parameters(path):
            return path
    return None


LISTING = _a_listing_openscad()
needs_a_listing_openscad = pytest.mark.skipif(
    LISTING is None, reason="no OpenSCAD here lists parameters (`apothecary openscad install`)"
)


@needs_a_listing_openscad
def test_a_real_snapshot_lists_every_kind(tmp_path):
    scad = tmp_path / "every_kind.scad"
    scad.write_text(
        "/* [Size] */\n// The width of it\nwidth = 34; // [10:100]\nheight = 5.5; // [1:0.5:20]\n"
        'hollow = true;\nlabel = "hello"; // 20\nshape = "round"; // [round, square, hex]\n'
        "named = 2; // [1:one, 2:two]\nvec = [1, 2, 3];\n/* [Hidden] */\nsecret = 9;\n"
        "cube([width, height, 3]);\n"
    )
    check = customizer.check_scad(scad, OpenSCADRenderer(str(LISTING)))
    assert check.ok and check.lists and check.messages == []
    fields = {f.name: f for f in scad_fields(check.parameters)}
    assert list(fields) == ["width", "height", "hollow", "label", "shape", "named", "vec"]
    assert [fields[n].type for n in fields] == [
        "number",
        "number",
        "boolean",
        "text",
        "enum",
        "enum",
        "vector",
    ]
    assert (fields["width"].min, fields["width"].max, fields["width"].group) == (10, 100, "Size")
    assert fields["height"].step == 0.5 and fields["width"].description == "The width of it"


@needs_a_listing_openscad
def test_a_real_snapshot_gives_the_librarys_model_less_parts_controls(monkeypatch):
    """solderfan has no Python model; its SCAD's own numbers are its controls."""
    from apothecary.projects.parts.solderfan import DEFAULT as solderfan

    spec = customizer_spec(solderfan, OpenSCADRenderer(str(LISTING)))
    fields = {f.name: f for f in spec.fields}
    assert spec.source == "customizer" and {"filterW", "fanW", "wall"} <= set(fields)
    assert all(fields[n].type == "number" for n in ("filterW", "fanW", "wall"))
    assert fields["filterW"].default == 130
