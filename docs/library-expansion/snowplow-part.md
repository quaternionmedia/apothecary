# Snowplow Part – Technical Specification

This document provides a full technical specification for the modular, dockable RC car snowplow part, following the Apothecary library standards.

## 1. Overview

- **Name**: Snowplow Blade Assembly
- **Description**: Parametric, bolt-on snowplow for RC car chassis. Modular blade, mount plate, and interface points for easy assembly and upgrades.

## 2. Parameters

| Parameter         | Type   | Default | Units | Description                       |
|-------------------|--------|---------|-------|-----------------------------------|
| blade_width       | float  | 120.0   | mm    | Total width of the plow blade     |
| blade_height      | float  | 45.0    | mm    | Height of the plow blade surface  |
| blade_thickness   | float  | 3.0     | mm    | Material thickness                |
| mount_width       | float  | 40.0    | mm    | Width of the mount plate          |
| mount_height      | float  | 12.0    | mm    | Height of the mount plate         |
| mount_thickness   | float  | 4.0     | mm    | Thickness of the mount plate      |
| bolt_diameter     | float  | 3.0     | mm    | Diameter of mounting holes        |
| bolt_spacing      | float  | 24.0    | mm    | Distance between bolt holes       |
| blade_angle       | float  | 10.0    | deg   | Forward rake angle of blade       |

## 3. Geometry

- **Blade**: Rotated rectangular plate (Cube) for snowplow surface
- **Mount Plate**: Rectangular plate (Cube) for chassis attachment
- **Bolt Holes**: Two cylindrical holes (Cylinder) in mount plate

## 4. Interfaces (YAML)

```yaml
interfaces:
  - name: mount_left
    type: bolt_hole
    diameter: 3.0
    position: { x: -12, y: 0, z: 0 }
    normal: { x: 0, y: 1, z: 0 }
  - name: mount_right
    type: bolt_hole
    diameter: 3.0
    position: { x: 12, y: 0, z: 0 }
    normal: { x: 0, y: 1, z: 0 }
  - name: blade_edge
    type: slot
    width: 2.0
    length: 100.0
    position: { x: 0, y: 0, z: -22 }
    normal: { x: 0, y: 0, z: -1 }
```

## 5. Assembly

- **Blade** is rotated by `blade_angle` and attached to the mount plate.
- **Mount Plate** is docked to the RC car chassis via `mount_left` and `mount_right` interfaces.
- **Bolt Holes** align with chassis mounting points.

## 6. Example Python Scene

```python
from apothecary import Scene, Cube, Cylinder, Translate, Rotate, Union, Difference, Vector3D

# Parameters
BLADE_WIDTH = 120
BLADE_HEIGHT = 45
BLADE_THICKNESS = 3
MOUNT_WIDTH = 40
MOUNT_HEIGHT = 12
MOUNT_THICKNESS = 4
BOLT_DIAMETER = 3
BOLT_SPACING = 24

blade = Rotate(
    a=10, v=Vector3D(x=1, y=0, z=0),
    children=[Cube(size=Vector3D(x=BLADE_WIDTH, y=BLADE_THICKNESS, z=BLADE_HEIGHT), center=True)]
)

mount_plate = Cube(size=Vector3D(x=MOUNT_WIDTH, y=MOUNT_THICKNESS, z=MOUNT_HEIGHT), center=True)

bolt_holes = Union(children=[
    Translate(v=Vector3D(x=-BOLT_SPACING/2, y=0, z=0), children=[Cylinder(d=BOLT_DIAMETER, h=20, center=True)]),
    Translate(v=Vector3D(x=BOLT_SPACING/2, y=0, z=0), children=[Cylinder(d=BOLT_DIAMETER, h=20, center=True)])
])

mount_with_holes = Difference(children=[mount_plate, bolt_holes])

assembly = Union(children=[
    Translate(v=Vector3D(x=0, y=0, z=BLADE_HEIGHT/2), children=[blade]),
    Translate(v=Vector3D(x=0, y=-BLADE_THICKNESS, z=MOUNT_HEIGHT/2), children=[mount_with_holes])
])

scene = Scene(name="rc_car_snowplow", objects=[assembly])
print(scene.render())
```

## 7. Metadata

- **Category**: rc/snowplow
- **Tags**: snowplow, rc, modular, bolt-on
- **Author**: Quaternion Media
- **Version**: 1.0

## 8. Testing

- Validate interface schema compliance
- Render in OpenSCAD and web viewer
- Check assembly fit with sample RC chassis

## 9. References

- [modular-interfaces.md](modular-interfaces.md)
- [interface-schema.md](interface-schema.md)
- [ui-architecture.md](ui-architecture.md)

---

For questions or proposals, see the [README](README.md) or open an issue in the repository.
