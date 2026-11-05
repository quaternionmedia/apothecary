"""What a G-code file does, read one line at a time, whichever machine it is for.

The modal interpreter both kinds of machine share: where the tool is, in millimetres,
through absolute and relative moves (G90/G91), absolute and relative extrusion
(M82/M83), a position set by hand (G92), inches (G20), a motion word carried over from
the line before, words written without a space (`G1X10`) and arcs (G2/G3, as chords).
It says nothing of what a move means: that is the process's (``process.py``). It
yields what it reads, in the file's order: a ``Move`` for each straight piece of tool
travel, a ``Comment`` for each comment, and a ``Dwell`` for each pause.

A line that homes (G28, `$H`), probes (G38.x) or moves in machine coordinates (G53)
is not drawn: the file does not say where those end in its own coordinates.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterable, Iterator, List, Optional, Tuple, Union

Point = Tuple[float, float, float]

_WORD = re.compile(r"([A-Z])\s*([-+]?(?:\d+\.?\d*|\.\d+))")
# Read left to right, so a `;` inside parentheses and parentheses after a `;` stay in the
# comment they are in: gcode.strip_gcode's grammar, which is what a job sends by.
_COMMENT = re.compile(r";(.*)$|\(([^)]*)\)")
# How finely an arc is written: a chord per ten degrees, the toolpath's own circles' step.
ARC_STEP = math.radians(10)
INCH_MM = 25.4
AXES = "XYZ"
# The G words that say nothing of where the tool goes next in the file's coordinates.
_NOT_DRAWN = {"G10", "G28", "G30", "G38", "G53"}


@dataclass(frozen=True)
class Move:
    """One straight piece of tool travel, in the file's coordinates, in millimetres."""

    start: Point
    end: Point
    feed: float  # mm/min, as the file last set it; 0 if it has not
    rapid: bool  # a G0
    extruded: float  # filament pushed along this move, in mm; a retract is negative
    spindle: float  # rpm while it runs; 0 with the spindle off
    line: int  # the file's line, from 1
    sent: int  # how many lines would be sent before this one: a job's count


@dataclass(frozen=True)
class Comment:
    text: str
    line: int


@dataclass(frozen=True)
class Dwell:
    """A pause, as written: what P and S say is the dialect's (``Process.dwell``)."""

    p: Optional[float]
    s: Optional[float]
    line: int


Event = Union[Move, Comment, Dwell]


def split_comments(raw: str) -> Tuple[str, List[str]]:
    """A line as the command it carries, upper-cased and squeezed, and its comments."""
    comments = [
        (m.group(1) if m.group(1) is not None else m.group(2)).strip()
        for m in _COMMENT.finditer(raw)
    ]
    return " ".join(_COMMENT.sub("", raw).split()).upper(), comments


def _code(letter: str, value: str) -> str:
    """A G or M word as one spelling: G00 is G0, and a sub-code (G38.2) its family."""
    return f"{letter}{int(float(value))}"


