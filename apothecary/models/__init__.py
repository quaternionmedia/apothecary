"""The value types parts and assemblies share: vectors, bounding boxes, colour,
print settings, hardware sizes and black boxes. docs/models.md shows each."""

from .blackbox import (
    BlackBox,
    BlackBoxProvider,
    Keepout,
    MountPoint,
    StubProvider,
)
from .bounds import BoundingBox3D
from .colors import GRAY, Color
from .units import HardwareSizes, PrintSettings
from .vectors import Vector2D, Vector3D

__all__ = [
    "BlackBox",
    "BlackBoxProvider",
    "Keepout",
    "MountPoint",
    "StubProvider",
    "Vector2D",
    "Vector3D",
    "BoundingBox3D",
    "Color",
    "GRAY",
    "HardwareSizes",
    "PrintSettings",
]
