"""The starter words.

Chosen without a photograph in hand, which makes them a guess. They are meant to
be replaced once somebody has pointed a camera at a real workbench.

Each is built from the tool's own primitives.

A prototype: no ratified record governs it.
"""

from __future__ import annotations

from ..booleans import Difference
from ..hierarchy import Assembly
from ..models.vectors import Vector3D
from ..primitives import Cube, Cylinder
from ..transforms import Scale, Translate
from .word import Word, WordList, WordShape


def _plate(name: str, shape: WordShape) -> Assembly:
    """A flat slab. The default reading of a rectangle."""
    return Assembly(
        name=name,
        role="word",
        base=Cube(size=Vector3D(x=shape.width, y=shape.depth, z=shape.height)),
    )


def _corner_at_origin(shape: WordShape, round_thing) -> Translate:
    """Every word is built with one corner at the origin (compose.py shifts each
    piece onto its middle). A cylinder is centred on its axis, so a round word
    stands on the middle of its box -- without this, every disc, post and wedge
    would be drawn half its size away from where it was seen."""
    return Translate(
        v=Vector3D(x=shape.width / 2, y=shape.depth / 2, z=0.0), children=[round_thing]
    )


def _round(shape: WordShape):
    """A cylinder whose footprint is ``width`` x ``depth``: a circle when the two
    are equal, else that circle squeezed along its shorter side into the ellipse
    the shape was found as. A circle of the longer side would put a mesh wider
    than the footprint, the bounds and the editor all say it is."""
    across = max(shape.width, shape.depth)
    circle = Cylinder(h=shape.height, r=across / 2)
    if shape.width == shape.depth:
        return circle
    # The circle keeps the longer side's radius, so it is faceted as that circle
    # is; a unit circle scaled up would be faceted as a pentagon.
    return Scale(
        v=Vector3D(x=shape.width / across, y=shape.depth / across, z=1.0), children=[circle]
    )


def _disc(name: str, shape: WordShape) -> Assembly:
    """A round flat piece. The default reading of a circle."""
    return Assembly(
        name=name,
        role="word",
        base=_corner_at_origin(shape, _round(shape)),
    )


def _post(name: str, shape: WordShape) -> Assembly:
    """A round upright. A circle that is much taller than it is wide."""
    return Assembly(
        name=name,
        role="word",
        base=_corner_at_origin(shape, _round(shape)),
    )


def _slot(name: str, shape: WordShape) -> Assembly:
    """A slab with a channel cut through it. The default reading of a long thin gap."""
    outer = Cube(size=Vector3D(x=shape.width, y=shape.depth, z=shape.height))
    channel = Translate(
        v=Vector3D(x=shape.width * 0.25, y=-shape.depth * 0.1, z=shape.height * 0.25),
        children=[Cube(size=Vector3D(x=shape.width * 0.5, y=shape.depth * 1.2, z=shape.height))],
    )
    return Assembly(
        name=name,
        role="word",
        base=Difference(children=[outer, channel]),
    )


def _wedge(name: str, shape: WordShape) -> Assembly:
    """A tapering block. The default reading of a triangle."""
    return Assembly(
        name=name,
        role="word",
        base=_corner_at_origin(
            shape,
            Cylinder(h=shape.height, r1=max(shape.width, shape.depth) / 2, r2=0.001, fn=3),
        ),
    )


def starter_words() -> WordList:
    """The vocabulary as it stands: every word a guess."""
    words = WordList()
    words.add(Word(name="plate", describes="a flat slab", build=_plate, tags=["flat"]))
    words.add(Word(name="disc", describes="a round flat piece", build=_disc, tags=["round"]))
    words.add(Word(name="post", describes="a round upright", build=_post, tags=["round", "tall"]))
    words.add(
        Word(name="slot", describes="a slab with a channel", build=_slot, tags=["flat", "cut"])
    )
    words.add(Word(name="wedge", describes="a tapering block", build=_wedge, tags=["angled"]))
    return words


__all__ = ["starter_words"]
