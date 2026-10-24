"""Tests for calibration cube part."""

import pytest

from apothecary.projects.parts.calibration_cube import DEFAULT, Params


class TestCalibrationCubeParams:
    """Test parameter model."""

    def test_default_params(self):
        """Default parameters are valid."""
        params = Params()
        assert params.size == 10.0  # Default is 10mm
        assert params.show_axes is True
        assert params.show_dimensions is True
        assert params.wall_thickness == 2.0

    def test_param_validation(self):
        """Parameters validate correctly."""
        # Size must be > 5
        with pytest.raises(ValueError):
            Params(size=3)

        # Size must be <= 100
        with pytest.raises(ValueError):
            Params(size=150)

        # Wall thickness must be > 0
        with pytest.raises(ValueError):
            Params(wall_thickness=0)


class TestCalibrationCubePart:
    """Test part wrapper."""

    def test_part_exists(self):
        """Part source file exists."""
        assert DEFAULT.source_file.exists()

    def test_part_metadata(self):
        """Part has correct metadata."""
        assert DEFAULT.name == "calibration_cube"
        assert DEFAULT.category == "calibration"
        assert "test" in DEFAULT.tags
        assert "demo" in DEFAULT.tags

    def test_bounds_default(self):
        """Default bounds match 10mm cube (axes are preview-only)."""
        bounds = DEFAULT.get_bounds()
        # Default cube is 10mm
        assert bounds.size.x == 10
        assert bounds.size.y == 10
        assert bounds.size.z == 10

    def test_bounds_without_axes(self):
        """Bounds without axes match cube size."""
        bounds = DEFAULT.get_bounds({"size": 30, "show_axes": False})
        assert bounds.size.x == 30
        assert bounds.size.y == 30
        assert bounds.size.z == 30

    def test_bounds_scale_with_size(self):
        """Bounds scale with size parameter."""
        for size in [10, 25, 50]:
            bounds = DEFAULT.get_bounds({"size": size, "show_axes": False})
            assert bounds.size.x == size
            assert bounds.volume == size**3

    def test_preview_color(self):
        """Part has preview color set."""
        assert DEFAULT.preview_color is not None
        assert DEFAULT.preview_color.to_hex() == "#808080"

    def test_geometry_dict(self):
        """Geometry dict has expected structure."""
        geo = DEFAULT.to_geometry_dict()

        assert "bounds" in geo
        assert "color" in geo
        assert "color_hex" in geo
        assert geo["bounds"]["size"] is not None


def test_bounds_of_a_partial_override_keep_the_default_size():
    """An override without `size` reported a 20 mm cube; the SCAD's default is 10."""
    from apothecary.projects.parts.calibration_cube import DEFAULT as cube

    assert cube.get_bounds({"show_dimensions": False}).size.x == 10
    assert cube.get_bounds({"size": 25}).size.x == 25
