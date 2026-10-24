"""Every number in a SCAD file is a control, or it is a number nobody tunes.

The point of a slider board is that the design can be moved. A dimension that
lives only in the SCAD file cannot be staged, validated or iterated -- it can
only be edited, which is the loop this tooling exists to replace.
"""

from __future__ import annotations

import re

import pytest

from apothecary.projects.parts.datum_cap import DEFAULT as CAP
from apothecary.projects.parts.datum_core import DEFAULT as CORE

PARTS = [pytest.param(CORE, id="datum_core"), pytest.param(CAP, id="datum_cap")]


def scad_numerics(path) -> list[str]:
    """Top-level `name = <number>;` assignments, in file order."""
    text = path.read_text(encoding="utf-8")
    return [m.group(1) for m in re.finditer(r"^(\w+)\s*=\s*-?[\d.]+\s*;", text, re.M)]


@pytest.mark.parametrize("part", PARTS)
def test_every_scad_number_has_a_parameter(part):
    declared = set(part.params_model.model_fields)
    missing = [n for n in scad_numerics(part.source_file) if n not in declared]
    assert not missing, f"{part.name}: no control for {missing}"


@pytest.mark.parametrize("part", PARTS)
def test_no_parameter_is_dead(part):
    """A parameter with no number behind it renders nothing when moved.

    `datum_core` carried six of these after the cover moved to `datum_cap` --
    indicator and contact dimensions the file no longer used.
    """
    numerics = set(scad_numerics(part.source_file))
    orphans = [f for f in part.params_model.model_fields if f not in numerics]
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
