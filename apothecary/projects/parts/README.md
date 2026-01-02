# apothecary.projects.parts
Thin Python wrappers for parts under `parts/`.

A wrapper exposes metadata and optional params for a single `.scad` file.

Minimal pattern:
```python
from pydantic import BaseModel, Field
from pathlib import Path
from .base import BasePart
from .skeleton import ROOT

class Params(BaseModel):
    foo: int = Field(1, ge=0)

def create(root: Path) -> BasePart:
    return BasePart(
        name="my_part",
        source_file=root / "parts" / "my-part.scad",
        params_model=Params,
        category="misc",
        tags=["demo"],
        readme_path=root / "parts" / "README.md",
    )

DEFAULT = create(ROOT)
```
