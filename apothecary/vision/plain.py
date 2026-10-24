"""A plain finder that actually looks at the pixels.

Deliberately simple and openly imperfect. It shrinks the picture, splits it into
light and dark, gathers touching pixels into blobs, and guesses each blob's
family from how much of its box it fills.

It will be beaten by anything trained on real pictures. That is fine and it is
the point: this runs on your own machine with the network switched off, using
one picture library that was already installed, and nothing about it can stop
working because somebody else changed their mind. Slow and yours can be made
fast later. See ``docs/plans/proposals/runs-and-stays-local.md``.

Every shape it reports is marked ``plain`` and carries a confidence well under
1.0, so nothing downstream mistakes a guess for a measurement.

PROTOTYPE — not ratified.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import List, Optional, Tuple

from ..models.vectors import Vector2D
from .geometry import edge_points, smallest_box
from .models import FoundShape, Picture, ShapeKind

# Every picture is resized to this along its longer edge before looking —
# shrunk if bigger, stretched if smaller. Shrinking keeps a large photograph
# quick. Stretching matters just as much: without it, the speckle floor below
# means something different in a thumbnail than in a photograph, and identical
# content is found in one and lost in the other.
WORKING_EDGE = 512

# A blob smaller than this many pixels is treated as speckle.
#
# A count, not a fraction of the picture. As a fraction it scaled with the
# picture, so a small shape in a large picture was thrown away for being small
# relative to a frame it had nothing to do with — measured at 33% of shapes
# found when they were drawn at 3-6% of the picture's short side. Speckle is
# speckle at any picture size, so an absolute floor is the honest test.
MIN_BLOB_PIXELS = 25

# How full of its *tightest* box each family is, and how far off we still
# accept. Against that box the numbers hold at any angle: a rectangle fills all
# of it, a circle about 0.785, a triangle about 0.5. The gaps between those
# three are wide, which is why one crude number gets as far as it does.
_FAMILIES: List[Tuple[ShapeKind, float, float]] = [
    (ShapeKind.RECT, 0.97, 0.12),
    (ShapeKind.DISC, 0.785, 0.08),
    (ShapeKind.TRI, 0.50, 0.11),
]

# Below this ratio of short edge to long edge, a blob is a line, whatever it fills.
LINE_RATIO = 0.12

# A shape narrower than this many pixels is named on too little evidence to
# trust. Measured: drawn at 3-6% of the picture's short side, naming was right
# 33% of the time, against 100% at 14-26%. The names are still reported, because
# a guess beats silence, but the confidence is pulled down to say so.
TRUSTWORTHY_PIXELS = 40
LEAST_TRUSTED = 0.35


class PictureLibraryMissing(RuntimeError):
    """Pillow is not installed, so pixels cannot be read."""


class PlainFinder:
    """Finds shapes using only Pillow and plain Python."""

    def __init__(self, working_edge: int = WORKING_EDGE) -> None:
        self.working_edge = working_edge

    def name(self) -> str:
        return "plain"

    def look(self, image: Path) -> Picture:
        # Take a plain string too. The protocol says Path, and everything inside
        # here needs one, but a caller with a string should get a picture rather
        # than a puzzle about a missing attribute.
        image = Path(image)
        try:
            from PIL import Image
        except ImportError as exc:  # pragma: no cover - depends on install
            raise PictureLibraryMissing(
                "the plain finder needs Pillow; install it or use the stated finder"
            ) from exc

        from PIL import ImageOps

        with Image.open(image) as opened:
            # A photograph from a phone is usually stored one way and meant to
            # be seen another, with a note saying which. Ignoring the note turns
            # every upright photograph on its side.
            upright = ImageOps.exif_transpose(opened)
            full_width, full_height = upright.size

            # A see-through background is stored as black underneath. Dropping
            # the see-through part without filling it first turns a dark shape
            # on nothing into a picture that is entirely dark, and nothing is
            # found at all.
            if upright.mode in ("RGBA", "LA") or "transparency" in upright.info:
                filled = Image.new("RGBA", upright.size, (255, 255, 255, 255))
                filled.paste(upright.convert("RGBA"), mask=upright.convert("RGBA"))
                upright = filled

            grey = upright.convert("L")
            scale = self.working_edge / max(grey.size)
            grey = grey.resize(
                (max(1, round(grey.width * scale)), max(1, round(grey.height * scale)))
            )
            pixels = list(grey.getdata())
            width, height = grey.size

        cut = _split_point(pixels)
        mask = _foreground(pixels, cut, width, height)
        blobs = _blobs(mask, width, height, MIN_BLOB_PIXELS)

        shapes = [shape for blob in blobs if (shape := _describe(blob, width, height)) is not None]
        return Picture(
            name=image.stem,
            pixel_width=full_width,
            pixel_height=full_height,
            shapes=shapes,
            finder=self.name(),
        )


def _split_point(pixels: List[int]) -> int:
    """Otsu's method: the brightness that best separates the picture in two.

    Tries every cut and keeps the one where the two sides are furthest apart
    relative to how spread out each side is.
    """
    counts = [0] * 256
    for value in pixels:
        counts[value] += 1
    total = len(pixels)
    sum_all = sum(i * counts[i] for i in range(256))

    best_cut, best_spread = 0, -1.0
    seen, sum_seen = 0, 0
    for cut in range(256):
        seen += counts[cut]
        if seen == 0:
            continue
        rest = total - seen
        if rest == 0:
            break
        sum_seen += cut * counts[cut]
        mean_low = sum_seen / seen
        mean_high = (sum_all - sum_seen) / rest
        spread = seen * rest * (mean_low - mean_high) ** 2
        if spread > best_spread:
            best_spread, best_cut = spread, cut
    return best_cut


def _foreground(pixels: List[int], cut: int, width: int, height: int) -> List[bool]:
    """Mark the shapes rather than the background.

    The background is whatever runs round the outside of the picture. Counting
    which side of the cut is rarer instead looks right until somebody
    photographs one object filling the frame — then the object is the majority,
    the background gets called the shape, and a single confident answer comes
    back describing the whole picture. Photographing a thing so it fills the
    frame is the normal way to photograph a thing.
    """
    dark = [value <= cut for value in pixels]

    border: List[bool] = []
    last_row = (height - 1) * width
    for x in range(width):
        border.append(dark[x])
        border.append(dark[last_row + x])
    for y in range(height):
        border.append(dark[y * width])
        border.append(dark[y * width + width - 1])

    background_is_dark = sum(border) * 2 > len(border)
    return [not value for value in dark] if background_is_dark else dark


def _blobs(mask: List[bool], width: int, height: int, min_area: int) -> List[List[int]]:
    """Gather touching marked pixels into groups, biggest first.

    Walks outward from each unvisited pixel using a queue rather than recursion,
    because a large blob would otherwise run out of stack.
    """
    seen = bytearray(len(mask))
    found: List[List[int]] = []
    for start in range(len(mask)):
        if seen[start] or not mask[start]:
            continue
        queue = deque([start])
        seen[start] = 1
        blob: List[int] = []
        while queue:
            here = queue.popleft()
            blob.append(here)
            x, y = here % width, here // width
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if 0 <= nx < width and 0 <= ny < height:
                    step = ny * width + nx
                    if not seen[step] and mask[step]:
                        seen[step] = 1
                        queue.append(step)
        if len(blob) >= max(1, min_area):
            found.append(blob)
    found.sort(key=len, reverse=True)
    return found


def _describe(blob: List[int], width: int, height: int) -> Optional[FoundShape]:
    """Turn one blob into a shape.

    The family is guessed from how much of its *tightest* box the blob fills —
    the smallest box at any angle, not the upright one. Judging by the upright
    box calls a square turned 45° a triangle, because both fill half of it. The
    tightest box gives the same answer whichever way the picture was taken, and
    hands back the angle as a bonus.
    """
    xs = [i % width for i in blob]
    ys = [i // width for i in blob]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    if max_x - min_x < 1 or max_y - min_y < 1:
        return None

    box = smallest_box(edge_points(blob, width, set(blob)))
    if box.area <= 0:
        return None

    fullness = len(blob) / box.area
    thinness = min(box.width, box.height) / max(box.width, box.height)
    # The angle is only meaningful for something with a long side. A circle has
    # no orientation, and a true square's is arbitrary within a quarter turn.
    # The threshold is deliberately close to square: a panel five pixels off
    # square has an unambiguous direction, and throwing it away built the panel
    # a quarter turn out.
    turned = box.degrees if thinness < 0.995 else 0.0

    if thinness < LINE_RATIO:
        kind, confidence = ShapeKind.LINE, 0.6
    else:
        kind, confidence = ShapeKind.POLY, 0.3
        for family, ideal, tolerance in _FAMILIES:
            gap = abs(fullness - ideal)
            if gap <= tolerance:
                # Closer to the ideal fullness means a slightly surer guess,
                # but never sure: the ceiling is 0.8, because this finder is
                # guessing from one crude number.
                kind = family
                confidence = round(0.45 + 0.35 * (1 - gap / tolerance), 2)
                break

    # A small shape is named from very few pixels, and the fullness number gets
    # noisy long before it gets wrong-looking. Say so in the confidence rather
    # than reporting a coarse guess at the same certainty as a clear one.
    narrow = min(box.width, box.height)
    if narrow < TRUSTWORTHY_PIXELS:
        share = max(0.0, narrow / TRUSTWORTHY_PIXELS)
        confidence = round(confidence * (LEAST_TRUSTED + (1 - LEAST_TRUSTED) * share), 2)

    # A circle looks the same whichever way round it is, so the direction its
    # tightest box happened to land in means nothing and reporting it would send
    # a round piece into the build at a made-up angle.
    if kind is ShapeKind.DISC:
        turned = 0.0

    return FoundShape(
        kind=kind,
        min_point=Vector2D(x=min_x / width, y=min_y / height),
        max_point=Vector2D(x=(max_x + 1) / width, y=(max_y + 1) / height),
        # Rounding can land exactly on half a turn, which is the same as none
        # and is outside what a shape will accept.
        turned_degrees=round(turned, 1) % 180.0,
        long_side=box.width / width,
        short_side=box.height / width,
        confidence=confidence,
        origin="plain",
    )
