"""Whiteboards drawn to order, for the tests that read them: one photographed from
one side (``photograph``), and one on a wall square on, its drawing changeable
(``drawing``)."""

from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFont

WIDE, HIGH = 1600, 1200
# The whiteboard's corners in ``photograph``: top-left, top-right, bottom-right,
# bottom-left. Its right side is further away, so shorter.
LEANING = [(180, 150), (1380, 300), (1400, 900), (160, 1050)]
INK, BLACK = (20, 30, 120), (10, 10, 10)


def onto(corners):
    """The mapping from a place on the whiteboard, each way 0 to 1, to the
    photograph: the projective one that takes the unit square to four corners."""
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = corners
    dx1, dx2, sx = x1 - x2, x3 - x2, x0 - x1 + x2 - x3
    dy1, dy2, sy = y1 - y2, y3 - y2, y0 - y1 + y2 - y3
    below = dx1 * dy2 - dx2 * dy1
    g = (sx * dy2 - dx2 * sy) / below
    h = (dx1 * sy - sx * dy1) / below
    a, b, c = x1 - x0 + g * x1, x3 - x0 + h * x3, x0
    d, e, f = y1 - y0 + g * y1, y3 - y0 + h * y3, y0

    def place(u, v):
        w = g * u + h * v + 1
        return ((a * u + b * v + c) / w, (d * u + e * v + f) / w)

    return place


def photograph(path, corners=LEANING):
    """A plate, a disc and a wedge drawn on a whiteboard seen from one side."""
    place = onto(corners)
    image = Image.new("RGB", (WIDE, HIGH), (60, 60, 64))
    pen = ImageDraw.Draw(image)
    pen.polygon([place(u, v) for u, v in ((0, 0), (1, 0), (1, 1), (0, 1))], fill=(238, 238, 236))
    ink = (20, 30, 120)
    plate = [(0.15, 0.2), (0.45, 0.2), (0.45, 0.45), (0.15, 0.45)]
    pen.polygon([place(u, v) for u, v in plate], outline=ink, width=8)
    # A disc 240 mm across on a whiteboard 1200 by 900: 0.2 of its width, 0.2667 of its height.
    ring = [
        (0.7 + 0.1 * math.cos(t / 60 * math.tau), 0.35 + 0.1333 * math.sin(t / 60 * math.tau))
        for t in range(60)
    ]
    pen.polygon([place(u, v) for u, v in ring], outline=ink, width=8)
    wedge = [(0.25, 0.9), (0.45, 0.9), (0.35, 0.6)]
    pen.polygon([place(u, v) for u, v in wedge], outline=ink, width=8)
    image.save(path)
    return path


def drawing(
    path, *, plate=(250, 250, 700, 520), disc=(900, 250, 1200, 550), wedge=True, words=True
):
    """A whiteboard on a wall, square on: a plate, a disc, a wedge, and writing."""
    image = Image.new("RGB", (1800, 1400), (60, 60, 64))
    pen = ImageDraw.Draw(image)
    pen.rectangle((100, 100, 1700, 1300), fill=(238, 238, 236))
    shift = (100, 100)
    move = lambda box: tuple(v + shift[i % 2] for i, v in enumerate(box))  # noqa: E731
    pen.rectangle(move(plate), outline=INK, width=9)
    if disc:
        pen.ellipse(move(disc), outline=INK, width=9)
    if wedge:
        pen.polygon(((450, 1050), (750, 1050), (600, 800)), outline=INK, width=9)
    if words:
        pen.text((1000, 900), "lid, 3 off", fill=BLACK, font=ImageFont.load_default(size=44))
    image.save(path)
