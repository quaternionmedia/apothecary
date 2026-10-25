"""What a page needs to draw real controls: integers as integers, the customizer's step,
enums with their options, a nested model as a group of fields, descriptions, and units
declared on the field -- a model's ``json_schema_extra={"unit": ...}``, a customizer
comment's bracket or trailing word -- and none where none is declared."""

from __future__ import annotations

from enum import Enum
from typing import List, Literal, Optional

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from apothecary.api import app
from apothecary.projects.parts import stl_renderer
from apothecary.projects.parts.base import BasePart
from apothecary.projects.parts.customizer import (
    check_scad,
    scad_fields,
    unit_of,
)
from apothecary.projects.parts.params import params_spec


class Style(int, Enum):
    FULL = 0
    AUTO_FIT = 1


class Holes(BaseModel):
    """Holes in the base."""

    magnets: bool = Field(False, description="Holes for magnets")
    depth: float = Field(2.0, gt=0, json_schema_extra={"unit": "mm"})


class Model(BaseModel):
    count: int = Field(3, ge=1, le=10, description="How many")
    width: float = Field(20.0, gt=0, json_schema_extra={"unit": "mm"}, description="Across")
    scoop: float = Field(0.5, ge=0, le=1)
    pitch: float = Field(2.5, multiple_of=0.5)
    offset: float = 0.0
    turns: int = 0
    style: Style = Field(Style.AUTO_FIT, description="Tab style")
    shape: Literal["round", "square"] = "round"
    chamfer: Optional[float] = Field(None, json_schema_extra={"unit": "mm"})
    holes: Holes = Field(default_factory=Holes)
    corner: List[float] = Field(default_factory=lambda: [1.0, 2.0])


def _fields(model=Model):
    part = BasePart(name="m", source_file=__file__, params_model=model)
    return {f.name: f for f in params_spec(part).fields}


class TestAModelsFields:
    def test_an_int_is_an_integer_with_a_step_of_one_and_whole_bounds(self):
        count = _fields()["count"]
        assert (count.type, count.integer, count.step, count.default) == ("number", True, 1.0, 3)
        assert isinstance(count.default, int) and (count.min, count.max) == (1, 10)
        turns = _fields()["turns"]
        assert turns.integer and turns.min < turns.max and float(turns.max).is_integer()

    def test_a_float_is_not_and_its_multiple_of_is_its_step(self):
        fields = _fields()
        assert fields["scoop"].integer is False and fields["scoop"].step is None
        assert fields["pitch"].step == 0.5

    def test_a_number_with_no_bound_and_a_zero_default_is_still_a_number(self):
        offset = _fields()["offset"]
        assert offset.type == "number" and offset.min < offset.max

    def test_a_unit_is_what_the_field_declares_and_none_where_it_declares_none(self):
        fields = _fields()
        assert fields["width"].unit == "mm" and fields["width"].description == "Across"
        assert fields["chamfer"].unit == "mm" and fields["chamfer"].type == "number"
        assert [n for n, f in fields.items() if f.unit] == ["width", "chamfer"]

    def test_an_enum_is_its_options_each_labelled_by_its_name(self):
        style = _fields()["style"]
        assert (style.type, style.default, style.description) == ("enum", 1, "Tab style")
        assert [(o.value, o.label) for o in style.options] == [(0, "full"), (1, "auto fit")]
        assert style.pattern == "^(0|1)$"

    def test_a_literal_is_an_enum_of_its_values(self):
        shape = _fields()["shape"]
        assert shape.type == "enum" and [(o.value, o.label) for o in shape.options] == [
            ("round", "round"),
            ("square", "square"),
        ]

    def test_a_nested_model_is_a_group_of_its_own_fields(self):
        holes = _fields()["holes"]
        assert holes.type == "group" and holes.description == "Holes in the base."
        assert holes.default == {"magnets": False, "depth": 2.0}
        inner = {f.name: f for f in holes.fields}
        assert (inner["magnets"].type, inner["magnets"].description) == (
            "boolean",
            "Holes for magnets",
        )
        assert (inner["depth"].type, inner["depth"].unit) == ("number", "mm")

    def test_a_list_of_numbers_is_a_vector(self):
        corner = _fields()["corner"]
        assert corner.type == "vector" and corner.default == [1.0, 2.0]


class TestTheLibrarysParts:
    def test_gridfinity_has_whole_numbers_choices_and_a_group(self):
        from apothecary.projects.parts.gridfinity import DEFAULT

        fields = {f.name: f for f in params_spec(DEFAULT).fields}
        assert fields["gridx"].integer and fields["gridx"].step == 1
        assert fields["gridz"].integer is False
        assert fields["style_tab"].type == "enum"
        assert [o.label for o in fields["style_tab"].options][:2] == ["full", "auto"]
        assert fields["hole_options"].type == "group"
        assert {f.type for f in fields["hole_options"].fields} == {"boolean"}

    def test_lengths_are_in_mm_where_the_model_says_so(self):
        body = TestClient(app).get("/parts/calibration_cube/params").json()
        units = {f["name"]: f["unit"] for f in body["fields"]}
        assert units == {
            "size": "mm",
            "show_axes": None,
            "show_dimensions": None,
            "wall_thickness": "mm",
        }


