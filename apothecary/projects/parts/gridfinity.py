"""
Gridfinity - Modular storage bin system integration.

This module integrates the gridfinity-rebuilt-openscad library as an
Apothecary part, providing parametric access to the modular storage system.

The gridfinity-rebuilt-openscad library is included as a git submodule at:
    parts/gridfinity/gridfinity-rebuilt-openscad/

To initialize the submodule:
    git submodule update --init

Reference:
    - https://gridfinity.com - Original Gridfinity system
    - https://github.com/kennetek/gridfinity-rebuilt-openscad - OpenSCAD library
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from pydantic import BaseModel, Field

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

# The library's 2.0.0 source ends a call's arguments with a comma, which
# OpenSCAD accepts from openscad/openscad#3814 (merged 2021-08-24), and relies
# on `$` variable scoping that 2021.01 does not have.
OPENSCAD_MIN_VERSION = "2021.08.24"


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

    # Grid dimensions. Every default is gridfinity-rebuilt-bins.scad's own: a
    # build with no overrides passes no -D and renders what the file says.
    gridx: int = Field(3, ge=1, le=10, description="Number of bases along X-axis")
    gridy: int = Field(2, ge=1, le=10, description="Number of bases along Y-axis")
    gridz: float = Field(6, ge=1, le=20, description="Bin height in units (1 unit = 7mm)")

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
        p = BinParams(**(params or {}))
        gridx, gridy, gridz = p.gridx, p.gridy, p.gridz
        include_lip, half_grid, gridz_define = p.include_lip, p.half_grid, p.gridz_define

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

        # The library centres a bin on X and Y and stands it on Z = 0.
        return BoundingBox3D(
            min_point=Vector3D(x=-width_x / 2, y=-width_y / 2, z=0),
            max_point=Vector3D(x=width_x / 2, y=width_y / 2, z=height),
        )

    def scad_overrides(self, params: Mapping[str, Any]) -> Dict[str, Any]:
        """The overrides given, under gridfinity-rebuilt-bins.scad's customizer
        names: ``hole_options`` as the six booleans the SCAD bundles itself,
        an enum as its number."""
        scad: Dict[str, Any] = {}
        for name, value in params.items():
            if name == "hole_options":
                scad.update(HoleOptions.model_validate(value).model_dump())
            else:
                scad[name] = value.value if isinstance(value, Enum) else value
        return scad

    @property
    def submodule_initialized(self) -> bool:
        """Check if the gridfinity submodule is initialized."""
        submodule_path = ROOT / "parts" / "gridfinity" / "gridfinity-rebuilt-openscad"
        if not submodule_path.exists():
            return False
        # Check for actual content (not just .git)
        contents = [c for c in submodule_path.iterdir() if c.name != ".git"]
        return len(contents) > 0

    def get_stl_output_path(self) -> Path:
        """parts/gridfinity/gridfinity.stl, outside the submodule's working tree."""
        return ROOT / "parts" / "gridfinity" / "gridfinity.stl"

    def can_generate_stl(self, openscad: Optional[Path] = None) -> Tuple[bool, str]:
        """The submodule's SCAD is present, and an OpenSCAD new enough for it."""
        if not self.submodule_initialized:
            return False, "Submodule not initialized. Run: git submodule update --init"
        return super().can_generate_stl(openscad)


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
        openscad_min_version=OPENSCAD_MIN_VERSION,
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
