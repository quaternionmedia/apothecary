"""A whiteboard's notes: its writing, kept with what it is about.

A note is a mark sorted as writing (``marks``): where it is, the mark it lies in
or nearest, and what it says where a person typed that. Apothecary reads no
handwriting. A size typed for a note beside a line is offered as the line's
length, which says how wide the whole picture is; it is taken by a person, by
building with that width.

The way out is ``apothecary/finders/words.py``: a whiteboard's words to
looksatwords as one transcript, and a note's region to qmcp. Nothing here
reaches anything.

A prototype: no ratified record governs it.
"""

from __future__ import annotations

import math
import re
from typing import List, Optional, Sequence, Tuple

from pydantic import BaseModel

from .marks import Answers, Kind, Mark, Words, _overlap_of
from .outline import WIDER_BY
from .plain import WORKING_EDGE

# How far a note may lie from a mark and still be about it, as a share of the picture.
NEAR = 0.15

# A size as a person types one: a number and a unit, and how many millimetres its unit is.
_SIZE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(mm|cm|m|in|\")(?![a-z])", re.IGNORECASE)
_MILLIMETRES = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4, '"': 25.4}


class Offer(BaseModel):
    """A size a note states for the line it is beside, and the picture's width
    that follows from it."""

    millimetres: float
    of: str
    picture_mm: float


class Note(BaseModel):
    """One mark of writing, with what it is about and what it says."""

    id: str
    min: Tuple[float, float]
    max: Tuple[float, float]
    # The mark it lies in, or the nearest diagram's mark, and which of the two.
    about: Optional[str] = None
    lies: Optional[str] = None
    colour: str = ""
    words: Optional[str] = None
    by: Optional[str] = None
    # What a model said it holds, kept beside a person's words and never over them.
    read: Optional[str] = None
    offer: Optional[Offer] = None


def _gap(a: Mark, b: Mark) -> float:
    """How far apart two marks' boxes are, as a share of the picture; none when
    they touch or overlap."""
    across = max(a.min_point.x - b.max_point.x, b.min_point.x - a.max_point.x, 0.0)
    down = max(a.min_point.y - b.max_point.y, b.min_point.y - a.max_point.y, 0.0)
    return math.hypot(across, down)


def notes_of(
    marks: Sequence[Mark], answers: Optional[Answers], tallness: float = 1.0
) -> List[Note]:
    """The notes among some marks, top to bottom as the marks are, each with a
    person's words for it where the answers hold any. ``tallness`` is the
    picture's height over its width, which a line's length is read with."""
    by_id = {mark.id: mark for mark in marks}
    drawn = [mark for mark in marks if mark.kind is Kind.DIAGRAM]
    found: List[Note] = []
    for mark in marks:
        if mark.kind is not Kind.WRITING:
            continue
        note = Note(
            id=mark.id,
            min=(mark.min_point.x, mark.min_point.y),
            max=(mark.max_point.x, mark.max_point.y),
            colour=mark.colour,
        )
        if mark.inside and mark.inside in by_id:
            note.about, note.lies = mark.inside, "inside"
        else:
            nearest = min(drawn, key=lambda other: _gap(mark, other), default=None)
            if nearest is not None and _gap(mark, nearest) <= NEAR:
                note.about, note.lies = nearest.id, "beside"
        for said in answers.words if answers else []:
            if _overlap_of(note.min, note.max, said.min, said.max) > 0.5:
                note.words, note.by = said.text, said.by
        about = by_id.get(note.about) if note.about else None
        if note.words and about is not None and about.line:
            note.offer = _offer(note.words, about, tallness)
        found.append(note)
    return found


def _offer(words: str, line: Mark, tallness: float) -> Optional[Offer]:
    """The size some words state, as the length of the line they are beside."""
    stated = _SIZE.match(words)
    if stated is None:
        return None
    millimetres = float(stated.group(1).replace(",", ".")) * _MILLIMETRES[stated.group(2).lower()]
    # A stroke is read wider than it is drawn, by this much at each end.
    wider = 2 * WIDER_BY / WORKING_EDGE
    length = math.hypot(
        max(line.max_point.x - line.min_point.x - wider, 0.0),
        max((line.max_point.y - line.min_point.y) * tallness - wider, 0.0),
    )
    if millimetres <= 0 or length <= 0:
        return None
    return Offer(millimetres=millimetres, of=line.id, picture_mm=round(millimetres / length, 1))


def say(marks: Sequence[Mark], mark_id: str, text: str, by: str = "you") -> Words:
    """A person's words for one note, as they are kept."""
    mark = next((m for m in marks if m.id == mark_id), None)
    if mark is None:
        raise KeyError(f"no mark {mark_id!r}; have {[m.id for m in marks]}")
    if mark.kind is not Kind.WRITING:
        raise ValueError(
            f"{mark_id} is {mark.kind.value}, not writing: `photo marks --say {mark_id}=writing` "
            "says it is, and then it has words"
        )
    if not text.strip():
        raise ValueError(f"{mark_id}: a note's words are what it says, and these are empty")
    return Words(
        min=(mark.min_point.x, mark.min_point.y),
        max=(mark.max_point.x, mark.max_point.y),
        text=text.strip(),
        by=by,
    )


def transcript(notes: Sequence[Note]) -> str:
    """A whiteboard's words in reading order, a line a note, each saying what it
    is about. Notes nobody has typed or read are left out."""
    lines = []
    for note in notes:
        said = note.words or note.read
        if not said:
            continue
        where = f" ({note.lies} {note.about})" if note.about else ""
        lines.append(f"{note.id}{where}: {said}")
    return "\n".join(lines)


__all__ = [
    "NEAR",
    "Note",
    "Offer",
    "notes_of",
    "say",
    "transcript",
]
