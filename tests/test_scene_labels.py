"""A scene document is JSON in and the same geometry out: each object says what it
is with ``type``, and a dump carries that tag so it loads back as itself."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from apothecary.example_hierarchy import create_example_site
from apothecary.hierarchy import Assembly
from apothecary.primitives import Cube, Cylinder, Sphere
from apothecary.scene import Scene, load_scene_from_json


@pytest.mark.parametrize(
    "saved, expected",
    [
        ({"type": "cylinder", "h": 10, "r": 5}, Cylinder),
        ({"type": "cylinder", "h": 10, "r1": 3, "r2": 5}, Cylinder),
        ({"type": "sphere", "r": 5, "fn": 64}, Sphere),
        ({"type": "cube", "size": {"x": 1, "y": 2, "z": 3}}, Cube),
    ],
)
def test_a_labelled_shape_comes_back_as_that_shape(saved, expected):
    (built,) = Scene.model_validate({"objects": [saved]}).objects
    assert isinstance(built, expected)


def test_a_dump_loads_back_as_the_same_scene():
    doc = {
        "objects": [
            {"type": "hull", "children": [{"type": "sphere", "r": 1}, {"type": "cube", "size": 2}]},
            {"type": "rotate", "a": {"x": 0, "y": 0, "z": 45}, "children": [{"type": "cube"}]},
            {"type": "import", "file": "parts/x/x.stl", "scale": 25.4},
        ]
    }
    scene = Scene.model_validate(doc)
    again = Scene.model_validate_json(scene.model_dump_json())
    assert again.render() == scene.render()
    assert "hull()" in scene.render() and 'import("parts/x/x.stl"' in scene.render()


def test_a_site_survives_a_round_trip_through_json():
    """Assembly.base holds geometry too; a saved site loads back and renders the same."""
    site = create_example_site()
    back = Assembly.model_validate_json(site.model_dump_json())
    assert back.to_scad_object().render() == site.to_scad_object().render()


@pytest.mark.parametrize("bad", [{"r": 5}, {"h": 10, "r": 5}, {"type": "blob"}])
def test_an_object_that_does_not_say_what_it_is_is_refused(bad):
    with pytest.raises(ValidationError):
        Scene.model_validate({"objects": [bad]})


def test_the_cli_loader_reads_the_documented_example(tmp_path):
    path = tmp_path / "scene.json"
    path.write_text(
        '{"name": "json_demo", "objects": [{"type": "cube", '
        '"size": {"x": 15, "y": 15, "z": 10}, "center": true}]}'
    )
    assert (
        "cube([15.0, 15.0, 10.0], center=true);" in load_scene_from_json(scene_file=path).render()
    )
