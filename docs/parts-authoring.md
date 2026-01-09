# Parts authoring guide

This document explains how to add new printable parts to the Apothecary toolkit using thin Python wrappers.

## Overview

Each source `.scad` under the top-level `parts/` directory can have a corresponding wrapper module under `apothecary/projects/parts/` that exposes:

- metadata (name, category, tags, description)
- an optional `Params` Pydantic model describing configurable parameters
- a `BasePart` instance with paths wired up
- a module-level `DEFAULT` instance used by the CLI

Wrappers are discovered by `scan_projects` and surfaced via CLI commands:

- `apothecary parts list`
- `apothecary parts info NAME`
- `apothecary parts render NAME` (writes an include stub or a custom template)

## Naming conventions

- File names in `parts/` are typically hyphenated (e.g. `my-part.scad`).
- Wrapper module names live under `apothecary/projects/parts/` and are imported as Python modules.
- The CLI maps a part *name* to a module name by:
  - lowercasing
  - replacing `-`, spaces, and `.` with `_`

Example: `"My Part.v1"` → module `apothecary.projects.parts.my_part_v1`.

If no wrapper is found, `apothecary parts info`/`render` will error with a message like:

> No wrapper module found for part 'NAME'. Tried module 'apothecary.projects.parts.name'. Run 'apothecary parts list' to see available parts.

## Wrapper template

A minimal wrapper looks like this:

```python
from pathlib import Path
from typing import Dict, Optional

from pydantic import BaseModel, Field

from .base import BasePart
from .skeleton import ROOT
from apothecary.models import BoundingBox3D, Vector3D, Color


class Params(BaseModel):
    width: float = Field(10.0, gt=0)
    height: float = Field(5.0, gt=0)


class MyPart(BasePart):
    """Custom part with calculated bounds."""
    
    def get_bounds(self, params: Optional[Dict] = None) -> BoundingBox3D:
        if params:
            w = params.get("width", 10)
            h = params.get("height", 5)
        elif self.params_model:
            defaults = self.params_model()
            w, h = defaults.width, defaults.height
        else:
            w, h = 10, 5
        
        return BoundingBox3D(
            min_point=Vector3D(x=0, y=0, z=0),
            max_point=Vector3D(x=w, y=w, z=h)
        )


def create(root: Path) -> MyPart:
    return MyPart(
        name="my_part",
        source_file=root / "parts" / "my-part" / "my-part.scad",
        params_model=Params,
        category="misc",
        tags=["demo"],
        readme_path=root / "parts" / "README.md",
        preview_color=Color.from_hex("#3366CC"),  # Blue
    )


DEFAULT = create(ROOT)
```

Key points:

- `ROOT` is the repository root as detected by the skeleton module.
- `name` should match the part's logical name; it is what appears in `parts list`.
- `source_file` should point to the actual `.scad` file (in `parts/<name>/<name>.scad`).
- `params_model` is optional; pass `None` if the part is not parameterized.
- `readme_path` is optional but recommended; it is used in structure/inventory reporting.
- `preview_color` sets the color used in the 3D viewer.
- Override `get_bounds()` to calculate accurate bounding boxes from parameters.

## Geometry models

Parts can use the geometry models from `apothecary.models` for:

| Model | Purpose |
|-------|--------|
| `Vector3D` | 3D positions and directions |
| `BoundingBox3D` | Spatial extents, center, size |
| `Color` | Preview colors (hex, RGB, named) |
| `PrintSettings` | FDM tolerances, layer heights |

Example bounds calculation:

```python
# For a cylinder
from apothecary.models import BoundingBox3D
bounds = BoundingBox3D.for_cylinder(h=20, r=5, center=False)

# For a cube
bounds = BoundingBox3D.for_cube(size=10, center=True)

# Custom bounds
bounds = BoundingBox3D(
    min_point=Vector3D(x=-5, y=-5, z=0),
    max_point=Vector3D(x=5, y=5, z=10)
)
```

The API exposes geometry metadata at `/parts/{name}` including bounds and color.

## Testing your part

1. Run `apothecary inventory projects` and confirm your part appears.
2. Run `apothecary parts list` and check that the wrapper name and module are shown.
3. Run `apothecary parts info my_part` and verify metadata.
4. Run `apothecary parts render my_part -o include.scad` and inspect the generated SCAD.

You can add regression tests under `tests/test_parts_wrappers.py` to assert that your wrapper's metadata and paths are correct.
