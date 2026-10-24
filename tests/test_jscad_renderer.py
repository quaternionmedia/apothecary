from pathlib import Path
import shutil
import subprocess

import pytest

from apothecary.example import create_example_scene
from apothecary.models.vectors import Vector3D


def test_scene_render_jscad_produces_module():
    scene = create_example_scene()
    js_code = scene.render_jscad()
    assert "export const main" in js_code
    assert "cuboid(" in js_code or "cylinder(" in js_code or "sphere(" in js_code


@pytest.mark.skipif(shutil.which("node") is None, reason="node runtime required")
def test_scene_render_jscad_passes_node_check(tmp_path: Path):
    scene = create_example_scene()
    js_code = scene.render_jscad()
    target = tmp_path / "scene.jscad.mjs"
    target.write_text(js_code, encoding="utf-8")
    proc = subprocess.run(
        ["node", "--check", str(target)], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout



def _js(*objects):
    from apothecary.scene import Scene

    return Scene(objects=list(objects)).render_jscad()


def test_openscad_degrees_become_jscad_radians_and_a_scalar_turn_is_about_z():
    from apothecary.primitives import Cube
    from apothecary.transforms import Rotate

    js = _js(Rotate(a=90, children=[Cube()]))
    assert "rotate([0, 0, 1.5707963267948966]" in js
    js = _js(Rotate(a=Vector3D(x=180, y=0, z=0), children=[Cube()]))
    assert "rotate([3.141592653589793, 0.0, 0.0]" in js


def test_an_uncentred_primitive_keeps_its_corner_and_base_at_the_origin():
    """JSCAD centres every primitive; OpenSCAD's default is a corner, a base."""
    from apothecary.primitives import Cube, Cylinder

    js = _js(Cube(size=Vector3D(x=2, y=4, z=6)), Cylinder(h=10, r=1))
    assert "cuboid({ size: [2.0, 4.0, 6.0], center: [1.0, 2.0, 3.0] })" in js
    assert "cylinder({ height: 10.0, radius: 1.0, center: [0, 0, 5.0] })" in js


def test_a_cone_is_a_cylinder_elliptic_and_a_hull_renders():
    """The datum_core site holds a hull; rendering it raised TypeError."""
    from apothecary.datum_core_site import create_datum_core_site
    from apothecary.primitives import Cylinder

    assert "cylinderElliptic({ height: 5.0, startRadius: [3.0, 3.0], endRadius: [1.0, 1.0]" in _js(
        Cylinder(h=5, r1=3, r2=1)
    )
    assert "hull(" in create_datum_core_site().render_jscad()
