"""Parameter overrides reaching OpenSCAD, and the bounds they are checked against.

Every part carries a typed ``Params`` model and a hand-written ``get_bounds``
beside hand-written OpenSCAD. Until these existed, neither the model nor the
bounds were connected to the geometry at all: the model never reached the
renderer, and nothing compared the declared envelope to the real one.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from apothecary.cli import cli
from apothecary.projects.parts.stl_renderer import scad_definitions, scad_literal


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
        assert scad_definitions({"show": "lid", "walls": 3}) == [
            "-D",
            'show="lid"',
            "-D",
            "walls=3",
        ]
        assert scad_definitions(None) == []


class TestParameterValidation:
    """A typo must fail before a render, not after one that ignored it."""

    def test_unknown_parameter_is_named_and_refused(self):
        result = CliRunner().invoke(
            cli, ["parts", "generate-stl", "datum-core", "-p", "headrooom=10"]
        )
        assert result.exit_code != 0
        assert "unknown parameter(s): headrooom" in result.output
        # The message has to say what is available, or the user is guessing.
        assert "headroom" in result.output

    def test_value_outside_the_model_is_refused(self):
        result = CliRunner().invoke(
            cli, ["parts", "generate-stl", "datum-core", "-p", "show=banana"]
        )
        assert result.exit_code != 0
        assert "invalid parameters" in result.output

    def test_pair_without_a_value_is_refused(self):
        result = CliRunner().invoke(cli, ["parts", "generate-stl", "datum-core", "-p", "show"])
        assert result.exit_code != 0
        assert "name=value" in result.output


@pytest.mark.slow
class TestBoundsMatchGeometry:
    """The declared envelope, measured against what OpenSCAD actually emits."""

    @pytest.mark.parametrize("show,height", [("tray", 15.6), ("lid", 5.0), ("exploded", 32.6)])
    def test_each_variant_verifies(self, show, height):
        result = CliRunner().invoke(cli, ["parts", "verify", "datum-core", "-p", f"show={show}"])
        assert result.exit_code == 0, result.output
        assert f"{height:.2f}" in result.output

    def test_info_reports_the_same_bounds_it_verifies(self):
        result = CliRunner().invoke(cli, ["parts", "info", "datum-core", "--json-out"])
        assert result.exit_code == 0
        size = json.loads(result.output)["bounds"]["size"]
        assert size == pytest.approx({"x": 46.8, "y": 46.8, "z": 15.6})
