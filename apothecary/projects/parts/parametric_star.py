from __future__ import annotations

from pathlib import Path

from apothecary.models import BoundingBox3D, Color, Vector3D

from .base import BasePart
from .skeleton import ROOT


def create(metadata_root: Path) -> BasePart:
    scad = metadata_root / "parts" / "parametric_star" / "parametric_star.scad"
    return BasePart(
        name="parametric_star",
        source_file=scad,
        description="Parametric star cookie cutter",
        category="cookie-cutter",
        tags=["star", "parametric", "cookie"],
        readme_path=metadata_root / "parts" / "README.md",
        preview_color=Color.from_hex("#FFD700"),  # Gold
        # Measured from the render of the SCAD's own call: 5 points, re=15, h=3.
        default_bounds=BoundingBox3D(
            min_point=Vector3D(x=-12.135, y=-14.266, z=0),
            max_point=Vector3D(x=15, y=14.266, z=3),
        ),
    )


# Default instance using repository root
DEFAULT = create(ROOT)
