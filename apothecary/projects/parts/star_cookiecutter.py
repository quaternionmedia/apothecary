from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from .base import BasePart
from .skeleton import ROOT


class Params(BaseModel):
    outer_radius: float = Field(25.0, gt=0)
    thickness: float = Field(1.2, gt=0)


def create(metadata_root: Path) -> BasePart:
    scad = metadata_root / "parts" / "star-cookiecutter" / "star-cookiecutter.scad"
    return BasePart(
        name="star_cookiecutter",
        source_file=scad,
        description="Star cookie cutter",
        params_model=Params,
        category="cookie-cutter",
        tags=["cookie", "star"],
        readme_path=metadata_root / "parts" / "README.md",
    )


DEFAULT = create(ROOT)
