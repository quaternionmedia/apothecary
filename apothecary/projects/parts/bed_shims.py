"""Shims that level a printer's bed on its solid mounts: one for each levelling screw
whose corner stands low, as thick as lifts that corner to the highest.

``apothecary/bed_shims.py`` computes the thicknesses from bed readings and the printer's
screws, and ``apothecary bed shims`` says them with the command that slices this part at
them (``-p thicknesses=... -p labels=...``). The part draws as many shims as it is
given thicknesses, so a corner that gets none is left out, and a printer with three
screws, or five, gets as many as it needs.

Every thickness the computation gives is a whole number of 0.1 mm layers over a first
layer of 0.2 mm, and the part declares that layer height, so a slice puts each shim's top
on a layer. Each shim's tab is thicker than the thinnest shim, so its label is cut into
the tab whatever the shim's thickness.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Dict, List, Literal, Mapping, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from apothecary.core import OpenSCADObject
from apothecary.models import BoundingBox3D, Color, PrintSettings, Vector3D

from .base import BasePart
from .skeleton import ROOT

MM = {"unit": "mm"}
FLOOR_UNDER_A_LABEL = 0.2  # what a label's cut leaves of the tab: one first layer

SCREW_HOLES = {"M3": 3.4, "M4": 4.6}
"""The hole each bed screw a shim may go round is given, mm: a clearance hole a little
over the screw. The part's ``screw`` chooses one; ``hole_d`` types another over it. The
SCAD holds the same two (its ``hole``)."""


class Params(BaseModel):
    """The shims' thicknesses and labels, and the size of each, each the SCAD's variable
    of the same name."""

    thicknesses: List[float] = Field(
        [0.5, 0.5, 0.5],
        min_length=1,
        max_length=12,
        description="Each shim's thickness, in the order of the labels",
        json_schema_extra={
            "unit": "mm",
            "items": {"type": "number", "minimum": 0.2, "maximum": 10},
        },
    )
    labels: str = Field(
        "FL BR BL",
        description="Each shim's label, cut into its tab: one word per shim, in order",
    )
    outer_d: float = Field(
        12.0,
        ge=6,
        le=40,
        description="The ring across, at least the mount's face it bears on: 12 mm is a "
        "default until calipers read the mount",
        json_schema_extra=MM,
    )
    screw: Literal["M3", "M4"] = Field(
        "M4",
        description="The bed screw a shim goes round, which sets its hole: M4 is a default "
        "until the screw is known",
    )
    hole_d: float = Field(
        0.0,
        ge=0,
        le=10,
        description="The hole, typed over the screw's where it needs another; 0 is the screw's own",
        json_schema_extra=MM,
    )
    slot: bool = Field(True, description="An open slot from the hole to the rim")
    gap: float = Field(
        4.0, ge=2, le=20, description="Between two shims on the bed", json_schema_extra=MM
    )
    tab_length: float = Field(
        14.0, ge=8, le=40, description="How far the tab reaches past the ring", json_schema_extra=MM
    )
    tab_width: float = Field(9.0, ge=5, le=30, description="The tab across", json_schema_extra=MM)
    tab_t: float = Field(
        1.2,
        ge=0.6,
        le=4,
        description="The tab's thickness, more than the shim's where it is thin",
        json_schema_extra=MM,
    )
    tab_clear: float = Field(
        1.0,
        ge=0,
        le=5,
        description="Between the ring's rim and where the tab thickens",
        json_schema_extra=MM,
    )
    label_size: float = Field(
        5.0, ge=2, le=8, description="The letters' height", json_schema_extra=MM
    )
    label_depth: float = Field(
        0.6, ge=0.2, le=2, description="How deep a label is cut into the tab", json_schema_extra=MM
    )

    @property
    def hole(self) -> float:
        """The hole the screw passes, mm: what is typed, else the screw's own."""
        return self.hole_d if self.hole_d > 0 else SCREW_HOLES[self.screw]

    @field_validator("thicknesses", mode="before")
    @classmethod
    def _from_words(cls, value: Any) -> Any:
        """``0.3,0.8,0.7`` (the shell's ``-p``) or ``[0.3, 0.8]`` as a list."""
        if isinstance(value, str):
            words = value.strip().strip("[]").replace(",", " ").split()
            try:
                return [float(w) for w in words]
            except ValueError as exc:
                raise ValueError(f"thicknesses are numbers, mm: {value!r}") from exc
        return value

    @field_validator("labels", mode="before")
    @classmethod
    def _labels_as_words(cls, value: Any) -> Any:
        """A list of labels, as the SCAD holds them and its text in the page reads them,
        is the same words."""
        if isinstance(value, (list, tuple)):
            return " ".join(str(v) for v in value)
        return value

    @field_validator("thicknesses")
    @classmethod
    def _printable(cls, value: List[float]) -> List[float]:
        for t in value:
            if not 0.2 <= t <= 10:
                raise ValueError(f"a shim is 0.2 to 10 mm thick, not {t:g}")
        return value

    @model_validator(mode="after")
    def _fits(self) -> "Params":
        words = self.labels.split()
        if len(words) != len(self.thicknesses):
            raise ValueError(
                f"{len(self.thicknesses)} thicknesses and {len(words)} labels: one label per shim"
            )
        if len(set(words)) != len(words):
            raise ValueError(f"each shim's label is its own: {words}")
        if any(not w.isalnum() for w in words):
            raise ValueError(f"a label is letters and digits: {words}")
        if self.hole_d and self.hole_d < 2:
            raise ValueError("a hole typed is 2 mm or more; 0 is the screw's own")
        if self.hole >= self.outer_d - 2:
            raise ValueError("the hole leaves under 1 mm of ring: a smaller hole or a wider ring")
        if self.tab_clear >= self.tab_length - 4:
            raise ValueError(
                "the tab's thick part is 4 mm long or more: a longer tab or less clear"
            )
        if self.tab_t - self.label_depth < FLOOR_UNDER_A_LABEL - 1e-9:
            raise ValueError(
                f"a label cut {self.label_depth:g} mm into a {self.tab_t:g} mm tab leaves under "
                f"{FLOOR_UNDER_A_LABEL:g} mm: a shallower label or a thicker tab"
            )
        return self


