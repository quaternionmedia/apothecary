from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from pydantic import BaseModel, Field

from apothecary.models import BoundingBox3D, Color, Vector3D

from .base import BasePart
from .skeleton import ROOT


class Params(BaseModel):
    points: int = Field(5, ge=3)
    inner_ratio: float = Field(0.4, gt=0, lt=1)
    outer_radius: float = Field(20, gt=0)
    thickness: float = Field(2.0, gt=0)


class ParametricStarPart(BasePart):
    """Parametric star with calculated bounds."""

    def get_bounds(self, params: Optional[Dict] = None) -> BoundingBox3D:
        """Calculate bounds from parameters."""
        if params:
            r = params.get("outer_radius", 20)
            h = params.get("thickness", 2.0)
        elif self.params_model:
            defaults = self.params_model()
            r, h = defaults.outer_radius, defaults.thickness
        else:
            r, h = 20, 2.0

        # Star is centered on origin in XY
        return BoundingBox3D(min_point=Vector3D(x=-r, y=-r, z=0), max_point=Vector3D(x=r, y=r, z=h))


def create(metadata_root: Path) -> ParametricStarPart:
    scad = metadata_root / "parts" / "parametric_star" / "parametric_star.scad"
    return ParametricStarPart(
        name="parametric_star",
        source_file=scad,
        description="Parametric star cookie cutter",
        params_model=Params,
        category="cookie-cutter",
        tags=["star", "parametric", "cookie"],
        readme_path=metadata_root / "parts" / "README.md",
        preview_color=Color.from_hex("#FFD700"),  # Gold
    )


# Default instance using repository root
DEFAULT = create(ROOT)
