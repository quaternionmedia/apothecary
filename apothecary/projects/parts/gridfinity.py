"""
Gridfinity - Modular storage bin system integration.

This module integrates the gridfinity-rebuilt-openscad library as an
Apothecary part, providing parametric access to the modular storage system.

The gridfinity-rebuilt-openscad library is included as a git submodule at:
    parts/gridfinity/gridfinity-rebuilt-openscad/

To initialize the submodule:
    apothecary submodules

Reference:
    - https://gridfinity.com - Original Gridfinity system
    - https://github.com/kennetek/gridfinity-rebuilt-openscad - OpenSCAD library
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from apothecary.models import (
    BoundingBox3D,
    Color,
    PrintSettings,
    Vector3D,
)

from .base import BasePart
from .skeleton import ROOT

# Gridfinity constants (from the library)
GRID_SIZE_MM = 42.0  # Standard gridfinity grid unit in mm
HEIGHT_UNIT_MM = 7.0  # Height unit in mm
STACKING_LIP_MM = 3.55  # Stacking lip height (with fillet)


class GridzDefine(int, Enum):
    """How gridz is used to calculate bin height."""

    UNITS_EXCLUDE_LIP = 0  # 7mm increments, excludes stacking lip
    INTERNAL_MM = 1  # Internal mm, excludes base & stacking lip
    EXTERNAL_EXCLUDE_LIP = 2  # External mm, excludes stacking lip
    EXTERNAL_MM = 3  # External mm, full height


class TabStyle(int, Enum):
    """Tab style for bin compartments."""

    FULL = 0
    AUTO = 1
    LEFT = 2
    CENTER = 3
    RIGHT = 4
    NONE = 5


class HoleOptions(BaseModel):
    """Hole configuration for Gridfinity bin bases."""

    refined_holes: bool = Field(True, description="Use gridfinity refined hole style")
    magnet_holes: bool = Field(False, description="Holes for 6mm x 2mm magnets")
    screw_holes: bool = Field(False, description="Holes for M3 screws")
    crush_ribs: bool = Field(True, description="Crush ribs to hold magnets")
    chamfer_holes: bool = Field(True, description="Chamfer for easy insertion")
    printable_hole_top: bool = Field(True, description="Printable without supports")


class BinParams(BaseModel):
    """
    Parameters for Gridfinity storage bins.

    The Gridfinity system uses a 42mm x 42mm grid. Bins are measured in
    grid units (gridx, gridy) and height units (gridz, where 1 unit = 7mm).

    Standard Zack Freedman bin heights:
        - Z unit 2 → 18.4mm total (7×2 + 4.4mm lip)
        - Z unit 3 → 25.4mm total (7×3 + 4.4mm lip)
        - Z unit 6 → 46.4mm total (7×6 + 4.4mm lip)
    """

    # Grid dimensions
    gridx: int = Field(1, ge=1, le=10, description="Number of bases along X-axis")
    gridy: int = Field(1, ge=1, le=10, description="Number of bases along Y-axis")
    gridz: float = Field(3, ge=1, le=20, description="Bin height in units (1 unit = 7mm)")

    # Height options
    gridz_define: GridzDefine = Field(
        GridzDefine.UNITS_EXCLUDE_LIP,
        description="How gridz calculates height",
    )
    include_lip: bool = Field(True, description="Include stacking lip on top")
    half_grid: bool = Field(False, description="Half-grid sized bins (21mm units)")

    # Compartments
    divx: int = Field(1, ge=0, le=10, description="X divisions (0 = solid)")
    divy: int = Field(1, ge=0, le=10, description="Y divisions (0 = solid)")

    # Features
    style_tab: TabStyle = Field(TabStyle.AUTO, description="Tab style for compartments")
    scoop: float = Field(1.0, ge=0, le=1, description="Scoop weight (0=none, 1=full)")

    # Hole options
    only_corners: bool = Field(False, description="Holes only at corners")
    hole_options: HoleOptions = Field(default_factory=HoleOptions)

    @field_validator("gridz")
    @classmethod
    def validate_gridz(cls, v: float) -> float:
        """Ensure gridz is a reasonable value."""
        if v < 1:
            raise ValueError("gridz must be at least 1")
        return v


class BaseplateParams(BaseModel):
    """Parameters for Gridfinity baseplates."""

    gridx: int = Field(4, ge=1, le=20, description="Grid units in X")
    gridy: int = Field(4, ge=1, le=20, description="Grid units in Y")

    # Style options
    style_plate: int = Field(0, ge=0, le=2, description="0=refined, 1=magnet, 2=weighted")
    enable_magnet: bool = Field(True, description="Include magnet holes")

    # Dimensions
    distancex: float = Field(0, ge=0, description="Extra X distance between grids")
    distancey: float = Field(0, ge=0, description="Extra Y distance between grids")


class GridfinityBinPart(BasePart):
    """
    Gridfinity storage bin with parametric configuration.

    This part wraps the gridfinity-rebuilt-bins.scad module, providing
    access to the full customizer options through Python.

    Example:
        >>> from apothecary.projects.parts.gridfinity import DEFAULT, BinParams
        >>> params = BinParams(gridx=2, gridy=1, gridz=3)
        >>> bounds = DEFAULT.get_bounds(params.model_dump())
        >>> print(f"Bin size: {bounds.size}")
    """

    def get_bounds(self, params: Optional[Dict] = None) -> BoundingBox3D:
        """
        Calculate bounds for a gridfinity bin based on parameters.

        Uses the standard gridfinity dimensions:
        - Grid unit: 42mm × 42mm
        - Height unit: 7mm
        - Stacking lip: ~3.55mm (added if include_lip=True)
        """
        if params:
            gridx = params.get("gridx", 1)
            gridy = params.get("gridy", 1)
            gridz = params.get("gridz", 3)
            include_lip = params.get("include_lip", True)
            half_grid = params.get("half_grid", False)
            gridz_define = params.get("gridz_define", 0)
        elif self.params_model:
            defaults = self.params_model()
            gridx = defaults.gridx
            gridy = defaults.gridy
            gridz = defaults.gridz
            include_lip = defaults.include_lip
            half_grid = defaults.half_grid
            gridz_define = (
                defaults.gridz_define.value
                if hasattr(defaults.gridz_define, "value")
                else defaults.gridz_define
            )
        else:
            gridx, gridy, gridz = 1, 1, 3
            include_lip = True
            half_grid = False
            gridz_define = 0

        # Calculate dimensions
        grid_unit = GRID_SIZE_MM / (2 if half_grid else 1)

        width_x = gridx * grid_unit
        width_y = gridy * grid_unit

        # Height calculation based on gridz_define
        if gridz_define == 0:  # 7mm units, excludes lip
            height = gridz * HEIGHT_UNIT_MM
        elif gridz_define == 1:  # Internal mm
            height = gridz  # Direct mm value
        elif gridz_define == 2:  # External mm, excludes lip
            height = gridz
        else:  # External mm, full
            height = gridz

        # Add stacking lip if enabled
        if include_lip:
            height += STACKING_LIP_MM

        return BoundingBox3D(
            min_point=Vector3D(x=0, y=0, z=0),
            max_point=Vector3D(x=width_x, y=width_y, z=height),
        )

    def get_recommended_print_settings(self) -> PrintSettings:
        """Return recommended print settings for Gridfinity bins."""
        return PrintSettings(
            nozzle_diameter=0.4,
            layer_height=0.2,
            wall_thickness=1.2,  # 3 perimeters for strength
            tolerance=0.2,  # Standard FDM tolerance for good fit
        )

    def get_scad_customizer_params(self, params: Optional[Dict] = None) -> Dict:
        """
        Convert Python params to OpenSCAD customizer format.

        Returns a dict that can be passed to OpenSCAD via -D flags.
        """
        if params is None:
            params = {}

        bin_params = BinParams(**params) if params else BinParams()

        return {
            "gridx": bin_params.gridx,
            "gridy": bin_params.gridy,
            "gridz": bin_params.gridz,
            "gridz_define": bin_params.gridz_define.value,
            "include_lip": bin_params.include_lip,
            "half_grid": bin_params.half_grid,
            "divx": bin_params.divx,
            "divy": bin_params.divy,
            "style_tab": bin_params.style_tab.value,
            "scoop": bin_params.scoop,
            "only_corners": bin_params.only_corners,
            "refined_holes": bin_params.hole_options.refined_holes,
            "magnet_holes": bin_params.hole_options.magnet_holes,
            "screw_holes": bin_params.hole_options.screw_holes,
            "crush_ribs": bin_params.hole_options.crush_ribs,
            "chamfer_holes": bin_params.hole_options.chamfer_holes,
            "printable_hole_top": bin_params.hole_options.printable_hole_top,
        }

    def get_available_variants(self) -> List[Dict]:
        """Return common bin configurations as named variants."""
        return [
            {
                "name": "1x1x3",
                "description": "Single unit bin, 3 height units",
                "params": {"gridx": 1, "gridy": 1, "gridz": 3},
            },
            {
                "name": "2x1x3",
                "description": "2-wide bin, 3 height units",
                "params": {"gridx": 2, "gridy": 1, "gridz": 3},
            },
            {
                "name": "2x2x3",
                "description": "2x2 bin, 3 height units",
                "params": {"gridx": 2, "gridy": 2, "gridz": 3},
            },
            {
                "name": "3x2x6",
                "description": "Large bin, 6 height units",
                "params": {"gridx": 3, "gridy": 2, "gridz": 6},
            },
            {
                "name": "1x1x2_divided",
                "description": "Small bin with 2x2 compartments",
                "params": {"gridx": 1, "gridy": 1, "gridz": 2, "divx": 2, "divy": 2},
            },
        ]

    @property
    def submodule_initialized(self) -> bool:
        """Check if the gridfinity submodule is initialized."""
        submodule_path = ROOT / "parts" / "gridfinity" / "gridfinity-rebuilt-openscad"
        if not submodule_path.exists():
            return False
        # Check for actual content (not just .git)
        contents = [c for c in submodule_path.iterdir() if c.name != ".git"]
        return len(contents) > 0

    @property
    def stl_output_dir(self) -> Path:
        """
        Get the directory where STL files should be stored.

        For gridfinity, we store STLs in parts/gridfinity/ instead of
        inside the submodule directory.
        """
        return ROOT / "parts" / "gridfinity"

    def get_stl_output_path(self) -> Path:
        """
        Override base class to put STL in parts/gridfinity/ not in submodule.
        """
        return self.stl_output_dir / "gridfinity.stl"

    @property
    def requires_dev_openscad(self) -> bool:
        """
        Whether this part requires a development build of OpenSCAD.

        gridfinity-rebuilt-openscad uses newer OpenSCAD syntax features
        that require version 2024.x+ (development snapshots).
        """
        return True

    @property
    def openscad_min_version(self) -> str:
        """Minimum OpenSCAD version required for this part."""
        return "2024.01"

    def get_stl_path(self, variant: Optional[str] = None) -> Path:
        """
        Get the STL output path for this part.

        Args:
            variant: Optional variant name (e.g., "1x1x3", "2x2x3")
                    If None, uses "default"

        Returns:
            Path where the STL should be stored
        """
        suffix = variant or "default"
        return self.stl_output_dir / f"gridfinity_{suffix}.stl"

    def can_generate_stl(self) -> tuple[bool, str]:
        """
        Check if STL generation is possible.

        Returns:
            Tuple of (can_generate, reason_if_not)
        """
        from .stl_renderer import get_renderer

        if not self.submodule_initialized:
            return False, "Submodule not initialized. Run: apothecary submodules"

        renderer = get_renderer()
        if not renderer.is_available:
            return False, "OpenSCAD not installed"

        version = renderer.get_version()
        # Check if installed version is too old
        is_old_version = version and any(
            v in version for v in ["2019", "2020", "2021", "2022", "2023"]
        )

        if is_old_version:
            # Check if nightly build is available
            nightly = renderer.find_nightly()
            if nightly:
                nightly_version = renderer.get_nightly_version()
                return True, f"Will use nightly build: {nightly} ({nightly_version})"
            else:
                return False, (
                    f"OpenSCAD {version} is too old. gridfinity requires 2024.x+ "
                    f"(development build). Install OpenSCAD Nightly from "
                    f"https://openscad.org/downloads.html#snapshots"
                )

        return True, "Ready"

    def get_openscad_path(self) -> Optional[Path]:
        """
        Get the appropriate OpenSCAD path for this part.

        Returns nightly build if stable version is too old.
        """
        from .stl_renderer import get_renderer

        renderer = get_renderer()
        if not renderer.is_available:
            return None

        version = renderer.get_version()
        is_old_version = version and any(
            v in version for v in ["2019", "2020", "2021", "2022", "2023"]
        )

        if is_old_version:
            nightly = renderer.find_nightly()
            if nightly:
                return nightly

        return renderer.openscad_path


def create(metadata_root: Path) -> GridfinityBinPart:
    """Create the Gridfinity bin part instance."""
    scad = (
        metadata_root
        / "parts"
        / "gridfinity"
        / "gridfinity-rebuilt-openscad"
        / "gridfinity-rebuilt-bins.scad"
    )

    return GridfinityBinPart(
        name="gridfinity",
        source_file=scad,
        description="Gridfinity modular storage bins - parametric OpenSCAD library",
        params_model=BinParams,
        category="storage",
        tags=["gridfinity", "storage", "modular", "bins", "organization", "parametric"],
        readme_path=metadata_root / "parts" / "gridfinity" / "README.md",
        preview_color=Color.from_hex("#4A90D9"),  # Gridfinity blue
        module_name="gridfinity-rebuilt-bins",
        print_settings=PrintSettings(
            nozzle_diameter=0.4,
            layer_height=0.2,
            tolerance=0.2,
        ),
    )


DEFAULT = create(ROOT)


# Convenience functions
def get_bin_dimensions(gridx: int = 1, gridy: int = 1, gridz: float = 3) -> Dict:
    """
    Calculate physical dimensions for a gridfinity bin.

    Args:
        gridx: Grid units in X direction
        gridy: Grid units in Y direction
        gridz: Height units (1 unit = 7mm)

    Returns:
        Dict with width, depth, height in mm
    """
    return {
        "width_mm": gridx * GRID_SIZE_MM,
        "depth_mm": gridy * GRID_SIZE_MM,
        "height_mm": gridz * HEIGHT_UNIT_MM + STACKING_LIP_MM,
        "grid_unit_mm": GRID_SIZE_MM,
        "height_unit_mm": HEIGHT_UNIT_MM,
    }


def check_submodule() -> bool:
    """Check if the gridfinity submodule is properly initialized."""
    return DEFAULT.submodule_initialized


if __name__ == "__main__":
    # Demo usage
    print(f"Gridfinity Part: {DEFAULT.name}")
    print(f"Description: {DEFAULT.description}")
    print(f"Submodule initialized: {DEFAULT.submodule_initialized}")
    print()

    # Show available variants
    print("Available variants:")
    for variant in DEFAULT.get_available_variants():
        print(f"  {variant['name']}: {variant['description']}")
    print()

    # Calculate bounds for default bin
    bounds = DEFAULT.get_bounds()
    print("Default bin (1x1x3) dimensions:")
    print(f"  Size: {bounds.size.x:.1f} x {bounds.size.y:.1f} x {bounds.size.z:.1f} mm")
    print(f"  Volume: {bounds.volume:.0f} mm³")
