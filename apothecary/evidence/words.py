"""The words a property answered in a word is asked among.

Colour and material are the family's lists, the ones ``qm.observation`` carries
beside it: a colour is one of the basic colour words, a material one a camera
can tell apart. A finer word (PLA, PETG) is a person's or a site's, and wins
over a guess. A colour's measured sRGB is a property of its own, ``rgb``, which
only a reader of pixels gives.
"""

from __future__ import annotations

from typing import Dict, Tuple

# The basic colour words, each with an sRGB anchor a measured colour is named by:
# the nearest anchor in CIE Lab, where a step reads as about the same difference
# in every hue.
COLOURS: Dict[str, str] = {
    "black": "#000000",
    "white": "#ffffff",
    "grey": "#808080",
    "red": "#c62828",
    "orange": "#f57c00",
    "yellow": "#fdd835",
    "green": "#2e7d32",
    "blue": "#1e56c8",
    "purple": "#6a1b9a",
    "pink": "#f48fb1",
    "brown": "#6d4c41",
}

MATERIALS: Tuple[str, ...] = (
    "plastic",
    "metal",
    "wood",
    "rubber",
    "fabric",
    "glass",
    "paper",
    "ceramic",
)

COLOUR_UNIT = "qm.colours/1"
MATERIAL_UNIT = "qm.materials/1"


def hex_of(rgb: Tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def rgb_of(text: str) -> Tuple[int, int, int]:
    text = text.lstrip("#")
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def _lab(rgb: Tuple[int, int, int]) -> Tuple[float, float, float]:
    """sRGB to CIE Lab, D65."""

    def linear(c: float) -> float:
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(c) for c in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def colour_distance(a: Tuple[int, int, int], b: Tuple[int, int, int]) -> float:
    """How far apart two colours are, in Lab."""
    la, lb = _lab(a), _lab(b)
    return sum((p - q) ** 2 for p, q in zip(la, lb, strict=True)) ** 0.5


def nearest_colour(rgb: Tuple[int, int, int], among: Dict[str, str] = COLOURS) -> Tuple[str, float]:
    """The colour word whose anchor is nearest, and how far it is."""
    return min(
        ((word, colour_distance(rgb, rgb_of(anchor))) for word, anchor in among.items()),
        key=lambda pair: pair[1],
    )