# --- the customizer's ------------------------------------------------------------------

SCAD = """/* [Size] */
// Width [mm]
width = 34; // [10:100]
// Depth, in mm
depth = 20; // [5:0.5:50]
height = 10; // mm
// Turn
angle = 30; // deg
count = 3; // [1:1:10]
gap = 0.5; // [0:0.1:2]
// Label [mm]
label = "hi"; // 20
corner = [1, 2]; // mm
plain = 7;
"""


def _entry(name, **kw):
    return {"name": name, "type": "number", "group": "Size", **kw}


LISTED = [
    _entry("width", caption="Width [mm]", initial=34.0, min=10.0, max=100.0, step=1.0),
    _entry("depth", caption="Depth, in mm", initial=20.0, min=5.0, max=50.0, step=0.5),
    _entry("height", initial=10.0, step=1.0),
    _entry("angle", caption="Turn", initial=30.0, step=1.0),
    _entry("count", initial=3.0, min=1.0, max=10.0, step=1.0),
    _entry("gap", initial=0.5, min=0.0, max=2.0, step=0.1),
    {"name": "label", "type": "string", "caption": "Label [mm]", "initial": "hi"},
    _entry("corner", initial=[1.0, 2.0]),
    _entry("plain", initial=7.0, step=1.0),
]


class TestTheCustomizersUnits:
    def test_a_caption_ending_in_a_unit_in_brackets_gives_it(self):
        assert unit_of(LISTED[0], SCAD) == ("mm", "Width")

    def test_the_parameters_own_comment_of_one_word_gives_it(self):
        assert unit_of(LISTED[2], SCAD) == ("mm", None)
        assert unit_of(LISTED[3], SCAD) == ("deg", "Turn")

    @pytest.mark.parametrize(
        "caption,line",
        [
            ("Depth, in mm", "depth = 20; // [5:0.5:50]"),  # a word in the caption is not one
            ("Holes (mm)", "hole = 3;"),  # nor a unit in round brackets
            ("Range [10:100]", "x = 5;"),  # a range in brackets is not a unit
            ("Choice [a, b]", "x = 5;"),
            ("Size [10]", "x = 5;"),  # nor a number
            (None, "x = 5; // [10:100] mm"),  # a word after a range is not read
            (None, "x = 5; // 20"),  # a number is not a unit
            (None, "x = 5; // two words"),
        ],
    )
    def test_anything_else_is_no_unit(self, caption, line):
        name = line.split("=")[0].strip()
        assert unit_of({"name": name, "caption": caption}, line + "\n")[0] is None

    def test_fields_carry_units_integers_and_steps(self):
        fields = {f.name: f for f in scad_fields(LISTED, text=SCAD)}
        assert (fields["width"].unit, fields["width"].description) == ("mm", "Width")
        assert (fields["depth"].unit, fields["depth"].step) == (None, 0.5)
        assert fields["height"].unit == "mm" and fields["angle"].unit == "deg"
        assert fields["corner"].type == "vector" and fields["corner"].unit == "mm"
        assert fields["label"].unit is None and fields["label"].description == "Label [mm]"
        assert fields["plain"].unit is None
        # Whole when its range, step and value are, as OpenSCAD's own slider steps it.
        assert fields["width"].integer and fields["count"].integer
        assert not fields["depth"].integer and not fields["gap"].integer
        # A number with no stated range is not held to whole numbers.
        assert not fields["plain"].integer and not fields["height"].integer
        assert fields["gap"].step == 0.1

    def test_without_the_text_a_caption_still_gives_one(self):
        fields = {f.name: f for f in scad_fields(LISTED)}
        assert fields["width"].unit == "mm" and fields["height"].unit is None


def test_a_real_snapshot_lists_what_the_units_are_read_beside(tmp_path, listing_openscad):
    scad = tmp_path / "units.scad"
    scad.write_text(SCAD.replace('label = "hi"; // 20\n', "") + "cube([width, depth, height]);\n")
    check = check_scad(scad, stl_renderer.OpenSCADRenderer(str(listing_openscad)))
    fields = {f.name: f for f in scad_fields(check.parameters, text=scad.read_text())}
    assert (fields["width"].unit, fields["width"].description) == ("mm", "Width")
    assert (fields["width"].min, fields["width"].max, fields["width"].integer) == (10, 100, True)
    assert (fields["depth"].step, fields["depth"].integer) == (0.5, False)
    assert fields["height"].unit == "mm" and fields["angle"].unit == "deg"
    assert fields["count"].integer and fields["plain"].unit is None
