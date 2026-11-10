"""A whiteboard photographed again: what changed, proposed and not done.

Two readings of one whiteboard, an earlier and a later, each squared to it so a
place on one is the same place on the other. Each shape of the earlier is
matched to the nearest of its family in the later. What follows is a list of
proposals: a shape that moved, one that changed size, one that is new, one that
is gone. A shape that matches and has not changed proposes nothing. A proposal
changes nothing; a person takes it or leaves it, and what they took is what the
later arrangement is built from. A shape whose sides a person stated is not
proposed over: its row says the drawing and the person disagree, and by how
much, and cannot be taken.

Each row taken or left is an example, as a word on a mark is.

A prototype: no ratified record governs it.
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Collection, List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field

from .models import FoundShape, Picture

FORMAT = "apothecary.again/1"

# A shape further than this from where it was, as a share of the picture, has moved.
MOVED = 0.012
# A shape whose long or short side differs by more than this share of itself has
# changed size.
RESIZED = 0.06
# A shape of the later picture further than this from every one of its family in
# the earlier is not the same shape.
REACH = 0.25


class Change(str, Enum):
    MOVED = "moved"
    RESIZED = "resized"
    NEW = "new"
    GONE = "gone"
    # The drawing changed a shape whose sides a person stated.
    DISAGREES = "disagrees"


class Proposal(BaseModel):
    """One row: what changed, of which shape, and by how much."""

    number: int
    change: Change
    # The shape's place in the earlier picture's list, and in the later's.
    before: Optional[int] = None
    after: Optional[int] = None
    kind: str
    says: str
    takeable: bool = True


class Taken(BaseModel):
    """What a person did with each row, as it is kept."""

    format: str = FORMAT
    rows: List[Proposal] = Field(default_factory=list)
    taken: List[int] = Field(default_factory=list)


def _shift(a: FoundShape, b: FoundShape, tallness: float) -> float:
    return math.hypot(a.centre.x - b.centre.x, (a.centre.y - b.centre.y) * tallness)


def _sides(shape: FoundShape, tallness: float) -> Tuple[float, float]:
    if shape.measured_sides:
        return shape.long_side, shape.short_side
    wide, tall = shape.width, shape.height * tallness
    return max(wide, tall), min(wide, tall)


def compare(before: Picture, after: Picture, stated: Collection[int] = ()) -> List[Proposal]:
    """What the later picture proposes of the earlier's shapes. ``stated`` holds
    the places, in the earlier's list, of shapes whose sides a person gave."""
    tallness = after.pixel_height / after.pixel_width
    pairs: List[Tuple[float, int, int]] = []
    for i, old in enumerate(before.shapes):
        for j, new in enumerate(after.shapes):
            if old.kind is new.kind and _shift(old, new, tallness) <= REACH:
                pairs.append((_shift(old, new, tallness), i, j))
    matched_old: dict = {}
    matched_new: set = set()
    for _, i, j in sorted(pairs):
        if i not in matched_old and j not in matched_new:
            matched_old[i] = j
            matched_new.add(j)

    rows: List[Tuple[Change, Optional[int], Optional[int], str, str, bool]] = []
    for i, old in enumerate(before.shapes):
        if i not in matched_old:
            rows.append(
                (
                    Change.GONE,
                    i,
                    None,
                    old.kind.value,
                    "it is not on the whiteboard now: drop it",
                    True,
                )
            )
            continue
        j = matched_old[i]
        new = after.shapes[j]
        moved = _shift(old, new, tallness)
        was, now = _sides(old, tallness), _sides(new, tallness)
        grew = max(
            abs(now[0] - was[0]) / max(was[0], 1e-9), abs(now[1] - was[1]) / max(was[1], 1e-9)
        )
        cuts = len(new.cuts) - len(old.cuts)
        if grew > RESIZED or cuts:
            by = f"its long side is {now[0] / max(was[0], 1e-9):.2f} times what it was"
            if cuts:
                by += f", with {abs(cuts)} cut(s) {'more' if cuts > 0 else 'fewer'}"
            if i in stated:
                rows.append(
                    (
                        Change.DISAGREES,
                        i,
                        j,
                        old.kind.value,
                        f"the drawing and a person's sides disagree: {by}",
                        False,
                    )
                )
            else:
                rows.append((Change.RESIZED, i, j, old.kind.value, by, True))
        elif moved > MOVED:
            rows.append(
                (
                    Change.MOVED,
                    i,
                    j,
                    old.kind.value,
                    f"it is {moved:.3f} of the picture's width from where it was",
                    True,
                )
            )
    for j, new in enumerate(after.shapes):
        if j not in matched_new:
            rows.append(
                (Change.NEW, None, j, new.kind.value, "it was not there before: make it", True)
            )
    return [
        Proposal(
            number=n, change=change, before=i, after=j, kind=kind, says=says, takeable=takeable
        )
        for n, (change, i, j, kind, says, takeable) in enumerate(rows, start=1)
    ]


def taken_from(
    before: Picture, after: Picture, proposals: Sequence[Proposal], taken: Collection[int]
) -> Picture:
    """The earlier picture's shapes with the rows a person took: a moved or
    resized shape as the later has it, a new one added, a gone one dropped.
    Every row left, the earlier's shape stays as it was."""
    wanted = set(taken)
    known = {proposal.number: proposal for proposal in proposals}
    for number in wanted:
        if number not in known:
            raise KeyError(f"no row {number}; have {sorted(known)}")
        if not known[number].takeable:
            raise ValueError(
                f"row {number} cannot be taken: {known[number].says}. A person's sides stand "
                "until that person changes them"
            )
    shapes: List[Optional[FoundShape]] = list(before.shapes)
    added: List[FoundShape] = []
    for proposal in proposals:
        if proposal.number not in wanted:
            continue
        if proposal.change is Change.GONE:
            shapes[proposal.before] = None
        elif proposal.change is Change.NEW:
            added.append(after.shapes[proposal.after])
        else:
            shapes[proposal.before] = after.shapes[proposal.after]
    return after.model_copy(update={"shapes": [s for s in shapes if s is not None] + added})


__all__ = [
    "Change",
    "FORMAT",
    "MOVED",
    "Proposal",
    "REACH",
    "RESIZED",
    "Taken",
    "compare",
    "taken_from",
]
