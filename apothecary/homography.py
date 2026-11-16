"""Four points of one plane onto four of another: the one mapping, its way back, and two
mappings one after the other.

A *homography* is a three-by-three matrix taking a point ``(x, y)`` of one plane to
``(u, v)`` of another: ``(x, y, 1)`` multiplied out is ``(u * w, v * w, w)``. Four
points and where each lands fix it, so long as no three of either four lie on one line:
then no mapping takes them there, and ``homography`` refuses with the three it found
(``Degenerate``).

Everything that maps a plane by four points does it here: a device's face onto a
photograph of it (``rig/panels.py``), a photograph squared to its whiteboard
(``vision/whiteboard.py``), and a machine's bed onto a projector's pixels
(``projector.py``). Written out in plain Python, as ``vision/projection.py`` is, so it
depends on nothing.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

Matrix = Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]
Point = Tuple[float, float]

# Twice the area of a triangle under which its three points are read as on one line.
FLAT = 1e-9
# A pivot smaller than this leaves the eight equations without one answer.
PIVOT = 1e-12
# A determinant smaller than this flattens the plane: no way back.
FLATTENED = 1e-15


class Degenerate(ValueError):
    """Four points that fix no mapping: three of them on one line, or none at all."""


def on_one_line(points: Sequence[Point]) -> Optional[Tuple[int, int, int]]:
    """The first three of four points (by their places, from 0) that lie on one line,
    or None when no three do."""
    for skip in range(3, -1, -1):
        which = tuple(i for i in range(4) if i != skip)
        a, b, c = (points[i] for i in which)
        if abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) < FLAT:
            return which  # type: ignore[return-value]
    return None


def homography(source: Sequence[Point], target: Sequence[Point]) -> Matrix:
    """The mapping taking each of four points onto its partner: eight equations, solved
    by elimination. ``Degenerate`` when three of either four lie on one line."""
    for name, points in (("from", source), ("onto", target)):
        if len(points) != 4:
            raise Degenerate(f"a mapping is fixed by four points {name}, not {len(points)}")
        three = on_one_line(points)
        if three is not None:
            places = ", ".join(str(i + 1) for i in three[:2]) + f" and {three[2] + 1}"
            raise Degenerate(
                f"points {places} of the four {name} lie on one line: "
                "three on a line fix no mapping"
            )
    rows: List[List[float]] = []
    for (x, y), (u, v) in zip(source, target, strict=True):
        rows.append([x, y, 1.0, 0.0, 0.0, 0.0, -u * x, -u * y, u])
        rows.append([0.0, 0.0, 0.0, x, y, 1.0, -v * x, -v * y, v])
    for column in range(8):
        pivot = max(range(column, 8), key=lambda r: abs(rows[r][column]))
        if abs(rows[pivot][column]) < PIVOT:
            raise Degenerate("four points that fix no mapping")
        rows[column], rows[pivot] = rows[pivot], rows[column]
        lead = rows[column][column]
        rows[column] = [value / lead for value in rows[column]]
        for r in range(8):
            if r != column and rows[r][column]:
                factor = rows[r][column]
                rows[r] = [a - factor * b for a, b in zip(rows[r], rows[column], strict=True)]
    h = [rows[r][8] for r in range(8)]
    return ((h[0], h[1], h[2]), (h[3], h[4], h[5]), (h[6], h[7], 1.0))


def apply(matrix: Matrix, x: float, y: float) -> Point:
    """Where ``(x, y)`` lands."""
    (a, b, c), (d, e, f), (g, h, i) = matrix
    w = g * x + h * y + i
    return ((a * x + b * y + c) / w, (d * x + e * y + f) / w)


def invert(matrix: Matrix) -> Matrix:
    """The mapping back. ``Degenerate`` for one that flattens the plane."""
    (a, b, c), (d, e, f), (g, h, i) = matrix
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(det) < FLATTENED:
        raise Degenerate("a mapping that flattens the plane has no way back")
    return (
        ((e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det),
        ((f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det),
        ((d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det),
    )


def compose(outer: Matrix, inner: Matrix) -> Matrix:
    """``inner`` first, then ``outer``."""
    return tuple(  # type: ignore[return-value]
        tuple(sum(outer[r][k] * inner[k][c] for k in range(3)) for c in range(3)) for r in range(3)
    )


__all__ = [
    "Degenerate",
    "Matrix",
    "Point",
    "apply",
    "compose",
    "homography",
    "invert",
    "on_one_line",
]
