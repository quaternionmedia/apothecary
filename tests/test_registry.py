import json
import os
from pathlib import Path

from apothecary.projects import registry
from apothecary.projects.registry import (
    _locate_wrapper_for_part,
    category_of,
    scan_projects,
    scan_templates,
    summarize_structure,
)


def test_scan_templates_and_summarize():
    root = Path(__file__).resolve().parents[1]
    assert root / "templates" / "basic.scad.j2" in scan_templates(root)

    summary = summarize_structure(root)
    assert "projects" in summary and "parts" in summary and "templates" in summary
    assert Path(summary["root"]).exists()


def test_locate_wrapper_for_known_parts():
    root = Path(__file__).resolve().parents[1]
    # datum_core keeps a Python wrapper
    scad = root / "parts" / "datum_core" / "datum_core.scad"
    assert _locate_wrapper_for_part(scad) == "apothecary.projects.parts.datum_core"
    # parametric_star is described by its part.json and has no wrapper
    star = root / "parts" / "parametric_star" / "parametric_star.scad"
    assert _locate_wrapper_for_part(star) is None
    item = next(p for p in scan_projects(root) if p.name == "parametric_star")
    assert item.sidecar == star.parent / "part.json" and item.has_part


def _add_part(root: Path, name: str) -> None:
    folder = root / "parts" / name
    folder.mkdir(parents=True)
    (folder / f"{name}.scad").write_text("cube(1);\n", encoding="utf-8")


def _names(root: Path) -> set[str]:
    return {p.name for p in scan_projects(root) if p.kind == "part"}


def test_a_scan_is_kept_until_the_parts_change(tmp_path, monkeypatch):
    scans = []
    real = registry._scan
    monkeypatch.setattr(registry, "_scan", lambda root: scans.append(root) or real(root))
    _add_part(tmp_path, "first")

    assert "first" in _names(tmp_path)
    assert "first" in _names(tmp_path)
    assert len(scans) == 1

    _add_part(tmp_path, "second")
    assert {"first", "second"} <= _names(tmp_path)
    assert len(scans) == 2

    registry.invalidate()
    _names(tmp_path)
    assert len(scans) == 3


def test_each_root_has_its_own_scan(tmp_path):
    _add_part(tmp_path / "a", "only_in_a")
    _add_part(tmp_path / "b", "only_in_b")
    assert "only_in_a" in _names(tmp_path / "a") - _names(tmp_path / "b")
    assert "only_in_b" in _names(tmp_path / "b") - _names(tmp_path / "a")


def test_a_caller_cannot_change_the_kept_scan(tmp_path):
    _add_part(tmp_path, "kept")
    scan_projects(tmp_path).clear()
    assert "kept" in _names(tmp_path)


def _describe(root: Path, name: str, text: str, at_second: int) -> None:
    """Write a part's part.json, its time set apart from any written before it, as an
    edit a second later would be."""
    sidecar = root / "parts" / name / "part.json"
    sidecar.write_text(text, encoding="utf-8")
    os.utime(sidecar, ns=(at_second * 10**9, at_second * 10**9))


def test_a_parts_category_is_kept_while_its_part_json_is_and_a_failure_never(tmp_path, monkeypatch):
    """Asked before the part is there: None, and found once it is. A part.json left as it
    was is not read again, an edited one is, and one that will not load is None and read
    again when next asked, its time unchanged."""
    assert category_of("later", tmp_path) is None
    _add_part(tmp_path, "later")
    _describe(tmp_path, "later", json.dumps({"category": "coupon"}), 1_000_000)
    assert category_of("later", tmp_path) == "coupon"

    loads = []
    real = registry.load_part
    monkeypatch.setattr(registry, "load_part", lambda item: loads.append(item) or real(item))
    assert category_of("later", tmp_path) == "coupon"
    assert loads == []

    _describe(tmp_path, "later", json.dumps({"category": "camera"}), 1_000_001)
    assert category_of("later", tmp_path) == "camera"
    _describe(tmp_path, "later", "{ this will not load", 1_000_002)
    assert category_of("later", tmp_path) is None
    loads.clear()
    assert category_of("later", tmp_path) is None
    assert len(loads) == 1  # a failure is asked again
    _describe(tmp_path, "later", json.dumps({"category": "machine"}), 1_000_002)
    assert category_of("later", tmp_path) == "machine"
