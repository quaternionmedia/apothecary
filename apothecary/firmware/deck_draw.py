"""What the deck's keys and strip are drawn as when they show more than a label: a
machine's tile, the strip's four panels, a graph, a progress bar, a bed's mesh.

``firmware/deck.py`` draws a label on a colour. This module draws from an ``art``, a
plain dict that says what is on the face -- numbers, a series, a fraction -- and
nothing of how it was found, so it is kept beside the image as what was sent and read
back from the deck's state. Each function takes an ``art`` and returns a Pillow image
of the size the device takes; ``deck.render`` makes it the JPEG.

A key's art (``kind: "tile"``) has a title along its top in its accent colour, a value
under it, a small line and, at its foot, a spark line of a series or a bar.

The strip's art has the screens along its top (``tabs``, the one showing lit), each a
quarter of the strip over its knob, so a tap on a quarter is a tap on its name; a body;
and a ``footer`` line. The body is one of:

- ``panels``: four, one over each knob, each a label, a value and a small line;
- ``graph``: series over a window of time, each with what it was asked to reach, the
  newest value written at the right;
- ``progress``: a job's name, how far it is as a number and a bar, and two lines;
- ``mesh``: a bed's heights as coloured cells, with lines beside them;
- ``machines``: two machines side by side, each its name, its state, a line of its
  numbers and its job's bar;
- ``lines``: a big line and small ones, for a screen with nothing to draw.

Nothing here reads a machine, a clock or a file: every number is in the art.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Iterable, List, Optional, Sequence, Tuple

BG = "#111418"
PANEL = "#1a1f26"
RULE = "#2c333c"
INK = "#ffffff"
DIM = "#9aa4ae"
FAINT = "#5c6670"
# The series' own colours, named in an art: a hotend is warm, a bed cool, a router's
# spindle and feed apart from both.
SERIES = {
    "hotend": "#ff7a3d",
    "bed": "#4aa8ff",
    "spindle": "#c38bff",
    "feed": "#3fd08a",
}

TAB_H = 20
FOOT_H = 18


@lru_cache(maxsize=32)
def font(size: int):
    from PIL import ImageFont

    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # a Pillow before 10.1 has the one size
        return ImageFont.load_default()


def colour(name: Optional[str], default: str = BG) -> str:
    from .deck import COLOURS

    if not name:
        return default
    return SERIES.get(name) or COLOURS.get(name) or name


def _fit(pen, text: str, size: int, width: float, least: int = 9):
    """The largest font no bigger than ``size`` that writes ``text`` within ``width``."""
    while size > least and pen.textlength(text, font=font(size)) > width:
        size -= 1
    return font(size)


def _clip(pen, text: str, f, width: float) -> str:
    if pen.textlength(text, font=f) <= width:
        return text
    while text and pen.textlength(text + "…", font=f) > width:
        text = text[:-1]
    return text + "…"


# --- a key ------------------------------------------------------------------------------


def draw_tile(size: Tuple[int, int], art: dict):
    """A key that shows a machine or a number: its title on a band of its accent colour,
    a value, a small line, and at its foot a spark line (``spark``) or a bar (``bar``).
    ``chosen`` frames it in white: the machine the screens are of."""
    from PIL import Image, ImageDraw

    w, h = size
    img = Image.new("RGB", size, BG)
    pen = ImageDraw.Draw(img)
    accent = colour(art.get("accent"), colour("grey"))
    band = 28
    pen.rectangle((0, 0, w, band), fill=accent)
    title = str(art.get("title") or "")
    pen.text((w / 2, band / 2 + 1), title, fill=INK, font=_fit(pen, title, 17, w - 8), anchor="mm")
    value = str(art.get("value") or "")
    foot = 26 if (art.get("spark") or art.get("bar") is not None) else 0
    if value:
        pen.text(
            (w / 2, band + (h - band - foot) * 0.40),
            value,
            fill=INK,
            font=_fit(pen, value, 34, w - 8),
            anchor="mm",
        )
    small = str(art.get("small") or "")
    if small:
        pen.text(
            (w / 2, band + (h - band - foot) * 0.82),
            small,
            fill=DIM,
            font=_fit(pen, small, 15, w - 6),
            anchor="mm",
        )
    box = (6, h - foot, w - 6, h - 6)
    if art.get("spark"):
        _spark(pen, box, art["spark"])
    elif art.get("bar") is not None:
        _bar(pen, (box[0], box[1] + 8, box[2], box[3]), float(art["bar"]), accent)
    if art.get("chosen"):
        pen.rectangle((0, 0, w - 1, h - 1), outline=INK, width=4)
    return img


def _bar(pen, box, fraction: float, fill: str) -> None:
    left, top, right, foot = box
    fraction = max(0.0, min(1.0, fraction))
    pen.rectangle(box, fill=PANEL, outline=RULE)
    if fraction > 0:
        pen.rectangle((left, top, left + (right - left) * fraction, foot), fill=fill)


def _spark(pen, box, spark: dict) -> None:
    """Each of ``spark["series"]``'s lines across ``box``, scaled together over ``lo`` to
    ``hi`` (the art's, else the series' own) and spaced by their times."""
    series = [s for s in spark.get("series", []) if s.get("points")]
    if not series:
        return
    lo, hi = _range(series, spark.get("lo"), spark.get("hi"))
    t0 = min(p[0] for s in series for p in s["points"])
    t1 = max(p[0] for s in series for p in s["points"])
    t0 = min(t0, t1 - float(spark.get("window_s") or 0)) if spark.get("window_s") else t0
    for one in series:
        _line(pen, box, one["points"], t0, t1, lo, hi, colour(one.get("colour")), 2)


# --- the strip ----------------------------------------------------------------------------


def draw_strip(size: Tuple[int, int], art: dict):
    """The strip: its screens along the top, a body, a footer line."""
    from PIL import Image, ImageDraw

    w, h = size
    img = Image.new("RGB", size, BG)
    pen = ImageDraw.Draw(img)
    accent = colour(art.get("accent"), colour("grey"))
    tabs: Sequence[str] = art.get("tabs") or []
    top = 0
    if tabs:
        top = TAB_H
        each = w / len(tabs)
        for i, name in enumerate(tabs):
            x0, x1 = i * each, (i + 1) * each
            lit = i == art.get("tab")
            if lit:
                pen.rectangle((x0, 0, x1, TAB_H - 1), fill=accent)
            else:
                pen.rectangle((x0, 0, x1, TAB_H - 1), fill=PANEL)
            if i:
                pen.line((x0, 0, x0, TAB_H - 1), fill=BG, width=2)
            pen.text(
                ((x0 + x1) / 2, TAB_H / 2),
                str(name),
                fill=INK if lit else DIM,
                font=font(14),
                anchor="mm",
            )
    footer = art.get("footer")
    foot = h - FOOT_H if footer else h
    body = art.get("body") or {}
    box = (0, top, w, foot)
    kind = body.get("kind")
    if kind == "panels":
        _panels(pen, box, body)
    elif kind == "graph":
        _graph(pen, box, body)
    elif kind == "progress":
        _progress(pen, box, body, accent)
    elif kind == "mesh":
        _mesh(pen, box, body)
    elif kind == "machines":
        _machines(pen, box, body)
    else:
        _lines(pen, box, body)
    if footer:
        tone = colour(art.get("footer_colour"), DIM) if art.get("footer_colour") else DIM
        if art.get("footer_colour") in ("red", "amber", "green"):
            pen.rectangle((0, foot, w, h), fill=colour(art["footer_colour"]))
            tone = INK
        f = font(13)
        pen.text(
            (8, foot + FOOT_H / 2),
            _clip(pen, str(footer), f, w - 16),
            fill=tone,
            font=f,
            anchor="lm",
        )
    return img


def _panels(pen, box, body: dict) -> None:
    """Four panels, one over each knob: what the knob does, its value, a small line. A
    panel's ``colour`` tints its value; ``off`` greys it (the knob does nothing now)."""
    x0, y0, x1, y1 = box
    panels = body.get("panels") or []
    if not panels:
        return
    each = (x1 - x0) / len(panels)
    for i, panel in enumerate(panels):
        left, right = x0 + i * each, x0 + (i + 1) * each
        if i:
            pen.line((left, y0 + 4, left, y1 - 4), fill=RULE, width=2)
        off = bool(panel.get("off"))
        label = str(panel.get("label") or "")
        pen.text((left + 10, y0 + 4), label, fill=FAINT if off else DIM, font=font(14), anchor="la")
        value = str(panel.get("value") or "")
        named = panel.get("colour")
        tint = FAINT if off else colour(named, INK) if named and named != "grey" else INK
        pen.text(
            ((left + right) / 2, y0 + (y1 - y0) * 0.50),
            value,
            fill=tint,
            font=_fit(pen, value, 30, each - 20),
            anchor="mm",
        )
        small = str(panel.get("small") or "")
        if small:
            f = font(13)
            pen.text(
                ((left + right) / 2, y1 - 3),
                _clip(pen, small, f, each - 12),
                fill=FAINT if off else DIM,
                font=f,
                anchor="md",
            )


