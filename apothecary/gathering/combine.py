"""Putting the pictures that belong together into one arrangement.

Three things happen here and they are deliberately different from each other:

- **Pictures of the same thing** become **one** set of pieces. A piece seen in
  two pictures is one piece, and it says which pictures saw it.
- **Pictures of parts of one larger thing** stay separate and are placed **side
  by side**, with a gap. They are not the same pieces and are not treated as
  though they were.
- **A picture on its own** is placed on its own, unchanged.

Everything lands in one ordinary arrangement, of the kind this tool already
knows how to show. There is no picture mode and no second viewer.

## Seeing a piece twice does not make it certain

A piece seen in two pictures is better evidence than a piece seen in one, and it
is nowhere near twice as good: the same finder, with the same weaknesses,
looking at the same object twice will make the same mistake twice. So agreement
moves confidence part of the way toward certainty and can never reach it. The
sum is written out in :func:`agreed_confidence` and the reasoning is the point,
not the number.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

from ..hierarchy import Assembly, Site
from ..models.vectors import Vector3D
from ..vision.album import Album, Built, Provenance
from .models import ALONE, SAME_THING, Cluster, Gathering, Kinship

# How much of the remaining doubt agreement between pictures may remove. Half,
# and never all of it: two sightings by one finder are not independent.
AGREEMENT_WEIGHT = 0.5

# The gap left between two parts of one larger thing, as a share of the width of
# the part to its left. Wide enough to read as separate, narrow enough to read
# as belonging together.
GAP = 0.25

SAFE = re.compile(r"[^A-Za-z0-9]+")


def tidy(name: str) -> str:
    """A name that can be a node and part of a dotted path.

    Dots are how every node in this tool is addressed, so a name carrying one
    would address something that is not itself.
    """
    cleaned = SAFE.sub("_", name).strip("_")
    return cleaned or "picture"


def _unused(wanted: str, taken: set) -> str:
    """A name nothing else in this arrangement has.

    Tidying turns "shed door" and "shed-door" into the same word, and two pieces
    sharing one name meant the second quietly replaced the first — a piece
    vanishing from the arrangement with nothing said. Numbers are added until
    the name is free, and the number is part of the name, so nothing is lost.
    """
    if wanted not in taken:
        taken.add(wanted)
        return wanted
    count = 2
    while f"{wanted}_{count}" in taken:
        count += 1
    settled = f"{wanted}_{count}"
    taken.add(settled)
    return settled


def agreed_confidence(confidences: Sequence[float]) -> float:
    """One number for a piece several pictures agree on.

    Starts from what the pictures typically said, then closes part of the gap to
    certainty — more for more sightings, never all of it, and never above the
    ceiling below. Two sightings from one finder are not two independent
    opinions, and a sum that treated them as though they were would report near
    certainty about a piece that has only ever been guessed at.
    """
    if not confidences:
        return 0.0
    typical = sum(confidences) / len(confidences)
    extra = len(confidences) - 1
    if extra <= 0:
        return typical
    # Scaled by what the pictures actually said, not only by how many of them
    # there were. Without this last factor, two sightings of something the
    # finder was not sure about *at all* came back at twenty-five per cent —
    # confidence conjured out of two admissions of ignorance.
    closed = (1.0 - typical) * (1.0 - 1.0 / (extra + 1)) * AGREEMENT_WEIGHT * typical
    return min(0.99, typical + closed)


def _piece_index(name: str) -> Optional[int]:
    """The number a built piece carries, which is its shape's place in the picture."""
    tail = name.rsplit("_", 1)[-1]
    return int(tail) - 1 if tail.isdigit() else None


def _pieces_of(site: Assembly) -> List[Assembly]:
    return list(site.children or [])


def _shape_to_piece(site: Assembly) -> Dict[int, Assembly]:
    found: Dict[int, Assembly] = {}
    for piece in _pieces_of(site):
        where = _piece_index(piece.name)
        if where is not None:
            found[where] = piece
    return found


def _anchor(cluster: Cluster, built: Dict[str, Built]) -> str:
    """The picture the others are merged into: the one that saw the most."""
    return max(
        cluster.pictures,
        key=lambda name: (len(_pieces_of(built[name].site)), name),
    )


