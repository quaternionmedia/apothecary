# Geometry Models

The `apothecary.models` package provides shared geometry primitives for OpenSCAD generation, visualization, and calculations.

## Overview

```python
from apothecary.models import (
    # Vectors
    Vector2D, Vector3D, ORIGIN, X_AXIS, Y_AXIS, Z_AXIS,
    # Bounds
    BoundingBox2D, BoundingBox3D,
    # Colors
    Color, BLACK, WHITE, RED, GREEN, BLUE,
    # Shapes
    Polygon2D, Circle2D, Arc2D,
    # Units
    Length, LengthUnit, convert_length, HardwareSizes, PrintSettings,
)
```

## Vectors

### Vector2D

2D vector for XY plane operations.

```python
from apothecary.models import Vector2D

v = Vector2D(x=3, y=4)
print(v.magnitude)      # 5.0
print(v.normalized())   # Vector2D(x=0.6, y=0.8)
print(v.to_list())      # [3, 4]

# Arithmetic
a = Vector2D(x=1, y=2)
b = Vector2D(x=3, y=4)
print(a + b)            # Vector2D(x=4, y=6)
print(a * 2)            # Vector2D(x=2, y=4)

# Polar coordinates
v = Vector2D.from_polar(r=10, theta_degrees=45)

# Rotation
rotated = v.rotate(90)  # Rotate 90 degrees
```

### Vector3D

3D vector for spatial operations.

```python
from apothecary.models import Vector3D, X_AXIS, Y_AXIS

v = Vector3D(x=1, y=2, z=3)
print(v.magnitude)      # 3.74...
print(v.to_list())      # [1, 2, 3]

# Cross product
z = X_AXIS.cross(Y_AXIS)  # Z_AXIS

# Dot product
print(X_AXIS.dot(Y_AXIS))  # 0 (perpendicular)

# Projections
print(v.xy)  # Vector2D(x=1, y=2)
print(v.xz)  # Vector2D(x=1, y=3)

# Coordinate systems
from_spherical = Vector3D.from_spherical(r=10, theta=45, phi=30)
from_cylindrical = Vector3D.from_cylindrical(r=5, theta=90, z=10)
```

## Bounding Boxes

### BoundingBox3D

Axis-aligned bounding box for 3D objects.

```python
from apothecary.models import BoundingBox3D, Vector3D

# From primitives
box = BoundingBox3D.for_cube(10)              # 10x10x10 at origin
box = BoundingBox3D.for_cube(10, center=True) # Centered on origin
box = BoundingBox3D.for_cylinder(h=20, r=5)   # Cylinder bounds
box = BoundingBox3D.for_sphere(r=10)          # Sphere bounds

# Custom bounds
box = BoundingBox3D(
    min_point=Vector3D(x=0, y=0, z=0),
    max_point=Vector3D(x=10, y=20, z=30)
)

# Properties
print(box.width)        # 10 (X dimension)
print(box.height)       # 20 (Y dimension)
print(box.depth)        # 30 (Z dimension)
print(box.size)         # Vector3D(x=10, y=20, z=30)
print(box.center)       # Vector3D(x=5, y=10, z=15)
print(box.volume)       # 6000
print(box.surface_area) # 2200

# Operations
box.contains_point(Vector3D(x=5, y=5, z=5))  # True
box.intersects(other_box)                     # True/False
expanded = box.expand(margin=2)               # Grow by 2 on all sides
combined = box.union(other_box)               # Smallest containing both
corners = box.corners()                       # List of 8 corner points
```

### BoundingBox2D

2D bounding box for XY plane operations.

```python
from apothecary.models import BoundingBox2D, Vector2D

box = BoundingBox2D(
    min_point=Vector2D(x=0, y=0),
    max_point=Vector2D(x=10, y=20)
)

print(box.width)   # 10
print(box.height)  # 20
print(box.area)    # 200
```

## Colors

### Color

RGBA color with multiple input/output formats.

```python
from apothecary.models import Color, RED, BLUE

# Creation
c = Color(r=1, g=0.5, b=0)              # Direct RGBA (0-1 range)
c = Color.from_rgb(255, 128, 0)         # From 0-255 range
c = Color.from_hex("#FF8000")           # From hex string
c = Color.from_hex("#F80")              # Short hex
c = Color.from_name("orange")           # Named color

# Output
print(c.to_hex())         # "#ff8000"
print(c.to_openscad())    # "[1, 0.5, 0]"
print(c.to_rgb_tuple())   # (1.0, 0.5, 0.0)

# Operations
transparent = c.with_alpha(0.5)
blended = RED.blend(BLUE, 0.5)  # Purple
```