def _range(series: Iterable[dict], lo=None, hi=None) -> Tuple[float, float]:
    values: List[float] = []
    for one in series:
        values += [p[1] for p in one.get("points") or [] if p[1] is not None]
        if one.get("target"):
            values.append(float(one["target"]))
    if not values:
        values = [0.0, 1.0]
    low = float(lo) if lo is not None else min(values)
    high = float(hi) if hi is not None else max(values)
    if high - low < 1e-6:
        high = low + 1.0
    return low, high


def _xy(box, t, v, t0, t1, lo, hi) -> Tuple[float, float]:
    x0, y0, x1, y1 = box
    span = (t1 - t0) or 1.0
    return (
        x0 + (x1 - x0) * (t - t0) / span,
        y1 - (y1 - y0) * (v - lo) / (hi - lo),
    )


def _line(pen, box, points, t0, t1, lo, hi, fill: str, width: int) -> None:
    xy = [_xy(box, t, v, t0, t1, lo, hi) for t, v in points if v is not None]
    if len(xy) == 1:
        x, y = xy[0]
        pen.ellipse((x - 2, y - 2, x + 2, y + 2), fill=fill)
    elif xy:
        pen.line(xy, fill=fill, width=width, joint="curve")


def _dashed(pen, a, b, fill: str, dash: float = 8, gap: float = 6) -> None:
    (xa, ya), (xb, yb) = a, b
    length = math.hypot(xb - xa, yb - ya)
    if length == 0:
        return
    step, at = dash + gap, 0.0
    while at < length:
        end = min(at + dash, length)
        pen.line(
            (
                xa + (xb - xa) * at / length,
                ya + (yb - ya) * at / length,
                xa + (xb - xa) * end / length,
                ya + (yb - ya) * end / length,
            ),
            fill=fill,
            width=1,
        )
        at += step


