"""Hardware sizes and 3D-printing settings, in millimetres.

OpenSCAD is unit-agnostic; every number here is mm.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class HardwareSizes:
    """Standard hardware dimensions for reference."""

    # Metric screws (nominal diameter in mm)
    M2 = 2.0
    M2_5 = 2.5
    M3 = 3.0
    M4 = 4.0
    M5 = 5.0
    M6 = 6.0
    M8 = 8.0
    M10 = 10.0

    # Metric clearance holes (close fit)
    M2_CLEARANCE = 2.2
    M3_CLEARANCE = 3.2
    M4_CLEARANCE = 4.3
    M5_CLEARANCE = 5.3
    M6_CLEARANCE = 6.4
    M8_CLEARANCE = 8.4

    # Common material thicknesses
    ACRYLIC_3MM = 3.0
    ACRYLIC_5MM = 5.0
    ACRYLIC_6MM = 6.0
    PLYWOOD_3MM = 3.0
    PLYWOOD_6MM = 6.0

    # 3D printing
    NOZZLE_0_4 = 0.4
    LAYER_0_2 = 0.2
    LAYER_0_1 = 0.1

    # Tolerances
    FDM_TIGHT = 0.1
    FDM_NORMAL = 0.2
    FDM_LOOSE = 0.3
    LASER_KERF = 0.1


class PrintSettings(BaseModel):
    """3D printing parameters for design calculations."""

    nozzle_diameter: float = Field(0.4, gt=0)
    layer_height: float = Field(0.2, gt=0)
    wall_thickness: float = Field(1.2, gt=0)  # Usually 3x nozzle
    tolerance: float = Field(0.2, ge=0)

    def clearance_hole(self, nominal: float) -> float:
        """Calculate clearance hole size for given nominal diameter."""
        return nominal + self.tolerance * 2

    def press_fit_hole(self, nominal: float) -> float:
        """Calculate press-fit hole size for given nominal diameter."""
        return nominal - self.tolerance
