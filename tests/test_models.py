"""Tests for geometry models."""

from apothecary.models import (
    BoundingBox3D,
    Color,
    HardwareSizes,
    PrintSettings,
    Vector2D,
    Vector3D,
)


class TestVector2D:
    """Tests for 2D vector operations."""

    def test_creation(self):
        v = Vector2D(x=3, y=4)
        assert v.x == 3
        assert v.y == 4

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


class TestVector3D:
    """Tests for 3D vector operations."""

    def test_creation(self):
        v = Vector3D(x=1, y=2, z=3)
        assert v.to_list() == [1, 2, 3]


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

    def test_intersection(self):
        box1 = BoundingBox3D.for_cube(10)
        box2 = BoundingBox3D(
            min_point=Vector3D(x=5, y=5, z=5), max_point=Vector3D(x=15, y=15, z=15)
        )
        assert box1.intersects(box2)


class TestColor:
    """Tests for color handling."""

    def test_from_hex(self):
        c = Color.from_hex("#ff0000")
        assert c.r == 1.0
        assert c.g == 0.0
        assert c.b == 0.0

    def test_to_hex(self):
        c = Color(r=1, g=0, b=0)
        assert c.to_hex() == "#ff0000"


class TestPrintSettings:
    """Tests for print settings."""

    def test_clearance_hole(self):
        ps = PrintSettings()
        clearance = ps.clearance_hole(3.0)
        assert clearance == 3.4  # 3.0 + 0.2 * 2


class TestHardwareSizes:
    """Tests for hardware constants."""

    def test_metric_screws(self):
        assert HardwareSizes.M3 == 3.0
        assert HardwareSizes.M3_CLEARANCE == 3.2