def _mapping(kinship: Optional[Kinship], anchor: str, other: str) -> Dict[int, int]:
    """Which shape in the other picture is which shape in the anchor.

    Empty when the two were never judged to be of the same thing, which is the
    honest outcome for a group joined through a third picture: nothing is
    assumed to correspond, and everything is added as newly seen.
    """
    if kinship is None or kinship.verdict != SAME_THING:
        return {}
    if kinship.left == anchor and kinship.right == other:
        return {right: left for left, right in kinship.pairs}
    if kinship.right == anchor and kinship.left == other:
        return dict(kinship.pairs)
    return {}


def _merge_same(
    cluster: Cluster, built: Dict[str, Built], gathering: Gathering
) -> Tuple[Assembly, Dict[str, Provenance], List[str]]:
    anchor = _anchor(cluster, built)
    base = built[anchor].site.model_copy(deep=True)
    pieces = _pieces_of(base)
    by_shape = _shape_to_piece(base)
    known: Dict[str, Provenance] = {}
    agreeing: Dict[str, List[float]] = {}

    taken = {piece.name for piece in pieces}
    for piece in pieces:
        about = built[anchor].album.provenance.get(piece.name)
        if about is None:
            continue
        known[piece.name] = about.model_copy(deep=True)
        known[piece.name].seen_in = [anchor]
        agreeing[piece.name] = [about.confidence]

    notes: List[str] = [f"{anchor} saw the most, so it is what the others were merged into"]

    for other in sorted(name for name in cluster.pictures if name != anchor):
        kinship = gathering.between(anchor, other)
        matches = _mapping(kinship, anchor, other)
        if not matches and kinship is not None and kinship.verdict != SAME_THING:
            notes.append(
                f"{other} was never judged to be of the same thing as {anchor} "
                f"directly — it joined through another picture — so none of its "
                f"shapes were assumed to be shapes {anchor} already saw"
            )
        # Every piece of the other picture, including any whose name does not
        # end in a number. An earlier version looked only at the numbered ones
        # and dropped the rest without a word — a piece disappearing from an
        # arrangement is precisely the failure this module exists to avoid.
        numbered = _shape_to_piece(built[other].site)
        place_of = {id(piece): where for where, piece in numbered.items()}
        for piece in _pieces_of(built[other].site):
            about = built[other].album.provenance.get(piece.name)
            if about is None:
                continue
            shape_here = place_of.get(id(piece))
            landed = matches.get(shape_here) if shape_here is not None else None
            if landed is not None and landed in by_shape:
                on = by_shape[landed]
                known[on.name].seen_in.append(other)
                agreeing[on.name].append(about.confidence)
                continue
            fresh = piece.model_copy(deep=True)
            fresh.name = _unused(f"{tidy(other)}_{tidy(fresh.name)}", taken)
            pieces.append(fresh)
            known[fresh.name] = about.model_copy(deep=True)
            known[fresh.name].seen_in = [other]
            agreeing[fresh.name] = [about.confidence]
            notes.append(f"{fresh.name} was only ever seen in {other}")

    for name, confidences in agreeing.items():
        about = known[name]
        about.confidence = agreed_confidence(confidences)
        seen = about.seen_in or [anchor]
        piece = next((p for p in pieces if p.name == name), None)
        if piece is not None:
            piece.comment = (
                f"{about.word} because {about.reason}; seen in "
                f"{len(seen)} picture(s) — {', '.join(sorted(seen))} — "
                f"at {about.confidence:.2f} confidence once they were put together"
                + ("" if about.sized else "; no real-world size was supplied")
            )

    base.children = pieces
    base.name = tidy(cluster.name)
    base.comment = (
        f"one thing, seen in {len(cluster.pictures)} picture(s): "
        f"{', '.join(sorted(cluster.pictures))}. {len(pieces)} piece(s)."
    )
    return base, known, notes


def _across(part: Assembly) -> float:
    """How wide a part really is, edge to edge.

    Measured from where each piece sits *and how big it is*. Measuring only the
    middles of the pieces reported three arrangements nearly four thousand units
    across as one unit across, and they were then laid out a unit apart — every
    one of them on top of the others, under a heading promising they would not
    be.
    """
    left: List[float] = []
    right: List[float] = []
    for piece in _pieces_of(part):
        if piece.position is None:
            continue
        middle = piece.position.x
        half = 0.0
        if piece.footprint is not None:
            half = max(abs(piece.footprint.max_point.x), abs(piece.footprint.min_point.x))
        left.append(middle - half)
        right.append(middle + half)
    if not left:
        return 1.0
    return max(max(right) - min(left), 0.0) or 1.0


