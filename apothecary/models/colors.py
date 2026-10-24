"""
Color models for OpenSCAD rendering.

Supports RGB, RGBA and hex color specifications.
"""

from __future__ import annotations

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

    def to_hex(self) -> str:
        """Return hex color string (#RRGGBB or #RRGGBBAA)."""
        r = int(self.r * 255)
        g = int(self.g * 255)
        b = int(self.b * 255)
        if self.a < 1.0:
            a = int(self.a * 255)
            return f"#{r:02x}{g:02x}{b:02x}{a:02x}"
        return f"#{r:02x}{g:02x}{b:02x}"

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


GRAY = Color(r=0.5, g=0.5, b=0.5)
