"""
2D shape models for extrusion and projection.

These models represent 2D profiles that can be extruded to 3D
or used in polygon operations.
"""

from __future__ import annotations

import math
from typing import List, Optional

from pydantic import BaseModel, Field, computed_field

from .vectors import Vector2D


class Polygon2D(BaseModel):
    """
    2D polygon defined by a list of vertices.

    Vertices should be in counter-clockwise order for a solid polygon.
    Can include paths for holes (clockwise order).
    """

    points: List[Vector2D] = Field(default_factory=list)
    paths: Optional[List[List[int]]] = None  # Optional paths for holes

    @computed_field
    @property
    def vertex_count(self) -> int:
        """Number of vertices."""
        return len(self.points)

    @computed_field
    @property
    def is_closed(self) -> bool:
        """Check if polygon is closed (first == last point)."""
        if len(self.points) < 2:
            return False
        first, last = self.points[0], self.points[-1]
        return abs(first.x - last.x) < 1e-10 and abs(first.y - last.y) < 1e-10

    def to_openscad_points(self) -> str:
        """Generate OpenSCAD points array."""
        points_str = ", ".join(f"[{p.x}, {p.y}]" for p in self.points)
        return f"[{points_str}]"

    def to_openscad(self) -> str:
        """Generate full OpenSCAD polygon() call."""
        if self.paths:
            paths_str = ", ".join(
                "[" + ", ".join(str(i) for i in path) + "]" for path in self.paths
            )
            return f"polygon(points={self.to_openscad_points()}, paths=[{paths_str}]);"
        return f"polygon({self.to_openscad_points()});"

    @property
    def area(self) -> float:
        """Calculate polygon area using shoelace formula."""
        n = len(self.points)
        if n < 3:
            return 0.0

        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += self.points[i].x * self.points[j].y
            area -= self.points[j].x * self.points[i].y
        return abs(area) / 2

    @property
    def centroid(self) -> Vector2D:
        """Calculate polygon centroid."""
        n = len(self.points)
        if n == 0:
            return Vector2D()
        if n < 3:
            return Vector2D(
                x=sum(p.x for p in self.points) / n, y=sum(p.y for p in self.points) / n
            )

        cx, cy = 0.0, 0.0
        area = 0.0

        for i in range(n):
            j = (i + 1) % n
            cross = self.points[i].x * self.points[j].y - self.points[j].x * self.points[i].y
            area += cross
            cx += (self.points[i].x + self.points[j].x) * cross
            cy += (self.points[i].y + self.points[j].y) * cross

        area /= 2
        if abs(area) < 1e-10:
            return Vector2D(
                x=sum(p.x for p in self.points) / n, y=sum(p.y for p in self.points) / n
            )

        return Vector2D(x=cx / (6 * area), y=cy / (6 * area))

    @classmethod
    def regular(cls, n: int, radius: float = 1.0, center: Optional[Vector2D] = None) -> "Polygon2D":
        """
        Create a regular n-gon.

        Args:
            n: Number of sides (must be >= 3)
            radius: Distance from center to vertices
            center: Center point (defaults to origin)
        """
        if n < 3:
            raise ValueError("Polygon must have at least 3 sides")

        center = center or Vector2D()
        points = []
        for i in range(n):
            angle = 2 * math.pi * i / n - math.pi / 2  # Start at top
            points.append(
                Vector2D(
                    x=center.x + radius * math.cos(angle), y=center.y + radius * math.sin(angle)
                )
            )

        return cls(points=points)

    @classmethod
    def rectangle(cls, width: float, height: float, center: bool = False) -> "Polygon2D":
        """Create a rectangle."""
        if center:
            hw, hh = width / 2, height / 2
            return cls(
                points=[
                    Vector2D(x=-hw, y=-hh),
                    Vector2D(x=hw, y=-hh),
                    Vector2D(x=hw, y=hh),
                    Vector2D(x=-hw, y=hh),
                ]
            )
        return cls(
            points=[
                Vector2D(x=0, y=0),
                Vector2D(x=width, y=0),
                Vector2D(x=width, y=height),
                Vector2D(x=0, y=height),
            ]
        )

    @classmethod
    def star(cls, points: int, outer_radius: float, inner_radius: float) -> "Polygon2D":
        """
        Create a star polygon.

        Args:
            points: Number of star points
            outer_radius: Radius to outer points
            inner_radius: Radius to inner valleys
        """
        if points < 3:
            raise ValueError("Star must have at least 3 points")

        vertices = []
        for i in range(points * 2):
            angle = math.pi * i / points - math.pi / 2
            r = outer_radius if i % 2 == 0 else inner_radius
            vertices.append(Vector2D(x=r * math.cos(angle), y=r * math.sin(angle)))

        return cls(points=vertices)


