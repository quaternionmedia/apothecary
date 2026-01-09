from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from pydantic import BaseModel, Field

from apothecary.models import BoundingBox3D, Color, Vector3D

from .base import BasePart
from .skeleton import ROOT


class Params(BaseModel):
    length: float = Field(100.0, gt=0)
    slot_width: float = Field(6.0, gt=0)
    slot_depth: float = Field(4.0, gt=0)


class VSlotPart(BasePart):
    """V-Slot rail with calculated bounds."""

    def get_bounds(self, params: Optional[Dict] = None) -> BoundingBox3D:
        """Calculate bounds from parameters (20x20mm extrusion profile)."""
        if params:
            length = params.get("length", 100)
        elif self.params_model:
            defaults = self.params_model()
            length = defaults.length
        else:
            length = 100

        # 20x20mm profile extruded along Z
        return BoundingBox3D(
            min_point=Vector3D(x=-10, y=-10, z=0), max_point=Vector3D(x=10, y=10, z=length)
        )


def create(metadata_root: Path) -> VSlotPart:
    scad = metadata_root / "parts" / "V-Slot" / "V-Slot.scad"
    return VSlotPart(
        name="v_slot",
        source_file=scad,
        description="V-Slot rail segment",
        params_model=Params,
        category="hardware",
        tags=["v-slot", "rail"],
        readme_path=metadata_root / "parts" / "README.md",
        preview_color=Color.from_hex("#C0C0C0"),  # Silver
    )


DEFAULT = create(ROOT)
