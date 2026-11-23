"""A badge composed in the page: a round face drawn from circles and strokes, or a word
in a font, engraved in a plate. The Badge window picks one and types the word; the faces
and the word are also the part's presets, each its numbers over the part's defaults.

A face is made on either machine: printed, or cut on the router -- its eyes and an open
mouth bored, a smile, a frown, a line or a wink a groove the tool's width, then the face
cut around from outside (``cuts``). A word is printed alone: OpenSCAD draws it in a
font's outlines, which the router's one end mill cannot follow, so its toolpath is
refused, saying so. The fonts offered are the Liberation family, which OpenSCAD's own
manual says it includes, so a word draws the same wherever the part renders.

Its SCAD places every hole and stroke as ``eyes_at``, ``mouth_at`` and ``strokes`` here
do, as shares of the face's radius, so what is cut is what is drawn.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Literal, Mapping, Optional, Tuple

from pydantic import BaseModel, Field, field_validator, model_validator

from apothecary.models import BoundingBox3D, Color, PrintSettings, Vector3D

from .base import BasePart, Preset
from .skeleton import ROOT

MM = {"unit": "mm"}

# Each face, and the emoji it is drawn after.
FACES: Dict[str, str] = {
    "open": "😮",
    "smile": "🙂",
    "neutral": "😐",
    "wink": "😉",
    "frown": "🙁",
    "grin": "😀",
}
# What each face is, as its preset says it.
FACE_WORDS: Dict[str, str] = {
    "open": "a face with its mouth open",
    "smile": "a smiling face",
    "neutral": "a face with a straight mouth",
    "wink": "a winking face",
    "frown": "a frowning face",
    "grin": "a grinning face",
}
Face = Literal["open", "smile", "neutral", "wink", "frown", "grin"]
# The fonts a word is drawn in: OpenSCAD's own, its Liberation family, as fontconfig names them.
FONTS = (
    "Liberation Sans:style=Bold",
    "Liberation Sans",
    "Liberation Serif:style=Bold",
    "Liberation Serif:style=Italic",
    "Liberation Mono:style=Bold",
)
Font = Literal[
    "Liberation Sans:style=Bold",
    "Liberation Sans",
    "Liberation Serif:style=Bold",
    "Liberation Serif:style=Italic",
    "Liberation Mono:style=Bold",
]

# Where the eyes and the mouth stand, as shares of the face's radius from its centre, as
# the SCAD places them: each eye out and up, an open mouth down; the eye's and the open
# mouth's diameters; the smile's arc, about the centre, and the frown's, below it.
EYE_OUT, EYE_UP, EYE = 0.35, 0.3, 0.3
MOUTH_DOWN, MOUTH = 0.4, 0.5
ARC, ARC_SEGMENTS = 0.55, 12
FROWN_DOWN = 0.95
LINE_HALF, LINE_DOWN = 0.3, 0.4
# What a word keeps clear of its plate's edge, in millimetres.
WORD_MARGIN = 3.0


def eyes_at(radius: float, face: str) -> Tuple[Tuple[float, float], ...]:
    """The centres of the eyes bored, from the face's centre: both, or the left alone
    where the right is winking (a stroke)."""
    left, right = (-EYE_OUT * radius, EYE_UP * radius), (EYE_OUT * radius, EYE_UP * radius)
    return (left,) if face == "wink" else (left, right)


def mouth_at(radius: float) -> Tuple[float, float]:
    """An open mouth's centre, from the face's centre."""
    return (0.0, -MOUTH_DOWN * radius)


def _arc(cy: float, r: float, start: float, end: float) -> List[Tuple[float, float]]:
    return [
        (
            round(r * math.cos(math.radians(start + (end - start) * k / ARC_SEGMENTS)), 3),
            round(cy + r * math.sin(math.radians(start + (end - start) * k / ARC_SEGMENTS)), 3),
        )
        for k in range(ARC_SEGMENTS + 1)
    ]


def strokes(radius: float, face: str) -> List[List[Tuple[float, float]]]:
    """Each stroke of the face, the points its centre line runs through, from the face's
    centre: the mouth's, and a winking eye's. An open face has none."""
    r = ARC * radius
    out: List[List[Tuple[float, float]]] = []
    if face in ("smile", "wink"):
        out.append(_arc(0.0, r, 215, 325))
    elif face == "grin":
        arc = _arc(0.0, r, 200, 340)
        out.append([*arc, arc[0]])  # the arc closed by its chord: a mouth open wide
    elif face == "frown":
        out.append(_arc(-FROWN_DOWN * radius, r, 55, 125))
    elif face == "neutral":
        out.append(
            [(-LINE_HALF * radius, -LINE_DOWN * radius), (LINE_HALF * radius, -LINE_DOWN * radius)]
        )
    if face == "wink":
        half = EYE * radius / 2
        x, y = EYE_OUT * radius, EYE_UP * radius
        out.append([(round(x - half, 3), round(y, 3)), (round(x + half, 3), round(y, 3))])
    return out


class Params(BaseModel):
    """The badge, each field the SCAD's variable of the same name."""

    kind: Literal["face", "word"] = Field("face", description="A face, or a word")
    face: Face = Field("smile", description="The face, drawn after its emoji")
    text: str = Field(
        "HELLO", min_length=1, max_length=24, description="The word, on a word's plate"
    )
    font: Font = Field("Liberation Sans:style=Bold", description="The word's font")
    diameter: float = Field(
        80.0, ge=50, le=200, description="The face, across", json_schema_extra=MM
    )
    width: float = Field(
        120.0, ge=30, le=220, description="A word's plate, wide", json_schema_extra=MM
    )
    height: float = Field(
        40.0, ge=15, le=120, description="A word's plate, high", json_schema_extra=MM
    )
    text_size: float = Field(
        16.0, ge=4, le=80, description="The word's letters, high", json_schema_extra=MM
    )
    thickness: float = Field(
        6.0, ge=2, le=40, description="The plate's thickness", json_schema_extra=MM
    )
    depth: float = Field(
        2.0,
        gt=0,
        le=20,
        description="How deep the face or the word is engraved",
        json_schema_extra=MM,
    )
    stroke: float = Field(
        6.0,
        ge=1,
        le=12,
        description="A face's strokes, wide: the router cuts them its tool's width",
        json_schema_extra=MM,
    )
    stock_margin: float = Field(
        10.0,
        ge=0,
        le=50,
        description="Stock beyond the face on every side (the router's)",
        json_schema_extra=MM,
    )

    @field_validator("text")
    @classmethod
    def _one_line_of_plain_words(cls, text: str) -> str:
        # Checked here, not as the schema's pattern, which the page reads as a choice.
        bad = [c for c in ('"', "\\", "\n") if c in text]
        if bad or not text.strip():
            raise ValueError(
                "a word is one line, with no double quote or backslash: "
                + (f"it has {', '.join(repr(c) for c in bad)}" if bad else "it is blank")
            )
        return text

    @model_validator(mode="after")
    def _engraved_not_through(self) -> "Params":
        if self.depth >= self.thickness:
            raise ValueError(
                f"engraved {self.depth:g} mm into a {self.thickness:g} mm plate goes through it: "
                "a shallower depth, or a thicker plate"
            )
        return self


