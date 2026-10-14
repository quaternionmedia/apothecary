# Geometry models

<!-- Each example block ends in a blank line; without it doctest reads the closing fence as output. -->

`apothecary.models` holds the few value types that parts, assemblies and the
photo path share: vectors, bounding boxes, colour, print settings, hardware
sizes and black boxes. The examples on this page run as doctests
(`tests/test_models.py` runs them), so they say what the code does.

```pycon
>>> from apothecary.models import (
...     BoundingBox3D, Color, GRAY, HardwareSizes, PrintSettings, Vector2D, Vector3D,
... )

```

## Units

Every length is in millimetres, and nothing in `apothecary.models` converts.
OpenSCAD and STL carry no units. A mesh drawn in other units is scaled once, on
the way in: `apothecary parts import --units in` (see
[geometry-from-elsewhere.md](geometry-from-elsewhere.md)).

## Vectors

`Vector3D` is a position, a size or an offset. It adds, subtracts, negates and
scales, and `to_list()` is the form OpenSCAD takes.

```pycon
>>> v = Vector3D(x=1, y=2, z=3)
>>> v.to_list()
[1.0, 2.0, 3.0]
>>> (v + Vector3D(x=1, y=1, z=1)).to_list()
[2.0, 3.0, 4.0]
>>> (v * 2 - v).to_list(), (-v).to_list()
([1.0, 2.0, 3.0], [-1.0, -2.0, -3.0])

```

`Vector2D` is the same in a plane; the photo path uses it for positions in a
picture.

```pycon
>>> (Vector2D(x=3, y=4) - Vector2D(x=1, y=1)).to_list()
[2.0, 3.0]

```

## Bounding boxes

`BoundingBox3D` is axis-aligned, from `min_point` to `max_point`. A part's
`get_bounds()` returns one, `apothecary parts verify` checks it against the
rendered STL, and `/parts/{name}` reports it under `geometry.bounds`.

The primitives' boxes follow OpenSCAD's placement: a cube starts at the origin
unless centred, and a cylinder stands on the XY plane centred on Z.

```pycon
>>> BoundingBox3D.for_cube(10).max_point.to_list()
[10.0, 10.0, 10.0]
>>> BoundingBox3D.for_cube(10, center=True).min_point.to_list()
[-5.0, -5.0, -5.0]
>>> can = BoundingBox3D.for_cylinder(h=20, r=5)
>>> can.min_point.to_list(), can.max_point.to_list()
([-5.0, -5.0, 0.0], [5.0, 5.0, 20.0])

```

`from_points` is the smallest box around a set of points; with none, it is the
empty box at the origin.

```pycon
>>> box = BoundingBox3D.from_points([Vector3D(x=10, y=0, z=30), Vector3D(x=0, y=20, z=0)])
>>> box.min_point.to_list(), box.max_point.to_list()
([0.0, 0.0, 0.0], [10.0, 20.0, 30.0])
>>> BoundingBox3D.from_points([]).volume
0.0

```

Width is X, height is Y and depth is Z. These, with `size`, `center`, `volume`
and `surface_area`, are computed fields, so they are part of the box's JSON.

```pycon
>>> box.width, box.height, box.depth
(10.0, 20.0, 30.0)
>>> box.size.to_list(), box.center.to_list()
([10.0, 20.0, 30.0], [5.0, 10.0, 15.0])
>>> box.volume, box.surface_area
(6000.0, 2200.0)
>>> sorted(box.model_dump())
['center', 'depth', 'height', 'max_point', 'min_point', 'size', 'surface_area', 'volume', 'width']

```

`intersects` counts touching as overlapping: two boxes that share a face
intersect. A layout that must leave a gap between two things checks
`not a.intersects(b)`, as `tests/test_garage_workbench.py` does for the
printer and the boards on the bench.

```pycon
>>> side_by_side = BoundingBox3D(
...     min_point=Vector3D(x=10, y=0, z=0), max_point=Vector3D(x=20, y=10, z=10)
... )
>>> BoundingBox3D.for_cube(10).intersects(side_by_side)
True
>>> BoundingBox3D.for_cube(9.9).intersects(side_by_side)
False

```

## Colour

`Color` holds red, green, blue and alpha from 0 to 1. A part's `preview_color`
is one; `GRAY` is the default.

```pycon
>>> blue = Color.from_hex("#3366CC")
>>> blue.to_openscad(), blue.to_hex()
('[0.2, 0.4, 0.8]', '#3366cc')
>>> Color.from_hex("#F80").to_hex()
'#ff8800'
>>> Color.from_rgb(0, 0, 0, a=128).to_openscad()
'[0.0, 0.0, 0.0, 0.5019607843137255]'
>>> GRAY.to_hex()
'#7f7f7f'

```

`to_hex` truncates rather than rounds, so a component of 0.5 is `7f`, not `80`.

## Print settings

`PrintSettings` is what a printer and its slicer settings do to a hole. The
defaults are a 0.4 mm nozzle, 0.2 mm layers, 1.2 mm walls and 0.2 mm of
tolerance.

```pycon
>>> ps = PrintSettings()
>>> ps.clearance_hole(3.0)
3.4
>>> ps.press_fit_hole(3.0)
2.8

```

A clearance hole is the nominal diameter plus the tolerance on each side; a
press-fit hole is the nominal minus one tolerance. `Feature.clearance_hole` in
`apothecary/hierarchy.py` sizes its cylinder this way; a site that prints
tighter passes its own `print_settings`:

```pycon
>>> PrintSettings(tolerance=HardwareSizes.FDM_TIGHT).clearance_hole(HardwareSizes.M3)
3.2

```

## Hardware sizes

`HardwareSizes` names common nominal sizes in mm: metric screws (`M2` to
`M10`), their close-fit clearance holes (`M3_CLEARANCE` and so on), sheet
thicknesses, nozzle and layer sizes, and FDM tolerances.

```pycon
>>> HardwareSizes.M3, HardwareSizes.M3_CLEARANCE, HardwareSizes.FDM_NORMAL
(3.0, 3.2, 0.2)

```

## Black boxes

`BlackBox`, `MountPoint`, `Keepout`, `BlackBoxProvider` and `StubProvider`
describe things apothecary places but does not author: a board, a connector, a
module. Their module docstring, `apothecary/models/blackbox.py`, says how a
provider is swapped; `apothecary/projects/parts/datum_core.py` derives a tray
from one.
