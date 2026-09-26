from __future__ import annotations

from pathlib import Path

from .base import BasePart
from .skeleton import ROOT


def create(metadata_root: Path) -> BasePart:
    scad = metadata_root / "parts" / "contranot" / "contranot.scad"
    return BasePart(
        name="contranot",
        source_file=scad,
        description="Contra-notation accessory",
        category="misc",
        tags=["contra", "notation"],
        readme_path=metadata_root / "parts" / "README.md",
    )


DEFAULT = create(ROOT)
