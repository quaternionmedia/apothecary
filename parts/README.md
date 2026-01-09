# parts/

Printable OpenSCAD sources. Each part has its own folder containing SCAD source and generated files.

## Structure

```
parts/
├── parametric_star/
│   ├── parametric_star.scad   # Source
│   └── parametric_star.stl    # Generated (via API or OpenSCAD)
├── couch_block/
│   ├── couch_block.scad
│   └── couch_block.stl
└── ...
```

## File Types

| Extension | Description |
|-----------|-------------|
| `.scad` | OpenSCAD source (required) |
| `.stl` | Generated mesh (auto-created via API) |
| `.jscad` | JSCAD module (generated on demand) |

## Adding a New Part

1. Create a folder: `parts/my-part/`
2. Add the SCAD file: `parts/my-part/my-part.scad`
3. Create wrapper: `apothecary/projects/parts/my_part.py`

Example wrapper:

```python
from pathlib import Path
from pydantic import BaseModel, Field
from .base import BasePart
from .skeleton import ROOT

class Params(BaseModel):
    size: float = Field(10.0, gt=0)

def create(root: Path) -> BasePart:
    return BasePart(
        name="my_part",
        source_file=root / "parts" / "my-part" / "my-part.scad",
        params_model=Params,
        category="demo",
        tags=["example"],
        description="My cool part",
    )

DEFAULT = create(ROOT)
```

## Naming Convention

- Folder name = part name (use hyphens: `my-part`)
- SCAD file = same as folder (`my-part.scad`)
- Wrapper module = underscored (`my_part.py`)

See [docs/parts-authoring.md](../docs/parts-authoring.md) for full guide.