def _graph(pen, box, body: dict) -> None:
    """Each series over the last ``window_s`` before ``now``: its line, what it was asked
    to reach dashed, and its newest value written at the right in its colour. Gridlines
    at round values; the window's length at the left."""
    x0, y0, x1, y1 = box
    series = body.get("series") or []
    plot = (x0 + 8, y0 + 8, x1 - 150, y1 - 6)
    now = float(body.get("now") or 0)
    window = float(body.get("window_s") or 600)
    t0, t1 = now - window, now
    lo, hi = _range(series, body.get("lo"), body.get("hi"))
    pad = (hi - lo) * 0.08
    lo, hi = max(0.0, lo - pad) if lo >= 0 else lo - pad, hi + pad
    grid = _grid_step(hi - lo)
    v = math.ceil(lo / grid) * grid
    while v < hi:
        _, y = _xy(plot, t0, v, t0, t1, lo, hi)
        pen.line((plot[0], y, plot[2], y), fill=RULE, width=1)
        pen.text((plot[2] + 4, y), f"{v:g}", fill=FAINT, font=font(11), anchor="lm")
        v += grid
    window_label = str(body.get("window_label") or "")
    if window_label:
        f = font(11)
        wide = pen.textlength(window_label, font=f)
        pen.rectangle((plot[0], plot[3] - 13, plot[0] + wide + 6, plot[3]), fill=BG)
        pen.text((plot[0] + 3, plot[3] - 1), window_label, fill=DIM, font=f, anchor="ld")
    labels = []
    for one in series:
        fill = colour(one.get("colour"))
        target = one.get("target")
        if target:
            _dashed(
                pen,
                _xy(plot, t0, target, t0, t1, lo, hi),
                _xy(plot, t1, target, t0, t1, lo, hi),
                fill,
            )
        points = [p for p in one.get("points") or [] if p[0] >= t0]
        _line(pen, plot, points, t0, t1, lo, hi, fill, 3)
        if one.get("value") is not None:
            labels.append((one, fill))
    # The newest of each series written at the right, one under the other: the value
    # in its colour, and what it was asked to reach beside it.
    ys = y0 + 4
    room = (y1 - y0 - 4) / max(1, len(labels))
    for one, fill in labels:
        words = str(one.get("value"))
        aim = str(one.get("aim") or "")
        big = _fit(pen, words, 22, 56)
        pen.text((x1 - 62, ys), words, fill=fill, font=big, anchor="ra")
        if aim:
            pen.text((x1 - 4, ys + 5), aim, fill=DIM, font=_fit(pen, aim, 12, 56), anchor="ra")
        ys += room
    if not any(one.get("points") for one in series):
        pen.text(
            ((plot[0] + plot[2]) / 2, (y0 + y1) / 2),
            str(body.get("empty") or "no readings yet"),
            fill=DIM,
            font=font(16),
            anchor="mm",
        )


