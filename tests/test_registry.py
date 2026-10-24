from pathlib import Path

from apothecary.projects import registry
from apothecary.projects.registry import (
    _locate_wrapper_for_part,
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
    # parametric_star should have a wrapper
    scad = root / "parts" / "parametric_star.scad"
    assert _locate_wrapper_for_part(scad) == "apothecary.projects.parts.parametric_star"
    # cookiecutter (modern spelling) should have a wrapper
    scad2 = root / "parts" / "star_cookiecutter.scad"
    assert _locate_wrapper_for_part(scad2) == "apothecary.projects.parts.star_cookiecutter"


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
