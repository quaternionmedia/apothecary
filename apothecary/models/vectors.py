"""
Vector and coordinate models for 3D geometry.

These models provide type-safe representations of positions, directions,
and transformations used throughout the OpenSCAD generation system.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel


class Vector2D(BaseModel):
    """2D vector for XY plane operations."""

    x: float = 0.0
    y: float = 0.0

    def to_list(self) -> List[float]:
        """Convert to OpenSCAD-compatible list."""
        return [self.x, self.y]

    def __add__(self, other: "Vector2D") -> "Vector2D":
        return Vector2D(x=self.x + other.x, y=self.y + other.y)

    def __sub__(self, other: "Vector2D") -> "Vector2D":
        return Vector2D(x=self.x - other.x, y=self.y - other.y)

    def __mul__(self, scalar: float) -> "Vector2D":
        return Vector2D(x=self.x * scalar, y=self.y * scalar)

    def __neg__(self) -> "Vector2D":
        return Vector2D(x=-self.x, y=-self.y)


class Vector3D(BaseModel):
    """3D vector for spatial operations."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def to_list(self) -> List[float]:
        """Convert to OpenSCAD-compatible list."""
        return [self.x, self.y, self.z]

    def __add__(self, other: "Vector3D") -> "Vector3D":
        return Vector3D(x=self.x + other.x, y=self.y + other.y, z=self.z + other.z)

    def __sub__(self, other: "Vector3D") -> "Vector3D":
        return Vector3D(x=self.x - other.x, y=self.y - other.y, z=self.z - other.z)

    def __mul__(self, scalar: float) -> "Vector3D":
        return Vector3D(x=self.x * scalar, y=self.y * scalar, z=self.z * scalar)

    def __neg__(self) -> "Vector3D":
        return Vector3D(x=-self.x, y=-self.y, z=-self.z)
