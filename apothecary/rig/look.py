"""Reading a panel's controls and sockets off a picture.

Every reading is made on the face, in fractions of it, and each point is
sampled from the picture through the face's mapping, so a face seen at a slant
reads as one seen straight on. The picture is read in grey through Pillow, as
the plain finder reads it, and nothing else is needed.

| Kind | Read as |
|---|---|
| knob | the angle round a ring inside it where it differs most from the ring's middle value: the pointer, over carlos's 270 degrees |
| fader, drawbar | the point along the travel, averaged across the slot, that differs most from the travel's middle value: the cap; up, or right, is more |
| switch | whichever half of its body is lighter: the lever; up is the top of the range |
| encoder | never: it turns without end, so a picture shows no position |
| socket | a plug, unless its centre is darker than the ring round it by ``HOLE_CONTRAST``: an empty hole; never when its hole is under ``MIN_SOCKET_PX`` from centre to edge in the picture, where centre and ring are the same few pixels |

Each answer carries a confidence, the contrast it was read on, well under 1.0
when that was faint, so nothing downstream takes a guess for a measurement.

A prototype: no ratified record governs it.
"""

from __future__ import annotations

import math
import statistics
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from pydantic import BaseModel

from ..vision.projection import Point
from . import panels
from .panels import Control, Panel, Socket

# Below this many grey levels, a pointer, a cap or a lever is not told from what
# it sits on.
MIN_CONTRAST = 40
# An empty socket's centre is this much darker than the ring round it.
HOLE_CONTRAST = 50
# A socket smaller than this, in pixels from its centre to its edge, is not read:
# its centre and the ring round it are the same few pixels. On drawn pictures the
# reads go wrong a little under it, and as surely as a large socket's are right;
# the rest is a margin for a real camera's blur and compression.
MIN_SOCKET_PX = 2.5
# A pointer this far past the sweep is in the gap at the bottom, and is not read.
PAST_SWEEP = 12.0
RING_SAMPLES = 120
TRAVEL_SAMPLES = 80


class Seen(BaseModel):
    """One control as the picture shows it."""

    name: str
    kind: str
    value: Optional[float] = None  # None when it was not read
    why: Optional[str] = None  # why it was not read
    confidence: float = 0.0


class Plug(BaseModel):
    """One socket as the picture shows it."""

    name: str
    plugged: Optional[bool] = None  # None when it was not read
    confidence: float = 0.0
    why: Optional[str] = None  # why it was not read


class Grey:
    """A picture's grey levels, sampled between pixels."""

    def __init__(self, width: int, height: int, data: bytes):
        self.width, self.height, self.data = width, height, data

    @classmethod
    def of(cls, image) -> "Grey":
        """From a Pillow image, any mode; a see-through background reads as white."""
        from PIL import Image

        if image.mode in ("RGBA", "LA") or "transparency" in image.info:
            filled = Image.new("RGBA", image.size, (255, 255, 255, 255))
            filled.paste(image.convert("RGBA"), mask=image.convert("RGBA"))
            image = filled
        grey = image.convert("L")
        return cls(grey.width, grey.height, grey.tobytes())

    @classmethod
    def open(cls, path: Path) -> "Grey":
        from PIL import Image, ImageOps

        with Image.open(path) as opened:
            # A phone's photograph is stored one way and meant to be seen another.
            return cls.of(ImageOps.exif_transpose(opened))

    def at(self, u: float, v: float) -> float:
        """The grey level at the picture's point ``(u, v)``, fractions across and down;
        white off the picture."""
        x, y = u * self.width - 0.5, v * self.height - 0.5
        if not (-0.5 <= x <= self.width - 0.5 and -0.5 <= y <= self.height - 0.5):
            return 255.0
        x0 = min(max(int(math.floor(x)), 0), self.width - 1)
        y0 = min(max(int(math.floor(y)), 0), self.height - 1)
        x1, y1 = min(x0 + 1, self.width - 1), min(y0 + 1, self.height - 1)
        fx, fy = min(max(x - x0, 0.0), 1.0), min(max(y - y0, 0.0), 1.0)
        row0, row1 = y0 * self.width, y1 * self.width
        top = self.data[row0 + x0] * (1 - fx) + self.data[row0 + x1] * fx
        bottom = self.data[row1 + x0] * (1 - fx) + self.data[row1 + x1] * fx
        return top * (1 - fy) + bottom * fy