def _grid_step(span: float) -> float:
    for step in (1, 2, 5, 10, 20, 25, 50, 100, 200, 500, 1000, 2000, 5000, 10000):
        if span / step <= 4:
            return float(step)
    return 10 ** math.ceil(math.log10(span))


def _progress(pen, box, body: dict, accent: str) -> None:
    """A job: its name and how far it is, a bar the strip's width, and two lines under
    it, the first at the left and the second at the right."""
    x0, y0, x1, y1 = box
    title = str(body.get("title") or "")
    percent = body.get("percent")
    right = f"{percent}%" if percent is not None else ""
    big = font(26)
    room = (x1 - x0) - 40 - (pen.textlength(right, font=big) if right else 0)
    pen.text(
        (x0 + 12, y0 + 6), _clip(pen, title, font(22), room), fill=INK, font=font(22), anchor="la"
    )
    if right:
        pen.text((x1 - 12, y0 + 3), right, fill=INK, font=big, anchor="ra")
    bar = body.get("bar")
    if bar is not None:
        _bar(
            pen,
            (x0 + 12, y0 + 36, x1 - 12, y0 + 46),
            float(bar),
            colour(body.get("bar_colour"), accent),
        )
    f = font(13)
    left = str(body.get("left") or "")
    right_line = str(body.get("right") or "")
    pen.text(
        (x0 + 12, y1 - 3), _clip(pen, left, f, (x1 - x0) * 0.55), fill=DIM, font=f, anchor="ld"
    )
    if right_line:
        pen.text(
            (x1 - 12, y1 - 3),
            _clip(pen, right_line, f, (x1 - x0) * 0.42),
            fill=DIM,
            font=f,
            anchor="rd",
        )


def _diverging(value: float, span: float) -> Tuple[int, int, int]:
    """A height as a colour: blue below the mean, red above it, white at it."""
    if span <= 0:
        return (230, 230, 230)
    k = max(-1.0, min(1.0, value / span))
    if k < 0:
        a = -k
        return (int(230 - 180 * a), int(230 - 110 * a), 255)
    return (255, int(230 - 150 * k), int(230 - 180 * k))


