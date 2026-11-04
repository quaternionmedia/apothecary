"""GRBL's dialect from a part's cuts: one tool, a depth per pass, feeds within the
router's bounds, and every operation named on the line before it so the cut
that streams it can say which it is in.

The work zero is the stock's front-left top corner; the tool travels at
``safe_z`` between cuts and plunges straight down into each. A pocket is cleared
in raster lines inset from its walls by the tool's radius, then its walls are
taken in one lap. A hole wider than the tool is bored in a circle; one the tool's
size, or smaller, is plunged, and the smaller one is said. An outline is cut
around from outside, the tool's radius beyond its edge.
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

from ..firmware import grbl
from .models import Bounds, Cuts, Hole, OperationSaid, Outline, Pocket, Toolpath

# The router's rapid, the maker's figure, is the feed's bound (grbl.FEED_MAX).
RAPID = float(grbl.FEED_MAX)
CIRCLE_SEGMENTS = 36
SPIN_UP_S = 2.0
EPS = 1e-6


def fmt(value: float) -> str:
    """A number as the toolpath writes it: three decimals at most, none when whole."""
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def passes(depth: float, step_down: float) -> List[float]:
    """The Z of each pass to ``depth``: ``step_down`` at a time, the last to the depth."""
    out: List[float] = []
    z = 0.0
    while depth - (-z) > EPS:
        z = max(-depth, z - step_down)
        out.append(round(z, 3))
    return out


class _Writer:
    """Lines as they are written, and what they add up to."""

    def __init__(self, cuts: Cuts):
        self.cuts = cuts
        self.lines: List[str] = []
        # Where the tool is taken to be before the first line: at the work zero, so
        # the first line lifts it to the safe height whatever it stood at.
        self.at: Tuple[float, float, float] = (0.0, 0.0, 0.0)
        self.cut_mm = 0.0
        self.rapid_mm = 0.0
        self.time_s = 0.0
        self.low: Optional[List[float]] = None
        self.high: Optional[List[float]] = None

    def comment(self, text: str) -> None:
        self.lines.append(f"({text.replace('(', '[').replace(')', ']')})")

    def _move(self, code: str, x, y, z, feed: Optional[float]) -> None:
        nx, ny, nz = (
            self.at[0] if x is None else x,
            self.at[1] if y is None else y,
            self.at[2] if z is None else z,
        )
        if (nx, ny, nz) == self.at:
            return  # already there: no line for a move that moves nothing
        words = [code]
        if x is not None:
            words.append(f"X{fmt(x)}")
        if y is not None:
            words.append(f"Y{fmt(y)}")
        if z is not None:
            words.append(f"Z{fmt(z)}")
        if feed is not None:
            words.append(f"F{fmt(feed)}")
        self.lines.append(" ".join(words))
        dist = math.dist(self.at, (nx, ny, nz))
        if feed is None:
            self.rapid_mm += dist
            self.time_s += dist / RAPID * 60.0
        else:
            self.cut_mm += dist
            self.time_s += dist / feed * 60.0
            r = self.cuts.tool.diameter / 2
            for px, py, pz in ((self.at[0], self.at[1], self.at[2]), (nx, ny, nz)):
                point = [px - r, py - r, pz]
                top = [px + r, py + r, pz]
                self.low = (
                    point
                    if self.low is None
                    else [min(a, b) for a, b in zip(self.low, point, strict=True)]
                )
                self.high = (
                    top
                    if self.high is None
                    else [max(a, b) for a, b in zip(self.high, top, strict=True)]
                )
        self.at = (nx, ny, nz)

    def rapid(self, x=None, y=None, z=None) -> None:
        self._move("G0", x, y, z, None)

    def feed(self, x=None, y=None, z=None) -> None:
        self._move("G1", x, y, z, self.cuts.feeds.cut)

    def plunge(self, z: float) -> None:
        self._move("G1", None, None, z, self.cuts.feeds.plunge)

    def up(self) -> None:
        self.rapid(z=self.cuts.safe_z)


def _pocket(w: _Writer, op: Pocket, label: str, messages: List[str]) -> Tuple[int, bool]:
    d = w.cuts.tool.diameter
    r = d / 2
    x0, x1, y0, y1 = op.x + r, op.x + op.w - r, op.y + r, op.y + op.h - r
    if x1 - x0 < -EPS or y1 - y0 < -EPS:
        messages.append(
            f"pocket {fmt(op.w)} x {fmt(op.h)} at {fmt(op.x)},{fmt(op.y)} is narrower than "
            f"the {fmt(d)} mm tool: not cut"
        )
        return 0, False
    zs = passes(op.depth, w.cuts.step_down)
    step = max(d * w.cuts.stepover, EPS)
    rows = max(1, math.ceil((y1 - y0) / step - EPS)) + 1
    for n, z in enumerate(zs, 1):
        w.comment(
            f"{label} pass {n}/{len(zs)}: pocket {fmt(op.w)} x {fmt(op.h)} at {fmt(op.x)},{fmt(op.y)} to z {fmt(z)}"
        )
        if n == 1:
            w.up()
            w.rapid(x=x0, y=y0)
        else:
            w.feed(x=x0, y=y0)
        w.plunge(z)
        for i in range(rows):
            y = y0 + (y1 - y0) * (i / (rows - 1) if rows > 1 else 0)
            w.feed(y=round(y, 3))
            w.feed(x=x1 if i % 2 == 0 else x0)
        # The walls, one lap from the corner the raster ended near.
        for cx, cy in ((x1, y1), (x1, y0), (x0, y0), (x0, y1), (x1, y1)):
            w.feed(x=cx, y=cy)
    w.up()
    return len(zs), True


def _hole(w: _Writer, op: Hole, label: str, messages: List[str]) -> Tuple[int, bool]:
    d = w.cuts.tool.diameter
    zs = passes(op.depth, w.cuts.step_down)
    where = f"hole {fmt(op.diameter)} mm at {fmt(op.x)},{fmt(op.y)}"
    if op.diameter <= d + EPS:
        if op.diameter < d - EPS:
            messages.append(f"{where} is smaller than the {fmt(d)} mm tool: bored to the tool")
        w.up()
        w.rapid(x=op.x, y=op.y)
        for n, z in enumerate(zs, 1):
            w.comment(f"{label} pass {n}/{len(zs)}: {where} plunged to z {fmt(z)}")
            w.plunge(z)
        w.up()
        return len(zs), True
    rc = (op.diameter - d) / 2
    ring = [
        (
            round(op.x + rc * math.cos(2 * math.pi * k / CIRCLE_SEGMENTS), 3),
            round(op.y + rc * math.sin(2 * math.pi * k / CIRCLE_SEGMENTS), 3),
        )
        for k in range(CIRCLE_SEGMENTS + 1)
    ]
    w.up()
    w.rapid(x=ring[0][0], y=ring[0][1])
    for n, z in enumerate(zs, 1):
        w.comment(f"{label} pass {n}/{len(zs)}: {where} bored to z {fmt(z)}")
        w.plunge(z)
        for px, py in ring[1:]:
            w.feed(x=px, y=py)
    w.up()
    return len(zs), True


def _outline(w: _Writer, op: Outline, label: str, messages: List[str]) -> Tuple[int, bool]:
    r = w.cuts.tool.diameter / 2
    depth = op.depth
    floor = w.cuts.stock.thickness + 1.0  # a millimetre into the spoilboard, and no more
    if depth > floor + EPS:
        messages.append(
            f"outline depth {fmt(op.depth)} is below the stock's {fmt(w.cuts.stock.thickness)} mm: "
            f"cut to {fmt(floor)}, a millimetre into the spoilboard"
        )
        depth = floor
    zs = passes(depth, w.cuts.step_down)
    corners = [
        (op.x - r, op.y - r),
        (op.x + op.w + r, op.y - r),
        (op.x + op.w + r, op.y + op.h + r),
        (op.x - r, op.y + op.h + r),
        (op.x - r, op.y - r),
    ]
    w.up()
    w.rapid(x=corners[0][0], y=corners[0][1])
    for n, z in enumerate(zs, 1):
        w.comment(
            f"{label} pass {n}/{len(zs)}: outline {fmt(op.w)} x {fmt(op.h)} at {fmt(op.x)},{fmt(op.y)} to z {fmt(z)}"
        )
        w.plunge(z)
        for cx, cy in corners[1:]:
            w.feed(x=cx, y=cy)
    w.up()
    return len(zs), True


def write(cuts: Cuts, name: str = "part") -> Toolpath:
    """The toolpath for ``cuts``: GRBL's dialect, one line per move, each operation
    announced in a comment the streaming cut reads (``op i/n pass p/m: ...``)."""
    w = _Writer(cuts)
    messages: List[str] = []
    said: List[OperationSaid] = []
    t, s, f = cuts.tool, cuts.stock, cuts.feeds
    w.comment(f"apothecary toolpath: {name}")
    w.comment(f"tool: {t.label}, {fmt(t.diameter)} mm, {t.flutes} flutes")
    w.comment(
        f"stock: {fmt(s.x)} x {fmt(s.y)} x {fmt(s.thickness)} mm, zero at its front-left top corner"
    )
    w.comment(
        f"feeds: cut {fmt(f.cut)}, plunge {fmt(f.plunge)} mm/min, {f.rpm} rpm; {fmt(cuts.step_down)} mm a pass"
    )
    w.lines += ["G21", "G90", "G17", "G54"]
    w.up()
    w.lines.append(f"M3 S{f.rpm}")
    w.lines.append(f"G4 P{fmt(SPIN_UP_S)}")
    w.time_s += SPIN_UP_S
    total = len(cuts.operations)
    for i, op in enumerate(cuts.operations, 1):
        label = f"op {i}/{total}"
        before = len(w.lines)
        if isinstance(op, Pocket):
            n, cut = _pocket(w, op, label, messages)
            words = (
                f"pocket {fmt(op.w)} x {fmt(op.h)} at {fmt(op.x)},{fmt(op.y)}, {fmt(op.depth)} deep"
            )
        elif isinstance(op, Hole):
            n, cut = _hole(w, op, label, messages)
            words = f"hole {fmt(op.diameter)} mm at {fmt(op.x)},{fmt(op.y)}, {fmt(op.depth)} deep"
        else:
            n, cut = _outline(w, op, label, messages)
            words = f"outline {fmt(op.w)} x {fmt(op.h)} at {fmt(op.x)},{fmt(op.y)}, {fmt(op.depth)} deep"
        said.append(
            OperationSaid(
                index=i, kind=op.kind, words=words, passes=n, lines=len(w.lines) - before, cut=cut
            )
        )
    w.up()
    w.lines.append("M5")
    w.rapid(x=0.0, y=0.0)
    w.lines.append("M30")
    bounds = (
        Bounds(min=[round(v, 3) for v in w.low], max=[round(v, 3) for v in w.high])
        if w.low
        else None
    )
    return Toolpath(
        lines=w.lines,
        operations=said,
        length_mm=round(w.cut_mm, 1),
        rapid_mm=round(w.rapid_mm, 1),
        time_s=round(w.time_s, 1),
        bounds=bounds,
        messages=messages,
    )


def text(toolpath: Toolpath) -> str:
    """The file, one line each, as the Cut card keeps it."""
    return "\n".join(toolpath.lines) + "\n"
