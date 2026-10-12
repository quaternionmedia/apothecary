"""A SCAD text's top-level assignments, as the page and the server both read them
(apothecary/projects/parts/assignments.py's grammar): where each is, its value or
its expression, the customizer's comment, and a value written back in place.
"""

from __future__ import annotations

import pytest

from apothecary.projects.parts.assignments import (
    Unparsed,
    customizer_comment,
    differences,
    last_of,
    literal_text,
    literal_value,
    parse_assignments,
    write_values,
)

TEXT = """// A block.
include <dims.scad>
use <lib/tools.scad>
/* [Size] */
// Width [mm]
width = 34; // [10:100]
depth = 20.5;    // [5:0.5:50]
height = 10; // mm
label = "a \\"quoted\\" one"; // 20
shape = "round"; // [round, square]
tabs = 2; // [0:none, 1:left, 2:both]
corner = [1, 2.5, -3];
on = true;
wall = width * 0.1;   // computed
a = 1; b = 2;
spread = [ for (i = [0:2]) i * width ];
/* [Hidden] */
$fn = 32;
module body(w = 5) {
    inner = 3;
    cube([w, inner, 1]);
}
after = 7;
function f(x) = x + 1;
body();
"""


def _by_name(text=TEXT):
    return {a.name: a for a in parse_assignments(text)}


class TestWhatIsAnAssignment:
    def test_only_top_level_statements_and_never_inside_a_module(self):
        names = [a.name for a in parse_assignments(TEXT)]
        assert names == [
            "width",
            "depth",
            "height",
            "label",
            "shape",
            "tabs",
            "corner",
            "on",
            "wall",
            "a",
            "b",
            "spread",
            "$fn",
            "after",
        ]

    def test_parameters_stop_at_the_first_module_and_hidden_hides(self):
        found = _by_name()
        assert found["width"].parameter and found["spread"].parameter
        assert not found["$fn"].parameter and found["$fn"].group == "Hidden"
        assert not found["after"].parameter and found["after"].group == "Hidden"
        assert found["width"].group == "Size"

    def test_literals_are_read_and_expressions_are_computed(self):
        found = _by_name()
        assert (found["width"].value, found["width"].computed) == (34, False)
        assert isinstance(found["width"].value, int) and found["depth"].value == 20.5
        assert found["label"].value == 'a "quoted" one'
        assert found["corner"].value == [1, 2.5, -3] and found["on"].value is True
        for name in ("wall", "spread"):
            assert found[name].computed and found[name].value is None
            assert found[name].value_known is False
        assert found["wall"].expression == "width * 0.1"

    def test_two_on_a_line_each_have_their_own_span(self):
        found = _by_name()
        line = "a = 1; b = 2;"
        start = TEXT.index(line)
        assert found["a"].line == found["b"].line
        assert (found["a"].from_, found["a"].to) == (start + 4, start + 5)
        assert TEXT[found["b"].from_ : found["b"].to] == "2"

    def test_the_span_is_the_value_exactly(self):
        for a in parse_assignments(TEXT):
            assert TEXT[a.from_ : a.to] == a.expression
        assert _by_name()["width"].line == 6

    def test_offsets_count_utf16_as_an_editor_in_the_page_does(self):
        text = "// 😀 a face\nsize = 3;\n"
        (size,) = parse_assignments(text)
        # The emoji is one code point and two UTF-16 units: the offset is one more.
        assert size.from_ == text.index("3") + 1 and size.to == size.from_ + 1
        assert size.start == text.index("3")


