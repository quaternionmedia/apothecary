"""Flat geometry the finder needs, written out rather than fetched.

Two things live here: the outline that wraps a set of points as tightly as
possible without bending inwards, and the smallest box — at any angle — that
still contains them.

Why the smallest box matters. Judging a shape by how much of its upright box it
fills only works when the shape is upright. Turn a square by 45° and it fills
half its upright box, which is exactly what a triangle does, so a turned square
gets called a triangle. Measured against the smallest box at *any* angle, a
square fills all of it however it is turned, a circle fills about 0.785, and a
triangle about 0.5 — and those numbers stay put when the picture does.

Nothing here is clever or new; both are textbook. They are written out because
the alternative is depending on something else to run.
"""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple

Point = Tuple[float, float]


def outline(points: Sequence[Point]) -> List[Point]:
    """The tightest outline that never bends inwards, going anticlockwise.

    Sorts the points, sweeps along the bottom and then the top, dropping any
    point that would make the path turn the wrong way. Duplicate points and
    points in a straight line are dropped.
    """
    unique = sorted(set(points))
    if len(unique) <= 2:
        return list(unique)

    def sweep(ordered: Sequence[Point]) -> List[Point]:
        built: List[Point] = []
        for point in ordered:
            while len(built) >= 2 and _turns_right(built[-2], built[-1], point):
                built.pop()
            built.append(point)
        return built

    lower = sweep(unique)
    upper = sweep(list(reversed(unique)))
    return lower[:-1] + upper[:-1]


def _turns_right(a: Point, b: Point, c: Point) -> bool:
    """True when going a → b → c bends clockwise or doubles back."""
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) <= 0


class SmallestBox(Tuple[float, float, float]):
    """The tightest box at any angle: its long side, short side, and direction.

    ``width`` is always the longer side and ``degrees`` always points along it.
    That matters: a rectangle's tightest box can be found lying either way round,
    and both give the same area, so without this rule the direction would be
    right only to a quarter turn and nobody downstream could use it.
    """

    __slots__ = ()

    @property
    def width(self) -> float:
        """The longer side."""
        return self[0]

    @property
    def height(self) -> float:
        """The shorter side."""
        return self[1]

    @property
    def degrees(self) -> float:
        """Which way the longer side runs, from 0 up to but not including 180."""
        return self[2]

    @property
    def area(self) -> float:
        return self[0] * self[1]


def smallest_box(points: Sequence[Point]) -> SmallestBox:
    """The tightest box containing every point, allowed to sit at any angle.

    The tightest such box always has one side lying flat against the outline, so
    every outline edge is tried in turn: turn the points until that edge is
    level, measure the upright box, keep the smallest.
    """
    edge = outline(points)
    if len(edge) < 3:
        # Everything on one line, or fewer than three points. The tightest box
        # is flat and lies along that line, so measure along it rather than
        # falling back to the upright span, which is neither the smallest box
        # nor a box that contains the points.
        if len(edge) < 2:
            return SmallestBox((0.0, 0.0, 0.0))
        (x0, y0), (x1, y1) = edge[0], edge[-1]
        return _longest_first(
            math.dist((x0, y0), (x1, y1)), 0.0, math.degrees(math.atan2(y1 - y0, x1 - x0))
        )

    best = SmallestBox((float("inf"), float("inf"), 0.0))
    for index, here in enumerate(edge):
        there = edge[(index + 1) % len(edge)]
        angle = math.atan2(there[1] - here[1], there[0] - here[0])
        cos, sin = math.cos(-angle), math.sin(-angle)

        low_x = low_y = float("inf")
        high_x = high_y = float("-inf")
        for x, y in edge:
            tx = x * cos - y * sin
            ty = x * sin + y * cos
            low_x, high_x = min(low_x, tx), max(high_x, tx)
            low_y, high_y = min(low_y, ty), max(high_y, ty)

        width, height = high_x - low_x, high_y - low_y
        if width * height < best.area:
            best = _longest_first(width, height, math.degrees(angle))
    return best


def _longest_first(along: float, across: float, degrees: float) -> SmallestBox:
    """Put the longer side first, and point the angle along it."""
    if across > along:
        along, across, degrees = across, along, degrees + 90.0
    return SmallestBox((along, across, degrees % 180.0))


def edge_points(members: Sequence[int], width: int, lookup: set) -> List[Point]:
    """Just the pixels of a blob that touch its outside.

    The outline only ever uses these, and there are far fewer of them than there
    are pixels in a solid shape, so finding them first keeps the work small on a
    large blob.
    """
    found: List[Point] = []
    for index in members:
        x, y = index % width, index // width
        # The left and right checks need the row guard: without it, the pixel
        # before column zero is the last pixel of the row above, so a shape
        # touching the left edge looks enclosed when it is not.
        if (
            x == 0
            or (index - 1) not in lookup
            or x == width - 1
            or (index + 1) not in lookup
            or (index - width) not in lookup
            or (index + width) not in lookup
        ):
            found.append((float(x), float(y)))
    return found


__all__ = ["Point", "SmallestBox", "edge_points", "outline", "smallest_box"]
