"""Tests for the parts library as a fractal tree (prototype, unratified).

Covers migrating the registered parts/ registry into leaf Assembly nodes --
see apothecary/example_parts_library.py's docstring for why this exists.
"""

from apothecary.example_parts_library import (
    CELL_PITCH,
    GRID_COLUMNS,
    create_parts_library_site,
    validate_parts_library,
)
from apothecary.projects.parts.skeleton import ROOT
from apothecary.projects.registry import scan_projects


def _registered_part_names():
    return {p.name for p in scan_projects(ROOT) if p.kind == "part" and p.wrapper}


def test_site_has_one_leaf_per_registered_part():
    site = create_parts_library_site()
    names = {leaf.name for leaf in site.children}
    assert names == _registered_part_names()


def test_every_leaf_is_a_part_role_with_part_ref_and_footprint():
    site = create_parts_library_site()
    for leaf in site.children:
        assert leaf.role == "part"
        assert leaf.part_ref == leaf.name
        assert leaf.footprint is not None
        # a leaf has no geometry/children of its own -- it's addressed by
        # part_ref, not composed like a Structure/Substructure/Feature
        assert leaf.children == []
        assert leaf.additions == []
        assert leaf.subtractions == []
        assert leaf.base is None


def test_leaves_are_arranged_on_a_non_overlapping_grid():
    site = create_parts_library_site()
    positions = {(leaf.position.x, leaf.position.y) for leaf in site.children}
    # every leaf got a distinct grid slot -- no two parts stacked at the same spot
    assert len(positions) == len(site.children)
    for leaf in site.children:
        assert leaf.position.x % CELL_PITCH == 0
        assert leaf.position.y % CELL_PITCH == 0
        assert leaf.position.x < GRID_COLUMNS * CELL_PITCH


def test_validate_parts_library_is_always_valid():
    site = create_parts_library_site()
    report = validate_parts_library(site)
    assert report.is_valid
    assert report.violations == []
