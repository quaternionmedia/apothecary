"""Tests for the Site/Structure/Substructure/Feature prototype (not ratified API)."""

from apothecary.example_hierarchy import create_example_site
from apothecary.hierarchy import Feature, Site, Structure, Substructure
from apothecary.models.units import HardwareSizes, PrintSettings
from apothecary.models.vectors import Vector3D
from apothecary.primitives import Cube


def test_feature_clearance_hole_uses_print_settings_tolerance():
    ps = PrintSettings(tolerance=0.3)
    feature = Feature.clearance_hole(
        "test_hole",
        position=Vector3D(),
        nominal_diameter=HardwareSizes.M3,
        depth=10,
        print_settings=ps,
    )
    rendered = feature.render()
    assert "Feature: test_hole" in rendered
    # M3 (3.0) + 2*0.3 tolerance = 3.6 diameter -> r=1.8
    assert "r=1.8" in rendered


def test_substructure_with_only_subtractions_and_no_base_raises():
    empty = Substructure(name="empty")
    try:
        empty.to_scad_object()
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "empty" in str(exc)


def test_substructure_composes_positive_and_negative_features():
    sub = Substructure(
        name="bracket",
        base=Cube(size=Vector3D(x=10, y=10, z=10)),
        additions=[Feature.boss("pad", position=Vector3D(), diameter=4, height=2)],
        subtractions=[
            Feature.clearance_hole(
                "hole", position=Vector3D(), nominal_diameter=3, depth=10
            )
        ],
    )
    rendered = sub.to_scad_object().render()
    assert "Substructure: bracket" in rendered
    assert "difference()" in rendered
    assert "Feature: pad" in rendered
    assert "Feature: hole" in rendered


def test_structure_names_its_material_in_the_rendered_comment():
    structure = Structure(
        name="panel",
        material="PETG",
        substructures=[
            Substructure(name="s1", base=Cube(size=Vector3D(x=1, y=1, z=1)))
        ],
    )
    rendered = structure.to_scad_object().render()
    assert "Structure: panel (PETG)" in rendered


def test_site_compiles_to_a_scene_and_renders_openscad():
    site = Site(
        name="tiny_site",
        structures=[
            Structure(
                name="s",
                substructures=[
                    Substructure(name="ss", base=Cube(size=Vector3D(x=1, y=1, z=1)))
                ],
            )
        ],
    )
    scene = site.to_scene()
    assert scene.name == "tiny_site"
    rendered = site.render()
    assert "cube(" in rendered


def test_site_renders_jscad():
    site = Site(
        name="tiny_site",
        structures=[
            Structure(
                name="s",
                substructures=[
                    Substructure(name="ss", base=Cube(size=Vector3D(x=1, y=1, z=1)))
                ],
            )
        ],
    )
    rendered = site.render_jscad()
    assert "export const main" in rendered


def test_example_site_renders_all_three_systems():
    site = create_example_site()
    rendered = site.render()
    assert "Structure: control_panel (PETG)" in rendered
    assert "Substructure: mounting_system" in rendered
    assert "Substructure: ventilation_system" in rendered
    assert "Substructure: cable_routing_system" in rendered
    # 4 corner bosses + 4 corner holes + 6 vent slots + 1 grommet hole
    assert rendered.count("Feature: corner_boss_") == 4
    assert rendered.count("Feature: corner_hole_") == 4
    assert rendered.count("Feature: vent_slot_") == 6
    assert "Feature: cable_grommet_hole" in rendered
