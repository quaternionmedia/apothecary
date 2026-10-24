"""Turning a picture into shapes, and shapes into something you can build.

The way in, in plain words: a picture goes to a *finder*, which reports flat
shapes as fractions of the picture with no real-world size attached. Those
shapes are matched to *words* — named, reusable pieces from
``apothecary.vocabulary`` — and the words are placed into an arrangement.

Nothing here reaches the network, and nothing here writes outside the folder it
is given. See ``docs/plans/proposals/runs-and-stays-local.md``.

PROTOTYPE — not ratified.
"""

from .album import Album, Built, Provenance
from .compose import ScaleUnknown, build, picture_to_site
from .finder import ShapeFinder, UnknownFinderError, get, names, register
from .models import FoundShape, Picture, ScaleReference, ShapeKind
from .plain import PlainFinder
from .stated import MissingDescriptionError, StatedFinder

__all__ = [
    "Album",
    "Built",
    "FoundShape",
    "Provenance",
    "Picture",
    "PlainFinder",
    "MissingDescriptionError",
    "ScaleReference",
    "ScaleUnknown",
    "ShapeFinder",
    "ShapeKind",
    "StatedFinder",
    "UnknownFinderError",
    "get",
    "names",
    "build",
    "picture_to_site",
    "register",
]