class _Tool:
    """What the file has said so far: the modal state a line is read against."""

    def __init__(self) -> None:
        self.at = [0.0, 0.0, 0.0]
        self.shift = [0.0, 0.0, 0.0]  # what G92 moved the file's zero by
        self.e = 0.0
        self.relative = False
        self.relative_e = False
        self.scale = 1.0
        self.motion: Optional[str] = None
        self.plane = "G17"
        self.feed = 0.0
        self.spindle = 0.0
        self.speed = 0.0

    def _target(self, words: dict) -> Point:
        out = []
        for i, axis in enumerate(AXES):
            if axis not in words:
                out.append(self.at[i])
            elif self.relative:
                out.append(self.at[i] + words[axis] * self.scale)
            else:
                out.append(words[axis] * self.scale + self.shift[i])
        return (out[0], out[1], out[2])

    def _push(self, words: dict) -> float:
        """The filament this line pushes; the file's count moves on with it."""
        if "E" not in words:
            return 0.0
        value = words["E"] * self.scale
        if self.relative_e:
            self.e += value
            return value
        pushed = value - self.e
        self.e = value
        return pushed

    def _arc(self, end: Point, words: dict, clockwise: bool) -> List[Point]:
        """The chords of an arc in the XY plane, from I and J or from R; a straight line
        where the file gives neither, or the arc is in another plane."""
        sx, sy, sz = self.at
        ex, ey, ez = end
        if self.plane != "G17":
            return [end]
        if "I" in words or "J" in words:
            cx = sx + words.get("I", 0.0) * self.scale
            cy = sy + words.get("J", 0.0) * self.scale
        elif "R" in words:
            r = words["R"] * self.scale
            dx, dy = ex - sx, ey - sy
            chord = math.hypot(dx, dy)
            if chord == 0 or abs(r) < chord / 2:
                return [end]
            h = math.sqrt(max(0.0, r * r - chord * chord / 4))
            # A negative R is the longer way round: the centre on the other side.
            side = (-1 if clockwise else 1) * (1 if r > 0 else -1)
            cx = (sx + ex) / 2 - side * h * dy / chord
            cy = (sy + ey) / 2 + side * h * dx / chord
        else:
            return [end]
        radius = math.hypot(sx - cx, sy - cy)
        begin = math.atan2(sy - cy, sx - cx)
        sweep = math.atan2(ey - cy, ex - cx) - begin
        if clockwise and sweep >= 0:
            sweep -= 2 * math.pi
        elif not clockwise and sweep <= 0:
            sweep += 2 * math.pi
        # A whole number of steps stays that many, whatever the arithmetic leaves over.
        steps = max(1, math.ceil(round(abs(sweep) / ARC_STEP, 9)))
        points: List[Point] = []
        for k in range(1, steps + 1):
            t = k / steps
            angle = begin + sweep * t
            points.append(
                (cx + radius * math.cos(angle), cy + radius * math.sin(angle), sz + (ez - sz) * t)
            )
        points[-1] = end
        return points

    def line(self, code: str, number: int, sent: int) -> Iterator[Event]:
        pairs = _WORD.findall(code)
        gs = [_code(k, v) for k, v in pairs if k == "G"]
        ms = [_code(k, v) for k, v in pairs if k == "M"]
        words = {k: float(v) for k, v in pairs if k not in "GM"}
        for g in gs:
            if g in ("G0", "G1", "G2", "G3"):
                self.motion = g
            elif g in ("G17", "G18", "G19"):
                self.plane = g
            elif g == "G20":
                self.scale = INCH_MM
            elif g == "G21":
                self.scale = 1.0
            elif g == "G90":
                self.relative = self.relative_e = False
            elif g == "G91":
                self.relative = self.relative_e = True
        for m in ms:
            if m == "M82":
                self.relative_e = False
            elif m == "M83":
                self.relative_e = True
            elif m in ("M3", "M4"):
                self.speed = words.get("S", self.speed)
                self.spindle = self.speed
            elif m == "M5":
                self.spindle = 0.0
        if "G92" in gs:
            for i, axis in enumerate(AXES):
                if axis in words:
                    self.shift[i] = self.at[i] - words[axis] * self.scale
            if "E" in words:
                self.e = words["E"] * self.scale
            return
        if "G4" in gs:
            yield Dwell(words.get("P"), words.get("S"), number)
            return
        if _NOT_DRAWN.intersection(gs):
            return
        if ms:
            return  # a machine word's S or X is not a move: M104 S200, M84 X Y E
        if "S" in words:
            self.speed = words["S"]
            if self.spindle:
                self.spindle = self.speed
        if "F" in words:
            self.feed = words["F"] * self.scale
        pushed = self._push(words)
        if self.motion is None or not any(axis in words for axis in AXES + "IJR"):
            return
        end = self._target(words)
        arc = self.motion in ("G2", "G3")
        points = self._arc(end, words, self.motion == "G2") if arc else [end]
        rapid = self.motion == "G0"
        start = (self.at[0], self.at[1], self.at[2])
        for point in points:
            if point != start:
                yield Move(
                    start,
                    point,
                    self.feed,
                    rapid,
                    pushed / len(points),
                    self.spindle,
                    number,
                    sent,
                )
            start = point
        self.at = list(end)


class Reader:
    """A file's lines, read once: every ``Move``, ``Comment`` and ``Dwell`` they say, in
    order, and once read, ``sent``, the lines a job would send: a file's last lines are
    often no move at all (`M104 S0`, `M84`)."""

    def __init__(self, lines: Iterable[str]) -> None:
        self._lines = lines
        self.sent = 0

    def __iter__(self) -> Iterator[Event]:
        tool = _Tool()
        for number, raw in enumerate(self._lines, 1):
            code, comments = split_comments(raw)
            for text in comments:
                yield Comment(text, number)
            if not code:
                continue
            self.sent += 1
            if code.startswith("$"):
                continue  # a controller's own line ($H, $X): no move the file can place
            yield from tool.line(code, number, self.sent - 1)


def read(lines: Iterable[str]) -> Iterator[Event]:
    """Every event of a file's lines, for a reader that does not need the count."""
    return iter(Reader(lines))
