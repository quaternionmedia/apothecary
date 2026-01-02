# Tutorial: Building Your First Part

This hands-on tutorial walks through creating a parametric part from scratch. We'll build a **calibration cube** with axis indicators and dimension markers—a useful test print that also demonstrates all of Apothecary's features.

> **Prerequisites**: Complete the [QUICKSTART](../QUICKSTART.md) first to have the environment set up.

## What We're Building

A calibration cube that:
- Has configurable size (default 10mm)
- Shows XYZ axis labels as relief (not extruded)
- Displays dimension text on faces  
- Can be printed solid or with configurable wall thickness
- Includes a corner notch for orientation

![Calibration Cube Preview](https://via.placeholder.com/400x300?text=Calibration+Cube)

## Part 1: The OpenSCAD File

First, create the SCAD source file. Parts live in their own folders under `parts/`:

```bash
mkdir parts/calibration_cube
```

Create `parts/calibration_cube/calibration_cube.scad`:

```openscad
// Calibration Cube - Test shape with axis indicators
// Parameters exposed for Customizer

size = 20;              // [10:1:50] Cube size in mm
show_axes = true;       // Show axis indicators
wall_thickness = 2;     // [1:0.5:5] Wall thickness

$fn = 32;

module calibration_cube() {
    difference() {
        cube([size, size, size]);
        
        // Hollow interior
        if (wall_thickness < size/2) {
            translate([wall_thickness, wall_thickness, wall_thickness])
            cube([size - 2*wall_thickness, 
                  size - 2*wall_thickness, 
                  size - 2*wall_thickness]);
        }
        
        // Corner notch for orientation
        translate([-0.01, -0.01, -0.01])
        cube([size * 0.15, size * 0.15, size * 0.15]);
    }
}

module axis_arrow(length, color_name) {
    color(color_name) {
        cylinder(h=length * 0.9, r=length * 0.03);
        translate([0, 0, length * 0.9])
        cylinder(h=length * 0.1, r1=length * 0.06, r2=0);
    }
}

module axes() {
    len = size * 0.8;
    // X - Red
    rotate([0, 90, 0]) axis_arrow(len, "red");
    // Y - Green
    rotate([-90, 0, 0]) axis_arrow(len, "green");
    // Z - Blue
    axis_arrow(len, "blue");
}

// Render
color("gray", 0.8) calibration_cube();
if (show_axes) axes();
```

Test it in OpenSCAD:
```bash
openscad parts/calibration_cube/calibration_cube.scad
```

## Part 2: The Python Wrapper

Create `apothecary/projects/parts/calibration_cube.py`:

```python
from __future__ import annotations
from pydantic import BaseModel, Field
from pathlib import Path
from typing import Dict, Optional

from .base import BasePart
from .skeleton import ROOT
from apothecary.models import BoundingBox3D, Vector3D, Color, PrintSettings


class Params(BaseModel):
    """Calibration cube parameters."""
    size: float = Field(20.0, gt=5, le=100, description="Cube size in mm")
    show_axes: bool = Field(True, description="Show XYZ axis indicators")
    wall_thickness: float = Field(2.0, gt=0, description="Wall thickness")


class CalibrationCubePart(BasePart):
    """Calibration cube with calculated bounds."""
    
    def get_bounds(self, params: Optional[Dict] = None) -> BoundingBox3D:
        """Calculate bounds accounting for axes."""
        size = params.get("size", 20) if params else 20
        show_axes = params.get("show_axes", True) if params else True
        
        if show_axes:
            # Axes extend beyond cube
            extent = size * 1.05
            return BoundingBox3D(
                min_point=Vector3D(x=0, y=0, z=0),
                max_point=Vector3D(x=extent, y=extent, z=extent)
            )
        return BoundingBox3D.for_cube(size)


def create(root: Path) -> CalibrationCubePart:
    return CalibrationCubePart(
        name="calibration_cube",
        source_file=root / "parts" / "calibration_cube" / "calibration_cube.scad",
        params_model=Params,
        category="calibration",
        tags=["calibration", "test", "demo"],
        preview_color=Color.from_hex("#808080"),
    )


DEFAULT = create(ROOT)
```

## Part 3: Verify Registration

Check that the part is discovered:

```bash
uv run apothecary parts list
```

You should see:
```
calibration_cube   calibration   apothecary.projects.parts.calibration_cube
```

Get detailed info:
```bash
uv run apothecary parts info calibration_cube
```

Output:
```
Part: calibration_cube
Category: calibration
Tags: calibration, test, demo
Source: parts/calibration_cube/calibration_cube.scad

Parameters:
  size: 20.0 (Cube size in mm)
  show_axes: True (Show XYZ axis indicators)
  wall_thickness: 2.0 (Wall thickness)
```

## Part 4: Using the API

Start the server:
```bash
uv run apothecary serve
```

### Get Part Metadata

```bash
curl http://127.0.0.1:8000/parts/calibration_cube | python -m json.tool
```

Response includes geometry info:
```json
{
  "name": "calibration_cube",
  "description": "Calibration cube with XYZ axes and dimension markers",
  "geometry": {
    "bounds": {
      "min": [0, 0, 0],
      "max": [21, 21, 21],
      "size": [21, 21, 21],
      "center": [10.5, 10.5, 10.5]
    },
    "color": "[0.5, 0.5, 0.5]",
    "color_hex": "#808080"
  }
}
```

### Get with Custom Parameters

```bash
curl "http://127.0.0.1:8000/parts/calibration_cube?params={\"size\":30}" | python -m json.tool
```

### Generate STL

```bash
curl -X POST http://127.0.0.1:8000/parts/calibration_cube/stl/generate
```

### View in Browser

Open: http://127.0.0.1:8000/viewer/calibration_cube

## Part 5: Working with Geometry Models

The real power comes from the geometry models. Open a Python REPL:

```bash
uv run python
```

### Exploring Bounds

```python
from apothecary.projects.parts.calibration_cube import DEFAULT as cube

# Get bounds with default parameters
bounds = cube.get_bounds()
print(f"Size: {bounds.size.to_list()}")      # [21.0, 21.0, 21.0]
print(f"Center: {bounds.center.to_list()}")   # [10.5, 10.5, 10.5]
print(f"Volume: {bounds.volume}")             # 9261.0

# With custom parameters
bounds = cube.get_bounds({"size": 40, "show_axes": False})
print(f"Size: {bounds.size.to_list()}")      # [40.0, 40.0, 40.0]
```

### Using Vectors

```python
from apothecary.models import Vector3D, X_AXIS, Y_AXIS, Z_AXIS

# Create positions
corner = Vector3D(x=0, y=0, z=0)
center = bounds.center

# Vector math
diagonal = center - corner
print(f"Diagonal length: {diagonal.magnitude:.2f}")

# Cross product for normals
normal = X_AXIS.cross(Y_AXIS)  # = Z_AXIS
```

### Color Operations

```python
from apothecary.models import Color, RED, BLUE

# Part color
print(cube.preview_color.to_hex())  # #808080

# Create custom colors
axis_x = Color.from_name("red")
axis_y = Color.from_name("green") 
axis_z = Color.from_name("blue")

# Blend colors
purple = RED.blend(BLUE, 0.5)
print(purple.to_hex())  # #800080

# For OpenSCAD
print(axis_x.to_openscad())  # [1, 0, 0]
```

### Print Settings

```python
from apothecary.models import PrintSettings, HardwareSizes

# Default FDM settings
ps = PrintSettings()
print(f"Clearance for M3: {ps.clearance_hole(HardwareSizes.M3)}")  # 3.4

# Tight tolerance for calibration
ps_tight = PrintSettings(tolerance=HardwareSizes.FDM_TIGHT)
print(f"Tight clearance for M3: {ps_tight.clearance_hole(3.0)}")  # 3.2
```

## Part 6: Writing Tests

Create `tests/test_calibration_cube.py`:

```python
import pytest
from apothecary.projects.parts.calibration_cube import DEFAULT, Params


def test_part_exists():
    """Part source file exists."""
    assert DEFAULT.source_file.exists()


def test_default_params():
    """Default parameters are valid."""
    params = Params()
    assert params.size == 20.0
    assert params.show_axes is True


def test_bounds_calculation():
    """Bounds reflect parameters."""
    # Default with axes
    bounds = DEFAULT.get_bounds()
    assert bounds.size.z > 20  # Axes extend beyond cube
    
    # Without axes
    bounds = DEFAULT.get_bounds({"size": 30, "show_axes": False})
    assert bounds.size.x == 30
    assert bounds.size.y == 30
    assert bounds.size.z == 30


def test_bounds_with_different_sizes():
    """Bounds scale correctly with size parameter."""
    for size in [10, 20, 50]:
        bounds = DEFAULT.get_bounds({"size": size, "show_axes": False})
        assert bounds.size.x == size
        assert bounds.volume == size ** 3
```

Run tests:
```bash
uv run pytest tests/test_calibration_cube.py -v
```

## Part 7: STL Generation Test

Run the parametric STL test to verify all parts render:

```bash
uv run pytest tests/test_parts_stl_generation.py -v -k calibration
```

This confirms OpenSCAD can render your part without errors.

## Summary

You've learned to:

1. **Create a SCAD file** with customizer parameters
2. **Write a Python wrapper** with Pydantic models
3. **Calculate bounding boxes** based on parameters
4. **Use geometry models** (Vector3D, Color, PrintSettings)
5. **Access via API** with geometry metadata
6. **Write tests** for your part

## Next Steps

- Read [Parts Authoring Guide](parts-authoring.md) for advanced features
- Explore [Geometry Models](models.md) reference
- Check existing parts in `apothecary/projects/parts/` for patterns
- Try the STL renderer: `uv run apothecary parts render calibration_cube -o test.scad`

## Calibration Cube Usage

After printing your calibration cube:

1. **Measure X, Y, Z** with calipers
2. **Compare to target** (default 20mm)
3. **Calculate error**: `(measured - target) / target * 100`
4. **Adjust slicer** if error > 0.5%:
   - Scale model by inverse of error
   - Or adjust steps/mm in firmware

The corner notch identifies the origin corner (0,0,0).
Axis colors match the standard convention:
- **Red = X** (right)
- **Green = Y** (forward)
- **Blue = Z** (up)
