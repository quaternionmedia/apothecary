"""One loader reads a part: from its ``part.json`` when the folder has one, else
from its wrapper, and a part that will not load is recorded by name."""

from __future__ import annotations

import json

import pytest

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
