"""Do the matched shapes sit in the same places relative to each other?

This is the check that turns a coincidence into evidence, and it was added
because the meter caught its absence: without it, two photographs of entirely
different things were joined into one object, because both happened to contain a
square, a disc and a triangle of roughly the same proportions. Matching shapes
one at a time cannot tell that apart from a real match. Matching them *as an
arrangement* can.

The idea is small. If two photographs are of one thing, then stepping sideways
and stepping closer are the only differences, and both are covered by one
sum: every shape moves by the same amount and everything scales by the same
factor. So look for a single move-and-scale that puts all the matched shapes of
one picture on top of their partners in the other, and see how badly it fits. A
real pair fits well. A coincidence does not fit at all.

**Two known limits, stated rather than hidden.**

- **Turning the camera is not covered.** A photograph taken with the camera
  rotated ninety degrees will not fit, and will be judged unrelated. Handheld
  photographs of a workbench are usually roughly upright, which is why this is
  a limit rather than a defect, but it is a limit.
- **Two matched shapes are not enough to fit a move and a scale**, because the
  sum has more unknowns than it has facts. With exactly two, all that can be
  checked is whether the line between them points the same way; that is one real
  check rather than three, and it is reported as the weaker thing it is.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from .models import ShapeMark

# How far a matched shape may sit from where the single move-and-scale says it
# should, as a share of the picture, averaged over all of them.
#
# Four percent, and the number was measured rather than chosen. At ten percent —
# the first guess, which looked generous and harmless — ten pairs of unrelated
# photographs were joined into single objects in one folder of twenty-seven.
# Genuine pairs come in at nought to two percent; the false ones sat at four to
# eight. Six percent still let three through. Four lets none through and costs
# nothing measurable in what it finds.
DRIFT_ALLOWED = 0.04

# The line between two matched shapes may point this many degrees differently
# before the pair is called a coincidence.
TURN_ALLOWED = 25.0

# A move-and-scale outside this range is not a photographer stepping closer, it
# is the sum finding a way to make nonsense fit.
SCALE_RANGE = (0.2, 5.0)


@dataclass(frozen=True)
class Fit:
    """Whether the matched shapes really are the same arrangement.

    ``kept`` is the important part. Some of the shapes that looked alike one by
    one will be coincidences, and the arrangement is what tells them apart — so
    this does not merely pass or fail the whole set, it says **which** of the
    matches belong to one move-and-scale and hands the rest back. Everything
    downstream counts the kept ones and ignores the others.
    """

    agrees: Optional[bool]
    drift: Optional[float]
    scale: Optional[float]
    because: str
    kept: Tuple[Tuple[int, int], ...] = ()

    @property
    def refutes(self) -> bool:
        """True only when this actively says the match is a coincidence."""
        return self.agrees is False


def _centres(marks: Sequence[ShapeMark], which: Sequence[int]) -> List[Tuple[float, float]]:
    return [(marks[i].centre.x, marks[i].centre.y) for i in which]


def _angle(one: Tuple[float, float], other: Tuple[float, float]) -> float:
    return math.degrees(math.atan2(other[1] - one[1], other[0] - one[0]))


def _apart(one: float, other: float) -> float:
    return abs((one - other + 180.0) % 360.0 - 180.0)


def _from_two(
    here: Sequence[Tuple[float, float]],
    there: Sequence[Tuple[float, float]],
    a: int,
    b: int,
) -> Optional[Tuple[float, float, float]]:
    """The move-and-scale two matched shapes imply, if they imply a sensible one."""
    span_here = math.dist(here[a], here[b])
    span_there = math.dist(there[a], there[b])
    if span_here <= 1e-6 or span_there <= 1e-6:
        return None
    scale = span_there / span_here
    if not SCALE_RANGE[0] <= scale <= SCALE_RANGE[1]:
        return None
    if _apart(_angle(here[a], here[b]), _angle(there[a], there[b])) > TURN_ALLOWED:
        return None
    mid_here = ((here[a][0] + here[b][0]) / 2, (here[a][1] + here[b][1]) / 2)
    mid_there = ((there[a][0] + there[b][0]) / 2, (there[a][1] + there[b][1]) / 2)
    return scale, mid_there[0] - scale * mid_here[0], mid_there[1] - scale * mid_here[1]


def _drift(
    here: Sequence[Tuple[float, float]],
    there: Sequence[Tuple[float, float]],
    which: Sequence[int],
    move: Tuple[float, float, float],
) -> float:
    """How far out the fit is, measured so that it does not matter which picture
    was handed in first.

    The obvious sum measures the error in the *second* picture's frame. That
    makes the whole check ``1/scale`` times stricter one way round than the
    other, and a reviewer showed the consequence: handing the same two
    photographs in in the other order changed a confident "the same thing" into
    "cannot tell". Dividing by the square root of the scale is what makes the
    number identical both ways, and it is the only thing that does.
    """
    scale, mx, my = move
    raw = math.sqrt(
        sum(
            (scale * here[i][0] + mx - there[i][0]) ** 2
            + (scale * here[i][1] + my - there[i][1]) ** 2
            for i in which
        )
        / max(1, len(which))
    )
    return raw / math.sqrt(scale) if scale > 0 else raw


def _one_each(pairs: Sequence[Tuple[int, int]], ranked: Sequence[Tuple[float, int]]) -> List[int]:
    """Keep one partner per shape, closest fit first.

    A shape is allowed several possible partners going in — deciding between
    them by how alike they look, before knowing the arrangement, is what let a
    coincidence take the place of the real match and block it. The arrangement
    decides instead, and one-to-one is enforced here, at the end, where it is a
    consequence rather than a guess.
    """
    used_left: set = set()
    used_right: set = set()
    kept: List[int] = []
    for _, index in ranked:
        i, j = pairs[index]
        if i in used_left or j in used_right:
            continue
        used_left.add(i)
        used_right.add(j)
        kept.append(index)
    return sorted(kept)


def arrangement_agrees(
    left: Sequence[ShapeMark],
    right: Sequence[ShapeMark],
    pairs: Sequence[Tuple[int, int]],
) -> Fit:
    """Find the largest set of matched shapes explained by one move-and-scale.

    Not *all* of them: two pictures that genuinely overlap along one edge share
    the shapes in the overlap and nothing else, and the shapes outside it throw
    up coincidental matches. Demanding that every match fit therefore threw away
    every real overlap — the meter caught exactly that. So the biggest agreeing
    set wins and the rest are handed back as coincidences.
    """
    if len(pairs) < 2:
        return Fit(
            None,
            None,
            None,
            "too few shapes match to say anything about how they are arranged",
            tuple(pairs),
        )

    here = _centres(left, [i for i, _ in pairs])
    there = _centres(right, [j for _, j in pairs])
    everyone = range(len(pairs))

    best_move: Optional[Tuple[float, float, float]] = None
    best: List[int] = []
    for a in everyone:
        for b in range(a + 1, len(pairs)):
            if pairs[a][0] == pairs[b][0] or pairs[a][1] == pairs[b][1]:
                continue
            move = _from_two(here, there, a, b)
            if move is None:
                continue
            agreeing = _one_each(
                pairs,
                sorted(
                    (
                        (_drift(here, there, [i], move), i)
                        for i in everyone
                        if _drift(here, there, [i], move) <= DRIFT_ALLOWED
                    )
                ),
            )
            if len(agreeing) > len(best):
                best, best_move = agreeing, move

    if len(best) < 2 or best_move is None:
        return Fit(
            False,
            None,
            None,
            "no two of the matching shapes sit the same way round in both "
            "pictures, so every match is a coincidence",
            (),
        )

    kept = tuple(pairs[i] for i in best)
    drift = _drift(here, there, best, best_move)
    scale = best_move[0]
    dropped = len(pairs) - len(best)
    tail = f"; {dropped} other match(es) do not fit and were dropped" if dropped else ""

    if len(best) == 2:
        return Fit(
            True,
            drift,
            scale,
            "only two shapes lie the same way round in both, which is weak "
            "evidence — two shapes cannot show more than that" + tail,
            kept,
        )
    return Fit(
        True,
        drift,
        scale,
        f"{len(best)} matching shapes line up under one step and zoom "
        f"({scale:.2f}×, {drift:.0%} out){tail}",
        kept,
    )


__all__ = ["DRIFT_ALLOWED", "Fit", "SCALE_RANGE", "TURN_ALLOWED", "arrangement_agrees"]
