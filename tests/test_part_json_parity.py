"""The parts that were Python modules holding only literals are `part.json`
files; what they say, and what `apothecary problems` says of them, is what the
modules said."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from apothecary.cli.main import cli
from apothecary.projects.parts.skeleton import ROOT
from apothecary.projects.registry import part_named

# name: (description, category, tags, preview colour hex, bounds min/max, display rotation)
RECORDED = {
    "contranot": ("Contra-notation accessory", "misc", ["contra", "notation"], None, None, None),
    "couch_block": (
        "Couch block spacer",
        "furniture",
        ["couch", "spacer", "block"],
        "#8B4513",
        ((-76.2, 0, 0), (76.2, 101.6, 50.8)),
        None,
    ),
    "dryerknob": (
        "Dryer knob replacement",
        "appliance",
        ["knob", "dryer", "replacement"],
        "#FFFFFF",
        ((-16.5, -16.5, 0), (16.5, 16.5, 20)),
        None,
    ),
    "matboard_cutter_mount": (
        "Matboard cutter mount",
        "tooling",
        ["matboard", "cutter", "mount"],
        None,
        None,
        None,
    ),
    "parametric_star": (
        "Parametric star cookie cutter",
        "cookie-cutter",
        ["star", "parametric", "cookie"],
        "#FFD700",
        ((-12.135, -14.266, 0), (15, 14.266, 3)),
        None,
    ),
    "solderfan": (
        "Soldering fan mount",
        "electronics",
        ["fan", "mount", "soldering"],
        None,
        None,
        (90, 0, 0),
    ),
    "star_cookiecutter": (
        "Star cookie cutter",
        "cookie-cutter",
        ["cookie", "star"],
        None,
        None,
        None,
    ),
}


@pytest.mark.parametrize("name", sorted(RECORDED))
def test_a_part_json_says_what_its_module_said(name):
    description, category, tags, color, bounds, rotation = RECORDED[name]
    part = part_named(name, ROOT)
    assert (part.description, part.category, part.tags) == (description, category, tags)
    assert part.readme_path == ROOT / "parts" / "README.md"
    assert part.source_file == ROOT / "parts" / name / f"{name}.scad"
    assert part.preview_color.to_hex().upper() == (color or "#7F7F7F")  # the base part's grey
    if bounds is None:
        assert part.default_bounds is None
    else:
        lo, hi = part.default_bounds.min_point, part.default_bounds.max_point
        assert ((lo.x, lo.y, lo.z), (hi.x, hi.y, hi.z)) == bounds
    if rotation is None:
        assert not any(
            (part.display_rotation.x, part.display_rotation.y, part.display_rotation.z)
        )
    else:
        r = part.display_rotation
        assert (r.x, r.y, r.z) == rotation


def test_problems_reads_these_parts_as_it_did_when_they_were_modules():
    """Each is read, none is reported broken, and what is open about one is a
    print-readiness check; which are open depends on the renders on disk."""
    result = CliRunner().invoke(cli, ["problems"])
    assert result.exit_code == 0, result.output
    for name in RECORDED:
        lines = [line for line in result.output.splitlines() if f" {name}:" in line]
        assert not any("raised" in line or "broken" in line for line in lines), lines
        assert all(("unbounded" in line or "unprintable" in line) for line in lines), lines
