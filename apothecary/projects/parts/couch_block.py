from __future__ import annotations

from pathlib import Path

from apothecary.models import BoundingBox3D, Color, Vector3D

from .base import BasePart
from .skeleton import ROOT


def create(metadata_root: Path) -> BasePart:
    scad = metadata_root / "parts" / "couch_block" / "couch_block.scad"
    return BasePart(
        name="couch_block",
        source_file=scad,
        description="Couch block spacer",
        category="furniture",
        tags=["couch", "spacer", "block"],
        readme_path=metadata_root / "parts" / "README.md",
        preview_color=Color.from_hex("#8B4513"),  # Brown
        # Measured from the render: 6 x 4 x 2 in.
        default_bounds=BoundingBox3D(
            min_point=Vector3D(x=-76.2, y=0, z=0), max_point=Vector3D(x=76.2, y=101.6, z=50.8)
        ),
    )


DEFAULT = create(ROOT)
