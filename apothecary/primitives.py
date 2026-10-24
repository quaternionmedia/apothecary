from pathlib import Path
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

    A mesh made elsewhere is rarely in this scene's frame: ``scale`` turns its
    units into millimetres (25.4 for a file in inches), ``rotate`` stands a
    Y-up file up (``x=90``), ``translate`` moves its origin to where the piece
    should sit. They render as ``translate(){rotate(){scale(){import()}}}``,
    which OpenSCAD passes through without a boolean, and ``bounds()`` reads
    the file to say where the transformed mesh ends up -- the footprint a
    site node needs for placement and overlap checks.
    """

    file: str
    convexity: int = Field(10, gt=0)
    scale: float = Field(1.0, gt=0)
    rotate: Vector3D = Field(default_factory=Vector3D)
    translate: Vector3D = Field(default_factory=Vector3D)

    def render(self, *_, **__) -> str:
        comment_str = f"// {self.comment}\n" if self.comment else ""
        path = self.file.replace("\\", "/")
        text = f'import("{path}", convexity={self.convexity});'
        if self.scale != 1.0:
            text = f"scale({self.scale}) {text}"
        if self.rotate != Vector3D():
            text = f"rotate([{self.rotate.x}, {self.rotate.y}, {self.rotate.z}]) {text}"
        if self.translate != Vector3D():
            t = self.translate
            text = f"translate([{t.x}, {t.y}, {t.z}]) {text}"
        return f"{comment_str}{text}"

    def resolved_path(self, root: Optional[Path] = None) -> Path:
        """Where the file is: as given if absolute, else under ``root`` (the repository)."""
        path = Path(self.file)
        if path.is_absolute():
            return path
        if root is None:
            from .projects.parts.skeleton import ROOT as root  # noqa: N813

        return Path(root) / path

    def bounds(self, root: Optional[Path] = None):
        """The box the transformed mesh fits in, read from the file (STL or OBJ)."""
        import math

        from . import meshes
        from .models.bounds import BoundingBox3D

        triangles = meshes.read_mesh(self.resolved_path(root))
        lo, hi = meshes.bounds(triangles)
        corners = [
            (x, y, z) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])
        ]
        rx, ry, rz = (math.radians(a) for a in (self.rotate.x, self.rotate.y, self.rotate.z))
        moved = []
        for x, y, z in corners:
            x, y, z = x * self.scale, y * self.scale, z * self.scale
            # OpenSCAD's rotate([x, y, z]) turns about X, then Y, then Z.
            y, z = y * math.cos(rx) - z * math.sin(rx), y * math.sin(rx) + z * math.cos(rx)
            x, z = x * math.cos(ry) + z * math.sin(ry), -x * math.sin(ry) + z * math.cos(ry)
            x, y = x * math.cos(rz) - y * math.sin(rz), x * math.sin(rz) + y * math.cos(rz)
            moved.append(
                Vector3D(x=x + self.translate.x, y=y + self.translate.y, z=z + self.translate.z)
            )
        return BoundingBox3D.from_points(moved)
