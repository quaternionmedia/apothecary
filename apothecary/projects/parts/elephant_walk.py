"""
Elephant Walk - All parts laid out side by side.

This is a special "meta-part" that imports and displays all other parts
in a grid layout, useful for previewing the entire parts library at once.
"""

from __future__ import annotations

from pathlib import Path

from .base import BasePart
from .skeleton import ROOT


def create(metadata_root: Path) -> BasePart:
    """Create the elephant walk part instance."""
    scad = metadata_root / "parts" / "elephant_walk.scad"
    return BasePart(
        name="elephant_walk",
        source_file=scad,
        description="All parts laid out side by side for preview",
        category="utility",
        tags=["preview", "all", "gallery", "utility"],
    )


DEFAULT = create(ROOT)
