"""Layout verification for the garage-workbench worked example (not ratified API).

"Verifiable" here means checked in code with apothecary.models.bounds.BoundingBox3D,
not eyeballed from a rendered .scad file: every printer Structure must sit exactly
on the bench's top surface, stay within the bench's footprint, and not overlap
its neighbors.
"""

import itertools

from apothecary.example_hierarchy import (
    BENCH_DEPTH,
    BENCH_TOP_Z,
    BENCH_WIDTH,
    create_example_site,
)


def _printer_structures(site):
    return [s for s in site.structures if s.name != "workbench"]


def test_site_has_one_bench_and_three_printers():
    site = create_example_site()
    names = [s.name for s in site.structures]
    assert names == ["workbench", "printer_1", "printer_2", "printer_3"]


def test_every_printer_sits_exactly_on_the_bench_top_surface():
    site = create_example_site()
    for printer in _printer_structures(site):
        bounds = printer.world_bounds()
        assert bounds is not None, f"{printer.name} has no footprint set"
        assert bounds.min_point.z == BENCH_TOP_Z


def test_every_printer_footprint_is_contained_within_the_bench_top():
    site = create_example_site()
    for printer in _printer_structures(site):
        bounds = printer.world_bounds()
        assert 0 <= bounds.min_point.x and bounds.max_point.x <= BENCH_WIDTH, (
            f"{printer.name} overhangs the bench in X: {bounds.min_point.x}..{bounds.max_point.x} "
            f"vs bench width {BENCH_WIDTH}"
        )
        assert 0 <= bounds.min_point.y and bounds.max_point.y <= BENCH_DEPTH, (
            f"{printer.name} overhangs the bench in Y: {bounds.min_point.y}..{bounds.max_point.y} "
            f"vs bench depth {BENCH_DEPTH}"
        )


def test_no_two_printers_overlap():
    site = create_example_site()
    printers = _printer_structures(site)
    for a, b in itertools.combinations(printers, 2):
        bounds_a, bounds_b = a.world_bounds(), b.world_bounds()
        assert not bounds_a.intersects(bounds_b), f"{a.name} and {b.name} overlap"


def test_bench_and_printers_render_with_expected_systems():
    site = create_example_site()
    rendered = site.render()
    assert "Structure: workbench (Steel frame, pine top)" in rendered
    assert "Substructure: frame_system" in rendered
    assert "Substructure: gantry_system" in rendered
    for i in (1, 2, 3):
        assert f"Structure: printer_{i} (Aluminum extrusion + PETG)" in rendered
    assert rendered.count("Feature: leg_") == 4
    assert "Feature: cable_pass_through" in rendered
    assert rendered.count("Feature: left_post") == 3
    assert rendered.count("Feature: right_post") == 3
    assert rendered.count("Feature: gantry_bar") == 3


def test_site_renders_valid_jscad():
    site = create_example_site()
    rendered = site.render_jscad()
    assert "export const main" in rendered
    assert "cube(" in rendered
