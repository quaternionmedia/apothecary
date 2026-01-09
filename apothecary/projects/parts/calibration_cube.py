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
    HardwareSizes,
    PrintSettings,
)

from .base import BasePart
from .skeleton import ROOT


class Params(BaseModel):
    """
    Calibration cube parameters.

    Attributes:
        size: Overall cube dimension in mm (default: 20mm calibration standard)
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
        if params:
            size = params.get("size", 20)
        elif self.params_model:
            defaults = self.params_model()
            size = defaults.size
        else:
            size = 20

        # Cube bounds (axes are preview-only, not in STL)
        return BoundingBox3D.for_cube(size, center=False)

    def get_recommended_print_settings(self) -> PrintSettings:
        """
        Return recommended print settings for calibration.

        Calibration cubes should be printed with tight tolerances
        to accurately measure dimensional accuracy.
        """
        return PrintSettings(
            nozzle_diameter=0.4,
            layer_height=0.2,
            wall_thickness=1.2,  # 3 perimeters
            tolerance=HardwareSizes.FDM_TIGHT,  # 0.1mm for calibration
        )

    def get_calibration_targets(self, params: Optional[Dict] = None) -> Dict:
        """
        Return target dimensions for calibration verification.

        After printing, measure these dimensions to check accuracy:
        - X, Y, Z dimensions should match 'size' parameter
        - Corner notch helps identify orientation
        - Dimension markers show expected values
        """
        size = params.get("size", 10) if params else 10
        wall = params.get("wall_thickness", 2) if params else 2

        return {
            "external_dimensions": {
                "x": size,
                "y": size,
                "z": size,
                "tolerance": "±0.1mm for well-calibrated printer",
            },
            "internal_dimensions": {
                "x": size - 2 * wall,
                "y": size - 2 * wall,
                "z": size - 2 * wall,
                "note": "Measure if printed hollow",
            },
            "corner_notch": {
                "size": size * 0.15,
                "position": "Top corner at origin (0, 0, Z)",
                "purpose": "Orientation reference",
            },
            "face_layout": {
                "+X (right)": "X axis label",
                "-X (left)": f"{size} dimension",
                "+Y (back)": "Y axis label",
                "-Y (front)": f"{size} dimension",
                "+Z (top)": "Z axis label + notch",
                "-Z (bottom)": "Flat (print bed)",
            },
            "verification_steps": [
                "1. Measure X dimension with calipers",
                "2. Measure Y dimension with calipers",
                "3. Measure Z dimension with calipers",
                "4. Calculate deviation from target",
                "5. Adjust flow/steps-per-mm if needed",
            ],
        }


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
        readme_path=metadata_root / "docs" / "tutorial.md",
        preview_color=Color.from_hex("#808080"),  # Gray
        print_settings=PrintSettings(
            nozzle_diameter=0.4,
            layer_height=0.2,
            tolerance=0.1,
        ),
    )


DEFAULT = create(ROOT)


# Convenience functions for tutorial use
def print_info():
    """Print part information for tutorial demonstration."""
    part = DEFAULT
    print(f"Part: {part.name}")
    print(f"Description: {part.description}")
    print(f"Category: {part.category}")
    print(f"Tags: {', '.join(part.tags)}")
    print(f"Source: {part.source_file}")
    print()

    # Show default parameters
    if part.params_model:
        defaults = part.params_model()
        print("Default Parameters:")
        for field_name, field_info in part.params_model.model_fields.items():
            value = getattr(defaults, field_name)
            print(f"  {field_name}: {value} - {field_info.description or ''}")
    print()

    # Show bounds
    bounds = part.get_bounds()
    print("Bounding Box:")
    print(f"  Size: {bounds.size.to_list()} mm")
    print(f"  Center: {bounds.center.to_list()} mm")
    print(f"  Volume: {bounds.volume:.1f} mm³")
    print()

    # Show color
    print(f"Preview Color: {part.preview_color.to_hex()}")


if __name__ == "__main__":
    print_info()
