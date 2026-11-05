"""The router coupon: a plate with a pocket and a column of holes, the first part
cut on the garage's router. Its SCAD draws the plate the cuts leave; this wrapper
says the cuts that make it from its stock (``cuts``), which the router's toolpath
is written from (``apothecary.cam``, ``docs/cam.md``, walkthrough 20).
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Mapping, Optional

from pydantic import BaseModel, Field

from apothecary.models import BoundingBox3D, Color, Vector3D

from .base import BasePart
from .skeleton import ROOT

MM = {"unit": "mm"}

# Where the pocket and the holes stand on the plate, as the SCAD places them.
POCKET_IN_FROM_LEFT = 20.0
HOLES_IN_FROM_RIGHT = 20.0


class Params(BaseModel):
    """The coupon's sizes, each the SCAD's variable of the same name."""

    plate_x: float = Field(
        120.0, ge=40, le=400, description="The plate's width", json_schema_extra=MM
    )
    plate_y: float = Field(
        80.0, ge=40, le=600, description="The plate's depth", json_schema_extra=MM
    )
    thickness: float = Field(
        10.0, ge=3, le=40, description="The stock's thickness", json_schema_extra=MM
    )
    pocket_w: float = Field(
        40.0, ge=6, le=200, description="The pocket's width", json_schema_extra=MM
    )
    pocket_h: float = Field(
        30.0, ge=6, le=200, description="The pocket's depth, in Y", json_schema_extra=MM
    )
    pocket_depth: float = Field(
        4.0, ge=1, le=20, description="How deep the pocket goes", json_schema_extra=MM
    )
    hole_diameter: float = Field(
        3.0, ge=1, le=30, description="Each hole's diameter", json_schema_extra=MM
    )
    holes: int = Field(2, ge=0, le=6, description="Holes in the column")
    stock_margin: float = Field(
        10.0, ge=0, le=50, description="Stock beyond the plate on every side", json_schema_extra=MM
    )


class RouterCouponPart(BasePart):
    """A plate cut from a sheet: the pocket, the holes, then the outline."""

    def get_bounds(self, params: Optional[Dict] = None) -> BoundingBox3D:
        p = Params(**(params or {}))
        return BoundingBox3D(
            min_point=Vector3D(x=0.0, y=0.0, z=0.0),
            max_point=Vector3D(x=p.plate_x, y=p.plate_y, z=p.thickness),
        )

    def cuts(self, params: Optional[Mapping[str, object]] = None):
        """The stock is the plate plus its margin on every side, the work zero at the
        stock's front-left top corner; the pocket is cleared first, the holes bored
        through, and the outline cut around last, through the stock."""
        from apothecary.cam.models import Cuts, Hole, Outline, Pocket, Stock

        p = Params(**(params or {}))
        m = p.stock_margin
        through = p.thickness + 0.5
        operations = [
            Pocket(
                x=m + POCKET_IN_FROM_LEFT,
                y=m + (p.plate_y - p.pocket_h) / 2,
                w=p.pocket_w,
                h=p.pocket_h,
                depth=p.pocket_depth,
            )
        ]
        for i in range(p.holes):
            operations.append(
                Hole(
                    x=m + p.plate_x - HOLES_IN_FROM_RIGHT,
                    y=round(m + p.plate_y * (i + 1) / (p.holes + 1), 3),
                    diameter=p.hole_diameter,
                    depth=through,
                )
            )
        operations.append(Outline(x=m, y=m, w=p.plate_x, h=p.plate_y, depth=through))
        return Cuts(
            stock=Stock(x=p.plate_x + 2 * m, y=p.plate_y + 2 * m, thickness=p.thickness),
            operations=operations,
        )


def create(root: Path) -> BasePart:
    return RouterCouponPart(
        name="router_coupon",
        source_file=root / "parts" / "router_coupon" / "router_coupon.scad",
        description="A plate with a pocket and holes, cut on the router from a sheet",
        params_model=Params,
        category="coupon",
        tags=["router", "cnc", "coupon", "test", "demo"],
        readme_path=root / "parts" / "router_coupon" / "README.md",
        preview_color=Color.from_hex("#c9a66b"),
    )


DEFAULT = create(ROOT)
