"""A one-layer square: what a printer's first layer is read from, for its first-layer
offset (``apothecary/slicer/first_layer_offset.py``).

The square is one first layer thick, and declares the first layer as ``bed_shims`` prints
it: the bed probed first, no brim and no skirt. So what it shows is the layer a shim's
is, and an offset found on it is the one a shim is printed with.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from pydantic import BaseModel, Field

from apothecary.models import BoundingBox3D, Color, PrintSettings, Vector3D

from .base import BasePart
from .skeleton import ROOT

MM = {"unit": "mm"}
FIRST_LAYER = 0.2  # the printer profile's first layer, and the SCAD's `height`


class Params(BaseModel):
    """The square's side, the SCAD's variable of the same name."""

    size: float = Field(50.0, ge=20, le=150, description="The square's side", json_schema_extra=MM)


class FirstLayerSquarePart(BasePart):
    """One square, a first layer thick."""

    def get_bounds(self, params: Optional[Dict] = None) -> BoundingBox3D:
        size = Params(**(params or {})).size
        return BoundingBox3D(
            min_point=Vector3D(x=0.0, y=0.0, z=0.0),
            max_point=Vector3D(x=size, y=size, z=FIRST_LAYER),
        )


def create(root: Path) -> BasePart:
    return FirstLayerSquarePart(
        name="first_layer_square",
        source_file=root / "parts" / "first_layer_square" / "first_layer_square.scad",
        description="A square one first layer thick, printed with the bed probed first: "
        "what a printer's first-layer offset is read from",
        params_model=Params,
        category="calibration",
        tags=["printer", "first layer", "calibration"],
        readme_path=root / "parts" / "first_layer_square" / "README.md",
        preview_color=Color.from_hex("#5b8def"),
        # The first layer as bed_shims prints it: probed first, no brim, no skirt.
        print_settings=PrintSettings(
            nozzle_diameter=0.4,
            layer_height=FIRST_LAYER,
            brim_width=0.0,
            skirt_loops=0,
            levelling="probe-each-print",
        ),
    )


DEFAULT = create(ROOT)
