"""Layout verification for the garage-workbench worked example (not ratified API).

"Verifiable" here means checked in code with apothecary.models.bounds.BoundingBox3D,
not eyeballed from a rendered .scad file: every printer Structure must sit exactly
on the bench's top surface, stay within the bench's footprint, and not overlap
its neighbors.
"""

import itertools

from apothecary.example_hierarchy import (
    BENCH_DEPTH,
    BENCH_MOUNTED_STRUCTURES,
    BENCH_TOP_Z,
    BENCH_WIDTH,
    create_example_site,
    validate_garage_layout,
)
from apothecary.hierarchy import Site, Structure, Substructure
from apothecary.models.bounds import BoundingBox3D
from apothecary.models.vectors import Vector3D
from apothecary.primitives import Cube


def _printer_structures(site):
    return [s for s in site.children if s.name in BENCH_MOUNTED_STRUCTURES]


def test_site_has_the_bench_printers_and_the_expanded_garage_systems():
    site = create_example_site()
    names = {s.name for s in site.children}
    assert {"workbench", "printer_1", "printer_2", "printer_3"} <= names
    assert {
        "garage_building",
        "lighting",
        "hvac",
        "electrical",
        "fluids",
        "storage_shelving",
        "cnc_router",
    } <= names


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


def test_garage_shell_fixtures_storage_and_cnc_router_render():
    site = create_example_site()
    rendered = site.render()
    assert "Structure: garage_building (Wood-framed, steel siding)" in rendered
    for wall in ("north_wall", "south_wall", "west_wall", "east_wall"):
        assert f"Substructure: {wall}" in rendered
    assert "Feature: door_opening" in rendered
    assert "Feature: window_opening" in rendered

    for fixture, output in (
        ("lighting", "light_output"),
        ("hvac", "vent_output"),
        ("electrical", "outlet_output"),
        ("fluids", "spigot_output"),
    ):
        assert f"Structure: {fixture}" in rendered
        assert f"Feature: {output}" in rendered

    assert "Structure: storage_shelving (Powder-coated steel)" in rendered
    assert rendered.count("Feature: shelf_") == 3

    assert "Structure: cnc_router" in rendered
    assert "Feature: cable_pass_through" in rendered  # unaffected by the additions above


def test_cnc_router_has_no_build_volume_and_is_not_job_compatible():
    site = create_example_site()
    router = next(s for s in site.children if s.name == "cnc_router")
    assert router.status == "idle"
    assert router.build_volume is None


def test_site_renders_valid_jscad():
    site = create_example_site()
    rendered = site.render_jscad()
    assert "export const main" in rendered
    assert "cube(" in rendered


def test_validate_garage_layout_is_clean_by_default():
    site = create_example_site()
    report = validate_garage_layout(site)
    assert report.is_valid
    assert report.violations == []


def test_validate_garage_layout_catches_overlap():
    site = create_example_site()
    printer_1, printer_2 = site.children[1], site.children[2]
    printer_2.position = Vector3D(
        x=printer_1.position.x, y=printer_1.position.y, z=printer_1.position.z
    )

    report = validate_garage_layout(site)
    assert not report.is_valid
    kinds = {v.kind for v in report.violations}
    assert "overlap" in kinds


def test_validate_garage_layout_catches_overhang():
    site = create_example_site()
    printer_1 = site.children[1]
    printer_1.position = Vector3D(
        x=BENCH_WIDTH - 10, y=printer_1.position.y, z=printer_1.position.z
    )

    report = validate_garage_layout(site)
    assert not report.is_valid
    kinds = {v.kind for v in report.violations}
    assert "out_of_bounds" in kinds


def test_validate_garage_layout_catches_wrong_height():
    site = create_example_site()
    printer_1 = site.children[1]
    printer_1.position = Vector3D(x=printer_1.position.x, y=printer_1.position.y, z=0)

    report = validate_garage_layout(site)
    assert not report.is_valid
    kinds = {v.kind for v in report.violations}
    assert "not_on_bench" in kinds


def test_validate_garage_layout_with_no_workbench_only_runs_generic_check():
    site = Site(
        name="no_bench",
        structures=[
            Structure(name="printer_1", substructures=[Substructure(name="s", base=Cube())])
        ],
    )
    report = validate_garage_layout(site)
    assert report.is_valid  # no bench, no overlaps -- nothing to flag


def test_validate_garage_layout_with_bench_missing_footprint_only_runs_generic_check():
    site = Site(
        name="bad_bench",
        structures=[
            Structure(name="workbench", substructures=[Substructure(name="s", base=Cube())]),
            Structure(
                name="printer_1",
                footprint=BoundingBox3D(max_point=Vector3D(x=10, y=10, z=10)),
                substructures=[Substructure(name="s", base=Cube())],
            ),
        ],
    )
    report = validate_garage_layout(site)
    assert report.is_valid  # workbench has no footprint, so nothing to check printers against


def test_validate_garage_layout_skips_structures_with_no_footprint():
    site = Site(
        name="garage",
        structures=[
            Structure(
                name="workbench",
                footprint=BoundingBox3D(max_point=Vector3D(x=100, y=100, z=10)),
                substructures=[Substructure(name="s", base=Cube())],
            ),
            Structure(
                name="mystery_object",  # no footprint, and not bench-mounted either
                substructures=[Substructure(name="s", base=Cube())],
            ),
        ],
    )
    report = validate_garage_layout(site)
    assert report.is_valid  # not in BENCH_MOUNTED_STRUCTURES -- nothing to check it against
