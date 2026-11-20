"""Tests for the Site/Structure/Substructure/Feature prototype (not ratified API).

See tests/test_garage_workbench.py for the worked-example / layout-verification tests.
"""

import pytest

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
    with pytest.raises(ValueError, match="empty"):
        empty.to_scad_object()


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
    with pytest.raises(ValueError, match="empty"):
        empty.to_scad_object()


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
    """Assembly is one generic recursive class, not four fixed levels: a Feature
    can itself carry a child Feature, so depth is unbounded.
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


def test_a_problem_names_its_pieces_by_tree_path_where_names_repeat():
    """Two printers each hold a left and a right post; only the second's overlap. The
    problem names the posts and, beside the names, the paths that say which printer's:
    a name alone is the same in both."""

    def printer(name: str, apart: float, at: float) -> Structure:
        post = BoundingBox3D(max_point=Vector3D(x=10, y=10, z=10))
        left = Substructure(name="left_post", footprint=post, base=Cube())
        right = Substructure(
            name="right_post", position=Vector3D(x=apart), footprint=post, base=Cube()
        )
        return Structure(
            name=name,
            position=Vector3D(x=at),
            footprint=BoundingBox3D(max_point=Vector3D(x=60, y=10, z=10)),
            substructures=[left, right],
        )

    site = Site(
        name="bench", structures=[printer("printer_a", 50, 0), printer("printer_b", 5, 100)]
    )
    report = site.validate()
    assert [(v.structures, v.paths) for v in report.violations] == [
        (["left_post", "right_post"], ["printer_b.left_post", "printer_b.right_post"])
    ]
    # Among a site's own pieces, the path is the name.
    clash = Site(name="bench", structures=[printer("printer_a", 50, 0), printer("printer_c", 50, 30)])
    assert [v.paths for v in clash.validate().violations] == [["printer_a", "printer_c"]]


def _block(**kwargs):
    return Assembly(
        name="block",
        footprint=BoundingBox3D(min_point=Vector3D(), max_point=Vector3D(x=10, y=20, z=30)),
        base=Cube(size=Vector3D(x=10, y=20, z=30), center=False),
        **kwargs,
    )


def test_a_node_with_no_turn_renders_and_bounds_as_it_always_did():
    node = _block(position=Vector3D(x=5, y=6, z=7))
    assert node.turn is None
    assert "rotate" not in node.to_scad_object().render()
    box = node.world_bounds()
    assert (box.min_point, box.max_point) == (
        Vector3D(x=5, y=6, z=7),
        Vector3D(x=15, y=26, z=37),
    )


def test_a_turn_is_made_about_the_nodes_origin_before_it_is_placed():
    node = _block(position=Vector3D(x=100), turn=Vector3D(z=90))
    rendered = node.to_scad_object().render()
    assert rendered.index("translate") < rendered.index("rotate")


def test_a_turned_nodes_world_bounds_contain_the_turned_footprint():
    box = _block(position=Vector3D(x=100), turn=Vector3D(z=90)).world_bounds()
    # x -> y, y -> -x: the 10 x 20 floor becomes 20 x 10, reaching to -20 along x
    assert (box.min_point.x, box.max_point.x) == pytest.approx((80.0, 100.0))
    assert (box.min_point.y, box.max_point.y) == pytest.approx((0.0, 10.0))
    assert (box.min_point.z, box.max_point.z) == pytest.approx((0.0, 30.0))


def test_the_tree_reports_the_turn_and_the_turned_bounds_and_none_for_a_node_not_turned():
    from apothecary.api import _assembly_tree

    plain = _assembly_tree(Assembly(name="s", role="site", children=[_block()]))
    assert plain["children"][0]["turn"] is None
    assert plain["children"][0]["world_bounds"]["max"] == [10, 20, 30]
    turned_tree = _assembly_tree(
        Assembly(name="s", role="site", children=[_block(turn=Vector3D(z=90))])
    )
    node = turned_tree["children"][0]
    assert node["turn"] == [0, 0, 90]
    assert node["world_bounds"]["max"][0] == pytest.approx(0.0)
    assert node["world_bounds"]["min"][0] == pytest.approx(-20.0)
