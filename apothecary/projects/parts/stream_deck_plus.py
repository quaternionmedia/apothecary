"""Elgato Stream Deck + -- the controller at the garage's bench, drawn as the device is.

A model built from the maker's published figures (see
``parts/stream_deck_plus/README.md`` for which numbers are the maker's and
which are assumed): eight LCD keys in two rows of four, a touch strip under
them and four knobs under that, on a body whose face slopes up toward the
back, standing on a base plate with its stand. The face's slope is a
parameter; the envelope is the maker's whatever it is set to.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from pydantic import BaseModel, Field

from apothecary.models import BoundingBox3D, Color, Vector3D

from .base import BasePart
from .skeleton import ROOT

# The maker's figures, in mm, as the SCAD file states them: the overall size, the
# stand included, and what the face carries. A site places the deck by these.
OVERALL = Vector3D(x=140.0, y=138.0, z=110.0)
KEYS = (4, 2)  # eight LCD keys: four across, two down
KNOBS = 4  # four encoders with a push function
STRIP = (108.0, 14.0)  # the LCD touch panel


class Params(BaseModel):
    """The face's slope, and whether the keys and the strip are drawn lit."""

    face_angle: float = Field(
        40.0,
        ge=30,
        le=41,
        description="The face's slope from the bench (degrees): assumed, the maker gives the overall size alone",
        json_schema_extra={"unit": "deg"},
    )
    lit: bool = Field(
        True,
        description="The keys and the strip drawn lit, as a deck apothecary is drawing shows them",
    )


class StreamDeckPlusPart(BasePart):
    def get_bounds(self, params: Optional[Dict] = None) -> BoundingBox3D:
        # The angle changes the body's thickness; the envelope stays the maker's.
        Params(**(params or {}))
        return BoundingBox3D(min_point=Vector3D(), max_point=OVERALL)


def create(root: Path) -> BasePart:
    return StreamDeckPlusPart(
        name="stream_deck_plus",
        source_file=root / "parts" / "stream_deck_plus" / "stream_deck_plus.scad",
        description="Elgato Stream Deck +: eight LCD keys, a touch strip and four knobs on a sloped "
        "face with its stand, from the maker's published size -- the controller at the bench "
        "whose knobs jog the machines.",
        params_model=Params,
        category="electronics",
        tags=["controller", "streamdeck", "elgato", "usb", "hid", "keys", "knobs", "touch"],
        readme_path=root / "parts" / "stream_deck_plus" / "README.md",
        preview_color=Color(r=0.12, g=0.12, b=0.12),
        default_bounds=BoundingBox3D(min_point=Vector3D(), max_point=OVERALL),
    )


DEFAULT = create(ROOT)
