"""Tests for geometry models."""
import math
import pytest

from apothecary.models import (
    Vector2D, Vector3D, ORIGIN, X_AXIS, Y_AXIS, Z_AXIS,
    BoundingBox2D, BoundingBox3D,
    Color, BLACK, WHITE, RED,
    Polygon2D, Circle2D, Arc2D,
    Length, LengthUnit, convert_length, HardwareSizes, PrintSettings,
)


class TestVector2D:
    """Tests for 2D vector operations."""
    
    def test_creation(self):
        v = Vector2D(x=3, y=4)
        assert v.x == 3
        assert v.y == 4
    
    def test_magnitude(self):
        v = Vector2D(x=3, y=4)
        assert v.magnitude == 5.0
    
    def test_addition(self):
        a = Vector2D(x=1, y=2)
        b = Vector2D(x=3, y=4)
        c = a + b
        assert c.x == 4
        assert c.y == 6
    
    def test_subtraction(self):
        a = Vector2D(x=5, y=7)
        b = Vector2D(x=2, y=3)
        c = a - b
        assert c.x == 3
        assert c.y == 4
    
    def test_scalar_multiply(self):
        v = Vector2D(x=2, y=3)
        w = v * 2
        assert w.x == 4
        assert w.y == 6
    
    def test_normalized(self):
        v = Vector2D(x=3, y=4)
        n = v.normalized()
        assert abs(n.magnitude - 1.0) < 1e-10
    
    def test_dot_product(self):
        a = Vector2D(x=1, y=0)
        b = Vector2D(x=0, y=1)
        assert a.dot(b) == 0  # Perpendicular
        assert a.dot(a) == 1  # Same direction
    
    def test_from_polar(self):
        v = Vector2D.from_polar(1, 90)
        assert abs(v.x) < 1e-10
        assert abs(v.y - 1) < 1e-10


class TestVector3D:
    """Tests for 3D vector operations."""
    
    def test_creation(self):
        v = Vector3D(x=1, y=2, z=3)
        assert v.to_list() == [1, 2, 3]
    
    def test_cross_product(self):
        # X cross Y = Z
        z = X_AXIS.cross(Y_AXIS)
        assert abs(z.x - Z_AXIS.x) < 1e-10
        assert abs(z.y - Z_AXIS.y) < 1e-10
        assert abs(z.z - Z_AXIS.z) < 1e-10
    
    def test_projections(self):
        v = Vector3D(x=1, y=2, z=3)
        assert v.xy.to_list() == [1, 2]
        assert v.xz.to_list() == [1, 3]
        assert v.yz.to_list() == [2, 3]


class TestBoundingBox3D:
    """Tests for 3D bounding boxes."""
    
    def test_from_cube(self):
        box = BoundingBox3D.for_cube(10)
        assert box.volume == 1000
        assert box.width == 10
        assert box.height == 10
        assert box.depth == 10
    
    def test_centered_cube(self):
        box = BoundingBox3D.for_cube(10, center=True)
        assert box.center.x == 0
        assert box.center.y == 0
        assert box.center.z == 0
    
    def test_contains_point(self):
        box = BoundingBox3D.for_cube(10)
        assert box.contains_point(Vector3D(x=5, y=5, z=5))
        assert not box.contains_point(Vector3D(x=15, y=5, z=5))
    
    def test_intersection(self):
        box1 = BoundingBox3D.for_cube(10)
        box2 = BoundingBox3D(
            min_point=Vector3D(x=5, y=5, z=5),
            max_point=Vector3D(x=15, y=15, z=15)
        )
        assert box1.intersects(box2)
    
    def test_union(self):
        box1 = BoundingBox3D.for_cube(10)
        box2 = BoundingBox3D(
            min_point=Vector3D(x=10, y=0, z=0),
            max_point=Vector3D(x=20, y=10, z=10)
        )
        union = box1.union(box2)
        assert union.width == 20
        assert union.height == 10


class TestColor:
    """Tests for color handling."""
    
    def test_from_hex(self):
        c = Color.from_hex("#ff0000")
        assert c.r == 1.0
        assert c.g == 0.0
        assert c.b == 0.0
    
    def test_from_name(self):
        c = Color.from_name("red")
        assert c.r == 1.0
        assert c.g == 0.0
        assert c.b == 0.0
    
    def test_to_hex(self):
        c = Color(r=1, g=0, b=0)
        assert c.to_hex() == "#ff0000"
    
    def test_blend(self):
        blended = BLACK.blend(WHITE, 0.5)
        assert abs(blended.r - 0.5) < 1e-10
        assert abs(blended.g - 0.5) < 1e-10
        assert abs(blended.b - 0.5) < 1e-10
    
    def test_with_alpha(self):
        c = RED.with_alpha(0.5)
        assert c.a == 0.5
        assert c.r == 1.0


class TestPolygon2D:
    """Tests for 2D polygons."""
    
    def test_regular_hexagon(self):
        hex = Polygon2D.regular(6, radius=10)
        assert hex.vertex_count == 6
    
    def test_rectangle(self):
        rect = Polygon2D.rectangle(10, 5)
        assert abs(rect.area - 50) < 1e-10
    
    def test_star(self):
        star = Polygon2D.star(5, outer_radius=10, inner_radius=5)
        assert star.vertex_count == 10
    
    def test_to_openscad(self):
        rect = Polygon2D.rectangle(10, 10)
        scad = rect.to_openscad()
        assert "polygon" in scad


class TestCircle2D:
    """Tests for 2D circles."""
    
    def test_properties(self):
        c = Circle2D(radius=5)
        assert c.diameter == 10
        assert abs(c.area - math.pi * 25) < 1e-10
    
    def test_to_polygon(self):
        c = Circle2D(radius=10)
        p = c.to_polygon(segments=8)
        assert p.vertex_count == 8


class TestUnits:
    """Tests for unit conversions."""
    
    def test_inch_to_mm(self):
        mm = convert_length(1, LengthUnit.INCH, LengthUnit.MILLIMETER)
        assert mm == 25.4
    
    def test_length_class(self):
        l = Length.inch(1)
        assert l.to_mm() == 25.4
    
    def test_length_arithmetic(self):
        a = Length.mm(10)
        b = Length.mm(5)
        c = a + b
        assert c.value == 15
    
    def test_print_settings(self):
        ps = PrintSettings()
        clearance = ps.clearance_hole(3.0)
        assert clearance == 3.4  # 3.0 + 0.2 * 2


class TestHardwareSizes:
    """Tests for hardware constants."""
    
    def test_metric_screws(self):
        assert HardwareSizes.M3 == 3.0
        assert HardwareSizes.M3_CLEARANCE == 3.2
