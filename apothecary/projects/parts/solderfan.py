from __future__ import annotations

from pathlib import Path

from apothecary.models import Vector3D

from .base import BasePart
from .skeleton import ROOT


def create(metadata_root: Path) -> BasePart:
    scad = metadata_root / "parts" / "solderfan" / "solderfan.scad"
    return BasePart(
        name="solderfan",
        source_file=scad,
        description="Soldering fan mount",
        category="electronics",
        tags=["fan", "mount", "soldering"],
        readme_path=metadata_root / "parts" / "README.md",
        # Rotate to lay flat (fan opening facing up)
        display_rotation=Vector3D(x=90, y=0, z=0),
    )


DEFAULT = create(ROOT)
