"""A region's colour, read off its pixels: the plain reader beside every model.

The median of each channel over the region, upright as the picture is seen, is
its ``rgb``; the basic colour word nearest it is its ``colour``. A colour in a
picture is the camera's: under warm light a white plug reads amber, so the
subject is the sighting, never the thing, until a person says otherwise.

Pillow alone, with the network off.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import List, Optional, Tuple

from ..evidence.observation import Observation, Origin, Ref, Region, Sighting, now
from ..evidence.words import COLOUR_UNIT, hex_of, nearest_colour

READER = "plain/colour"

# A region narrower than this many pixels on a side is too small to name.
SMALLEST_PIXELS = 2


def digest(picture: Path) -> str:
    """A picture file's SHA-256: the name a sighting gives it."""
    return hashlib.sha256(picture.read_bytes()).hexdigest()


def crop(picture: Path, box: Tuple[float, float, float, float]):
    """The region of a picture, upright, as RGB: in memory, never written."""
    from PIL import Image, ImageOps

    with Image.open(picture) as opened:
        upright = ImageOps.exif_transpose(opened).convert("RGB")
    width, height = upright.size
    left, top, right, bottom = box
    pixels = (
        max(0, int(left * width)),
        max(0, int(top * height)),
        min(width, max(int(left * width) + 1, int(round(right * width)))),
        min(height, max(int(top * height) + 1, int(round(bottom * height)))),
    )
    return upright.crop(pixels)


def mean_rgb(region_pixels) -> Tuple[int, int, int]:
    """A cropped region's mean colour, each channel 0 to 255."""
    from PIL import ImageStat

    return tuple(int(c) for c in ImageStat.Stat(region_pixels).mean[:3])


def read_colour(
    picture: Path,
    box: Tuple[float, float, float, float],
    region: str,
    taken: str,
    path: Optional[str] = None,
) -> List[Observation]:
    """The region's ``rgb`` and ``colour``, as the plain reader reads them; unread,
    with why, when the region is too small. ``path`` is how the evidence names the
    picture, its path under the picture root; the file's own path otherwise."""
    from PIL import ImageStat

    seen = digest(picture)
    subject = Sighting(sighting=Region(picture=seen, region=region, box=box))
    origin = Origin(kind="read", by={"name": READER})
    evidence = [Ref(kind="picture", id=seen, path=path or str(picture), box=box)]
    region_pixels = crop(picture, box)
    common = dict(subject=subject, origin=origin, at=taken, recorded_at=now(), evidence=evidence)
    if min(region_pixels.size) < SMALLEST_PIXELS:
        why = f"the region is too small to read: {region_pixels.size[0]} × {region_pixels.size[1]} pixels"
        return [
            Observation(property="rgb", why=why, **common),
            Observation(property="colour", why=why, **common),
        ]
    median = tuple(int(c) for c in ImageStat.Stat(region_pixels).median[:3])
    word, _ = nearest_colour(median)
    return [
        Observation(property="rgb", value=hex_of(median), unit="sRGB", **common),
        Observation(property="colour", value=word, unit=COLOUR_UNIT, **common),
    ]