class Face:
    """One panel's face as it lies in one picture."""

    def __init__(self, grey: Grey, panel: Panel, corners: Sequence[Point]):
        self.grey, self.panel = grey, panel
        self.onto = panels.face_onto(corners)

    def at(self, x: float, y: float) -> float:
        return self.grey.at(*panels.apply(self.onto, x, y))

    def mm(self, across: float, down: float) -> Tuple[float, float]:
        """A size in millimetres, as fractions of this face."""
        return across / self.panel.width_mm, down / self.panel.height_mm

    def pixels(self, x: float, y: float, rx: float, ry: float) -> float:
        """How far ``rx`` across or ``ry`` down from a point on the face is in the
        picture, in its pixels: the shorter of the two."""
        cx, cy = panels.apply(self.onto, x, y)
        ax, ay = panels.apply(self.onto, x + rx, y)
        bx, by = panels.apply(self.onto, x, y + ry)
        w, h = self.grey.width, self.grey.height
        return min(
            math.hypot((ax - cx) * w, (ay - cy) * h), math.hypot((bx - cx) * w, (by - cy) * h)
        )


def _peak(values: Sequence[float], circular: bool) -> Tuple[float, float]:
    """Where the values stand out most from their middle value, as a fractional
    index (the centre of the run around it), and by how much."""
    middle = statistics.median(values)
    lighter = max(values) - middle
    darker = middle - min(values)
    sign = 1.0 if lighter >= darker else -1.0
    standout = [sign * (value - middle) for value in values]
    best = max(range(len(values)), key=standout.__getitem__)
    height = standout[best]
    # The run of samples at least half as far out, round the best one.
    n = len(values)
    total = weight = 0.0
    taken = 0
    for direction in (1, -1):
        step = 0 if direction == 1 else 1
        while taken < n:
            index = best + direction * step
            if not circular and not 0 <= index < n:
                break
            if standout[index % n] < height / 2:
                break
            total += standout[index % n] * index
            weight += standout[index % n]
            step += 1
            taken += 1
    return (total / weight if weight else float(best)), height


def _knob(face: Face, control: Control) -> Seen:
    rx, ry = face.mm(panels.KNOB_MM * control.size / 2, panels.KNOB_MM * control.size / 2)
    ring = []
    for i in range(RING_SAMPLES):
        angle = 2 * math.pi * i / RING_SAMPLES
        ring.append(
            face.at(
                control.x + 0.65 * rx * math.sin(angle), control.y - 0.65 * ry * math.cos(angle)
            )
        )
    index, height = _peak(ring, circular=True)
    seen = Seen(name=control.name, kind=control.kind, confidence=min(1.0, height / 128))
    if height < MIN_CONTRAST:
        seen.why = "no pointer to see"
        return seen
    degrees = (index * 360.0 / RING_SAMPLES) % 360.0
    if degrees > 180:
        degrees -= 360
    if abs(degrees) > panels.SWEEP + PAST_SWEEP:
        seen.why = f"it points past its sweep, at {degrees:.0f} degrees"
        return seen
    turned = max(-panels.SWEEP, min(panels.SWEEP, degrees))
    fraction = (turned + panels.SWEEP) / (2 * panels.SWEEP)
    seen.value = control.minimum + fraction * (control.maximum - control.minimum)
    return seen