class SetScad(OpenSCADObject):
    """A SCAD file with each of ``values`` written over its own top-level assignment: the
    part's SCAD as its parameters set it, one assignment per name, so OpenSCAD has no
    value overwritten to warn about."""

    source: str
    values: Dict[str, Any]

    def render(self) -> str:
        from .stl_renderer import scad_literal

        text = self.source
        for name, value in self.values.items():
            line = re.compile(rf"^({re.escape(name)}\s*=\s*)[^;]*;", re.M)
            literal = scad_literal(value)
            text, found = line.subn(lambda m, lit=literal: f"{m.group(1)}{lit};", text, count=1)
            if not found:
                raise ValueError(f"{name} is assigned nowhere at the top of the part's SCAD")
        return text.rstrip("\n")


class BedShimsPart(BasePart):
    """Shims in a column along Y, as many as their thicknesses.

    Its SCAD is written from its parameters (``geometry``): the file's own assignments,
    each set to the value given. So the page edits its numbers in Parameters and never
    its text, and Parameters shows the shims drawn -- the ones a printer's readings call
    for, once the page stands them on the piece -- rather than the file's defaults."""

    def geometry(self, params: Mapping[str, Any]) -> OpenSCADObject:
        values = self.scad_overrides(Params(**params).model_dump())
        return SetScad(source=self.source_file.read_text(encoding="utf-8"), values=values)

    def get_bounds(self, params: Optional[Dict] = None) -> BoundingBox3D:
        p = Params(**(params or {}))
        n = len(p.thicknesses)
        r = p.outer_d / 2
        # Each ring's slot opens toward +X, so its rim there ends where the slot's edge meets it.
        right = math.sqrt(r * r - (p.hole / 2) ** 2) if p.slot else r
        return BoundingBox3D(
            min_point=Vector3D(x=0.0, y=0.0, z=0.0),
            max_point=Vector3D(
                x=p.tab_length + r + right,
                y=n * p.outer_d + (n - 1) * p.gap,
                z=max(max(p.thicknesses), p.tab_t),
            ),
        )

    def scad_overrides(self, params: Mapping[str, Any]) -> Dict[str, Any]:
        """The labels go to the SCAD as a list of words."""
        out = dict(params)
        if "labels" in out:
            out["labels"] = str(out["labels"]).split()
        return out


def create(root: Path) -> BasePart:
    return BedShimsPart(
        name="bed_shims",
        source_file=root / "parts" / "bed_shims" / "bed_shims.scad",
        description="A shim for each levelling screw whose corner stands low, as thick as "
        "lifts it to the highest, stacked on the bed's solid mounts; its label on a tab",
        params_model=Params,
        category="calibration",
        tags=["printer", "bed", "levelling", "shim"],
        readme_path=root / "parts" / "bed_shims" / "README.md",
        preview_color=Color.from_hex("#c9a227"),
        # No brim, said as none: each shim's slot opens its hole to its rim, so a brim
        # round its outside would print into both. Make these slices it to probe first.
        print_settings=PrintSettings(nozzle_diameter=0.4, layer_height=0.1, brim_width=0.0),
    )


DEFAULT = create(ROOT)
