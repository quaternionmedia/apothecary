"""
Calibration Cube - Test shape with axis indicators and dimensions.

This part demonstrates:
- Parametric models with bounds calculation
- Color-coded axis visualization
- Print settings integration
- All geometry model features

Use this as a reference for creating new parts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from pydantic import BaseModel, Field

from apothecary.models import (
    BoundingBox3D,
    Color,
    PrintSettings,
)

from .base import BasePart
from .skeleton import ROOT


class Params(BaseModel):
    """
    Calibration cube parameters.

    Attributes:
        size: Overall cube dimension in mm (default 10, as the SCAD)
        show_axes: Include XYZ axis indicators for preview (not rendered to STL)
        show_dimensions: Include size markers on -X and -Y faces
        wall_thickness: Shell thickness for hollow printing

    Face layout:
        +X (right):  "X" axis label
        -X (left):   dimension value
        +Y (back):   "Y" axis label
        -Y (front):  dimension value
        +Z (top):    "Z" axis label + orientation notch
        -Z (bottom): flat (print bed surface)
    """

    size: float = Field(10.0, gt=5, le=100, description="Cube size in mm")
    show_axes: bool = Field(True, description="Show XYZ axis indicators (preview only)")
    show_dimensions: bool = Field(True, description="Show dimension markers")
    wall_thickness: float = Field(2.0, gt=0, le=10, description="Wall thickness")


class CalibrationCubePart(BasePart):
    """
    Calibration cube with calculated bounds and print settings.

    This part is designed for:
    - Printer calibration (dimensional accuracy)
    - Understanding coordinate systems (XYZ axes)
    - Testing slicer settings

    Features:
    - X, Y, Z labels as relief cut into +X, +Y, +Z faces
    - Dimension values on -X and -Y faces
    - Bottom (-Z) is flat for stable printing
    - Orientation notch on top corner
    - Axis arrows shown in preview only (not rendered to STL)
    """

    def get_bounds(self, params: Optional[Dict] = None) -> BoundingBox3D:
        """
        Calculate bounds from parameters.

        Since axes are preview-only (not rendered to STL), bounds
        always reflect just the cube geometry.
        """
        size = (params or {}).get("size", Params().size)
        return BoundingBox3D.for_cube(size, center=False)


def create(metadata_root: Path) -> CalibrationCubePart:
    """Create the calibration cube part instance."""
    scad = metadata_root / "parts" / "calibration_cube" / "calibration_cube.scad"
    return CalibrationCubePart(
        name="calibration_cube",
        source_file=scad,
        description="Calibration cube with XYZ axes and dimension markers",
        params_model=Params,
        category="calibration",
        tags=["calibration", "test", "axes", "dimensions", "demo"],
        readme_path=metadata_root / "parts" / "README.md",
        preview_color=Color.from_hex("#808080"),  # Gray
        print_settings=PrintSettings(
            nozzle_diameter=0.4,
            layer_height=0.2,
            tolerance=0.1,
        ),
    )


DEFAULT = create(ROOT)
