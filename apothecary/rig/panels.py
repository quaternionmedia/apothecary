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
picture's own corners in -- and ``face_onto`` makes from them the one mapping
from a point of the face to a point of the picture: ``apothecary/homography.py``'s,
whose ``apply``, ``invert`` and ``compose`` are named here too for the rig's readers.
"""

from __future__ import annotations

from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple

from ..homography import Matrix, Point, apply, compose, homography, invert
from ..vision.projection import CORNERS

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


def face_onto(corners: Sequence[Point]) -> Matrix:
    """A face's point, as fractions of it, to the picture's, from the face's corners there.
    ValueError (``homography.Degenerate``) when three of the corners lie on one line."""
    return homography(CORNERS, corners)


__all__ = [
    "Control",
    "Panel",
    "Socket",
    "apply",
    "compose",
    "face_onto",
    "face_size",
    "invert",
    "panel",
]