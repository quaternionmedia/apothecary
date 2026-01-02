from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from pydantic import BaseModel, Field

from apothecary.models import BoundingBox3D, Color, Vector3D

from .base import BasePart
from .skeleton import ROOT


class Params(BaseModel):
    width: float = Field(40, gt=0)
    depth: float = Field(40, gt=0)
    height: float = Field(20, gt=0)


class CouchBlockPart(BasePart):
    """Couch block with calculated bounds."""

    def get_bounds(self, params: Optional[Dict] = None) -> BoundingBox3D:
        """Calculate bounds from parameters."""
        if params:
            w = params.get("width", 40)
            d = params.get("depth", 40)
            h = params.get("height", 20)
        elif self.params_model:
            defaults = self.params_model()
            w, d, h = defaults.width, defaults.depth, defaults.height
        else:
            w, d, h = 40, 40, 20

        return BoundingBox3D(min_point=Vector3D(x=0, y=0, z=0), max_point=Vector3D(x=w, y=d, z=h))


def create(metadata_root: Path) -> CouchBlockPart:
    scad = metadata_root / "parts" / "couch_block" / "couch_block.scad"
    return CouchBlockPart(
        name="couch_block",
        source_file=scad,
        description="Couch block spacer",
        params_model=Params,
        category="furniture",
        tags=["couch", "spacer", "block"],
        readme_path=metadata_root / "parts" / "README.md",
        preview_color=Color.from_hex("#8B4513"),  # Brown
    )


DEFAULT = create(ROOT)
