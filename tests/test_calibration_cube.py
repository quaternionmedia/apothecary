"""Tests for calibration cube part."""
import pytest
from apothecary.projects.parts.calibration_cube import DEFAULT, Params, CalibrationCubePart


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
            assert bounds.volume == size ** 3
    
    def test_preview_color(self):
        """Part has preview color set."""
        assert DEFAULT.preview_color is not None
        assert DEFAULT.preview_color.to_hex() == "#808080"
    
    def test_calibration_targets(self):
        """Calibration targets are calculated."""
        targets = DEFAULT.get_calibration_targets()
        
        assert "external_dimensions" in targets
        assert targets["external_dimensions"]["x"] == 10  # Default size is 10mm
        assert "verification_steps" in targets
        assert len(targets["verification_steps"]) > 0
    
    def test_calibration_targets_custom_size(self):
        """Calibration targets reflect custom parameters."""
        targets = DEFAULT.get_calibration_targets({"size": 40, "wall_thickness": 4})
        
        assert targets["external_dimensions"]["x"] == 40
        assert targets["internal_dimensions"]["x"] == 32  # 40 - 2*4
    
    def test_geometry_dict(self):
        """Geometry dict has expected structure."""
        geo = DEFAULT.to_geometry_dict()
        
        assert "bounds" in geo
        assert "color" in geo
        assert "color_hex" in geo
        assert geo["bounds"]["size"] is not None


class TestRecommendedPrintSettings:
    """Test print settings recommendations."""
    
    def test_has_print_settings(self):
        """Part provides print settings."""
        settings = DEFAULT.get_recommended_print_settings()
        
        assert settings.nozzle_diameter == 0.4
        assert settings.layer_height == 0.2
        assert settings.tolerance == 0.1  # Tight for calibration
