from __future__ import annotations

from pathlib import Path

from apothecary.models import BoundingBox3D, Color, Vector3D

from .base import BasePart
from .skeleton import ROOT


def create(metadata_root: Path) -> BasePart:
    scad = metadata_root / "parts" / "dryerknob" / "dryerknob.scad"
    return BasePart(
        name="dryerknob",
        source_file=scad,
        description="Dryer knob replacement",
        category="appliance",
        tags=["knob", "dryer", "replacement"],
        readme_path=metadata_root / "parts" / "README.md",
        preview_color=Color.from_hex("#FFFFFF"),  # White
        # Measured from the render; the SCAD is a fixed d=33, h=20 cylinder.
        default_bounds=BoundingBox3D(
            min_point=Vector3D(x=-16.5, y=-16.5, z=0), max_point=Vector3D(x=16.5, y=16.5, z=20)
        ),
    )


DEFAULT = create(ROOT)