def _mesh(pen, box, body: dict) -> None:
    """A bed's heights, rows from the front, as cells coloured about their mean (blue low,
    red high), drawn as the bed is seen from the front; lines beside them."""
    x0, y0, x1, y1 = box
    mesh = [[v for v in row] for row in body.get("mesh") or [] if row]
    area = (x0 + 10, y0 + 4, x0 + 190, y1 - 4)
    if mesh:
        values = [v for row in mesh for v in row if v is not None]
        mean = sum(values) / len(values) if values else 0.0
        span = max((abs(v - mean) for v in values), default=0.0)
        rows, cols = len(mesh), max(len(r) for r in mesh)
        cw, ch = (area[2] - area[0]) / cols, (area[3] - area[1]) / rows
        for r, row in enumerate(mesh):
            # Rows are from the front: the front row is drawn at the bottom.
            top = area[3] - (r + 1) * ch
            for c, v in enumerate(row):
                left = area[0] + c * cw
                fill = _diverging(v - mean, span) if v is not None else (60, 60, 60)
                pen.rectangle((left + 1, top + 1, left + cw - 1, top + ch - 1), fill=fill)
    else:
        pen.rectangle(area, outline=RULE)
        pen.text(
            ((area[0] + area[2]) / 2, (area[1] + area[3]) / 2),
            "no reading",
            fill=DIM,
            font=font(14),
            anchor="mm",
        )
    lines = body.get("lines") or []
    y = y0 + 4
    for i, line in enumerate(lines):
        f = font(20 if i == 0 else 14)
        if y + (20 if i == 0 else 14) > y1:
            break  # no room: what is left is in the words
        pen.text(
            (area[2] + 18, y),
            _clip(pen, str(line), f, x1 - area[2] - 30),
            fill=INK if i == 0 else DIM,
            font=f,
            anchor="la",
        )
        y += 24 if i == 0 else 17


def _machines(pen, box, body: dict) -> None:
    """Machines side by side, each a column: its name, its state in its colour, a line of
    its numbers, and its job's bar with what it is over it, or nothing where none runs."""
    x0, y0, x1, y1 = box
    machines = body.get("machines") or []
    if not machines:
        return
    each = (x1 - x0) / len(machines)
    small = font(13)
    for i, one in enumerate(machines):
        left, right = x0 + i * each, x0 + (i + 1) * each
        if i:
            pen.line((left, y0 + 4, left, y1 - 4), fill=RULE, width=2)
        tint = colour(one.get("colour"), DIM)
        pen.rectangle((left + 6, y0 + 5, left + 11, y0 + 21), fill=tint)
        pen.text(
            (left + 17, y0 + 3), str(one.get("name") or ""), fill=INK, font=font(17), anchor="la"
        )
        state = str(one.get("state") or "")
        f = font(15)
        shown = tint if tint != colour("grey") else DIM
        pen.text(
            (right - 10, y0 + 5), _clip(pen, state, f, each * 0.5), fill=shown, font=f, anchor="ra"
        )
        line = str(one.get("line") or "")
        pen.text(
            (left + 12, y0 + 24),
            _clip(pen, line, small, each - 24),
            fill=DIM,
            font=small,
            anchor="la",
        )
        if one.get("bar") is not None:
            label = str(one.get("bar_label") or "")
            if label:
                pen.text(
                    (left + 12, y1 - 11),
                    _clip(pen, label, small, each - 24),
                    fill=INK,
                    font=small,
                    anchor="ld",
                )
            _bar(
                pen,
                (left + 12, y1 - 9, right - 12, y1 - 3),
                float(one["bar"]),
                colour(one.get("colour"), colour("blue")),
            )


def _lines(pen, box, body: dict) -> None:
    x0, y0, x1, y1 = box
    text = str(body.get("text") or "")
    pen.text(
        (x0 + 12, y0 + 4),
        _clip(pen, text, font(22), x1 - x0 - 24),
        fill=INK,
        font=font(22),
        anchor="la",
    )
    y = y0 + 31
    for line in body.get("small") or []:
        if not line:
            continue
        if y + 14 > y1:
            break
        f = font(14)
        pen.text(
            (x0 + 12, y), _clip(pen, str(line), f, x1 - x0 - 24), fill=DIM, font=f, anchor="la"
        )
        y += 16
