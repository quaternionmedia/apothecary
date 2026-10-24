"""Parameter overrides reaching OpenSCAD, and the bounds they are checked against."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner
from rendered_parts import built_stl_fixture, registered_parts  # noqa: F401

from apothecary.cli import cli
from apothecary.meshes import bounds, read_mesh
from apothecary.projects.parts.stl_renderer import get_renderer, scad_definitions, scad_literal

DECLARING_BOUNDS = [
    pytest.param(part, id=name)
    for name, part in registered_parts()
    if part is not None and part.get_bounds() is not None
]


class TestScadLiteral:
    """A Python value has to survive the trip into OpenSCAD source."""

    def test_string_carries_its_quotes(self):
        # -D values are parsed as source, so a bare word is an identifier.
        assert scad_literal("tray") == '"tray"'

    def test_bool_is_not_an_integer(self):
        # bool subclasses int; true/false are not 1/0 in OpenSCAD.
        assert scad_literal(True) == "true"
        assert scad_literal(False) == "false"

    def test_numbers_and_vectors(self):
        assert scad_literal(1.6) == "1.6"
        assert scad_literal(40) == "40"
        assert scad_literal([1, 2, 3]) == "[1, 2, 3]"

    def test_embedded_quote_is_escaped(self):
        assert scad_literal('a"b') == '"a\\"b"'

    def test_unrepresentable_values_are_refused(self):
        with pytest.raises(ValueError):
            scad_literal(float("inf"))
        with pytest.raises(TypeError):
            scad_literal({"a": 1})

    def test_definitions_are_flag_value_pairs(self):
        assert scad_definitions({"tag": "lid", "walls": 3}) == [
            "-D",
            'tag="lid"',
            "-D",
            "walls=3",
        ]
        assert scad_definitions(None) == []


class TestParameterValidation:
    """A typo must fail before a render, not after one that ignored it."""

    def test_unknown_parameter_is_named_and_refused(self):
        result = CliRunner().invoke(
            cli, ["parts", "generate-stl", "datum_core", "-p", "headrooom=10"]
        )
        assert result.exit_code != 0
        assert "unknown parameter(s): headrooom" in result.output
        # The message has to say what is available, or the user is guessing.
        assert "headroom" in result.output

    def test_value_outside_the_model_is_refused(self):
        result = CliRunner().invoke(cli, ["parts", "generate-stl", "datum_core", "-p", "walls=-1"])
        assert result.exit_code != 0
        assert "invalid parameters" in result.output

    def test_pair_without_a_value_is_refused(self):
        result = CliRunner().invoke(cli, ["parts", "generate-stl", "datum_core", "-p", "show"])
        assert result.exit_code != 0
        assert "name=value" in result.output


class TestBoundsMatchGeometry:
    """The declared envelope, measured against what OpenSCAD actually emits."""

    @pytest.mark.slow
    @pytest.mark.parametrize("part", DECLARING_BOUNDS)
    def test_declared_bounds_are_the_rendered_ones(self, part, built_stl):
        """`apothecary parts verify --all`, corners as well as sizes: a box of the
        right size in the wrong place misleads a layout just as much."""
        declared = part.get_bounds()
        lo, hi = bounds(read_mesh(built_stl(part)))
        assert list(lo) == pytest.approx(declared.min_point.to_list(), abs=0.5), part.name
        assert list(hi) == pytest.approx(declared.max_point.to_list(), abs=0.5), part.name

    @pytest.mark.skipif(not get_renderer().is_available, reason="OpenSCAD not installed")
    def test_verify_measures_the_part_as_overridden(self):
        """The command itself, on a part whose one parameter moves its box."""
        result = CliRunner().invoke(cli, ["parts", "verify", "v_slot", "-p", "length=50"])
        assert result.exit_code == 0, result.output
        assert "50.00" in result.output

    def test_info_reports_the_same_bounds_it_verifies(self):
        result = CliRunner().invoke(cli, ["parts", "info", "datum_core", "--json-out"])
        assert result.exit_code == 0
        size = json.loads(result.output)["bounds"]["size"]
        assert size == pytest.approx({"x": 46.8, "y": 46.8, "z": 15.6})