class Circle2D(BaseModel):
    """
    Circle representation for 2D operations.

    Can be converted to polygon for OpenSCAD or used directly.
    """

    radius: float = Field(1.0, gt=0)
    center: Vector2D = Vector2D()
    segments: Optional[int] = Field(None, gt=2)  # $fn override

    @computed_field
    @property
    def diameter(self) -> float:
        """Circle diameter."""
        return self.radius * 2

    @computed_field
    @property
    def circumference(self) -> float:
        """Circle circumference."""
        return 2 * math.pi * self.radius

    @computed_field
    @property
    def area(self) -> float:
        """Circle area."""
        return math.pi * self.radius**2

    def to_openscad(self) -> str:
        """Generate OpenSCAD circle() call."""
        fn_str = f", $fn={self.segments}" if self.segments else ""
        if self.center.x != 0 or self.center.y != 0:
            return f"translate([{self.center.x}, {self.center.y}]) circle(r={self.radius}{fn_str});"
        return f"circle(r={self.radius}{fn_str});"

    def to_polygon(self, segments: Optional[int] = None) -> Polygon2D:
        """Convert to polygon with specified segments."""
        n = segments or self.segments or 32
        return Polygon2D.regular(n, self.radius, self.center)

    def point_at_angle(self, angle_degrees: float) -> Vector2D:
        """Get point on circle at given angle from center."""
        rad = math.radians(angle_degrees)
        return Vector2D(
            x=self.center.x + self.radius * math.cos(rad),
            y=self.center.y + self.radius * math.sin(rad),
        )


class Arc2D(BaseModel):
    """
    Circular arc for 2D path construction.
    """

    radius: float = Field(1.0, gt=0)
    start_angle: float = 0.0  # degrees
    end_angle: float = 90.0  # degrees
    center: Vector2D = Vector2D()
    segments: Optional[int] = Field(None, gt=0)

    @computed_field
    @property
    def sweep_angle(self) -> float:
        """Angular extent of arc in degrees."""
        return self.end_angle - self.start_angle

    @computed_field
    @property
    def arc_length(self) -> float:
        """Length of arc."""
        return abs(math.radians(self.sweep_angle)) * self.radius

    def to_points(self, segments: Optional[int] = None) -> List[Vector2D]:
        """Generate points along the arc."""
        n = segments or self.segments or max(8, int(abs(self.sweep_angle) / 10))
        points = []

        for i in range(n + 1):
            t = i / n
            angle = math.radians(self.start_angle + t * self.sweep_angle)
            points.append(
                Vector2D(
                    x=self.center.x + self.radius * math.cos(angle),
                    y=self.center.y + self.radius * math.sin(angle),
                )
            )

        return points

    @property
    def start_point(self) -> Vector2D:
        """Point at start of arc."""
        rad = math.radians(self.start_angle)
        return Vector2D(
            x=self.center.x + self.radius * math.cos(rad),
            y=self.center.y + self.radius * math.sin(rad),
        )

    @property
    def end_point(self) -> Vector2D:
        """Point at end of arc."""
        rad = math.radians(self.end_angle)
        return Vector2D(
            x=self.center.x + self.radius * math.cos(rad),
            y=self.center.y + self.radius * math.sin(rad),
        )
