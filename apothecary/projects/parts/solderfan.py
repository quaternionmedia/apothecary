from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from apothecary.models import Vector3D

from .base import BasePart
from .skeleton import ROOT


class Params(BaseModel):
    fan_diameter: float = Field(40, gt=0)
    mount_hole_diameter: float = Field(3, gt=0)
    thickness: float = Field(3, gt=0)


def create(metadata_root: Path) -> BasePart:
    scad = metadata_root / "parts" / "solderfan" / "solderfan.scad"
    return BasePart(
        name="solderfan",
        source_file=scad,
        description="Soldering fan mount",
        params_model=Params,
        category="electronics",
        tags=["fan", "mount", "soldering"],
        readme_path=metadata_root / "parts" / "README.md",
        # Rotate to lay flat (fan opening facing up)
        display_rotation=Vector3D(x=90, y=0, z=0),
    )


DEFAULT = create(ROOT)
