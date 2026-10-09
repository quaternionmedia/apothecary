from __future__ import annotations

from pathlib import Path

from .base import BasePart
from .skeleton import ROOT


def create(metadata_root: Path) -> BasePart:
    scad = metadata_root / "parts" / "matboard_cutter_mount" / "matboard_cutter_mount.scad"
    return BasePart(
        name="matboard_cutter_mount",
        source_file=scad,
        description="Matboard cutter mount",
        category="tooling",
        tags=["matboard", "cutter", "mount"],
        readme_path=metadata_root / "parts" / "README.md",
    )


DEFAULT = create(ROOT)
