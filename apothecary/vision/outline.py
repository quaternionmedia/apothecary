"""A finder that reads a drawing: marker strokes on a whiteboard.

Where the plain finder gathers dark pixels into blobs, this one reads what a
stroke encloses. A pixel is a stroke's when it is darker than the whiteboard
near it, so a shadow or a glare across the whiteboard moves no stroke to the
wrong side, and a smear is not a stroke. The ground is the largest light region the strokes leave, whatever runs
round the picture's edge, and is never a shape. A stroke lying on the ground
that closes is the shape of what it encloses, named by the plain finder's rule
and no surer than the plain finder is. A mark filled in is the shape it covers.
A stroke that neither closes nor fills a shape -- a dimension line, an arrow,
writing -- is not reported, and neither is a stroke inside a shape.

Find shapes offers it for a picture that holds a drawing, one closed stroke
at least (``reads``), so a picture of filled shapes keeps its one finder.

Pillow and plain Python, with the network switched off. Every shape is marked
``outline``.

A prototype: no ratified record governs it.
"""

from __future__ import annotations

import functools
from array import array
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

from .models import FoundShape, Picture, ShapeKind
from .plain import (
    _FLIP,
    MIN_BLOB_PIXELS,
    WORKING_EDGE,
    PictureLibraryMissing,
    _blobs,
    _describe,
    _split_point,
)

# How far round a pixel the whiteboard's own brightness is looked for, as a share
# of the working edge: the lightest there is taken as the whiteboard's. Wider than
# any stroke, narrower than a shadow's soft edge.
SURROUND = 1 / 32

# A pixel is a stroke's when it is darker than the whiteboard near it by this
# share of the whiteboard's brightness. A share, not a count: a stroke under a
# shadow is as much darker than the shadowed whiteboard as one in the light is
# than the lit. A smear is darker by less.
DARKER_BY = 0.25

# How many pixels a stroke is widened by on every side before it is read.
WIDER_BY = 2

# A mark with no hole is a shape filled in when some of it lies this many pixels
# from its own edge: more than half a marker's line, however the line turns.
FILLED_FROM = 8

# Where a stroke's upper neighbour is the picture's own edge.
OUTSIDE = -1

# What a mark with no hole is reported as: a filled shape, never a line or a scribble.
_FILLED = (ShapeKind.RECT, ShapeKind.DISC, ShapeKind.TRI)


class OutlineFinder:
    """Finds what a drawing's strokes enclose, using only Pillow and plain Python."""

    def __init__(self, working_edge: int = WORKING_EDGE) -> None:
        self.working_edge = working_edge

    def name(self) -> str:
        return "outline"

    def look(self, image: Path) -> Picture:
        return self._look(Path(image))[0]

    def reads(self, image: Path) -> bool:
        """Whether a picture holds a drawing: a closed stroke lying on its ground."""
        from .cache import picture_hash

        return _closed_strokes(picture_hash(Path(image)), Path(image), self.working_edge) > 0

    def model_digest(self, image: Path) -> str:
        """What the answer rests on besides the picture: a person's words on its
        marks, where a file of them lies beside it (``marks.answers_path``), and
        the sorter's table. What ``apothecary.vision.cache`` keys an answer by."""
        from . import marks

        return marks.digest(Path(image))

    def _look(self, image: Path) -> Tuple[Picture, int]:
        """The picture as read, and how many of its shapes a closed stroke made:
        the shapes of the marks sorted as a diagram's (``apothecary.vision.marks``),
        by the sorter or by a person's word beside the picture."""
        from . import marks

        image = Path(image)
        reading = read_strokes(image, self.working_edge)
        sorted_marks = marks.apply(marks.sort(reading), marks.answers_beside(image))
        drawn = marks.diagram_strokes(sorted_marks)
        read = shapes_of(reading, keep=lambda stroke: stroke.index in drawn)
        picture = Picture(
            name=image.stem,
            pixel_width=reading.full_width,
            pixel_height=reading.full_height,
            shapes=[shape for shape, _, _ in read],
            finder=self.name(),
        )
        return picture, sum(1 for _, closed, _ in read if closed)


@functools.lru_cache(maxsize=256)
def _closed_strokes(digest: str, image: Path, working_edge: int) -> int:
    """How many closed strokes a picture holds, read once for its bytes' hash."""
    try:
        return OutlineFinder(working_edge)._look(image)[1]
    except (OSError, ValueError):
        return 0


@dataclass
class Stroke:
    """One touching run of marker: its pixels in the working picture, what lies
    round it and what it encloses."""

    index: int
    blob: List[int]
    # The label of the region it lies in, or ``OUTSIDE`` where it meets the top edge.
    outer: int
    on_ground: bool
    # The labels of the regions it encloses, and whether any of them is light:
    # with none light it is a mark filled in, or a line.
    holes: List[int]
    closed: bool
    # Its upright box in working pixels: left, top, right, bottom, each inclusive.
    box: Tuple[int, int, int, int]


