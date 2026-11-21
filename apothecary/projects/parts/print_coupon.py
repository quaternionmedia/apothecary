"""The printer's piece made to be measured: a plate with two square blocks on it, a
square pocket in each, a square window through the plate and a single-wall fin.

Its sizes are chosen so caliper readings of it separate what the print tuning loop
solves for (``apothecary/print_tuning.py``): outside sizes of three nominals along
each of X and Y (the plate, block A, block B) and inside sizes of three (A's pocket,
B's pocket, the window), so a scale is told from an offset; the plate and the window
read at the base, where the first layer is, and the blocks and pockets above it, so
the first layer's spread is told from the faces'; three tops at three heights, so the
first layer's height is told from a scale in Z; and the fin, one line wide, whose
thickness is kept and said. ``measures`` is the plan: each feature named, in the order
to read it, with its jaws and the line they close along, its nominal the distance
between the faces it meets; ``apothecary parts verify print_coupon`` finds each on the
render. ``PLAN_SEPARATES`` is what the plan claims, and tests/test_print_coupon_part.py
asks the design matrix.

Every height is a whole number of 0.2 mm layers over a first layer of 0.2 mm, and the
part declares that layer height, so a slice puts each top on a layer's.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Optional

from pydantic import BaseModel, Field, model_validator

from apothecary.models import BoundingBox3D, Color, PrintSettings, Vector3D
from apothecary.models.measures import MeasuredFeature, MeasurePlan

from .base import BasePart
from .skeleton import ROOT

MM = {"unit": "mm"}

# The least wall a pocket leaves in its block, and the room behind block A for its label.
WALL = 2.0
LABEL_ROOM = 6.0

PLAN_SEPARATES = ("scale_x", "scale_y", "scale_z", "contour", "hole", "foot", "first")


class Params(BaseModel):
    """The coupon's sizes, each the SCAD's variable of the same name."""

    plate_x: float = Field(
        54.0, ge=40, le=120, description="The plate along X, its long side", json_schema_extra=MM
    )
    plate_y: float = Field(
        36.0, ge=30, le=100, description="The plate along Y", json_schema_extra=MM
    )
    plate_t: float = Field(
        2.0, ge=1, le=6, description="The plate's thickness: the first top", json_schema_extra=MM
    )
    a_size: float = Field(20.0, ge=10, le=40, description="Block A, square", json_schema_extra=MM)
    a_height: float = Field(
        10.0, ge=2, le=30, description="Block A above the plate", json_schema_extra=MM
    )
    a_pocket: float = Field(
        12.0, ge=4, le=30, description="Block A's pocket, square", json_schema_extra=MM
    )
    b_size: float = Field(12.0, ge=8, le=30, description="Block B, square", json_schema_extra=MM)
    b_height: float = Field(
        6.0, ge=2, le=30, description="Block B above the plate", json_schema_extra=MM
    )
    b_pocket: float = Field(
        6.0, ge=3, le=20, description="Block B's pocket, square", json_schema_extra=MM
    )
    window: float = Field(
        8.0, ge=4, le=20, description="A square window through the plate", json_schema_extra=MM
    )
    fin_t: float = Field(
        0.45, ge=0.2, le=1.2, description="The fin's thickness: one line", json_schema_extra=MM
    )
    fin_length: float = Field(
        15.0, ge=5, le=30, description="The fin along Y", json_schema_extra=MM
    )
    fin_height: float = Field(
        6.0, ge=2, le=20, description="The fin above the plate", json_schema_extra=MM
    )
    margin: float = Field(
        4.0,
        ge=3,
        le=10,
        description="From the plate's edge to what stands on it",
        json_schema_extra=MM,
    )
    gap: float = Field(
        6.0, ge=4, le=12, description="Between two features: room for a jaw", json_schema_extra=MM
    )
    label_depth: float = Field(
        0.6, ge=0.2, le=1, description="How deep a label is cut", json_schema_extra=MM
    )

    @model_validator(mode="after")
    def _fits(self) -> "Params":
        if self.label_depth >= self.plate_t:
            raise ValueError("a label is cut into the plate, not through it")
        for block, size, pocket in (
            ("A", self.a_size, self.a_pocket),
            ("B", self.b_size, self.b_pocket),
        ):
            if pocket > size - 2 * WALL:
                raise ValueError(
                    f"block {block}'s pocket leaves under {WALL:g} mm of wall: a smaller pocket"
                )
        if len({self.a_size, self.b_size}) < 2 or len({self.a_pocket, self.b_pocket}) < 2:
            raise ValueError(
                "the blocks, and their pockets, are of two sizes: one size cannot tell a "
                "scale from an offset"
            )
        at = layout(self)
        needs = {
            "X, for the fin": at.fin_x0 + self.fin_t + self.margin,
            "Y, for the window": at.w_y0 + self.window + self.margin,
            "Y, for block A's label": at.a_y0 + self.a_size + LABEL_ROOM,
            "Y, for the fin": at.fin_y0 + self.fin_length + self.margin,
        }
        for what, reach in needs.items():
            have = self.plate_x if what.startswith("X") else self.plate_y
            if reach > have + 1e-9:
                raise ValueError(
                    f"the plate is {have:g} mm along {what.split(',')[0]} and needs "
                    f"{reach:g}{what[1:]}"
                )
        return self


@dataclass(frozen=True)
class Layout:
    """Where each feature stands on the plate, as the SCAD places it."""

    a_x0: float
    a_y0: float
    b_x0: float
    b_y0: float
    fin_x0: float
    fin_y0: float
    w_x0: float
    w_y0: float


def layout(p: Params) -> Layout:
    b_x0 = p.margin + p.a_size + p.gap
    return Layout(
        a_x0=p.margin,
        a_y0=p.margin,
        b_x0=b_x0,
        b_y0=p.margin,
        fin_x0=b_x0 + p.b_size + p.gap,
        fin_y0=p.margin,
        w_x0=b_x0 + (p.b_size - p.window) / 2,
        w_y0=p.margin + p.b_size + p.gap,
    )


def plan(p: Params) -> MeasurePlan:
    """What a person reads of the coupon, in the order to read it."""
    at = layout(p)
    mid_t = p.plate_t / 2
    a_mid = (at.a_x0 + p.a_size / 2, at.a_y0 + p.a_size / 2, p.plate_t + p.a_height / 2)
    b_mid = (at.b_x0 + p.b_size / 2, at.b_y0 + p.b_size / 2, p.plate_t + p.b_height / 2)
    w_mid = (at.w_x0 + p.window / 2, at.w_y0 + p.window / 2, mid_t)
    a_in, b_in = (p.a_size - p.a_pocket) / 2, (p.b_size - p.b_pocket) / 2
    a_top, b_top = p.plate_t + p.a_height, p.plate_t + p.b_height

    def read(name, kind, axis, level, jaw, words, point, faces) -> MeasuredFeature:
        return MeasuredFeature(
            name=name,
            kind=kind,
            axis=axis,
            level=level,
            jaw=jaw,
            words=words,
            at=point,
            faces=faces,
        )

    features = [
        read("plate_x", "outside", "x", "base", "outside",
             "the plate across X, its long side, jaws over its whole thickness",
             (0.0, p.margin / 2, mid_t), (0.0, p.plate_x)),
        read("plate_y", "outside", "y", "base", "outside",
             "the plate across Y, jaws over its whole thickness",
             (p.margin / 2, 0.0, mid_t), (0.0, p.plate_y)),
        read("a_x", "outside", "x", "above", "outside", "block A across X, jaws above the plate",
             (0.0, a_mid[1], a_mid[2]), (at.a_x0, at.a_x0 + p.a_size)),
        read("a_y", "outside", "y", "above", "outside", "block A across Y, jaws above the plate",
             (a_mid[0], 0.0, a_mid[2]), (at.a_y0, at.a_y0 + p.a_size)),
        read("b_x", "outside", "x", "above", "outside", "block B across X, jaws above the plate",
             (0.0, b_mid[1], b_mid[2]), (at.b_x0, at.b_x0 + p.b_size)),
        read("b_y", "outside", "y", "above", "outside", "block B across Y, jaws above the plate",
             (b_mid[0], 0.0, b_mid[2]), (at.b_y0, at.b_y0 + p.b_size)),
        read("a_pocket_x", "inside", "x", "above", "inside", "block A's pocket across X",
             (0.0, a_mid[1], a_mid[2]), (at.a_x0 + a_in, at.a_x0 + a_in + p.a_pocket)),
        read("a_pocket_y", "inside", "y", "above", "inside", "block A's pocket across Y",
             (a_mid[0], 0.0, a_mid[2]), (at.a_y0 + a_in, at.a_y0 + a_in + p.a_pocket)),
        read("b_pocket_x", "inside", "x", "above", "inside", "block B's pocket across X",
             (0.0, b_mid[1], b_mid[2]), (at.b_x0 + b_in, at.b_x0 + b_in + p.b_pocket)),
        read("b_pocket_y", "inside", "y", "above", "inside", "block B's pocket across Y",
             (b_mid[0], 0.0, b_mid[2]), (at.b_y0 + b_in, at.b_y0 + b_in + p.b_pocket)),
        read("window_x", "inside", "x", "base", "inside", "the window W across X, at its narrowest",
             (0.0, w_mid[1], mid_t), (at.w_x0, at.w_x0 + p.window)),
        read("window_y", "inside", "y", "base", "inside", "the window W across Y, at its narrowest",
             (w_mid[0], 0.0, mid_t), (at.w_y0, at.w_y0 + p.window)),
        read("plate_z", "height", "z", "above", "outside",
             "the plate's thickness, at its front-left corner",
             (p.margin / 2, p.margin / 2, 0.0), (0.0, p.plate_t)),
        read("b_z", "height", "z", "above", "outside", "block B's top over the bed face",
             (at.b_x0 + b_in / 2, at.b_y0 + b_in / 2, 0.0), (0.0, b_top)),
        read("a_z", "height", "z", "above", "outside", "block A's top over the bed face",
             (at.a_x0 + a_in / 2, at.a_y0 + a_in / 2, 0.0), (0.0, a_top)),
        read("fin", "wall", "x", "above", "outside", "the fin F across, halfway up",
             (0.0, at.fin_y0 + p.fin_length / 2, p.plate_t + p.fin_height / 2),
             (at.fin_x0, at.fin_x0 + p.fin_t)),
    ]  # fmt: skip
    return MeasurePlan(
        features=features,
        separates=list(PLAN_SEPARATES),
    )


class PrintCouponPart(BasePart):
    """The printer's coupon: measured with calipers, a turn of the print tuning loop."""

    def get_bounds(self, params: Optional[Dict] = None) -> BoundingBox3D:
        p = Params(**(params or {}))
        return BoundingBox3D(
            min_point=Vector3D(x=0.0, y=0.0, z=0.0),
            max_point=Vector3D(
                x=p.plate_x,
                y=p.plate_y,
                z=p.plate_t + max(p.a_height, p.b_height, p.fin_height),
            ),
        )

    def measures(self, params: Optional[Mapping[str, object]] = None) -> MeasurePlan:
        return plan(Params(**(params or {})))


def create(root: Path) -> BasePart:
    return PrintCouponPart(
        name="print_coupon",
        source_file=root / "parts" / "print_coupon" / "print_coupon.scad",
        description="A plate, two blocks with pockets, a window and a fin, measured with "
        "calipers to tune a printer",
        params_model=Params,
        category="calibration",
        tags=["printer", "calibration", "coupon", "test"],
        readme_path=root / "parts" / "print_coupon" / "README.md",
        preview_color=Color.from_hex("#4f8fd0"),
        print_settings=PrintSettings(nozzle_diameter=0.4, layer_height=0.2),
    )


DEFAULT = create(ROOT)
