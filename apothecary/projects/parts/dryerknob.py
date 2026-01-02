from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from pydantic import BaseModel, Field

from apothecary.models import BoundingBox3D, Color

from .base import BasePart
from .skeleton import ROOT


class Params(BaseModel):
    shaft_diameter: float = Field(6.0, gt=0)
    knob_diameter: float = Field(30.0, gt=0)
    height: float = Field(15.0, gt=0)


class DryerKnobPart(BasePart):
    """Dryer knob with calculated cylindrical bounds."""

    def get_bounds(self, params: Optional[Dict] = None) -> BoundingBox3D:
        """Calculate bounds from parameters (cylindrical shape)."""
        if params:
            d = params.get("knob_diameter", 30)
            h = params.get("height", 15)
        elif self.params_model:
            defaults = self.params_model()
            d, h = defaults.knob_diameter, defaults.height
        else:
            d, h = 30, 15

        r = d / 2
        return BoundingBox3D.for_cylinder(h=h, r=r, center=False)


def create(metadata_root: Path) -> DryerKnobPart:
    scad = metadata_root / "parts" / "dryerknob" / "dryerknob.scad"
    return DryerKnobPart(
        name="dryerknob",
        source_file=scad,
        description="Dryer knob replacement",
        params_model=Params,
        category="appliance",
        tags=["knob", "dryer", "replacement"],
        readme_path=metadata_root / "parts" / "README.md",
        preview_color=Color.from_hex("#FFFFFF"),  # White
    )


DEFAULT = create(ROOT)