def _place_side_by_side(parts: Sequence[Assembly]) -> None:
    """Lay parts out in a row, left to right, without overlapping."""
    offset = 0.0
    for part in parts:
        widest = _across(part)
        part.position = Vector3D(x=offset, y=0.0, z=0.0)
        offset += widest * (1.0 + GAP)


def combine(
    cluster: Cluster, built: Dict[str, Built], gathering: Gathering
) -> Tuple[Assembly, Dict[str, Provenance], List[str]]:
    """One arrangement for one group of pictures, and what is known about it."""
    missing = [name for name in cluster.pictures if name not in built]
    if missing:
        raise KeyError(
            f"{cluster.name!r} names picture(s) nothing was built from: "
            f"{', '.join(sorted(missing))}"
        )

    if cluster.kind == ALONE:
        only = cluster.pictures[0]
        alone = built[only].site.model_copy(deep=True)
        alone.name = tidy(cluster.name)
        known = {
            name: about.model_copy(deep=True)
            for name, about in built[only].album.provenance.items()
        }
        for about in known.values():
            about.seen_in = [only]
        return alone, known, list(cluster.because)

    if cluster.kind == SAME_THING:
        return _merge_same(cluster, built, gathering)

    parts: List[Assembly] = []
    known: Dict[str, Provenance] = {}
    notes: List[str] = list(cluster.because)
    for members in cluster.made_of:
        inner = Cluster(
            name=f"part_{tidy(members[0])}",
            kind=SAME_THING if len(members) > 1 else ALONE,
            pictures=list(members),
            because=[],
        )
        part, about, said = combine(inner, built, gathering)
        parts.append(part)
        for name, one in about.items():
            known[f"{part.name}.{name}"] = one
        notes.extend(said)
    _place_side_by_side(parts)

    larger = Site(tidy(cluster.name), structures=parts)
    larger.comment = (
        f"one larger thing, made of {len(parts)} part(s) placed side by side; "
        f"the parts are not the same pieces and were not merged"
    )
    return larger, known, notes


def whole_gathering(
    gathering: Gathering, built: Dict[str, Built], *, name: str = "gathering"
) -> Built:
    """Everything that resolved, in one arrangement, laid out in a row.

    Pictures nothing could be read from are not here. They are not silently
    gone: ``gathering.set_aside`` says which and why, and the report and the map
    both show them.
    """
    placed: List[Assembly] = []
    known: Dict[str, Provenance] = {}
    notes: List[str] = []
    for cluster in gathering.clusters:
        usable = [p for p in cluster.pictures if p in built]
        if not usable:
            continue
        if len(usable) != len(cluster.pictures):
            notes.append(
                f"{cluster.name}: only {len(usable)} of {len(cluster.pictures)} "
                "pictures had anything built from them"
            )
            cluster = cluster.model_copy(
                update={
                    "pictures": usable,
                    "kind": ALONE if len(usable) == 1 else cluster.kind,
                    "made_of": [
                        [p for p in part if p in built]
                        for part in cluster.made_of
                        if any(p in built for p in part)
                    ],
                }
            )
        part, about, said = combine(cluster, built, gathering)
        placed.append(part)
        for path, one in about.items():
            known[f"{part.name}.{path}"] = one
        notes.extend(said)

    _place_side_by_side(placed)
    site = Site(tidy(name), structures=placed)
    joined = [c for c in gathering.clusters if c.kind != ALONE]
    site.comment = (
        f"{len(gathering.readings)} picture(s) taken in; "
        f"{len(gathering.readable())} readable; "
        f"{len(joined)} group(s) of pictures turned out to be of the same thing "
        f"or of one larger thing; {len(gathering.set_aside)} set aside"
    )

    first = next(iter(built.values()), None)
    album = Album(
        site_name=site.name,
        picture_name=f"{len(gathering.readings)} pictures",
        pixel_width=first.album.pixel_width if first else 1,
        pixel_height=first.album.pixel_height if first else 1,
        finder=first.album.finder if first else "none",
        provenance=known,
    )
    return Built(site=site, album=album)


__all__ = [
    "AGREEMENT_WEIGHT",
    "GAP",
    "agreed_confidence",
    "combine",
    "tidy",
    "whole_gathering",
]
