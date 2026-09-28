"""A piece made from a picture is a part like any other.

``MadePart`` wraps one ``Made`` record (``vision/looks.py``) as a ``BasePart``, so
the one parameter contract (``projects/parts/params.py``) and the one editor in
the browser serve it as they serve a part from the parts folder:

- ``params_model`` is a ``PieceParams`` built for the record: the word the piece
  is made as, drawn from the vocabulary, and its three sides in millimetres,
  each defaulting to what the piece is now;
- ``contested`` carries the piece's provenance as candidates a person can turn
  to: the thickness is always a guess, since a picture from above cannot see
  it, and the sides the finder measured are offered whenever the piece no
  longer has them (a person stated a size, or the look was re-scaled);
- ``geometry`` is what ``piece_from_shape`` builds for the parameters, so the
  geometry seam that renders a Python-built part renders a made piece too;
- ``get_bounds`` is the box the piece occupies as built, standing on its own
  middle and turned as its shape was seen.

A made piece has no file: its ``source_file`` names one that does not exist,
and the record is its source. ``validate_overrides`` is ``BasePart``'s.

PROTOTYPE -- not ratified.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Type

from pydantic import BaseModel, Field, create_model

from ..core import OpenSCADObject
from ..models.bounds import BoundingBox3D
from ..models.vectors import Vector3D
from ..projects.parts.base import BasePart, ContestedValue
from .compose import THICKNESS_GUESS, piece_from_shape
from .looks import Made, found_size

SIDES = ("width", "depth", "height")


def word_pattern() -> str:
    """A pattern that admits the vocabulary's words and nothing else. The page
    draws its drop-down from the words in it."""
    from ..vocabulary import starter_words

    return "^(" + "|".join(re.escape(name) for name in starter_words().names()) + ")$"


class PieceParams(BaseModel):
    """What a made piece takes: its word, and its sides in millimetres."""

    word: str = Field("plate", description="the word the piece is made as")
    width: float = Field(1.0, gt=0, description="the shape's long side, mm")
    depth: float = Field(1.0, gt=0, description="the shape's short side, mm")
    height: float = Field(1.0, gt=0, description="how thick, mm; a picture cannot see this")


def piece_params(record: Made) -> Type[PieceParams]:
    """``PieceParams`` whose defaults are what the piece is now: its word and its
    sides as built, so a staged set that names only one side keeps the rest."""
    base = PieceParams.model_fields
    return create_model(
        "PieceParams",
        __base__=PieceParams,
        word=(
            str,
            Field(record.word, pattern=word_pattern(), description=base["word"].description),
        ),
        **{
            side: (float, Field(record.parameters[side], gt=0, description=base[side].description))
            for side in SIDES
        },
    )


def candidates(record: Made) -> Dict[str, List[ContestedValue]]:
    """The provenance of a made piece's sides, as candidates its editor offers.

    ``height`` always carries the guess: a picture from above cannot see
    thickness, so the number stands only until a person states one, and the
    guess is where a stated one returns to. ``width`` and ``depth`` carry the
    finder's measurement whenever the piece no longer has it -- after a person
    stated a size, or after its look was re-scaled -- so the measured number is
    one click away.
    """
    found = found_size(record)
    where = f"{record.finder}, confidence {record.confidence:.2f}, {record.picture}"
    at = f"at {record.mm_across:g} mm across the picture"
    contested: Dict[str, List[ContestedValue]] = {
        "height": [
            ContestedValue(
                value=found["height"],
                source=f"THICKNESS_GUESS ({THICKNESS_GUESS:g}) × the shorter side, {record.finder}",
                note="a picture from above cannot see thickness; the guess stands until a "
                "person states one",
            )
        ]
    }
    for side, edge, box_edge in (("width", "long", "across"), ("depth", "short", "down")):
        if math.isclose(found[side], record.parameters[side], rel_tol=1e-9, abs_tol=1e-9):
            continue
        measured = (
            f"the shape's {edge} side {at}"
            if record.shape.measured_sides
            else f"the shape's upright box, {box_edge}, {at}"
        )
        contested[side] = [ContestedValue(value=found[side], source=where, note=measured)]
    return contested


class MadePart(BasePart):
    """A piece made from a picture, as the part it is."""

    record: Made

    @classmethod
    def of(cls, record: Made) -> "MadePart":
        part = cls(
            name=record.piece,
            # No file: the record is the source. A path nothing has written.
            source_file=Path("made") / record.site / f"{record.piece}.scad",
            description=(
                f"a {record.word} made from shape {record.shape_index} of {record.picture}, "
                f"seen at {record.host or 'the floor'} by {record.finder}"
            ),
            params_model=piece_params(record),
            category=record.word,
            tags=["made", record.word],
            contested=candidates(record),
            record=record,
        )
        part.default_bounds = part.get_bounds()
        return part

    def _params(self, params: Optional[Mapping[str, Any]]) -> PieceParams:
        assert self.params_model is not None
        return self.params_model(**dict(params or {}))

    def geometry(self, params: Mapping[str, Any]) -> OpenSCADObject:
        """What ``piece_from_shape`` builds for these parameters: the word's body,
        shifted onto its own middle and turned as the shape was seen."""
        from ..vocabulary import WordShape

        p = self._params(params)
        piece, _about = piece_from_shape(
            self.record.shape,
            name=self.record.piece,
            word=p.word,
            reason=self.record.reason,
            per_unit=self.record.mm_across,
            tallness=self.record.pixel_height / self.record.pixel_width,
            finder=self.record.finder,
            size=WordShape(width=p.width, depth=p.depth, height=p.height),
        )
        assert piece.base is not None
        return piece.base

    def get_bounds(self, params: Optional[Dict] = None) -> BoundingBox3D:
        """The box the piece occupies as built: its sides, standing on its own
        middle, turned about it by the shape's ``turned_degrees``. A round word
        fills its longer side both ways, which the piece's footprint does not say
        either."""
        p = self._params(params)
        turn = math.radians(self.record.shape.turned_degrees)
        half_x = abs(p.width / 2 * math.cos(turn)) + abs(p.depth / 2 * math.sin(turn))
        half_y = abs(p.width / 2 * math.sin(turn)) + abs(p.depth / 2 * math.cos(turn))
        return BoundingBox3D(
            min_point=Vector3D(x=-half_x, y=-half_y, z=0.0),
            max_point=Vector3D(x=half_x, y=half_y, z=p.height),
        )


__all__ = ["MadePart", "PieceParams", "SIDES", "candidates", "piece_params", "word_pattern"]
