from __future__ import annotations

from pathlib import Path

from .base import BasePart
from .skeleton import ROOT


def create(metadata_root: Path) -> BasePart:
    scad = metadata_root / "parts" / "star_cookiecutter" / "star_cookiecutter.scad"
    return BasePart(
        name="star_cookiecutter",
        source_file=scad,
        description="Star cookie cutter",
        category="cookie-cutter",
        tags=["cookie", "star"],
        readme_path=metadata_root / "parts" / "README.md",
    )


DEFAULT = create(ROOT)