### Named Colors

Common colors are available as constants:

```python
from apothecary.models import (
    BLACK, WHITE, GRAY,
    RED, GREEN, BLUE,
    YELLOW, CYAN, MAGENTA,
    ORANGE,
)
```

Full list in `NAMED_COLORS` dict includes: silver, pink, purple, brown, lime, navy, teal, olive, maroon, gold, coral, salmon, crimson, indigo, violet, turquoise, beige, ivory, khaki.

## 2D Shapes

### Polygon2D

Polygon defined by vertices.

```python
from apothecary.models import Polygon2D

# Regular polygons
hexagon = Polygon2D.regular(n=6, radius=10)
triangle = Polygon2D.regular(n=3, radius=5)

# Rectangle
rect = Polygon2D.rectangle(width=20, height=10)
rect_centered = Polygon2D.rectangle(20, 10, center=True)

# Star
star = Polygon2D.star(points=5, outer_radius=20, inner_radius=10)

# Properties
print(hexagon.vertex_count)  # 6
print(hexagon.area)          # ~259.8
print(hexagon.centroid)      # Vector2D near origin

# OpenSCAD output
print(hexagon.to_openscad())  # polygon([[...], ...]);
```

### Circle2D

Circle for 2D operations.

```python
from apothecary.models import Circle2D

c = Circle2D(radius=10)
print(c.diameter)       # 20
print(c.circumference)  # ~62.8
print(c.area)           # ~314.1

# Convert to polygon
poly = c.to_polygon(segments=32)

# Point on circle
point = c.point_at_angle(45)  # 45 degrees from center
```

## Units

### Length Conversion

```python
from apothecary.models import Length, LengthUnit, convert_length

# Direct conversion
mm = convert_length(1, LengthUnit.INCH, LengthUnit.MILLIMETER)  # 25.4

# Length class
l = Length.inch(1)
print(l.to_mm())      # 25.4
print(l.to(LengthUnit.CENTIMETER))  # Length(value=2.54, unit=cm)

# Arithmetic
a = Length.mm(10)
b = Length.mm(5)
print(a + b)  # Length(value=15, unit=mm)
print(a * 2)  # Length(value=20, unit=mm)
```

### Hardware Sizes

Common hardware dimensions in mm:

```python
from apothecary.models import HardwareSizes

# Metric screws
HardwareSizes.M3           # 3.0
HardwareSizes.M3_CLEARANCE # 3.2 (close fit)

# Material thicknesses
HardwareSizes.ACRYLIC_3MM  # 3.0
HardwareSizes.PLYWOOD_6MM  # 6.0

# 3D printing
HardwareSizes.NOZZLE_0_4   # 0.4
HardwareSizes.LAYER_0_2    # 0.2
HardwareSizes.FDM_NORMAL   # 0.2 (tolerance)
```

### Print Settings

```python
from apothecary.models import PrintSettings

ps = PrintSettings(
    nozzle_diameter=0.4,
    layer_height=0.2,
    wall_thickness=1.2,
    tolerance=0.2
)

# Calculated values
print(ps.min_wall)  # 0.4 (minimum printable wall)
print(ps.min_hole)  # 0.8 (minimum printable hole)

# Hole sizing
print(ps.clearance_hole(3.0))  # 3.4 (M3 clearance)
print(ps.press_fit_hole(3.0))  # 2.8 (M3 press fit)
```

## Integration with Parts

Parts can use these models for accurate geometry calculation:

```python
from apothecary.projects.parts.base import BasePart
from apothecary.models import BoundingBox3D, Vector3D, Color

class MyPart(BasePart):
    def get_bounds(self, params=None) -> BoundingBox3D:
        w = params.get("width", 10) if params else 10
        return BoundingBox3D(
            min_point=Vector3D(x=0, y=0, z=0),
            max_point=Vector3D(x=w, y=w, z=w)
        )

part = MyPart(
    name="my_part",
    source_file=...,
    preview_color=Color.from_hex("#3366CC"),
)

# Use geometry info
bounds = part.get_bounds({"width": 20})
print(bounds.center)  # Vector3D(x=10, y=10, z=10)
print(part.to_geometry_dict())  # For API/viewer
```

The API exposes this at `/parts/{name}`:

```json
{
  "geometry": {
    "bounds": {
      "min": [0, 0, 0],
      "max": [20, 20, 20],
      "size": [20, 20, 20],
      "center": [10, 10, 10]
    },
    "color": "[0.2, 0.4, 0.8]",
    "color_hex": "#3366cc"
  }
}
```
