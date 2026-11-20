"""The value types parts and assemblies share: vectors, bounding boxes, colour,
print settings, hardware sizes, black boxes and interfaces. docs/models.md shows
each; docs/connections.md says how interfaces meet."""

from .blackbox import (
    BlackBox,
    BlackBoxProvider,
    Keepout,
    MountPoint,
    StubProvider,
)
from .bounds import BoundingBox3D
from .colors import GRAY, Color
from .interfaces import BoltHole, Fit, Interface, Slot, Socket, Spigot, fit, read_interfaces
from .units import HardwareSizes, PrintSettings
from .vectors import Vector2D, Vector3D

__all__ = [
    "BlackBox",
    "BlackBoxProvider",
    "Keepout",
    "MountPoint",
    "StubProvider",
    "BoltHole",
    "Fit",
    "Interface",
    "Slot",
    "Socket",
    "Spigot",
    "fit",
    "read_interfaces",
    "Vector2D",
    "Vector3D",
    "BoundingBox3D",
    "Color",
    "GRAY",
    "HardwareSizes",
    "PrintSettings",
]
