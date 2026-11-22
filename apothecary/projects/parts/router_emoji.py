"""The router's calibration piece, a 😮: a round face cut around from outside, two
eyes and a mouth bored through it. Its SCAD draws the face the cuts leave; this
wrapper says the cuts that make it from its stock (``cuts``), each feature named,
so its toolpath's record says what a person measures of the piece: the face across,
an outside size; an eye and the mouth across, inside sizes. Measured with calipers
and kept under measured in its cabinet's Feedback window, they give the router's tool
allowance (``apothecary.cam.measured``, ``docs/cam.md``).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, Mapping, Optional, Tuple

from pydantic import BaseModel, Field, model_validator

from apothecary.models import BoundingBox3D, Color, Vector3D

from .base import BasePart
from .skeleton import ROOT

MM = {"unit": "mm"}

# Where the eyes and the mouth stand on the face, as shares of its radius from its
# centre, as the SCAD places them: each eye out and up, the mouth down.
EYE_OUT = 0.35
EYE_UP = 0.3
MOUTH_DOWN = 0.35
# Millimetres of face left between the holes, and between a hole and the edge.
WALL = 3.0


def eyes_at(radius: float) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """The left eye's centre and the right's, from the face's centre."""
    return (-EYE_OUT * radius, EYE_UP * radius), (EYE_OUT * radius, EYE_UP * radius)


def mouth_at(radius: float) -> Tuple[float, float]:
    """The mouth's centre, from the face's centre."""
    return (0.0, -MOUTH_DOWN * radius)


class Params(BaseModel):
    """The piece's sizes, each the SCAD's variable of the same name."""

    face_diameter: float = Field(
        60.0, ge=40, le=200, description="The face, across", json_schema_extra=MM
    )
    eye_diameter: float = Field(
        10.0,
        ge=8,
        le=40,
        description="Each eye, across: wider than the tool, so it is bored",
        json_schema_extra=MM,
    )
    mouth_diameter: float = Field(
        20.0, ge=8, le=80, description="The mouth, across", json_schema_extra=MM
    )
    thickness: float = Field(
        6.0, ge=3, le=40, description="The stock's thickness", json_schema_extra=MM
    )
    stock_margin: float = Field(
        10.0, ge=0, le=50, description="Stock beyond the face on every side", json_schema_extra=MM
    )

    @model_validator(mode="after")
    def _holes_stand_apart(self) -> "Params":
        r = self.face_diameter / 2
        eye, mouth = self.eye_diameter / 2, self.mouth_diameter / 2
        (lx, ly), (rx, ry) = eyes_at(r)
        mx, my = mouth_at(r)
        gaps = {
            "an eye and the face's edge": r - math.hypot(rx, ry) - eye,
            "the eyes": (rx - lx) - 2 * eye,
            "the mouth and the face's edge": r - math.hypot(mx, my) - mouth,
            "an eye and the mouth": math.hypot(rx - mx, ry - my) - eye - mouth,
        }
        for between, gap in gaps.items():
            if gap < WALL:
                raise ValueError(
                    f"{gap:.1f} mm of face between {between}, under the {WALL:g} mm it "
                    "needs: a wider face, or smaller eyes or mouth"
                )
        return self


class RouterEmojiPart(BasePart):
    """A 😮 cut from a sheet: the eyes and the mouth bored, then the face cut around."""

    def get_bounds(self, params: Optional[Dict] = None) -> BoundingBox3D:
        p = Params(**(params or {}))
        return BoundingBox3D(
            min_point=Vector3D(x=0.0, y=0.0, z=0.0),
            max_point=Vector3D(x=p.face_diameter, y=p.face_diameter, z=p.thickness),
        )

    def cuts(self, params: Optional[Mapping[str, object]] = None):
        """The stock is the face's square plus its margin on every side, the work zero
        at the stock's front-left top corner; the eyes and the mouth are bored through
        first, and the face cut around last, through the stock."""
        from apothecary.cam.models import Cuts, Disc, Hole, Stock

        p = Params(**(params or {}))
        r = p.face_diameter / 2
        cx = cy = p.stock_margin + r
        through = p.thickness + 0.5
        operations = [
            Hole(
                x=round(cx + ex, 3),
                y=round(cy + ey, 3),
                diameter=p.eye_diameter,
                depth=through,
                name="eye",
            )
            for ex, ey in eyes_at(r)
        ]
        mx, my = mouth_at(r)
        operations.append(
            Hole(
                x=round(cx + mx, 3),
                y=round(cy + my, 3),
                diameter=p.mouth_diameter,
                depth=through,
                name="mouth",
            )
        )
        operations.append(Disc(x=cx, y=cy, diameter=p.face_diameter, depth=through, name="face"))
        side = p.face_diameter + 2 * p.stock_margin
        return Cuts(stock=Stock(x=side, y=side, thickness=p.thickness), operations=operations)


def create(root: Path) -> BasePart:
    return RouterEmojiPart(
        name="router_emoji",
        source_file=root / "parts" / "router_emoji" / "router_emoji.scad",
        description="A 😮 cut on the router, its face, eyes and mouth measured to calibrate it",
        params_model=Params,
        category="coupon",
        tags=["router", "cnc", "coupon", "calibration", "test"],
        readme_path=root / "parts" / "router_emoji" / "README.md",
        preview_color=Color.from_hex("#f2c230"),
    )


DEFAULT = create(ROOT)
