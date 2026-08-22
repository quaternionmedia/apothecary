from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from .base import BasePart
from .skeleton import ROOT


class Params(BaseModel):
    blade_width: float = Field(10.0, gt=0)
    mount_thickness: float = Field(3.0, gt=0)


def create(metadata_root: Path) -> BasePart:
    scad = metadata_root / "parts" / "matboard_cutter_mount" / "matboard_cutter_mount.scad"
    return BasePart(
        name="matboard_cutter_mount",
        source_file=scad,
        description="Matboard cutter mount",
        params_model=Params,
        category="tooling",
        tags=["matboard", "cutter", "mount"],
        readme_path=metadata_root / "parts" / "README.md",
    )


DEFAULT = create(ROOT)
