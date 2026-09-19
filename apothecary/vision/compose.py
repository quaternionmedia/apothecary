"""Turning found shapes into an arrangement you could build.

The important decision here is what happens when nobody has said how big the
picture is in the real world. Answer: the pieces are still placed, but with no
size attached and marked ``unsized``, so the overlap check stays quiet instead
of being confidently wrong about millimetres nobody supplied. Nothing is
inferred and there is no default.

A picture is flat and a thing you build is not, so a thickness has to come from
somewhere. It is a guess, it is written down as a guess in every node's note,
and it is the first thing to replace once real measurements exist.

PROTOTYPE — not ratified. See ``docs/plans/features/scale-references.md``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from ..hierarchy import Assembly, Site
from ..models.bounds import BoundingBox3D
from ..models.vectors import Vector3D
from ..transforms import Rotate, Translate
from .album import Album, Built, Provenance
from .models import Picture, ScaleReference

if TYPE_CHECKING:  # pragma: no cover - for readers and type checkers only
    from ..vocabulary import WordList

# How thick a flat shape is assumed to be, as a fraction of its shorter side.
# A guess, and named as one everywhere it lands.
THICKNESS_GUESS = 0.15

# Thickness never drops below this, so a very thin shape still has a body.
MIN_THICKNESS = 0.01


class ScaleUnknown(ValueError):
    """A real-world size was asked for and the reference could not supply one."""


def picture_to_site(
    picture: Picture,
    *,
    name: Optional[str] = None,
    scale: Optional[ScaleReference] = None,
    words: Optional["WordList"] = None,
    require_scale: bool = False,
) -> Assembly:
    """Build one arrangement from everything found in one picture.

    Just the arrangement. Use :func:`build` when you also want to know how each
    piece came to be there.
    """
    return build(picture, name=name, scale=scale, words=words, require_scale=require_scale).site


def build(
    picture: Picture,
    *,
    name: Optional[str] = None,
    scale: Optional[ScaleReference] = None,
    words: Optional["WordList"] = None,
    require_scale: bool = False,
    picture_path: Optional[Path] = None,
) -> Built:
    """Build one arrangement, and record how each piece came to be there.

    ``scale`` says how to turn fractions of the picture into millimetres. Leave
    it out and the pieces are placed without a size. Set ``require_scale`` to
    refuse rather than place unsized pieces.
    """
    # Fetched here rather than at the top of the file. The vocabulary needs to
    # describe shapes, and shapes live in this package, so importing it up there
    # made the two packages depend on each other and whichever was imported
    # second failed.
    from ..vocabulary import WordShape, starter_words, word_for

    # `or` would swallow an explicitly empty list, which a caller supplying a
    # curated vocabulary would never expect.
    vocabulary = starter_words() if words is None else words
    per_unit = scale.millimetres_per_unit(picture) if scale else None

    if require_scale and per_unit is None:
        raise ScaleUnknown(
            "no usable real-world reference: give a width for the whole picture, "
            "or name a shape whose real width is known"
        )

    sized = per_unit is not None
    factor = per_unit if sized else 1.0
    # Across and down are measured against different edges: a position across
    # is a fraction of the picture's width, a position down is a fraction of its
    # height, and the size supplied is millimetres across. Multiplying a
    # downward fraction by that alone stretches every picture that is not
    # square — on an ordinary photograph, by a third.
    tallness = picture.pixel_height / picture.pixel_width

    pieces = []
    known: dict = {}
    for index, shape in enumerate(picture.shapes, start=1):
        choice = word_for(shape)
        word = vocabulary.get(choice.word)

        # Prefer the shape's own sides over its upright box. A bar lying at 35°
        # has an upright box far larger than the bar, and building that box
        # would be building the wrong object.
        if shape.measured_sides:
            width = max(shape.long_side * factor, MIN_THICKNESS)
            depth = max(shape.short_side * factor, MIN_THICKNESS)
        else:
            width = max(shape.width * factor, MIN_THICKNESS)
            depth = max(shape.height * tallness * factor, MIN_THICKNESS)
        thickness = max(min(width, depth) * THICKNESS_GUESS, MIN_THICKNESS)

        piece = word.make(
            f"{choice.word}_{index}",
            WordShape(width=width, depth=depth, height=thickness, sized=sized),
        )

        # Words are built with one corner at the origin. Shift each piece onto
        # its own middle before anything else: a piece turned about its corner
        # swings away from where it was seen, and a piece turned about its
        # middle stays put.
        if piece.base is not None:
            piece.base = Translate(
                v=Vector3D(x=-width / 2, y=-depth / 2, z=0.0), children=[piece.base]
            )
            # A picture counts its angles the other way round from a build,
            # because the downward direction is flipped just below. Turning the
            # other way puts the piece back the way it looked.
            if shape.turned_degrees:
                piece.base = Rotate(
                    a=Vector3D(x=0.0, y=0.0, z=-shape.turned_degrees),
                    children=[piece.base],
                )

        centre = shape.centre
        piece.position = Vector3D(
            x=centre.x * factor,
            # A picture counts downward from the top; a build counts away from
            # the front. Flipping here keeps what you see and what you build the
            # same way up.
            y=(1.0 - centre.y) * tallness * factor,
            z=0.0,
        )
        # The piece now straddles its own position, so its extent does too.
        piece.footprint = (
            BoundingBox3D(
                min_point=Vector3D(x=-width / 2, y=-depth / 2, z=0.0),
                max_point=Vector3D(x=width / 2, y=depth / 2, z=thickness),
            )
            if sized
            else None
        )
        piece.status = None if sized else "unsized"
        # The viewer already gathers nodes by category and offers them as
        # filters. Naming the word here means grouping by word costs nothing:
        # the machinery for it was already there.
        piece.category = choice.word
        piece.comment = (
            f"{choice.word} because {choice.reason}; "
            f"found by {picture.finder} at {shape.confidence:.2f} confidence; "
            f"thickness is a guess at {THICKNESS_GUESS:g} of the shorter side"
            + ("" if sized else "; no real-world size was supplied")
        )
        known[piece.name] = Provenance(
            word=choice.word,
            reason=choice.reason,
            finder=picture.finder,
            confidence=shape.confidence,
            origin=shape.origin,
            sized=sized,
            turned_degrees=shape.turned_degrees,
            thickness_guessed=True,
        )
        pieces.append(piece)

    site = Site(name or picture.name, structures=pieces)
    site.comment = (
        f"from the picture {picture.name!r}, {len(pieces)} piece(s), "
        f"found by {picture.finder}"
        + (
            f"; {per_unit:g} mm across the full width"
            if sized
            else "; no real-world size, so nothing here is measured"
        )
    )
    return Built(
        site=site,
        album=Album(
            site_name=site.name,
            picture_name=picture.name,
            picture_path=picture_path,
            pixel_width=picture.pixel_width,
            pixel_height=picture.pixel_height,
            finder=picture.finder,
            millimetres_across=per_unit,
            provenance=known,
        ),
    )


__all__ = ["MIN_THICKNESS", "THICKNESS_GUESS", "ScaleUnknown", "build", "picture_to_site"]
