from apothecary.models.vectors import Vector3D
from apothecary.primitives import Cube, Sphere, Cylinder
from apothecary.transforms import Translate, Rotate, Scale
from apothecary.booleans import Union, Difference, Intersection


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


def test_a_comment_cannot_become_code():
    """A newline in a comment used to end the comment and start geometry."""
    out = Cube(comment="a\nsphere(100);").render()
    assert out.splitlines()[:2] == ["// a", "// sphere(100);"]


def test_a_quote_in_a_mesh_path_stays_in_the_string():
    from apothecary.primitives import Import

    assert Import(file='we"ird.stl').render() == 'import("we\\"ird.stl", convexity=10);'


def test_one_radius_given_sets_both_ends_as_the_viewer_draws_it():
    """Cylinder(r1=3) rendered `r=1` while the viewer drew a 3 mm cylinder."""
    from apothecary.primitives import Cylinder

    assert "r=3.0" in Cylinder(h=5, r1=3).render()
    assert "r1=3.0, r2=1.0" in Cylinder(h=5, r1=3, r2=1).render()
    assert Cylinder(h=5, r2=2).radii() == (2, 2)
