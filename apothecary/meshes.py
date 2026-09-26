"""Mesh files made elsewhere: read them, measure them, write them as STL.

A person brings a mesh -- exported from CAD, downloaded, scanned -- and wants it
in a site and drawn in the world. Everything the viewer draws is an STL, and
OpenSCAD imports STL, so the one thing this module has to do well is turn what
a person has into binary STL and say how big it is. Pure Python, no
dependency: a workbench model is tens of thousands of triangles, and that
takes well under a second here.

Formats read: STL (binary and ASCII) and OBJ (``v`` and ``f`` lines; a face
with more than three corners is fanned). Anything else -- 3MF, STEP, glTF --
is named as not read, with the tool that would read it, rather than guessed.
"""

from __future__ import annotations

import math
import struct
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

Triangle = Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]

READABLE_SUFFIXES = {".stl", ".obj"}
# Named, not read: what would read them if it were ever wanted.
NOT_READ = {
    ".3mf": "a 3MF is a zip of XML meshes; OpenSCAD imports it directly if built with lib3mf",
    ".step": "STEP is B-rep, not a mesh; export an STL from the CAD tool that made it",
    ".stp": "STEP is B-rep, not a mesh; export an STL from the CAD tool that made it",
    ".gltf": "export an STL or OBJ from the tool that made it",
    ".glb": "export an STL or OBJ from the tool that made it",
    ".ply": "export an STL or OBJ from the tool that made it",
}


class MeshError(ValueError):
    """A file that is not a mesh this module reads."""


def read_mesh(path: Path) -> List[Triangle]:
    """The triangles of an STL or OBJ file, in the file's own units."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".stl":
        return read_stl(path.read_bytes())
    if suffix == ".obj":
        return read_obj(path.read_text(encoding="utf-8", errors="replace"))
    why = NOT_READ.get(suffix, "not a mesh format this reads (STL or OBJ)")
    raise MeshError(f"{path.name}: {why}")


def read_stl(data: bytes) -> List[Triangle]:
    """Binary or ASCII STL. Binary is judged by its size, not its header: an
    ASCII file can start with "solid" and so can a binary one."""
    if len(data) >= 84:
        count = struct.unpack_from("<I", data, 80)[0]
        if 84 + count * 50 == len(data):
            return _read_binary_stl(data, count)
    text = data.decode("utf-8", errors="replace")
    if text.lstrip().lower().startswith("solid"):
        return _read_ascii_stl(text)
    raise MeshError("not an STL: neither a binary triangle count that fits nor 'solid'")


def _read_binary_stl(data: bytes, count: int) -> List[Triangle]:
    triangles: List[Triangle] = []
    offset = 84
    for _ in range(count):
        values = struct.unpack_from("<12f", data, offset)
        triangles.append(
            (
                (values[3], values[4], values[5]),
                (values[6], values[7], values[8]),
                (values[9], values[10], values[11]),
            )
        )
        offset += 50
    return triangles


def _read_ascii_stl(text: str) -> List[Triangle]:
    triangles: List[Triangle] = []
    corners: List[Tuple[float, float, float]] = []
    for line in text.splitlines():
        words = line.split()
        if len(words) == 4 and words[0] == "vertex":
            try:
                corners.append((float(words[1]), float(words[2]), float(words[3])))
            except ValueError as exc:
                raise MeshError(f"not a vertex: {line.strip()!r}") from exc
            if len(corners) == 3:
                triangles.append((corners[0], corners[1], corners[2]))
                corners = []
    if corners:
        raise MeshError("an ASCII STL with a facet that has fewer than three vertices")
    return triangles


def read_obj(text: str) -> List[Triangle]:
    """Wavefront OBJ: ``v x y z`` and ``f a b c ...`` (1-based, negative
    indexes from the end, ``a/t/n`` forms). Materials, normals, groups: ignored."""
    vertices: List[Tuple[float, float, float]] = []
    triangles: List[Triangle] = []
    for number, line in enumerate(text.splitlines(), 1):
        words = line.split()
        if not words or words[0].startswith("#"):
            continue
        if words[0] == "v" and len(words) >= 4:
            try:
                vertices.append((float(words[1]), float(words[2]), float(words[3])))
            except ValueError as exc:
                raise MeshError(f"line {number}: not a vertex: {line.strip()!r}") from exc
        elif words[0] == "f":
            corners = []
            for word in words[1:]:
                index_text = word.split("/", 1)[0]
                try:
                    index = int(index_text)
                except ValueError as exc:
                    raise MeshError(f"line {number}: not a face index: {word!r}") from exc
                index = index - 1 if index > 0 else len(vertices) + index
                if not 0 <= index < len(vertices):
                    raise MeshError(
                        f"line {number}: face names vertex {word!r}, which is not there"
                    )
                corners.append(vertices[index])
            for i in range(1, len(corners) - 1):  # a fan from the first corner
                triangles.append((corners[0], corners[i], corners[i + 1]))
    if not triangles:
        raise MeshError("an OBJ with no faces")
    return triangles


def write_stl(triangles: Sequence[Triangle], path: Path, name: str = "apothecary") -> None:
    """Binary STL, with a normal computed per triangle (a viewer wants one)."""
    header = name.encode("ascii", "replace")[:80].ljust(80, b"\0")
    out = bytearray(header)
    out += struct.pack("<I", len(triangles))
    for a, b, c in triangles:
        n = _normal(a, b, c)
        out += struct.pack("<12fH", *n, *a, *b, *c, 0)
    Path(path).write_bytes(bytes(out))


def _normal(a, b, c) -> Tuple[float, float, float]:
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    if length == 0:
        return (0.0, 0.0, 0.0)
    return (nx / length, ny / length, nz / length)


def bounds(
    triangles: Iterable[Triangle],
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """The axis-aligned box the triangles fit in: (min, max)."""
    lo = [math.inf, math.inf, math.inf]
    hi = [-math.inf, -math.inf, -math.inf]
    for triangle in triangles:
        for corner in triangle:
            for axis in range(3):
                if corner[axis] < lo[axis]:
                    lo[axis] = corner[axis]
                if corner[axis] > hi[axis]:
                    hi[axis] = corner[axis]
    if lo[0] == math.inf:
        raise MeshError("a mesh with no triangles has no bounds")
    return (lo[0], lo[1], lo[2]), (hi[0], hi[1], hi[2])


def transform(triangles: Iterable[Triangle], scale: float = 1.0, up: str = "z") -> List[Triangle]:
    """Scale every corner, and turn a Y-up mesh (most game and web tools) into
    Z-up (OpenSCAD, the viewer, every printer): a quarter turn about X, so y
    becomes z and z becomes -y, and the winding is kept (it is a rotation)."""
    out: List[Triangle] = []
    for a, b, c in triangles:
        corners = []
        for x, y, z in (a, b, c):
            x, y, z = x * scale, y * scale, z * scale
            if up == "y":
                x, y, z = x, -z, y
            corners.append((x, y, z))
        out.append((corners[0], corners[1], corners[2]))
    return out


UNIT_SCALES = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4, "inch": 25.4}
