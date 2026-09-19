"""The five words we start with.

Chosen without a photograph in hand, which makes them a guess. They are meant to
be replaced once somebody has pointed a camera at a real workbench. See the note
at the end of ``docs/plans/HANDOFF.md``.

Each is built out of pieces the tool already had — nothing new was invented to
make a word possible.

PROTOTYPE — not ratified.
"""

from __future__ import annotations

from ..booleans import Difference
from ..hierarchy import Assembly
from ..models.vectors import Vector3D
from ..primitives import Cube, Cylinder
from ..transforms import Translate
from .word import Word, WordList, WordShape


def _plate(name: str, shape: WordShape) -> Assembly:
    """A flat slab. The default reading of a rectangle."""
    return Assembly(
        name=name,
        role="word",
        base=Cube(size=Vector3D(x=shape.width, y=shape.depth, z=shape.height)),
    )


def _disc(name: str, shape: WordShape) -> Assembly:
    """A round flat piece. The default reading of a circle."""
    return Assembly(
        name=name,
        role="word",
        base=Cylinder(h=shape.height, r=max(shape.width, shape.depth) / 2),
    )


def _post(name: str, shape: WordShape) -> Assembly:
    """A round upright. A circle that is much taller than it is wide."""
    return Assembly(
        name=name,
        role="word",
        base=Cylinder(h=shape.height, r=max(shape.width, shape.depth) / 2),
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
        base=Cylinder(h=shape.height, r1=max(shape.width, shape.depth) / 2, r2=0.001, fn=3),
    )


def starter_words() -> WordList:
    """The vocabulary as it stands. Five words, all guesses."""
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
