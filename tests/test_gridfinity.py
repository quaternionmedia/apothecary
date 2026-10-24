"""Tests for Gridfinity part wrapper and submodule integration."""

from pathlib import Path
from unittest.mock import patch

import pytest

from apothecary.models import BoundingBox3D
from apothecary.projects.parts.gridfinity import (
    DEFAULT,
    GRID_SIZE_MM,
    HEIGHT_UNIT_MM,
    STACKING_LIP_MM,
    BinParams,
    GridfinityBinPart,
    GridzDefine,
    TabStyle,
    get_bin_dimensions,
)
from apothecary.projects.parts.stl_renderer import (
    RenderResult,
    build_stl,
    read_params_sidecar,
)


class TestGridfinityConstants:
    """Test Gridfinity dimension constants."""

    def test_grid_size(self):
        """Standard gridfinity grid is 42mm."""
        assert GRID_SIZE_MM == 42.0

    def test_height_unit(self):
        """Height unit is 7mm."""
        assert HEIGHT_UNIT_MM == 7.0

    def test_stacking_lip(self):
        """Stacking lip is ~3.55mm."""
        assert STACKING_LIP_MM == pytest.approx(3.55, abs=0.1)


class TestBinParams:
    """Tests for BinParams model."""

    def test_default_params(self):
        """The defaults are gridfinity-rebuilt-bins.scad's own."""
        params = BinParams()
        assert params.gridx == 3
        assert params.gridy == 2
        assert params.gridz == 6
        assert params.include_lip is True
        assert params.divx == 1
        assert params.divy == 1

    def test_custom_params(self):
        """Test custom parameter values."""
        params = BinParams(
            gridx=3,
            gridy=2,
            gridz=6,
            divx=3,
            divy=2,
            scoop=0.5,
        )
        assert params.gridx == 3
        assert params.gridy == 2
        assert params.gridz == 6
        assert params.divx == 3
        assert params.scoop == 0.5

    def test_gridz_validation(self):
        """Test gridz must be at least 1."""
        with pytest.raises(ValueError):
            BinParams(gridz=0)

    def test_enum_defaults(self):
        """Test enum field defaults."""
        params = BinParams()
        assert params.gridz_define == GridzDefine.UNITS_EXCLUDE_LIP
        assert params.style_tab == TabStyle.AUTO

    def test_hole_options_default(self):
        """Test hole options have sensible defaults."""
        params = BinParams()
        assert params.hole_options.refined_holes is True
        assert params.hole_options.magnet_holes is False
        assert params.hole_options.crush_ribs is True


