"""Describing a picture in a way that survives moving the camera.

Two photographs of one object, taken a step apart, share almost nothing at the
level of pixels. Every position moves, every size changes, the light shifts. So
none of those is used on its own.

What is used:

- **What shapes are in it and what proportions they have.** Stepping back halves
  every size and leaves every proportion alone. A bar three times longer than it
  is wide stays three times longer than it is wide.
- **How much of the picture each shape takes up.** This does move when you step
  back, but everything moves together, so the *ratio between* two shapes in one
  picture holds. Sizes are therefore compared against the biggest shape in their
  own picture rather than against the other picture.
- **How light and dark the picture is overall.** Weak on its own — two pictures
  of different things in the same room look alike this way — which is exactly
  why it is only ever used to support an answer, never to reach one.

This will be beaten by anything trained on real photographs. It runs on your own
machine with the network off, which is the trade being made on purpose.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from ..models.vectors import Vector2D
from ..vision.models import FoundShape, Picture
from .models import ShapeMark, Signature

# How many buckets the light-and-dark profile is cut into. Sixteen is coarse
# enough that a small change in exposure does not move a picture into another
# bucket, and fine enough to tell a dark scene from a bright one.
TONE_BUCKETS = 16

# The picture is shrunk before its light and dark are counted. The profile is a
# share, not a count, so shrinking changes nothing about the answer and a great
# deal about how long it takes.
TONE_EDGE = 64


def _proportion(shape: FoundShape) -> float:
    """How many times longer than wide, never less than one."""
    if shape.measured_sides and shape.short_side > 0:
        return max(shape.long_side / shape.short_side, 1.0)
    width, height = shape.width, shape.height
    if min(width, height) <= 0:
        return 1.0
    return max(width, height) / min(width, height)


# How close to the edge counts as touching it, as a share of the picture.
AT_THE_EDGE = 0.01


def _cut_off(shape: FoundShape) -> bool:
    """Whether the shape runs off the edge of the picture.

    A rectangle half outside the frame is still reported as a rectangle, with the
    proportions of the half that stayed in. Comparing that with the whole
    rectangle in another picture and calling them different shapes is how a
    close-up came to be judged a separate object. A shape at the edge is
    therefore allowed to match, but never counted against a picture when it does
    not: it is not evidence either way.
    """
    return (
        shape.min_point.x <= AT_THE_EDGE
        or shape.min_point.y <= AT_THE_EDGE
        or shape.max_point.x >= 1.0 - AT_THE_EDGE
        or shape.max_point.y >= 1.0 - AT_THE_EDGE
    )


def _area(shape: FoundShape) -> float:
    if shape.measured_sides:
        return min(max(shape.long_side * shape.short_side, 0.0), 1.0)
    return min(max(shape.width * shape.height, 0.0), 1.0)


def tone_of(path: Optional[Path]) -> List[float]:
    """How much of the picture is dark, middling and light, as shares.

    Empty when there is no picture to look at. An empty profile is honest: it
    means this was never measured, and everything downstream treats it that way
    rather than treating it as a perfect match or a perfect mismatch.
    """
    if path is None:
        return []
    try:
        from PIL import Image, ImageOps
    except ImportError:  # pragma: no cover - the picture library is required
        return []
    try:
        with Image.open(path) as opened:
            upright = ImageOps.exif_transpose(opened)
            grey = upright.convert("L")
            grey.thumbnail((TONE_EDGE, TONE_EDGE))
            counts = grey.histogram()
    except (OSError, ValueError):
        # A picture that cannot be read is not an argument for or against
        # anything. Say nothing rather than say zero.
        return []
    per_bucket = 256 // TONE_BUCKETS
    buckets = [
        float(sum(counts[start : start + per_bucket])) for start in range(0, 256, per_bucket)
    ]
    total = sum(buckets)
    if total <= 0:
        return []
    return [count / total for count in buckets]


def signature_of(picture: Picture, *, path: Optional[Path] = None) -> Signature:
    """Describe one picture so it can be compared with another."""
    marks = [
        ShapeMark(
            kind=shape.kind,
            proportion=_proportion(shape),
            area=_area(shape),
            centre=Vector2D(x=shape.centre.x, y=shape.centre.y),
            confidence=shape.confidence,
            cut_off=_cut_off(shape),
        )
        for shape in picture.shapes
    ]
    return Signature(
        picture=picture.name,
        marks=marks,
        tone=tone_of(path),
        wideness=picture.pixel_width / picture.pixel_height,
    )


def tone_alike(left: List[float], right: List[float]) -> Optional[float]:
    """How alike two light-and-dark profiles are, from 0 to 1.

    ``None`` when either was never measured — which is not the same as zero, and
    the difference matters: an unmeasured profile must not be allowed to argue
    against a match it knows nothing about.
    """
    if not left or not right or len(left) != len(right):
        return None
    return sum(min(a, b) for a, b in zip(left, right, strict=True))


__all__ = ["TONE_BUCKETS", "TONE_EDGE", "signature_of", "tone_alike", "tone_of"]
