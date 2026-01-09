"""
Models package for Apothecary.

Provides shared geometry primitives, color models, and unit utilities
for OpenSCAD generation.
"""

from .bounds import (
    BoundingBox2D,
    BoundingBox3D,
)
from .colors import (
    BLACK,
    BLUE,
    CYAN,
    GRAY,
    GREEN,
    MAGENTA,
    NAMED_COLORS,
    ORANGE,
    RED,
    WHITE,
    YELLOW,
    Color,
)
from .shapes import (
    Arc2D,
    Circle2D,
    Polygon2D,
)
from .units import (
    HardwareSizes,
    Length,
    LengthUnit,
    PrintSettings,
    convert_length,
)
from .vectors import (
    ORIGIN,
    ORIGIN_2D,
    X_AXIS,
    X_AXIS_2D,
    Y_AXIS,
    Y_AXIS_2D,
    Z_AXIS,
    Vector2D,
    Vector3D,
)

__all__ = [
    # Vectors
    "Vector2D",
    "Vector3D",
    "ORIGIN",
    "ORIGIN_2D",
    "X_AXIS",
    "Y_AXIS",
    "Z_AXIS",
    "X_AXIS_2D",
    "Y_AXIS_2D",
    # Bounds
    "BoundingBox2D",
    "BoundingBox3D",
    # Colors
    "Color",
    "NAMED_COLORS",
    "BLACK",
    "WHITE",
    "RED",
    "GREEN",
    "BLUE",
    "YELLOW",
    "CYAN",
    "MAGENTA",
    "ORANGE",
    "GRAY",
    # Shapes
    "Polygon2D",
    "Circle2D",
    "Arc2D",
    # Units
    "LengthUnit",
    "Length",
    "convert_length",
    "HardwareSizes",
    "PrintSettings",
]
