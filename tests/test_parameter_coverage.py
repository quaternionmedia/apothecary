"""Every number in a SCAD file is a control, or it is a number nobody tunes.

The point of a slider board is that the design can be moved. A dimension that
lives only in the SCAD file cannot be staged, validated or iterated -- it can
only be edited, which is the loop this tooling exists to replace.
"""

from __future__ import annotations

import re
from importlib import import_module

import pytest

from apothecary.projects.parts.base import scad_variables
from apothecary.projects.parts.datum_cap import DEFAULT as CAP
from apothecary.projects.parts.datum_core import DEFAULT as CORE
from apothecary.projects.parts.skeleton import ROOT
from apothecary.projects.parts.stl_renderer import geometry_scad
from apothecary.projects.registry import scan_projects

PARTS = [pytest.param(CORE, id="datum_core"), pytest.param(CAP, id="datum_cap")]


def _parts_with_params():
    found = {}
    for item in scan_projects(ROOT):
        if item.kind == "part" and item.wrapper:
            part = import_module(item.wrapper).DEFAULT
            if part.params_model is not None:
                found[item.name] = part
    return [pytest.param(part, id=name) for name, part in sorted(found.items())]


def _moved(value):
    """A different valid value for a number or a flag; anything else unchanged."""
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value + 1
    return value


def scad_numerics(path) -> list[str]:
    """Top-level `name = <number>;` assignments, in file order."""
    text = path.read_text(encoding="utf-8")
    return [m.group(1) for m in re.finditer(r"^(\w+)\s*=\s*-?[\d.]+\s*;", text, re.M)]


@pytest.mark.parametrize("part", PARTS)
def test_every_scad_number_has_a_parameter(part):
    declared = set(part.params_model.model_fields)
    missing = [n for n in scad_numerics(part.source_file) if n not in declared]
    assert not missing, f"{part.name}: no control for {missing}"


@pytest.mark.parametrize("part", _parts_with_params())
def test_no_parameter_is_dead(part):
    """A parameter that reaches nothing is reported as a success while the
    slider moves and the part does not. A part built by Python geometry must
    generate different SCAD for each; any other must pass each as `-D` names
    its SCAD assigns, since OpenSCAD ignores the rest."""
    defaults = part.params_model()
    fields = list(part.params_model.model_fields)
    if part.geometry({}) is not None:
        at_rest = geometry_scad(part, {})
        dead = [
            f
            for f in fields
            if geometry_scad(part, part.validate_overrides({f: _moved(getattr(defaults, f))}))
            == at_rest
        ]
    else:
        variables = scad_variables(part.source_file)
        emitted = {
            f: set(part.scad_overrides(part.validate_overrides({f: getattr(defaults, f)})))
            for f in fields
        }
        dead = [f for f, names in emitted.items() if not names or not names <= variables]
    assert not dead, f"{part.name}: {dead} reach nothing"


@pytest.mark.parametrize("part", PARTS)
def test_every_default_matches_the_scad_default(part):
    """A control that starts somewhere the file does not is lying at rest."""
    text = part.source_file.read_text(encoding="utf-8")
    values = {
        m.group(1): float(m.group(2))
        for m in re.finditer(r"^(\w+)\s*=\s*(-?[\d.]+)\s*;", text, re.M)
    }
    defaults = part.params_model()
    for name, value in values.items():
        assert getattr(defaults, name) == pytest.approx(value), name


def test_a_part_without_a_model_refuses_a_name_its_scad_does_not_declare():
    """dryerknob has no Python model; `-p knob_diameter=60` used to render the
    defaults and report success, because OpenSCAD ignores an unknown -D."""
    from apothecary.projects.parts.dryerknob import DEFAULT as knob

    declared = scad_variables(knob.source_file)
    with pytest.raises(ValueError, match="unknown parameter"):
        knob.validate_overrides({"knob_diameter": 60})
    if declared:
        name = sorted(declared)[0]
        assert knob.validate_overrides({name: 1}) == {name: 1}