def _fader(face: Face, control: Control) -> Seen:
    vertical = control.orient == "vertical"
    cap_across, cap_along = (mm * control.size for mm in panels.CAP_MM)
    if vertical:
        across, along = face.mm(cap_across, cap_along)
    else:
        along, across = face.mm(cap_along, cap_across)
    # The travel runs over `length` of the face; the cap's centre reaches both
    # ends, so half a cap more is looked at past each.
    travel = control.length
    reach = along / 2 / travel
    width = across * 0.3
    profile = []
    steps = [-reach + (1 + 2 * reach) * i / (TRAVEL_SAMPLES - 1) for i in range(TRAVEL_SAMPLES)]
    for t in steps:
        level = 0.0
        for offset in (-1.0, -0.5, 0.0, 0.5, 1.0):
            if vertical:
                level += face.at(control.x + offset * width, control.y - travel / 2 + t * travel)
            else:
                level += face.at(control.x - travel / 2 + t * travel, control.y + offset * width)
        profile.append(level / 5)
    index, height = _peak(profile, circular=False)
    seen = Seen(name=control.name, kind=control.kind, confidence=min(1.0, height / 128))
    if height < MIN_CONTRAST:
        seen.why = "no cap to see along its travel"
        return seen
    t = min(1.0, max(0.0, -reach + (1 + 2 * reach) * index / (TRAVEL_SAMPLES - 1)))
    fraction = 1.0 - t if vertical else t
    seen.value = control.minimum + fraction * (control.maximum - control.minimum)
    return seen


def _switch(face: Face, control: Control) -> Seen:
    wide, tall = face.mm(panels.SWITCH_MM[0] * control.size, panels.SWITCH_MM[1] * control.size)
    halves = []
    for top in (True, False):
        levels = []
        for i in range(5):
            for j in range(4):
                dx = (i - 2) / 2 * wide * 0.3
                dy = (j + 0.5) / 4 * tall * 0.45
                levels.append(face.at(control.x + dx, control.y + (-dy if top else dy)))
        halves.append(sum(levels) / len(levels))
    lift = halves[0] - halves[1]
    seen = Seen(name=control.name, kind=control.kind, confidence=min(1.0, abs(lift) / 128))
    if abs(lift) < MIN_CONTRAST / 2:
        seen.why = "its lever is not told from its body"
        return seen
    seen.value = control.maximum if lift > 0 else control.minimum
    return seen


def control(face: Face, control: Control) -> Seen:
    if control.kind == "knob":
        return _knob(face, control)
    if control.kind in ("fader", "drawbar"):
        return _fader(face, control)
    if control.kind == "switch":
        return _switch(face, control)
    return Seen(
        name=control.name,
        kind=control.kind,
        why="an encoder turns without end, so a picture shows no position",
    )


def socket(face: Face, socket: Socket) -> Plug:
    rx, ry = face.mm(panels.SOCKET_MM * socket.size / 2, panels.SOCKET_MM * socket.size / 2)
    radius = face.pixels(socket.x, socket.y, rx, ry)
    if radius < MIN_SOCKET_PX:
        return Plug(
            name=socket.name,
            why=f"too small in the picture to read, {2 * radius:.1f} px across",
        )
    centre = [
        face.at(socket.x + dx * 0.3 * rx, socket.y + dy * 0.3 * ry)
        for dx in (-1, -0.5, 0, 0.5, 1)
        for dy in (-1, -0.5, 0, 0.5, 1)
        if dx * dx + dy * dy <= 1
    ]
    ring = [
        face.at(socket.x + r * rx * math.sin(a), socket.y - r * ry * math.cos(a))
        for r in (0.65, 0.8)
        for a in (2 * math.pi * i / 24 for i in range(24))
    ]
    hole = statistics.median(ring) - statistics.median(centre)
    return Plug(
        name=socket.name,
        plugged=hole < HOLE_CONTRAST,
        confidence=min(1.0, abs(hole - HOLE_CONTRAST) / HOLE_CONTRAST),
    )


def read_face(grey: Grey, panel: Panel, corners: Sequence[Point]) -> Tuple[List[Seen], List[Plug]]:
    """Every control and every socket on one face of one picture."""
    face = Face(grey, panel, corners)
    return (
        [control(face, each) for each in panel.controls],
        [socket(face, each) for each in panel.sockets],
    )
