"""One loader reads a part: from its ``part.json`` when the folder has one, else
from its wrapper, and a part that will not load is recorded by name."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from apothecary.projects.parts.base import BasePart
from apothecary.projects.parts.described import DescribedPart
from apothecary.projects.parts.stl_renderer import get_renderer, render_part
from apothecary.projects.registry import (
    PartLoadError,
    load_part,
    load_parts,
    part_named,
    scan_projects,
)


def _folder(root, name, scad="cube([3, 4, 5]);\n", sidecar=None):
    folder = root / "parts" / name
    folder.mkdir(parents=True)
    (folder / f"{name}.scad").write_text(scad, encoding="utf-8")
    if sidecar is not None:
        (folder / "part.json").write_text(sidecar, encoding="utf-8")
    return folder


def test_a_folder_holding_only_a_part_json_is_found_and_loads_as_a_part(tmp_path):
    _folder(tmp_path, "zz_only_json", sidecar=json.dumps({"category": "testing", "tags": ["x"]}))
    item = next(p for p in scan_projects(tmp_path) if p.name == "zz_only_json")
    assert item.wrapper is None and item.sidecar.name == "part.json" and item.has_part
    part = load_part(item)
    assert isinstance(part, DescribedPart)
    assert part.category == "testing" and part.exists
    assert part_named("zz_only_json", tmp_path).name == "zz_only_json"


@pytest.mark.skipif(not get_renderer().is_available, reason="OpenSCAD not installed")
def test_a_part_json_part_renders_as_a_wrapper_part_does(tmp_path):
    _folder(tmp_path, "zz_renders", sidecar="{}")
    part = part_named("zz_renders", tmp_path)
    out = tmp_path / "out.stl"
    result = render_part(part, out)
    assert result.success and out.is_file()


def test_a_broken_part_json_is_reported_by_name_not_passed_over(tmp_path):
    _folder(tmp_path, "zz_good", sidecar="{}")
    _folder(tmp_path, "zz_broken", sidecar="{not json")
    loaded = load_parts(tmp_path)
    assert [item.name for item, _ in loaded.parts if item.name.startswith("zz_")] == ["zz_good"]
    assert [f.name for f in loaded.failed] == ["zz_broken"]
    assert "part.json" in loaded.failed[0].source and "zz_broken" in loaded.failed[0].error
    with pytest.raises(PartLoadError) as raised:
        part_named("zz_broken", tmp_path)
    assert raised.value.name == "zz_broken"


def test_a_part_json_that_turns_its_part_is_refused_saying_what_to_do(tmp_path):
    """A part's SCAD lays it the way up it prints, which is its STL: a part.json that
    says display_rotation is refused when the part loads, by name, with what to do
    instead -- lay it so in the SCAD, and declare rest for how it stands in use."""
    _folder(tmp_path, "zz_flat", sidecar="{}")
    turned = {"category": "testing", "display_rotation": [90, 0, 0]}
    _folder(tmp_path, "zz_turned", sidecar=json.dumps(turned))
    loaded = load_parts(tmp_path)
    assert [item.name for item, _ in loaded.parts if item.name.startswith("zz_")] == ["zz_flat"]
    assert [(f.name, Path(f.source).name) for f in loaded.failed] == [("zz_turned", "part.json")]
    error = loaded.failed[0].error
    for said in ("display_rotation turns nothing", "Lay it so in the SCAD", "declare rest"):
        assert said in error, error
    with pytest.raises(PartLoadError, match="display_rotation turns nothing") as raised:
        part_named("zz_turned", tmp_path)
    assert raised.value.name == "zz_turned"


def test_check_and_problems_say_a_refused_part_json_did_not_load(tmp_path):
    """`apothecary check` names the part.json; `apothecary problems` reports the part
    broken, and its detail (`--detail`) is what to do."""
    from apothecary.cli.system import _openscad_for
    from apothecary.spaces import _broken

    _folder(tmp_path, "zz_turned", sidecar=json.dumps({"display_rotation": [90, 0, 0]}))
    with pytest.raises(PartLoadError) as raised:
        part_named("zz_turned", tmp_path)
    assert _openscad_for("zz_turned", raised.value) == (
        "  ✗ zz_turned: its part.json does not load (apothecary problems --detail)"
    )
    problem = _broken("zz_turned", raised.value.cause)
    assert problem.kind == "broken" and "Lay it so in the SCAD" in problem.detail


def test_a_wrapper_that_turns_its_part_is_refused(tmp_path):
    with pytest.raises(ValidationError, match="display_rotation turns nothing"):
        BasePart(name="zz_turned", source_file=tmp_path / "zz.scad", display_rotation=[90, 0, 0])


def test_a_rest_names_only_what_its_scad_assigns(tmp_path):
    """A rest's names are -D definitions of the SCAD's own variables. One the SCAD does
    not assign draws nothing, so a part.json that moved display_rotation under rest
    would rest as it prints and say nothing: it is refused when the part loads, naming
    what is not assigned."""
    resting = {"rest": {"print": False}}
    _folder(
        tmp_path, "zz_rests", scad="print = true;\ncube([3, 4, 5]);\n", sidecar=json.dumps(resting)
    )
    turned = {"rest": {"display_rotation": [90, 0, 0]}}
    _folder(tmp_path, "zz_turned", sidecar=json.dumps(turned))
    loaded = load_parts(tmp_path)
    assert [item.name for item, _ in loaded.parts if item.name.startswith("zz_")] == ["zz_rests"]
    assert [f.name for f in loaded.failed] == ["zz_turned"]
    assert "rest: display_rotation is not assigned in zz_turned.scad" in loaded.failed[0].error


def test_a_rest_definition_is_no_parameter(tmp_path):
    """Set by hand, a rest definition would turn what a slice reads: an override that
    names one is refused, by a part with no Params model too, whose SCAD assigns it."""
    resting = {"rest": {"print": False}}
    _folder(
        tmp_path,
        "zz_rests",
        scad="print = true;\nw = 3;\ncube([w, 4, 5]);\n",
        sidecar=json.dumps(resting),
    )
    part = part_named("zz_rests", tmp_path)
    assert part.validate_overrides({"w": 4}) == {"w": 4}
    with pytest.raises(ValueError, match="print says how zz_rests rests, in its rest"):
        part.validate_overrides({"print": True})


def test_a_part_that_is_not_registered_is_a_key_error(tmp_path):
    _folder(tmp_path, "zz_present", sidecar="{}")
    with pytest.raises(KeyError):
        part_named("zz_absent", tmp_path)


def test_a_wrapper_that_will_not_import_is_recorded_with_its_module(monkeypatch):
    from dataclasses import replace

    item = next(p for p in scan_projects(_root()) if p.name == "contranot")
    broken = replace(item, wrapper="apothecary.projects.parts.zz_no_such_wrapper", sidecar=None)
    with pytest.raises(PartLoadError) as raised:
        load_part(broken)
    assert raised.value.source == "apothecary.projects.parts.zz_no_such_wrapper"
    assert isinstance(raised.value.cause, ModuleNotFoundError)


def _root():
    from apothecary.projects.parts.skeleton import ROOT

    return ROOT


def test_a_part_json_names_the_readme_it_shares(tmp_path):
    _folder(tmp_path, "zz_shared_readme", sidecar=json.dumps({"readme": "../README.md"}))
    (tmp_path / "parts" / "README.md").write_text("# parts\n", encoding="utf-8")
    assert part_named("zz_shared_readme", tmp_path).readme_path == tmp_path / "parts" / "README.md"
    own = _folder(tmp_path, "zz_own_readme", sidecar="{}")
    (own / "README.md").write_text("# own\n", encoding="utf-8")
    assert part_named("zz_own_readme", tmp_path).readme_path == own / "README.md"


def test_no_import_hook_serves_a_part_json_part():
    import sys
    from importlib import import_module

    from apothecary.projects.parts import described

    assert not any("Described" in type(f).__name__ for f in sys.meta_path)
    assert not hasattr(described, "install_finder") and not hasattr(described, "__path__")
    with pytest.raises(ModuleNotFoundError):
        import_module("apothecary.projects.parts.described.arduino_uno")


def test_only_the_registry_imports_a_wrapper_by_its_module_path():
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    pattern = re.compile(r"import_module\(\s*\w+\.wrapper\b")
    found = [
        str(path.relative_to(root))
        for folder in ("apothecary", "tests")
        for path in sorted((root / folder).rglob("*.py"))
        if path.name != "test_part_loader.py" and pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert found == ["apothecary/projects/registry.py"]


def test_a_part_has_the_name_of_its_folder():
    """The registry's name, the part's own name and the name a URL or the CLI
    takes are one."""
    from apothecary.projects.parts.skeleton import ROOT

    loaded = load_parts(ROOT)
    assert loaded.failed == []
    assert {item.name: part.name for item, part in loaded.parts if item.name != part.name} == {}
