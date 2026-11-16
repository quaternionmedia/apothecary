"""A whiteboard found in a photograph, and the photograph squared to it.

A photograph taken from one side shows a whiteboard as a leaning four-sided
shape. Its corners are found from the outline of the ground the outline finder
reads the strokes on, and the photograph is redrawn as the whiteboard seen
square on: a picture as wide as the whiteboard, which every other step reads as
it reads any picture. Squared, the picture's width is the whiteboard's, so the
whiteboard's width sizes everything drawn on it.

A person's word on a corner wins. It is kept as an example beside the
photograph: where the finder put the corners, and where the person did.

Pillow and plain Python, with the network switched off.

A prototype: no ratified record governs it.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from pydantic import BaseModel

from ..homography import homography
from .geometry import edge_points, outline
from .outline import WIDER_BY, is_light, read_strokes

FORMAT = "apothecary.corners/1"

# A whiteboard's surface is at least this bright, of 255, where it is lightest in
# the picture: under it, nothing in the picture is a whiteboard.
DARKEST_GROUND = 100

# A squared picture's longer edge, in pixels.
SQUARED_EDGE = 1600

# The part a whiteboard of a site is, and the folder under the picture root its
# squared pictures are kept in: made from a photograph, never listed as one.
PART = "whiteboard"
SQUARED_FOLDER = "squared"

Corner = Tuple[float, float]
# The order corners are named, read and kept in.
NAMES = ("top-left", "top-right", "bottom-right", "bottom-left")


class Corners(BaseModel):
    """A whiteboard's four corners in a photograph, as fractions of it, with what
    the finder said where a person said otherwise."""

    format: str = FORMAT
    picture: str = ""
    corners: List[Corner]
    by: str = "finder"
    guess: Optional[List[Corner]] = None
    # Whether the whiteboard's ground reaches the photograph's own edge, so the
    # corners are the photograph's and nothing was found.
    fills: bool = False


class NoWhiteboard(ValueError):
    """Nothing light enough, or large enough, to be a whiteboard."""


def corners_path(image: Path) -> Path:
    """Where a person's word on a photograph's corners lies beside it."""
    return Path(image).with_suffix(".corners.json")


def find(image: Path) -> Corners:
    """The whiteboard's corners as the finder sees them: the four points of its
    ground's outline furthest towards each corner of the photograph."""
    reading = read_strokes(Path(image))
    if not reading.regions or not reading.ground:
        raise NoWhiteboard(f"{Path(image).name}: nothing in it is a whiteboard's surface")
    ground = reading.regions[reading.ground - 1]
    sample = ground[:: max(1, len(ground) // 500)]
    brightness = sum(reading.grey[i] for i in sample) / len(sample)
    if not is_light(ground, reading.grey, reading.light_from) or brightness < DARKEST_GROUND:
        raise NoWhiteboard(f"{Path(image).name}: nothing in it is light enough to be a whiteboard")
    if len(ground) < 0.15 * reading.width * reading.height:
        raise NoWhiteboard(
            f"{Path(image).name}: its lightest surface is under a sixth of it, too small to square"
        )
    hull = outline(edge_points(ground, reading.width, set(ground)))
    wide, high = reading.width - 1, reading.height - 1
    picked = [
        min(hull, key=lambda p: p[0] + p[1]),
        max(hull, key=lambda p: p[0] - p[1]),
        max(hull, key=lambda p: p[0] + p[1]),
        min(hull, key=lambda p: p[0] - p[1]),
    ]
    # The surface is read short of its own edge by what a stroke is widened by,
    # the wall's edge being read as one: each corner goes that far back out.
    out = WIDER_BY - 0.5
    middle_x = sum(x for x, _ in picked) / 4
    middle_y = sum(y for _, y in picked) / 4
    picked = [
        (
            min(max(x + (out if x > middle_x else -out), 0), wide),
            min(max(y + (out if y > middle_y else -out), 0), high),
        )
        for x, y in picked
    ]
    found = [(round(x / wide, 4), round(y / high, 4)) for x, y in picked]
    near = 2 / max(wide, high)
    fills = all(min(x, 1 - x) <= near and min(y, 1 - y) <= near for x, y in found)
    return Corners(corners=found, fills=fills)


def with_word(image: Path, found: Corners) -> Corners:
    """The corners with the person's word that lies beside the photograph, if any."""
    path = corners_path(image)
    if not path.is_file():
        return found
    try:
        held = json.loads(path.read_text(encoding="utf-8"))
        if held.get("format") != FORMAT:
            return found
        said = Corners.model_validate(held)
    except (OSError, ValueError):
        return found
    return said.model_copy(update={"guess": found.corners, "fills": False})


def say(
    image: Path, found: Corners, moved: Sequence[Tuple[str, Corner]], by: str = "you"
) -> Corners:
    """A person's word on some corners, by name, kept beside the photograph."""
    from .cache import picture_hash

    corners = list(found.corners)
    for name, where in moved:
        if name not in NAMES:
            raise KeyError(f"no corner {name!r}; a corner is one of {', '.join(NAMES)}")
        x, y = where
        if not (0 <= x <= 1 and 0 <= y <= 1):
            raise ValueError(
                f"{name} at {x}, {y}: a corner is a fraction of the photograph, 0 to 1"
            )
        corners[NAMES.index(name)] = (x, y)
    said = Corners(
        picture=picture_hash(Path(image)),
        corners=corners,
        by=by,
        guess=found.guess or found.corners,
    )
    corners_path(image).write_text(said.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return said


def proportions(image: Path, corners: Corners) -> float:
    """How many times wider than tall the whiteboard is, from its sides' lengths
    in the photograph. Seen from far to one side it reads narrower than it is."""
    from PIL import Image, ImageOps

    with Image.open(image) as opened:
        wide, high = ImageOps.exif_transpose(opened).size
    tl, tr, br, bl = [(x * wide, y * high) for x, y in corners.corners]
    across = (math.dist(tl, tr) + math.dist(bl, br)) / 2
    down = (math.dist(tl, bl) + math.dist(tr, br)) / 2
    return across / max(down, 1e-9)


def square(
    image: Path,
    out: Path,
    corners: Optional[Corners] = None,
    wide_over_tall: Optional[float] = None,
) -> Tuple[Corners, Tuple[int, int]]:
    """Redraw a photograph as its whiteboard seen square on, written to ``out``.

    The corners are the finder's with a person's word beside the photograph,
    unless given. The picture is as many times wider than tall as
    ``wide_over_tall`` says, a whiteboard's own proportions, or as its sides read
    in the photograph. What was used, and the squared picture's size, come back.
    """
    from PIL import Image, ImageOps

    image, out = Path(image), Path(out)
    used = corners or with_word(image, find(image))
    ratio = wide_over_tall or proportions(image, used)
    if ratio >= 1:
        size = (SQUARED_EDGE, max(1, round(SQUARED_EDGE / ratio)))
    else:
        size = (max(1, round(SQUARED_EDGE * ratio)), SQUARED_EDGE)
    with Image.open(image) as opened:
        upright = ImageOps.exif_transpose(opened).convert("RGB")
        wide, high = upright.size
        squared = upright.transform(
            size,
            Image.Transform.PERSPECTIVE,
            data=_from_square([(x * wide, y * high) for x, y in used.corners], size),
            resample=Image.Resampling.BICUBIC,
        )
    squared.save(out)
    return used, size


def _from_square(corners: Sequence[Corner], size: Tuple[int, int]) -> Tuple[float, ...]:
    """The eight numbers that take a pixel of the squared picture to its place in
    the photograph: the mapping (``apothecary/homography.py``) of the squared
    picture's rectangle onto four corners, named top-left, top-right, bottom-right,
    bottom-left, its last number 1 and left out, as Pillow takes it. ValueError when
    three of the corners lie on one line."""
    wide, high = size
    rectangle = ((0.0, 0.0), (wide, 0.0), (wide, high), (0.0, high))
    (a, b, c), (d, e, f), (g, h, _) = homography(rectangle, list(corners))
    return (a, b, c, d, e, f, g, h)


def is_whiteboard(node) -> bool:
    """Whether a site's structure is a whiteboard: the part ``PART``."""
    return getattr(node, "part_ref", None) == PART


def surface_of(node) -> Tuple[float, float]:
    """A whiteboard's writing surface, width and height in mm: its part's, at the
    sizes the part is drawn at."""
    from ..projects.parts.whiteboard import surface

    size = surface()
    return size.x, size.z


def squared_name(source: Path, corners: Corners) -> str:
    """The name a squared picture is kept under: its photograph's, and a digest of
    the photograph and the corners, so other corners are another picture."""
    import hashlib

    from .cache import picture_hash

    held = picture_hash(source) + json.dumps(
        [[round(x, 4), round(y, 4)] for x, y in corners.corners]
    )
    return f"{source.stem}-{hashlib.sha256(held.encode()).hexdigest()[:12]}.png"


def square_kept(
    source: Path, root: Path, corners: Corners, wide_over_tall: float
) -> Tuple[str, Tuple[int, int]]:
    """A photograph squared to its whiteboard and kept under the picture root, in
    ``SQUARED_FOLDER``, the person's alone: its path there, and its size."""
    import os

    folder = root / SQUARED_FOLDER
    if folder.is_symlink():
        raise OSError(f"{SQUARED_FOLDER}/ is a link elsewhere; nothing is kept there")
    folder.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(folder, 0o700)
    except OSError:
        pass
    out = folder / squared_name(source, corners)
    if not out.is_file():
        square(source, out, corners, wide_over_tall)
    from PIL import Image

    with Image.open(out) as kept:
        size = kept.size
    return out.relative_to(root).as_posix(), size


__all__ = [
    "Corners",
    "FORMAT",
    "NAMES",
    "NoWhiteboard",
    "SQUARED_EDGE",
    "PART",
    "SQUARED_FOLDER",
    "corners_path",
    "is_whiteboard",
    "square_kept",
    "squared_name",
    "surface_of",
    "find",
    "proportions",
    "say",
    "square",
    "with_word",
]
