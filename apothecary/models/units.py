"""
Unit conversion utilities for dimensional modeling.

OpenSCAD is unit-agnostic, but these helpers make it easier to work
with real-world dimensions and convert between unit systems.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class LengthUnit(str, Enum):
    """Supported length units."""

    # Metric
    MILLIMETER = "mm"
    CENTIMETER = "cm"
    METER = "m"
    MICROMETER = "um"

    # Imperial
    INCH = "in"
    FOOT = "ft"
    THOU = "thou"  # Thousandth of an inch (mil)


# Conversion factors to millimeters (base unit)
_TO_MM = {
    LengthUnit.MILLIMETER: 1.0,
    LengthUnit.CENTIMETER: 10.0,
    LengthUnit.METER: 1000.0,
    LengthUnit.MICROMETER: 0.001,
    LengthUnit.INCH: 25.4,
    LengthUnit.FOOT: 304.8,
    LengthUnit.THOU: 0.0254,
}


def convert_length(value: float, from_unit: LengthUnit, to_unit: LengthUnit) -> float:
    """
    Convert a length value between units.

    Args:
        value: The numeric value to convert
        from_unit: Source unit
        to_unit: Target unit

    Returns:
        Converted value in target units
    """
    # Convert to mm, then to target
    mm_value = value * _TO_MM[from_unit]
    return mm_value / _TO_MM[to_unit]


class Length(BaseModel):
    """
    A length value with associated unit.

    Provides easy conversion and arithmetic with unit awareness.
    """

    value: float = 0.0
    unit: LengthUnit = LengthUnit.MILLIMETER

    def to(self, target_unit: LengthUnit) -> "Length":
        """Convert to different unit."""
        return Length(value=convert_length(self.value, self.unit, target_unit), unit=target_unit)

    def to_mm(self) -> float:
        """Get value in millimeters."""
        return convert_length(self.value, self.unit, LengthUnit.MILLIMETER)

    def to_inches(self) -> float:
        """Get value in inches."""
        return convert_length(self.value, self.unit, LengthUnit.INCH)

    def __add__(self, other: "Length") -> "Length":
        other_converted = convert_length(other.value, other.unit, self.unit)
        return Length(value=self.value + other_converted, unit=self.unit)

    def __sub__(self, other: "Length") -> "Length":
        other_converted = convert_length(other.value, other.unit, self.unit)
        return Length(value=self.value - other_converted, unit=self.unit)

    def __mul__(self, scalar: float) -> "Length":
        return Length(value=self.value * scalar, unit=self.unit)

    def __truediv__(self, scalar: float) -> "Length":
        return Length(value=self.value / scalar, unit=self.unit)

    def __str__(self) -> str:
        return f"{self.value}{self.unit.value}"

    @classmethod
    def mm(cls, value: float) -> "Length":
        """Create length in millimeters."""
        return cls(value=value, unit=LengthUnit.MILLIMETER)

    @classmethod
    def cm(cls, value: float) -> "Length":
        """Create length in centimeters."""
        return cls(value=value, unit=LengthUnit.CENTIMETER)

    @classmethod
    def m(cls, value: float) -> "Length":
        """Create length in meters."""
        return cls(value=value, unit=LengthUnit.METER)

    @classmethod
    def inch(cls, value: float) -> "Length":
        """Create length in inches."""
        return cls(value=value, unit=LengthUnit.INCH)

    @classmethod
    def ft(cls, value: float) -> "Length":
        """Create length in feet."""
        return cls(value=value, unit=LengthUnit.FOOT)


# Common hardware dimensions (in mm)
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

    @property
    def min_wall(self) -> float:
        """Minimum printable wall thickness."""
        return self.nozzle_diameter

    @property
    def min_hole(self) -> float:
        """Minimum printable hole diameter."""
        return self.nozzle_diameter * 2

    def clearance_hole(self, nominal: float) -> float:
        """Calculate clearance hole size for given nominal diameter."""
        return nominal + self.tolerance * 2

    def press_fit_hole(self, nominal: float) -> float:
        """Calculate press-fit hole size for given nominal diameter."""
        return nominal - self.tolerance
