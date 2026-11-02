"""A device's panel as carlos draws it, and where a point of it lies in a picture.

A carlos catalogue entry places each control and socket on a face of the
device as fractions across and down that face, origin top left, and gives the
device's real size as a box in millimetres. ``panel`` reads one face of an
entry into what the reader needs: each control with its kind, its place and its
range, each socket with its place, and the face's size.

Sizes are carlos's drawing sizes read as millimetres: at size 1 a knob is
``KNOB_MM`` across, a socket ``SOCKET_MM``, a fader's cap ``CAP_MM`` and a
switch's body ``SWITCH_MM`` (static/demo.css, in carlos, draws them in pixels).
Real photographs measure them; until then this is the guess.

A face lies in a picture through its four corners -- top left, top right,
bottom right, bottom left, the order ``vision/projection.py`` writes a
picture's own corners in -- and ``homography`` makes from them the one mapping
from a point of the face to a point of the picture. Written out in plain
Python, as ``vision/projection.py`` is.
"""

from __future__ import annotations

from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple

from ..vision.projection import CORNERS, Matrix, Point

# Carlos's drawing sizes, read as millimetres, at size 1.
KNOB_MM = 18.0
SOCKET_MM = 11.0
CAP_MM = (10.0, 5.0)  # across the travel, along it
SWITCH_MM = (8.0, 14.0)  # wide, tall
# A knob turns this far each way from straight up, as carlos draws it.
SWEEP = 135.0

KINDS = ("knob", "fader", "drawbar", "encoder", "switch")


class Control(NamedTuple):
    name: str
    label: str
    kind: str  # one of KINDS
    x: float
    y: float
    size: float
    orient: str  # a fader's or drawbar's: "vertical" or "horizontal"
    length: float  # its travel, a fraction of the face's height (vertical) or width
    minimum: float
    maximum: float
    default: float


class Socket(NamedTuple):
    name: str
    label: str
    x: float
    y: float
    size: float


class Panel(NamedTuple):
    device: str
    side: str
    width_mm: float
    height_mm: float
    controls: List[Control]
    sockets: List[Socket]


def face_size(box: Dict[str, float], side: str) -> Tuple[float, float]:
    """A face's width and height in mm, from the device's box, as carlos derives them."""
    if side in ("front", "back"):
        return box["width"], box["height"]
    if side in ("top", "bottom"):
        return box["width"], box["depth"]
    return box["depth"], box["height"]


def panel(entry: Dict[str, Any], side: str) -> Optional[Panel]:
    """One face of a catalogue entry; None when the entry has no measured layout."""
    layout = entry.get("layout") or {}
    box = layout.get("box")
    if not box:
        return None
    face = layout.get("face", "front")
    width, height = face_size(box, side)
    ranges = {p["name"]: p for p in entry.get("parameters", [])}
    labels = {j["name"]: j.get("label") or j["name"] for j in entry.get("jacks", [])}
    controls = []
    for name, place in (layout.get("controls") or {}).items():
        if place.get("side", face) != side or name not in ranges:
            continue
        parameter = ranges[name]
        low, high = float(parameter.get("min", 0)), float(parameter.get("max", 127))
        controls.append(
            Control(
                name=name,
                label=parameter.get("label") or name,
                kind=place.get("kind", "knob"),
                x=float(place["x"]),
                y=float(place["y"]),
                size=float(place.get("size", 1)),
                orient=place.get("orient", "vertical"),
                length=float(place.get("length", 0.2)),
                minimum=low,
                maximum=high,
                default=float(parameter.get("default", (low + high) / 2)),
            )
        )
    sockets = [
        Socket(
            name=name,
            label=labels.get(name, name),
            x=float(place["x"]),
            y=float(place["y"]),
            size=float(place.get("size", 1)),
        )
        for name, place in (layout.get("jacks") or {}).items()
        if place.get("side", face) == side
    ]
    return Panel(entry["id"], side, float(width), float(height), controls, sockets)


# --- one face onto a picture -----------------------------------------------------------


def homography(source: Sequence[Point], target: Sequence[Point]) -> Matrix:
    """The mapping taking each of four points onto its partner: eight equations,
    solved by elimination. ValueError when three of either four lie on a line."""
    for points in (source, target):
        for skip in range(4):
            a, b, c = (points[i] for i in range(4) if i != skip)
            if abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) < 1e-9:
                raise ValueError("four corners, three of them on one line: no face lies there")
    rows: List[List[float]] = []
    for (x, y), (u, v) in zip(source, target, strict=True):
        rows.append([x, y, 1.0, 0.0, 0.0, 0.0, -u * x, -u * y, u])
        rows.append([0.0, 0.0, 0.0, x, y, 1.0, -v * x, -v * y, v])
    for column in range(8):
        pivot = max(range(column, 8), key=lambda r: abs(rows[r][column]))
        if abs(rows[pivot][column]) < 1e-12:
            raise ValueError("four corners that make no mapping: no face lies there")
        rows[column], rows[pivot] = rows[pivot], rows[column]
        lead = rows[column][column]
        rows[column] = [value / lead for value in rows[column]]
        for r in range(8):
            if r != column and rows[r][column]:
                factor = rows[r][column]
                rows[r] = [a - factor * b for a, b in zip(rows[r], rows[column], strict=True)]
    h = [rows[r][8] for r in range(8)]
    return ((h[0], h[1], h[2]), (h[3], h[4], h[5]), (h[6], h[7], 1.0))


def face_onto(corners: Sequence[Point]) -> Matrix:
    """A face's point, as fractions of it, to the picture's, from the face's corners there."""
    return homography(CORNERS, corners)


def apply(matrix: Matrix, x: float, y: float) -> Point:
    (a, b, c), (d, e, f), (g, h, i) = matrix
    w = g * x + h * y + i
    return ((a * x + b * y + c) / w, (d * x + e * y + f) / w)


def invert(matrix: Matrix) -> Matrix:
    """The mapping back. ValueError for one that flattens the plane."""
    (a, b, c), (d, e, f), (g, h, i) = matrix
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(det) < 1e-15:
        raise ValueError("a mapping that flattens the plane has no way back")
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
