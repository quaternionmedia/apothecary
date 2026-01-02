from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from .base import BasePart
from .skeleton import ROOT


class Params(BaseModel):
    diameter: float = Field(10.0, gt=0)
    height: float = Field(5.0, gt=0)


def create(metadata_root: Path) -> BasePart:
    scad = metadata_root / "parts" / "contranot" / "contranot.scad"
    return BasePart(
        name="contranot",
        source_file=scad,
        description="Contra-notation accessory",
        params_model=Params,
        category="misc",
        tags=["contra", "notation"],
        readme_path=metadata_root / "parts" / "README.md",
    )


DEFAULT = create(ROOT)