@dataclass
class Reading:
    """A picture read as strokes: the working picture, its strokes, the regions
    they leave, and which region is the whiteboard's own surface."""

    width: int
    height: int
    full_width: int
    full_height: int
    grey: bytes
    rgb: bytes
    light_from: int
    regions: List[List[int]]
    ground: int
    strokes: List[Stroke] = field(default_factory=list)
    # The stroke that encloses each region, by the region's label.
    encloser: Dict[int, int] = field(default_factory=dict)


def read_strokes(image: Path, working_edge: int = WORKING_EDGE) -> Reading:
    """A picture's strokes, each with what lies round it and what it encloses."""
    try:
        from PIL import Image, ImageFilter, ImageOps
    except ImportError as exc:  # pragma: no cover - depends on install
        raise PictureLibraryMissing(
            "the outline finder needs Pillow; install it or use the stated finder"
        ) from exc

    with Image.open(image) as opened:
        upright = ImageOps.exif_transpose(opened)
        full_width, full_height = upright.size
        if upright.mode in ("RGBA", "LA") or "transparency" in upright.info:
            filled = Image.new("RGBA", upright.size, (255, 255, 255, 255))
            filled.paste(upright.convert("RGBA"), mask=upright.convert("RGBA"))
            upright = filled
        scale = working_edge / max(upright.size)
        size = (max(1, round(upright.width * scale)), max(1, round(upright.height * scale)))
        colour = upright.convert("RGB").resize(size)
        grey = colour.convert("L")
        width, height = grey.size
        # The lightest within reach, four pixels further at each pass.
        around = grey
        for _ in range(max(1, round(working_edge * SURROUND / 4))):
            around = around.filter(ImageFilter.MaxFilter(9))
        around = around.filter(ImageFilter.BoxBlur(4))
        pixels = grey.tobytes()
        marked = bytes(
            1 if value < near - near * DARKER_BY else 0
            for value, near in zip(pixels, around.tobytes(), strict=True)
        )
        # Wider all round: a stroke a pixel thin on a slant holds together, and
        # a gap in one no wider than twice this closes.
        stroke_mask = (
            Image.frombytes("L", (width, height), marked)
            .filter(ImageFilter.MaxFilter(2 * WIDER_BY + 1))
            .tobytes()
        )
        light_from = _split_point(grey.histogram())
        rgb = colour.tobytes()

    blobs = _blobs(stroke_mask, width, height, MIN_BLOB_PIXELS)
    regions = _blobs(stroke_mask.translate(_FLIP), width, height, MIN_BLOB_PIXELS)
    reading = Reading(
        width=width,
        height=height,
        full_width=full_width,
        full_height=full_height,
        grey=pixels,
        rgb=rgb,
        light_from=light_from,
        regions=regions,
        ground=_ground(regions, pixels, light_from) if regions else 0,
    )
    if not regions:
        return reading
    # A region's label is its place in the list, from 1; a stroke's pixel, and a
    # speck too small to be either, is 0.
    labels = array("i", bytes(4 * width * height))
    for label, region in enumerate(regions, start=1):
        for index in region:
            labels[index] = label
    for index, blob in enumerate(blobs):
        top = min(blob)
        outer = labels[top - width] if top >= width else OUTSIDE
        holes = sorted(_touching(blob, labels, width, height) - {outer, 0})
        xs = [pixel % width for pixel in blob]
        ys = [pixel // width for pixel in blob]
        reading.strokes.append(
            Stroke(
                index=index,
                blob=blob,
                outer=outer,
                on_ground=outer == reading.ground,
                holes=holes,
                closed=any(_light(regions[hole - 1], pixels, light_from) for hole in holes),
                box=(min(xs), min(ys), max(xs), max(ys)),
            )
        )
        for hole in holes:
            reading.encloser[hole] = index
    return reading


def shapes_of(
    reading: Reading,
    keep: Optional[Callable[[Stroke], bool]] = None,
    lying_in: Optional[int] = None,
) -> List[Tuple[FoundShape, bool, int]]:
    """The shapes the strokes lying in one region make, largest first: each with
    whether a closed stroke made it (a mark filled in did not) and its stroke's
    index. The region is the ground unless ``lying_in`` names another; ``keep``
    leaves a stroke out."""
    width, height = reading.width, reading.height
    region = reading.ground if lying_in is None else lying_in
    found: List[Tuple[int, FoundShape, bool, int]] = []
    for stroke in reading.strokes:
        if stroke.outer != region or (keep is not None and not keep(stroke)):
            continue
        whole = _filled(stroke.blob, width)
        covered = _describe(whole, width, height)
        if not stroke.closed and len(stroke.holes) <= 1:
            # A mark filled in: no hole, or one as dark as the mark, which is the
            # middle of a filled shape wider than the whiteboard is looked for round
            # a pixel. It is read as narrow as it was drawn.
            drawn = _describe(_narrowed(whole, width), width, height)
            if drawn is not None and (stroke.holes or _a_filled_shape(drawn, stroke.blob, width)):
                found.append((len(stroke.blob), drawn, False, stroke.index))
            continue
        for hole in stroke.holes:
            inside = _filled(reading.regions[hole - 1], width)
            shape = _describe(inside, width, height)
            if shape is None:
                continue
            if len(stroke.holes) == 1 and covered is not None:
                # A marker's line has a width, and the drawing means its middle:
                # halfway between what the stroke encloses and what it covers.
                shape = _between(shape, covered)
            found.append((len(inside), shape, True, stroke.index))
    found.sort(key=lambda one: one[0], reverse=True)
    return [
        (shape.model_copy(update={"origin": "outline"}), closed, index)
        for _, shape, closed, index in found
    ]


def _a_filled_shape(mark: FoundShape, blob: List[int], width: int) -> bool:
    """Whether a mark with no hole is a shape filled in: one of the families, and
    deeper than a marker's line is wide."""
    if mark.kind not in _FILLED:
        return False
    from PIL import ImageFilter

    box, _, _ = _boxed(blob, width, margin=FILLED_FROM)
    for _ in range(FILLED_FROM // 2):
        box = box.filter(ImageFilter.MinFilter(5))
    return box.getbbox() is not None


def _light(region: List[int], pixels: bytes, light_from: int) -> bool:
    """Whether a region is on the light side of the picture's split of light from dark."""
    sample = region[:: max(1, len(region) // 500)]
    return sum(pixels[index] for index in sample) / len(sample) > light_from


def _ground(regions: List[List[int]], pixels: bytes, light_from: int) -> int:
    """The label of the whiteboard's own surface: the largest light region, or the
    largest of all when none is light."""
    for label, region in enumerate(regions, start=1):
        if _light(region, pixels, light_from):
            return label
    return 1


def _touching(stroke: List[int], labels: array, width: int, height: int) -> Set[int]:
    """The labels of every region a stroke's pixels sit against."""
    last = width * height
    beside: Set[int] = set()
    for index in stroke:
        column = index % width
        if column:
            beside.add(labels[index - 1])
        if column < width - 1:
            beside.add(labels[index + 1])
        if index >= width:
            beside.add(labels[index - width])
        if index + width < last:
            beside.add(labels[index + width])
    return beside


def _filled(blob: List[int], width: int) -> List[int]:
    """A blob with everything it encloses: each pixel its own box holds that the
    box's edge cannot reach without crossing the blob."""
    from PIL import ImageDraw

    box, left, top = _boxed(blob, width, margin=1)
    wide = box.width
    ImageDraw.floodfill(box, (0, 0), 128)
    return [
        (top + offset // wide) * width + left + offset % wide
        for offset, value in enumerate(box.tobytes())
        if value != 128
    ]


def _narrowed(blob: List[int], width: int) -> List[int]:
    """A blob less what its strokes were widened by."""
    from PIL import ImageFilter

    box, left, top = _boxed(blob, width, margin=1)
    wide = box.width
    box = box.filter(ImageFilter.MinFilter(2 * WIDER_BY + 1))
    return [
        (top + offset // wide) * width + left + offset % wide
        for offset, value in enumerate(box.tobytes())
        if value
    ]


def _boxed(blob: List[int], width: int, margin: int):
    """A blob drawn alone, white on black, ``margin`` pixels of black round it,
    with where the drawing's left and top are in the picture."""
    from PIL import Image

    xs = [index % width for index in blob]
    ys = [index // width for index in blob]
    left, top = min(xs) - margin, min(ys) - margin
    wide, high = max(xs) - left + margin + 1, max(ys) - top + margin + 1
    cells = bytearray(wide * high)
    for x, y in zip(xs, ys, strict=True):
        cells[(y - top) * wide + (x - left)] = 255
    return Image.frombytes("L", (wide, high), bytes(cells)), left, top


def _between(inner: FoundShape, outer: FoundShape) -> FoundShape:
    """The inner shape, its place and sides moved halfway to the outer one's."""

    def half(a: float, b: float) -> float:
        return (a + b) / 2

    return inner.model_copy(
        update={
            "min_point": inner.min_point.model_copy(
                update={
                    "x": half(inner.min_point.x, outer.min_point.x),
                    "y": half(inner.min_point.y, outer.min_point.y),
                }
            ),
            "max_point": inner.max_point.model_copy(
                update={
                    "x": half(inner.max_point.x, outer.max_point.x),
                    "y": half(inner.max_point.y, outer.max_point.y),
                }
            ),
            "long_side": half(inner.long_side, outer.long_side),
            "short_side": half(inner.short_side, outer.short_side),
        }
    )


__all__ = [
    "DARKER_BY",
    "FILLED_FROM",
    "OUTSIDE",
    "SURROUND",
    "WIDER_BY",
    "OutlineFinder",
    "Reading",
    "Stroke",
    "read_strokes",
    "shapes_of",
]