class TestTheComment:
    def test_a_bracket_alone_is_the_customizers(self):
        found = _by_name()
        assert (found["width"].min, found["width"].max, found["width"].step) == (10, 100, None)
        assert (found["depth"].min, found["depth"].step, found["depth"].max) == (5, 0.5, 50)
        assert [o.value for o in found["shape"].options] == ["round", "square"]
        assert [(o.value, o.label) for o in found["tabs"].options] == [
            (0, "none"),
            (1, "left"),
            (2, "both"),
        ]
        assert found["label"].step == 20  # a string's maximum length

    def test_a_word_is_its_unit_and_a_caption_in_brackets_too(self):
        found = _by_name()
        assert (found["width"].unit, found["width"].caption) == ("mm", "Width")
        assert found["height"].unit == "mm" and found["height"].comment == "mm"
        assert found["corner"].comment is None and found["corner"].unit is None

    @pytest.mark.parametrize(
        "comment,says",
        [
            ("[10:100]", {"min": 10, "max": 100}),
            ("[1:0.5:20]", {"min": 1, "step": 0.5, "max": 20}),
            ("[10]", {"min": 0, "max": 10}),
            ("0.5", {"step": 0.5}),
            ("[10:100] mm", {}),  # a word after the bracket: not read, as OpenSCAD does not
            ("Cube size in mm", {}),
            ("", {}),
        ],
    )
    def test_what_a_comment_tells(self, comment, says):
        told = customizer_comment(comment)
        assert {k: v for k, v in told.items() if k != "options"} == says


class TestWritingAValue:
    def test_round_trip_a_value_rewritten_keeps_its_line_and_comment(self):
        written = write_values(TEXT, {"width": 50, "depth": 7.25, "shape": "square"})
        assert "width = 50; // [10:100]\n" in written
        assert "depth = 7.25;    // [5:0.5:50]\n" in written
        assert 'shape = "square"; // [round, square]\n' in written
        again = _by_name(written)
        assert (again["width"].value, again["depth"].value) == (50, 7.25)
        assert (again["width"].min, again["width"].max) == (10, 100)
        assert again["width"].comment == "[10:100]" and again["width"].line == 6
        # Nothing else moved: the rest of the text is as it was.
        assert (
            written.replace("50", "34", 1)
            .replace("7.25", "20.5")
            .replace('"square"; //', '"round"; //')
            == TEXT
        )

    def test_a_computed_one_is_replaced_by_the_plain_value(self):
        written = write_values(TEXT, {"wall": 3.4})
        assert "wall = 3.4;   // computed\n" in written
        assert not _by_name(written)["wall"].computed

    def test_a_name_not_assigned_is_appended_on_a_line_of_its_own(self):
        written = write_values("size = 1;", {"extra": [1, 2], "size": 2})
        assert written == "size = 2;\nextra = [1, 2];\n"

    def test_the_last_assignment_is_the_one_written(self):
        assert write_values("x = 1;\nx = 2;\n", {"x": 5}) == "x = 1;\nx = 5;\n"

    @pytest.mark.parametrize(
        "value,text",
        [
            (12, "12"),
            (12.0, "12"),
            (0.1, "0.1"),
            (-2.5, "-2.5"),
            (True, "true"),
            (False, "false"),
            ("a\\b", '"a\\\\b"'),
            ([1, 2.5], "[1, 2.5]"),
            (None, "undef"),
        ],
    )
    def test_a_literal_is_written_and_read_back(self, value, text):
        assert literal_text(value) == text
        assert literal_value(text) == value

    def test_an_expression_is_no_literal(self):
        for expression in ("size * 2", "f(1)", "[0:2]", "[1, x]", "1 + 2"):
            with pytest.raises(Unparsed):
                literal_value(expression)

    def test_what_a_text_sets_otherwise_than_another(self):
        own = "a = 1;\nb = 2;\nc = a * 2;\n"
        assert differences(write_values(own, {"b": 3}), own) == {"b": 3}
        assert differences(own + "d = 4;\n", own) == {"d": 4}
        assert differences(own.replace("a * 2", "a * 3"), own) == {"c": "a * 3"}
        assert last_of(parse_assignments(own))["c"].computed


def test_the_calibration_cubes_scad_reads_as_its_customizer_does():
    from apothecary.projects.parts.calibration_cube import DEFAULT as CUBE

    found = {a.name: a for a in parse_assignments(CUBE.source_file.read_text())}
    assert [n for n, a in found.items() if a.parameter] == [
        "size",
        "show_axes",
        "show_dimensions",
        "wall_thickness",
    ]
    # "[10:1:50] Cube size in mm": text after the bracket, so no range, as OpenSCAD reads it.
    assert found["size"].min is None and found["size"].comment.startswith("[10:1:50]")
    assert found["axis_length"].computed and not found["axis_length"].parameter
