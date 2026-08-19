from typing import Optional, Union

from pydantic import Field

from .core import OpenSCADObject
from .models.vectors import Vector3D


class Cube(OpenSCADObject):
    """Cube primitive"""

    size: Union[float, Vector3D] = 1.0
    center: bool = False

    def render(self, *_, **__) -> str:
        comment_str = f"// {self.comment}\n" if self.comment else ""
        size_str = (
            f"[{self.size.x}, {self.size.y}, {self.size.z}]"
            if isinstance(self.size, Vector3D)
            else str(self.size)
        )
        return f"{comment_str}cube({size_str}, center={str(self.center).lower()});"


class Sphere(OpenSCADObject):
    """Sphere primitive"""

    r: float = Field(1.0, gt=0)
    fn: Optional[int] = Field(None, gt=2)

    def render(self, *_, **__) -> str:
        comment_str = f"// {self.comment}\n" if self.comment else ""
        fn_str = f", $fn={self.fn}" if self.fn else ""
        return f"{comment_str}sphere(r={self.r}{fn_str});"


class Cylinder(OpenSCADObject):
    """Cylinder primitive"""

    h: float = Field(1.0, gt=0)
    r: Optional[float] = Field(None, ge=0)
    r1: Optional[float] = Field(None, ge=0)
    r2: Optional[float] = Field(None, ge=0)
    center: bool = False
    fn: Optional[int] = Field(None, gt=2)

    def render(self, *_, **__) -> str:
        comment_str = f"// {self.comment}\n" if self.comment else ""
        radius_str = (
            f"r={self.r}"
            if self.r is not None
            else (
                f"r1={self.r1}, r2={self.r2}"
                if self.r1 is not None and self.r2 is not None
                else "r=1"
            )
        )
        fn_str = f", $fn={self.fn}" if self.fn else ""
        return f"{comment_str}cylinder(h={self.h}, {radius_str}, center={str(self.center).lower()}{fn_str});"


class Import(OpenSCADObject):
    """Geometry loaded from a mesh file rather than constructed.

    A catalog leaf refers to a registered part instead of describing its own
    shape, and the generated OpenSCAD for one is the same `import()` the
    elephant-walk generator already emits. The path is written POSIX-style so
    the same scene renders identically on Windows.
    """

    file: str
    convexity: int = Field(10, gt=0)

    def render(self, *_, **__) -> str:
        comment_str = f"// {self.comment}\n" if self.comment else ""
        path = self.file.replace("\\", "/")
        return f'{comment_str}import("{path}", convexity={self.convexity});'

