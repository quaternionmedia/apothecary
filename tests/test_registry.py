from pathlib import Path

from apothecary.projects.registry import (
    _locate_wrapper_for_part,
    scan_templates,
    summarize_structure,
)


def test_scan_templates_and_summarize():
    root = Path(__file__).resolve().parents[1]
    tpls = scan_templates(root)
    # We have at least the provided templates directory in the repo
    assert isinstance(tpls, list)

    summary = summarize_structure(root)
    assert "projects" in summary and "parts" in summary and "templates" in summary
    assert Path(summary["root"]).exists()


def test_locate_wrapper_for_known_parts():
    root = Path(__file__).resolve().parents[1]
    # parametric_star should have a wrapper
    scad = root / "parts" / "parametric_star.scad"
    assert _locate_wrapper_for_part(scad) == "apothecary.projects.parts.parametric_star"
    # cookiecutter (modern spelling) should have a wrapper
    scad2 = root / "parts" / "star-cookiecutter.scad"
    assert _locate_wrapper_for_part(scad2) == "apothecary.projects.parts.star_cookiecutter"