PRESETS: Dict[str, Preset] = {
    **{
        face: Preset(
            params={"kind": "face", "face": face},
            description=f"{FACE_WORDS[face]}, {emoji}: printed, or cut on the router",
            label=f"{emoji} {face.capitalize()}",
        )
        for face, emoji in FACES.items()
    },
    "word": Preset(
        params={"kind": "word"},
        description="a word on a plate, in a font: printed; the router cuts a face",
        label="✎ Word",
    ),
}


class Refused(ValueError):
    """A badge the router does not cut, saying why."""


class BadgePart(BasePart):
    """A face or a word engraved in a plate, printed, or a face cut on the router."""

    def get_bounds(self, params: Optional[Dict] = None) -> BoundingBox3D:
        p = Params(**(params or {}))
        x, y = (p.diameter, p.diameter) if p.kind == "face" else (p.width, p.height)
        return BoundingBox3D(
            min_point=Vector3D(x=0.0, y=0.0, z=0.0),
            max_point=Vector3D(x=x, y=y, z=p.thickness),
        )

    def cuts(self, params: Optional[Mapping[str, object]] = None):
        """A face from its stock: the face's square plus its margin on every side, the work
        zero at the stock's front-left top corner. The eyes and an open mouth bored to the
        depth, each stroke a groove to it, then the face cut around, through. A word is
        refused, and a stroke other than the tool's width."""
        from apothecary.cam.models import Cuts, Disc, Groove, Hole, Stock, Tool

        p = Params(**(params or {}))
        tool = Tool()
        if p.kind == "word":
            raise Refused(
                "a word is printed, not cut: its letters are a font's outlines, which the "
                "router's one end mill cannot follow -- choose a face to cut, or make the word "
                "on a printer"
            )
        if abs(p.stroke - tool.diameter) > 1e-6:
            raise Refused(
                f"a face's strokes are {p.stroke:g} mm wide and the router cuts them its "
                f"{tool.diameter:g} mm tool's width: stroke {tool.diameter:g} to cut it"
            )
        r = p.diameter / 2
        cx = cy = p.stock_margin + r
        operations = [
            Hole(x=round(cx + ex, 3), y=round(cy + ey, 3), diameter=EYE * r, depth=p.depth)
            for ex, ey in eyes_at(r, p.face)
        ]
        if p.face == "open":
            mx, my = mouth_at(r)
            operations.append(
                Hole(x=round(cx + mx, 3), y=round(cy + my, 3), diameter=MOUTH * r, depth=p.depth)
            )
        for line in strokes(r, p.face):
            operations.append(
                Groove(
                    points=[(round(cx + x, 3), round(cy + y, 3)) for x, y in line], depth=p.depth
                )
            )
        operations.append(Disc(x=cx, y=cy, diameter=p.diameter, depth=p.thickness + 0.5))
        side = p.diameter + 2 * p.stock_margin
        return Cuts(
            stock=Stock(x=side, y=side, thickness=p.thickness), tool=tool, operations=operations
        )


def create(root: Path) -> BasePart:
    return BadgePart(
        name="badge",
        source_file=root / "parts" / "badge" / "badge.scad",
        description="A face or a word engraved in a plate: printed, or a face cut on the router",
        params_model=Params,
        category="misc",
        tags=["badge", "emoji", "text", "router", "cnc"],
        readme_path=root / "parts" / "badge" / "README.md",
        preview_color=Color.from_hex("#f2c230"),
        # printer_1's nozzle and layers; three lines to a wall.
        print_settings=PrintSettings(
            nozzle_diameter=0.4, layer_height=0.2, wall_thickness=1.2, tolerance=0.2
        ),
        presets=PRESETS,
    )


DEFAULT = create(ROOT)
