"""Tests for the Site/Structure/Substructure/Feature prototype (not ratified API).

See tests/test_garage_workbench.py for the worked-example / layout-verification tests.
"""

from apothecary.hierarchy import Assembly, Feature, Site, Structure, Substructure
from apothecary.models.bounds import BoundingBox3D
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
    rendered = feature.to_scad_object().render()
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


def test_structure_world_bounds_is_none_without_a_footprint():
    structure = Structure(name="s", substructures=[Substructure(name="ss", base=Cube())])
    assert structure.world_bounds() is None


def test_structure_world_bounds_offsets_footprint_by_position():
    structure = Structure(
        name="s",
        position=Vector3D(x=100, y=200, z=300),
        footprint=BoundingBox3D(min_point=Vector3D(), max_point=Vector3D(x=10, y=20, z=30)),
        substructures=[Substructure(name="ss", base=Cube())],
    )
    bounds = structure.world_bounds()
    assert bounds.min_point == Vector3D(x=100, y=200, z=300)
    assert bounds.max_point == Vector3D(x=110, y=220, z=330)


def test_structure_category_defaults_to_none_and_is_settable():
    plain = Structure(name="s", substructures=[Substructure(name="ss", base=Cube())])
    assert plain.category is None

    tagged = Structure(
        name="s", category="mechanical", substructures=[Substructure(name="ss", base=Cube())]
    )
    assert tagged.category == "mechanical"


def test_structure_with_no_substructures_raises():
    empty = Structure(name="empty")
    try:
        empty.to_scad_object()
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "empty" in str(exc)


def test_substructure_world_bounds_is_none_without_a_footprint():
    sub = Substructure(name="ss", base=Cube())
    assert sub.world_bounds() is None


def test_substructure_world_bounds_offsets_footprint_by_position():
    sub = Substructure(
        name="ss",
        position=Vector3D(x=5, y=10, z=15),
        footprint=BoundingBox3D(min_point=Vector3D(), max_point=Vector3D(x=1, y=2, z=3)),
        base=Cube(),
    )
    bounds = sub.world_bounds()
    assert bounds.min_point == Vector3D(x=5, y=10, z=15)
    assert bounds.max_point == Vector3D(x=6, y=12, z=18)


def test_substructure_with_nonzero_position_wraps_in_translate():
    sub = Substructure(name="ss", position=Vector3D(x=1, y=2, z=3), base=Cube())
    rendered = sub.to_scad_object().render()
    assert "translate([1.0, 2.0, 3.0])" in rendered


def test_feature_can_have_a_child_feature_one_level_deeper_than_the_fixed_four():
    """Assembly is one generic recursive class, not four fixed levels -- a
    Feature (a leaf under the old model, with no children slot at all) can
    itself carry a child Feature, proving depth is genuinely unbounded.
    """
    chamfer = Feature.boss("chamfer", position=Vector3D(), diameter=6, height=1)
    boss = Feature.boss("boss", position=Vector3D(), diameter=4, height=2)
    boss.children = [chamfer]

    assert isinstance(boss, Assembly)
    assert boss.children[0] is chamfer

    rendered = boss.to_scad_object().render()
    assert "Feature: boss" in rendered
    assert "Feature: chamfer" in rendered


def test_validate_recurses_below_the_root_not_just_at_site_level():
    """The overlap check generalizes to every level: two Substructures that
    are siblings under the same Structure, not just two Structures under a
    Site, are checked against each other.
    """
    overlapping_box = BoundingBox3D(max_point=Vector3D(x=10, y=10, z=10))
    sub_a = Substructure(name="sub_a", footprint=overlapping_box, base=Cube())
    sub_b = Substructure(name="sub_b", footprint=overlapping_box, base=Cube())
    structure = Structure(name="panel", substructures=[sub_a, sub_b])

    report = structure.validate()
    assert not report.is_valid
    assert report.violations[0].kind == "overlap"
    assert set(report.violations[0].structures) == {"sub_a", "sub_b"}
