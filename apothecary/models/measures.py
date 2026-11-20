"""A measurement plan: what a person reads of a printed piece with calipers, and where.

A part made to be measured declares its plan (``BasePart.measures``): each feature
named, what kind of size it is -- across two outer faces, across a hole or a slot, a
top's height over the bed face, a single wall's thickness -- along which axis, whether
the jaws take in the first layer, which jaws read it, and, in the part's own frame, the
line the jaws close along and the two faces they meet. The nominal size is the
distance between those faces, so the plan cannot say one size and draw another:
``apothecary parts verify`` reads each line across the part's render and finds the
faces there (``meshes.crossings``).

A slice records the plan of what it sliced, so a turn of the print tuning loop knows
what the piece's features are (``apothecary/slicer/tuning.py``); ``feature`` hands
one to the error model (``apothecary/print_tuning.py``). ``separates`` says which of
that model's terms the plan claims to determine, and ``check`` asks the design matrix
whether it does.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field, model_validator

from .. import print_tuning as pt
from ..meshes import Triangle, crossings

# The jaws a feature is read with: the outside jaws, the inside jaws, or the depth rod.
Jaw = Literal["outside", "inside", "depth"]
AXIS = {"x": 0, "y": 1, "z": 2}
# The most a face found on a render may stand from where the plan draws it, mm: the
# coupon is boxes, which a render draws exactly, to an STL's single precision.
MEASURE_TOLERANCE = 0.01


class MeasuredFeature(BaseModel):
    """One size of a printed piece a person reads, as drawn."""

    name: str = Field(..., pattern=r"^[a-z][a-z0-9_]{0,39}$")
    kind: Literal["outside", "inside", "height", "wall"]
    axis: Literal["x", "y", "z"]
    level: Literal["base", "above"] = "above"
    jaw: Jaw
    words: str  # what to read, as a person reads it
    # The line the jaws close along passes through ``at`` along ``axis``, in the part's
    # frame; the faces they meet are at ``faces`` along it.
    at: Tuple[float, float, float]
    faces: Tuple[float, float]
    nominal: float = 0.0  # the distance between the faces: filled from them

    @model_validator(mode="after")
    def _from_the_faces(self) -> "MeasuredFeature":
        lo, hi = self.faces
        if not hi > lo:
            raise ValueError(f"{self.name}: its far face is past its near one")
        self.nominal = round(hi - lo, 6)
        pt.Feature(self.name, self.kind, self.axis, self.nominal, self.level)  # its checks
        return self

    def feature(self) -> pt.Feature:
        return pt.Feature(self.name, self.kind, self.axis, self.nominal, self.level)

    def read_on(self, triangles: Iterable[Triangle]) -> Optional[Tuple[float, float]]:
        """The faces a render has nearest this feature's two, along its line: what a
        caliper closing there would meet. None where the line meets the render nowhere."""
        cuts = crossings(triangles, self.at, AXIS[self.axis])
        if not cuts:
            return None
        lo = min(cuts, key=lambda c: abs(c - self.faces[0]))
        hi = min(cuts, key=lambda c: abs(c - self.faces[1]))
        return lo, hi


class MeasurePlan(BaseModel):
    """What a person reads of a piece, in the order to read it, and the error model's
    terms the plan claims to determine."""

    features: List[MeasuredFeature]
    separates: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _named_once(self) -> "MeasurePlan":
        names = [f.name for f in self.features]
        dup = {n for n in names if names.count(n) > 1}
        if dup:
            raise ValueError(f"a feature is named once: {sorted(dup)}")
        for name in self.separates:
            pt.term(name)
        return self

    def feature(self, name: str) -> MeasuredFeature:
        for f in self.features:
            if f.name == name:
                return f
        raise KeyError(f"no feature {name!r}: the plan reads {', '.join(self.names)}")

    @property
    def names(self) -> List[str]:
        return [f.name for f in self.features]

    def check(self) -> Dict[str, bool]:
        """Which terms the plan's features determine, read once each."""
        return pt.separable(f.feature() for f in self.features)


def box_plan(size: Tuple[float, float, float]) -> MeasurePlan:
    """The plan of a part that declares none, from the box of what was sliced: its X and
    Y across, read at the base where the first layer is widest, and its height. It
    separates nothing: a box's three sizes cannot tell a scale from an offset."""
    x, y, z = size
    return MeasurePlan(
        features=[
            MeasuredFeature(
                name="x",
                kind="outside",
                axis="x",
                level="base",
                jaw="outside",
                words="the part across X, at its widest",
                at=(0.0, y / 2, z / 2),
                faces=(0.0, x),
            ),
            MeasuredFeature(
                name="y",
                kind="outside",
                axis="y",
                level="base",
                jaw="outside",
                words="the part across Y, at its widest",
                at=(x / 2, 0.0, z / 2),
                faces=(0.0, y),
            ),
            MeasuredFeature(
                name="z",
                kind="height",
                axis="z",
                jaw="outside",
                words="the part's height, bed face to top",
                at=(x / 2, y / 2, 0.0),
                faces=(0.0, z),
            ),
        ]
    )
