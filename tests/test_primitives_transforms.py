from apothecary.booleans import Difference, Intersection, Union
from apothecary.models.vectors import Vector3D
from apothecary.primitives import Cube, Cylinder, Sphere
from apothecary.transforms import Rotate, Scale, Translate


def test_cube_vector_size_and_comment():
    c = Cube(size=Vector3D(x=1, y=2, z=3), center=True, comment="box")
    s = c.render()
    assert "// box" in s and "cube([1.0, 2.0, 3.0], center=true);" in s


def test_sphere_with_fn():
    s = Sphere(r=2.5, fn=24)
    out = s.render()
    assert out == "sphere(r=2.5, $fn=24);"


def test_cylinder_with_r1_r2_and_center():
    cy = Cylinder(h=10, r1=5, r2=2, center=True)
    out = cy.render()
    assert "cylinder(h=10.0, r1=5.0, r2=2.0, center=true);" in out


def test_translate_rotate_scale_nesting_and_indent():
    child = Sphere(r=1)
    t = Translate(v=Vector3D(x=1, y=2, z=3), children=[child])
    s = t.render()
    assert s.splitlines()[0].startswith("translate([") and "sphere(" in s

    r_vec = Rotate(a=Vector3D(x=90, y=0, z=0), children=[child])
    assert "rotate([90.0, 0.0, 0.0])" in r_vec.render()

    r_axis = Rotate(a=45.0, v=Vector3D(x=0, y=0, z=1), children=[child])
    assert "rotate(a=45.0, v=[0.0, 0.0, 1.0])" in r_axis.render()

    sc = Scale(v=Vector3D(x=2, y=2, z=0.5), children=[child])
    assert "scale([2.0, 2.0, 0.5])" in sc.render()


def test_boolean_blocks_render_children():
    u = Union(children=[Cube(), Sphere(r=1)])
    d = Difference(children=[Cube(), Sphere(r=1)])
    i = Intersection(children=[Cube(), Sphere(r=1)])
    assert "union() {" in u.render()
    assert "difference() {" in d.render()
    assert "intersection() {" in i.render()


def test_vector_to_list():
    v = Vector3D(x=1.0, y=2.0, z=3.0)
    assert v.to_list() == [1.0, 2.0, 3.0]
