"""
Vector and coordinate models for 3D geometry.

These models provide type-safe representations of positions, directions,
and transformations used throughout the OpenSCAD generation system.
"""

from __future__ import annotations

import math
from typing import List, Tuple

from pydantic import BaseModel


class Vector2D(BaseModel):
    """2D vector for XY plane operations."""

    x: float = 0.0
    y: float = 0.0

    def to_list(self) -> List[float]:
        """Convert to OpenSCAD-compatible list."""
        return [self.x, self.y]

    def to_tuple(self) -> Tuple[float, float]:
        """Convert to tuple."""
        return (self.x, self.y)

    def __add__(self, other: "Vector2D") -> "Vector2D":
        return Vector2D(x=self.x + other.x, y=self.y + other.y)

    def __sub__(self, other: "Vector2D") -> "Vector2D":
        return Vector2D(x=self.x - other.x, y=self.y - other.y)

    def __mul__(self, scalar: float) -> "Vector2D":
        return Vector2D(x=self.x * scalar, y=self.y * scalar)

    def __neg__(self) -> "Vector2D":
        return Vector2D(x=-self.x, y=-self.y)

    @property
    def magnitude(self) -> float:
        """Length of the vector."""
        return math.sqrt(self.x**2 + self.y**2)

    def normalized(self) -> "Vector2D":
        """Return unit vector in same direction."""
        mag = self.magnitude
        if mag == 0:
            return Vector2D()
        return Vector2D(x=self.x / mag, y=self.y / mag)

    def dot(self, other: "Vector2D") -> float:
        """Dot product with another vector."""
        return self.x * other.x + self.y * other.y

    def rotate(self, angle_degrees: float) -> "Vector2D":
        """Rotate vector by angle (in degrees)."""
        rad = math.radians(angle_degrees)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        return Vector2D(x=self.x * cos_a - self.y * sin_a, y=self.x * sin_a + self.y * cos_a)

    @classmethod
    def from_polar(cls, r: float, theta_degrees: float) -> "Vector2D":
        """Create vector from polar coordinates."""
        rad = math.radians(theta_degrees)
        return cls(x=r * math.cos(rad), y=r * math.sin(rad))


class Vector3D(BaseModel):
    """3D vector for spatial operations."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def to_list(self) -> List[float]:
        """Convert to OpenSCAD-compatible list."""
        return [self.x, self.y, self.z]

    def to_tuple(self) -> Tuple[float, float, float]:
        """Convert to tuple."""
        return (self.x, self.y, self.z)

    def __add__(self, other: "Vector3D") -> "Vector3D":
        return Vector3D(x=self.x + other.x, y=self.y + other.y, z=self.z + other.z)

    def __sub__(self, other: "Vector3D") -> "Vector3D":
        return Vector3D(x=self.x - other.x, y=self.y - other.y, z=self.z - other.z)

    def __mul__(self, scalar: float) -> "Vector3D":
        return Vector3D(x=self.x * scalar, y=self.y * scalar, z=self.z * scalar)

    def __neg__(self) -> "Vector3D":
        return Vector3D(x=-self.x, y=-self.y, z=-self.z)

    @property
    def magnitude(self) -> float:
        """Length of the vector."""
        return math.sqrt(self.x**2 + self.y**2 + self.z**2)

    @property
    def xy(self) -> Vector2D:
        """Project onto XY plane."""
        return Vector2D(x=self.x, y=self.y)

    @property
    def xz(self) -> Vector2D:
        """Project onto XZ plane."""
        return Vector2D(x=self.x, y=self.z)

    @property
    def yz(self) -> Vector2D:
        """Project onto YZ plane."""
        return Vector2D(x=self.y, y=self.z)

    def normalized(self) -> "Vector3D":
        """Return unit vector in same direction."""
        mag = self.magnitude
        if mag == 0:
            return Vector3D()
        return Vector3D(x=self.x / mag, y=self.y / mag, z=self.z / mag)

    def dot(self, other: "Vector3D") -> float:
        """Dot product with another vector."""
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: "Vector3D") -> "Vector3D":
        """Cross product with another vector."""
        return Vector3D(
            x=self.y * other.z - self.z * other.y,
            y=self.z * other.x - self.x * other.z,
            z=self.x * other.y - self.y * other.x,
        )

    @classmethod
    def from_spherical(cls, r: float, theta: float, phi: float) -> "Vector3D":
        """
        Create vector from spherical coordinates.

        Args:
            r: Radius (distance from origin)
            theta: Azimuthal angle in XY plane from X axis (degrees)
            phi: Polar angle from Z axis (degrees)
        """
        theta_rad = math.radians(theta)
        phi_rad = math.radians(phi)
        sin_phi = math.sin(phi_rad)
        return cls(
            x=r * sin_phi * math.cos(theta_rad),
            y=r * sin_phi * math.sin(theta_rad),
            z=r * math.cos(phi_rad),
        )

    @classmethod
    def from_cylindrical(cls, r: float, theta: float, z: float) -> "Vector3D":
        """
        Create vector from cylindrical coordinates.

        Args:
            r: Radial distance in XY plane
            theta: Angle from X axis in XY plane (degrees)
            z: Height along Z axis
        """
        rad = math.radians(theta)
        return cls(x=r * math.cos(rad), y=r * math.sin(rad), z=z)


# Common unit vectors
ORIGIN = Vector3D(x=0, y=0, z=0)
X_AXIS = Vector3D(x=1, y=0, z=0)
Y_AXIS = Vector3D(x=0, y=1, z=0)
Z_AXIS = Vector3D(x=0, y=0, z=1)

ORIGIN_2D = Vector2D(x=0, y=0)
X_AXIS_2D = Vector2D(x=1, y=0)
Y_AXIS_2D = Vector2D(x=0, y=1)
