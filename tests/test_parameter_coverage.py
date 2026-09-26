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
from apothecary.projects.registry import scan_projects

PARTS = [pytest.param(CORE, id="datum_core"), pytest.param(CAP, id="datum_cap")]

# Owner decision pending: snowplow's parameters drive only the Python assembly
# behind `parts render`; its SCAD is flat literals.
NOT_YET_WIRED = {"snowplow"}


def _parts_with_params():
    found = {}
    for item in scan_projects(ROOT):
        if item.kind == "part" and item.wrapper:
            part = import_module(item.wrapper).DEFAULT
            if part.params_model is not None:
                found[item.name] = part
    return [
        pytest.param(
            part,
            id=name,
            marks=[pytest.mark.xfail(strict=True, reason="owner decision pending")]
            if name in NOT_YET_WIRED
            else [],
        )
        for name, part in sorted(found.items())
    ]


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
    """A parameter with no SCAD variable behind it is passed as `-D`, ignored,
    and reported as a success: the slider moves and the part does not."""
    variables = scad_variables(part.source_file)
    orphans = [f for f in part.params_model.model_fields if f not in variables]
    assert not orphans, f"{part.name}: {orphans} have no SCAD variable"


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