class TestGridfinityBinPart:
    """Tests for GridfinityBinPart wrapper."""

    def test_default_instance_exists(self):
        """Test DEFAULT instance is created."""
        assert DEFAULT is not None
        assert DEFAULT.name == "gridfinity"
        assert DEFAULT.category == "storage"

    def test_description(self):
        """Test part has description."""
        assert "gridfinity" in DEFAULT.description.lower()
        assert "modular" in DEFAULT.description.lower()

    def test_tags(self):
        """Test part has appropriate tags."""
        assert "gridfinity" in DEFAULT.tags
        assert "storage" in DEFAULT.tags
        assert "parametric" in DEFAULT.tags

    def test_params_model(self):
        """Test params_model is BinParams."""
        assert DEFAULT.params_model == BinParams

    def test_get_bounds_default(self):
        """Test bounds calculation with default params."""
        bounds = DEFAULT.get_bounds()

        assert isinstance(bounds, BoundingBox3D)
        # 3x2x6 bin: 126mm x 84mm x (6*7 + 3.55)mm
        assert bounds.size.x == pytest.approx(3 * GRID_SIZE_MM, abs=0.1)
        assert bounds.size.y == pytest.approx(2 * GRID_SIZE_MM, abs=0.1)
        expected_height = 6 * HEIGHT_UNIT_MM + STACKING_LIP_MM
        assert bounds.size.z == pytest.approx(expected_height, abs=0.1)

    def test_get_bounds_of_one_override_keeps_the_other_defaults(self):
        bounds = DEFAULT.get_bounds({"gridx": 1})
        assert bounds.size.x == pytest.approx(GRID_SIZE_MM, abs=0.1)
        assert bounds.size.y == pytest.approx(2 * GRID_SIZE_MM, abs=0.1)

    def test_get_bounds_custom(self):
        """Test bounds calculation with custom params."""
        bounds = DEFAULT.get_bounds({"gridx": 2, "gridy": 3, "gridz": 6})

        assert bounds.size.x == pytest.approx(2 * GRID_SIZE_MM, abs=0.1)
        assert bounds.size.y == pytest.approx(3 * GRID_SIZE_MM, abs=0.1)
        expected_height = 6 * HEIGHT_UNIT_MM + STACKING_LIP_MM
        assert bounds.size.z == pytest.approx(expected_height, abs=0.1)

    def test_get_bounds_no_lip(self):
        """Test bounds without stacking lip."""
        bounds = DEFAULT.get_bounds({"gridx": 1, "gridy": 1, "gridz": 3, "include_lip": False})

        expected_height = 3 * HEIGHT_UNIT_MM  # No lip
        assert bounds.size.z == pytest.approx(expected_height, abs=0.1)

    def test_scad_overrides_translate_only_what_was_given(self):
        """Customizer names are flat: hole_options is the SCAD's six booleans,
        an enum is its plain int, and a default build passes nothing."""
        given = DEFAULT.validate_overrides(
            {"gridx": 2, "style_tab": TabStyle.LEFT, "hole_options": {"magnet_holes": True}}
        )
        scad = DEFAULT.scad_overrides(given)
        assert scad == {
            "gridx": 2,
            "style_tab": 2,
            "refined_holes": True,
            "magnet_holes": True,
            "screw_holes": False,
            "crush_ribs": True,
            "chamfer_holes": True,
            "printable_hole_top": True,
        }
        assert type(scad["style_tab"]) is int
        assert DEFAULT.scad_overrides({}) == {}

    # That each name it emits is a variable of the SCAD, and each default the
    # SCAD's own, is tests/test_parameter_coverage.py's, for every part.

    def test_build_stl_hands_openscad_the_customizer_names(self, tmp_path, monkeypatch):
        stl = tmp_path / "gridfinity.stl"
        monkeypatch.setattr(GridfinityBinPart, "get_stl_output_path", lambda self: stl)
        monkeypatch.setattr(
            GridfinityBinPart, "can_generate_stl", lambda self, openscad=None: (True, "")
        )
        handed = []

        class Renderer:
            openscad_path = None

            def render_stl(self, scad_path, stl_path=None, timeout=120.0, params=None):
                handed.append(params)
                stl_path.write_text("solid fake\nendsolid fake\n")
                return RenderResult(success=True, stl_path=stl_path)

        given = {"gridx": 2, "hole_options": {"magnet_holes": True}}
        assert build_stl(DEFAULT, given, renderer=Renderer()).success
        assert "hole_options" not in handed[0]
        assert handed[0]["gridx"] == 2 and handed[0]["magnet_holes"] is True
        recorded = read_params_sidecar(stl)["params"]
        assert recorded["gridx"] == 2 and recorded["hole_options"]["magnet_holes"] is True
        assert build_stl(DEFAULT, given, renderer=Renderer()).skipped == "fresh"

    def test_get_stl_output_path(self):
        """Test STL output path is not in submodule."""
        stl_path = DEFAULT.get_stl_output_path()
        # Should be parts/gridfinity/gridfinity.stl, NOT inside submodule
        assert "gridfinity-rebuilt-openscad" not in str(stl_path)
        assert stl_path.name == "gridfinity.stl"


class TestGetBinDimensions:
    """Tests for convenience dimension calculator."""

    def test_default_dimensions(self):
        """Test default 1x1x3 dimensions."""
        dims = get_bin_dimensions()

        assert dims["width_mm"] == GRID_SIZE_MM
        assert dims["depth_mm"] == GRID_SIZE_MM
        expected_height = 3 * HEIGHT_UNIT_MM + STACKING_LIP_MM
        assert dims["height_mm"] == pytest.approx(expected_height, abs=0.1)

    def test_custom_dimensions(self):
        """Test custom grid dimensions."""
        dims = get_bin_dimensions(gridx=2, gridy=3, gridz=6)

        assert dims["width_mm"] == 2 * GRID_SIZE_MM
        assert dims["depth_mm"] == 3 * GRID_SIZE_MM
        expected_height = 6 * HEIGHT_UNIT_MM + STACKING_LIP_MM
        assert dims["height_mm"] == pytest.approx(expected_height, abs=0.1)

    def test_includes_constants(self):
        """Test response includes unit constants."""
        dims = get_bin_dimensions()
        assert dims["grid_unit_mm"] == GRID_SIZE_MM
        assert dims["height_unit_mm"] == HEIGHT_UNIT_MM


class TestCanGenerateSTL:
    """Tests for STL generation capability checking."""

    def test_submodule_not_initialized_message(self):
        """Test message when submodule not initialized."""
        with patch.object(
            GridfinityBinPart,
            "submodule_initialized",
            new_callable=lambda: property(lambda self: False),
        ):
            part = GridfinityBinPart(
                name="test",
                source_file=Path("/tmp/test.scad"),
            )
            can_gen, reason = part.can_generate_stl()
            assert can_gen is False
            assert "git submodule update --init" in reason
