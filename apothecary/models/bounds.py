"""
Bounding box and spatial extent models.

These models represent axis-aligned bounding boxes (AABB) for
calculating object extents, collision detection, and layout.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, computed_field

from .vectors import Vector3D


class BoundingBox3D(BaseModel):
    """Axis-aligned bounding box in 3D."""

    min_point: Vector3D = Vector3D()
    max_point: Vector3D = Vector3D()

    @computed_field
    @property
    def width(self) -> float:
        """Size along X axis."""
        return self.max_point.x - self.min_point.x

    @computed_field
    @property
    def height(self) -> float:
        """Size along Y axis."""
        return self.max_point.y - self.min_point.y

    @computed_field
    @property
    def depth(self) -> float:
        """Size along Z axis."""
        return self.max_point.z - self.min_point.z

    @computed_field
    @property
    def size(self) -> Vector3D:
        """Dimensions as a vector."""
        return Vector3D(x=self.width, y=self.height, z=self.depth)

    @computed_field
    @property
    def center(self) -> Vector3D:
        """Center point of the box."""
        return Vector3D(
            x=(self.min_point.x + self.max_point.x) / 2,
            y=(self.min_point.y + self.max_point.y) / 2,
            z=(self.min_point.z + self.max_point.z) / 2,
        )

    @computed_field
    @property
    def volume(self) -> float:
        """Volume of the bounding box."""
        return self.width * self.height * self.depth

    @computed_field
    @property
    def surface_area(self) -> float:
        """Surface area of the bounding box."""
        return 2 * (self.width * self.height + self.height * self.depth + self.depth * self.width)

    def intersects(self, other: "BoundingBox3D") -> bool:
        """Check if two boxes overlap."""
        return (
            self.min_point.x <= other.max_point.x
            and self.max_point.x >= other.min_point.x
            and self.min_point.y <= other.max_point.y
            and self.max_point.y >= other.min_point.y
            and self.min_point.z <= other.max_point.z
            and self.max_point.z >= other.min_point.z
        )

    @classmethod
    def from_points(cls, points: List[Vector3D]) -> "BoundingBox3D":
        """Create smallest box containing all points."""
        if not points:
            return cls()

        xs = [p.x for p in points]
        ys = [p.y for p in points]
        zs = [p.z for p in points]
        return cls(
            min_point=Vector3D(x=min(xs), y=min(ys), z=min(zs)),
            max_point=Vector3D(x=max(xs), y=max(ys), z=max(zs)),
        )

    @classmethod
    def for_cube(cls, size: float, center: bool = False) -> "BoundingBox3D":
        """Create bounding box for a cube primitive."""
        if center:
            half = size / 2
            return cls(
                min_point=Vector3D(x=-half, y=-half, z=-half),
                max_point=Vector3D(x=half, y=half, z=half),
            )
        return cls(min_point=Vector3D(), max_point=Vector3D(x=size, y=size, z=size))

    @classmethod
    def for_cylinder(cls, h: float, r: float, center: bool = False) -> "BoundingBox3D":
        """Create bounding box for a cylinder primitive."""
        if center:
            return cls(
                min_point=Vector3D(x=-r, y=-r, z=-h / 2), max_point=Vector3D(x=r, y=r, z=h / 2)
            )
        return cls(min_point=Vector3D(x=-r, y=-r, z=0), max_point=Vector3D(x=r, y=r, z=h))
