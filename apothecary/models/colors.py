"""
Color models for OpenSCAD rendering.

Supports named colors, RGB, RGBA, and hex color specifications.
"""

from __future__ import annotations

from typing import Tuple

from pydantic import BaseModel, Field


class Color(BaseModel):
    """
    RGBA color representation for OpenSCAD.

    All components are in the range [0, 1].
    """

    r: float = Field(0.5, ge=0, le=1)
    g: float = Field(0.5, ge=0, le=1)
    b: float = Field(0.5, ge=0, le=1)
    a: float = Field(1.0, ge=0, le=1)

    def to_openscad(self) -> str:
        """Return OpenSCAD color() argument string."""
        if self.a < 1.0:
            return f"[{self.r}, {self.g}, {self.b}, {self.a}]"
        return f"[{self.r}, {self.g}, {self.b}]"

    def to_rgb_tuple(self) -> Tuple[float, float, float]:
        """Return (r, g, b) tuple."""
        return (self.r, self.g, self.b)

    def to_rgba_tuple(self) -> Tuple[float, float, float, float]:
        """Return (r, g, b, a) tuple."""
        return (self.r, self.g, self.b, self.a)

    def to_hex(self) -> str:
        """Return hex color string (#RRGGBB or #RRGGBBAA)."""
        r = int(self.r * 255)
        g = int(self.g * 255)
        b = int(self.b * 255)
        if self.a < 1.0:
            a = int(self.a * 255)
            return f"#{r:02x}{g:02x}{b:02x}{a:02x}"
        return f"#{r:02x}{g:02x}{b:02x}"

    def with_alpha(self, alpha: float) -> "Color":
        """Return new color with different alpha."""
        return Color(r=self.r, g=self.g, b=self.b, a=alpha)

    def blend(self, other: "Color", factor: float = 0.5) -> "Color":
        """Blend with another color. factor=0 returns self, factor=1 returns other."""
        return Color(
            r=self.r + (other.r - self.r) * factor,
            g=self.g + (other.g - self.g) * factor,
            b=self.b + (other.b - self.b) * factor,
            a=self.a + (other.a - self.a) * factor,
        )

    @classmethod
    def from_rgb(cls, r: int, g: int, b: int, a: int = 255) -> "Color":
        """Create from 0-255 RGB values."""
        return cls(r=r / 255, g=g / 255, b=b / 255, a=a / 255)

    @classmethod
    def from_hex(cls, hex_str: str) -> "Color":
        """Create from hex string (#RGB, #RRGGBB, or #RRGGBBAA)."""
        hex_str = hex_str.lstrip("#")

        if len(hex_str) == 3:
            # #RGB -> #RRGGBB
            hex_str = "".join(c * 2 for c in hex_str)

        if len(hex_str) == 6:
            r = int(hex_str[0:2], 16)
            g = int(hex_str[2:4], 16)
            b = int(hex_str[4:6], 16)
            return cls.from_rgb(r, g, b)

        if len(hex_str) == 8:
            r = int(hex_str[0:2], 16)
            g = int(hex_str[2:4], 16)
            b = int(hex_str[4:6], 16)
            a = int(hex_str[6:8], 16)
            return cls.from_rgb(r, g, b, a)

        raise ValueError(f"Invalid hex color: #{hex_str}")

    @classmethod
    def from_name(cls, name: str) -> "Color":
        """Create from named color."""
        name_lower = name.lower()
        if name_lower not in NAMED_COLORS:
            raise ValueError(f"Unknown color name: {name}")
        return NAMED_COLORS[name_lower]


# OpenSCAD named colors (subset of CSS colors)
NAMED_COLORS = {
    # Grayscale
    "black": Color(r=0, g=0, b=0),
    "white": Color(r=1, g=1, b=1),
    "gray": Color(r=0.5, g=0.5, b=0.5),
    "grey": Color(r=0.5, g=0.5, b=0.5),
    "silver": Color(r=0.75, g=0.75, b=0.75),
    "darkgray": Color(r=0.66, g=0.66, b=0.66),
    "lightgray": Color(r=0.83, g=0.83, b=0.83),
    # Primary
    "red": Color(r=1, g=0, b=0),
    "green": Color(r=0, g=0.5, b=0),
    "blue": Color(r=0, g=0, b=1),
    # Secondary
    "cyan": Color(r=0, g=1, b=1),
    "magenta": Color(r=1, g=0, b=1),
    "yellow": Color(r=1, g=1, b=0),
    # Extended
    "orange": Color(r=1, g=0.65, b=0),
    "pink": Color(r=1, g=0.75, b=0.8),
    "purple": Color(r=0.5, g=0, b=0.5),
    "brown": Color(r=0.65, g=0.16, b=0.16),
    "lime": Color(r=0, g=1, b=0),
    "navy": Color(r=0, g=0, b=0.5),
    "teal": Color(r=0, g=0.5, b=0.5),
    "olive": Color(r=0.5, g=0.5, b=0),
    "maroon": Color(r=0.5, g=0, b=0),
    # Material-like colors
    "gold": Color(r=1, g=0.84, b=0),
    "coral": Color(r=1, g=0.5, b=0.31),
    "salmon": Color(r=0.98, g=0.5, b=0.45),
    "crimson": Color(r=0.86, g=0.08, b=0.24),
    "indigo": Color(r=0.29, g=0, b=0.51),
    "violet": Color(r=0.93, g=0.51, b=0.93),
    "turquoise": Color(r=0.25, g=0.88, b=0.82),
    "beige": Color(r=0.96, g=0.96, b=0.86),
    "ivory": Color(r=1, g=1, b=0.94),
    "khaki": Color(r=0.94, g=0.9, b=0.55),
}

# Convenience color constants
BLACK = NAMED_COLORS["black"]
WHITE = NAMED_COLORS["white"]
RED = NAMED_COLORS["red"]
GREEN = NAMED_COLORS["green"]
BLUE = NAMED_COLORS["blue"]
YELLOW = NAMED_COLORS["yellow"]
CYAN = NAMED_COLORS["cyan"]
MAGENTA = NAMED_COLORS["magenta"]
ORANGE = NAMED_COLORS["orange"]
GRAY = NAMED_COLORS["gray"]
