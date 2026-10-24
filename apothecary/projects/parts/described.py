"""Parts described by a sidecar instead of a Python wrapper.

A folder under ``parts/`` that holds a ``<name>.scad`` and a ``part.json`` is
a part, with no module to write: the sidecar says what the wrapper would
have said (category, tags, colour, orientation, a description) and, for a
mesh brought from elsewhere, where it came from (source, author, licence,
units, up axis) -- the provenance the open-license record asks every
vendored thing to carry.

The registry names such a part's wrapper ``apothecary.projects.parts.described.<name>``,
and this module is an importer for that name: importing it builds a module
holding ``DEFAULT``, a :class:`DescribedPart`, from the sidecar, so every
place that does ``import_module(wrapper).DEFAULT`` -- the API, the CLI, the
readiness checks, the elephant walk -- sees one more ordinary part.
"""

from __future__ import annotations

import importlib.abc
import importlib.machinery
import json
import sys
import types
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

from apothecary.models import BoundingBox3D, Color, Vector3D

from .base import BasePart

SIDECAR = "part.json"
PACKAGE = __name__  # apothecary.projects.parts.described
# A module with a __path__ is a package to the import system, which is what
# lets ``described.<name>`` be looked up through the finder below.
__path__: List[str] = []


class Provenance(BaseModel):
    """Where a mesh made elsewhere came from. Recorded, never fetched."""

    title: Optional[str] = None
    author: Optional[str] = None
    url: Optional[str] = None
    license: Optional[str] = Field(None, description="an SPDX identifier, e.g. CC-BY-4.0")
    obtained: Optional[str] = Field(None, description="the date the person brought the file")
    note: Optional[str] = None
    file: Optional[str] = Field(None, description="the file as brought, kept beside the part")
    units: str = Field("mm", description="the units the file was in: mm, cm, m, in")
    up: str = Field("z", description="which axis was up in the file: z or y")


class Description(BaseModel):
    """The sidecar's shape."""

    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    preview_color: Optional[List[float]] = Field(None, description="[r, g, b] in 0..1")
    display_rotation: Optional[List[float]] = Field(None, description="[rx, ry, rz] degrees")
    bounds: Optional[Dict[str, List[float]]] = Field(
        None, description='{"min": [x, y, z], "max": [x, y, z]} in mm, as placed'
    )
    source: Optional[Provenance] = None


class DescribedPart(BasePart):
    """A part whose wrapper is its sidecar."""

    sidecar_path: Optional[Path] = None
    source: Optional[Provenance] = None


def sidecar_for(scad_path: Path) -> Optional[Path]:
    """The sidecar beside a part's SCAD, if there is one."""
    candidate = Path(scad_path).parent / SIDECAR
    return candidate if candidate.is_file() else None


def read_description(sidecar_path: Path) -> Description:
    try:
        return Description.model_validate(json.loads(sidecar_path.read_text(encoding="utf-8")))
    except (OSError, ValueError, ValidationError) as exc:
        raise ValueError(f"{sidecar_path}: not a part description: {exc}") from exc


def part_from_sidecar(scad_path: Path, sidecar_path: Optional[Path] = None) -> DescribedPart:
    """A :class:`DescribedPart` for ``scad_path``, from the sidecar beside it."""
    scad_path = Path(scad_path)
    sidecar_path = sidecar_path or (scad_path.parent / SIDECAR)
    described = read_description(sidecar_path)
    name = described.name or scad_path.stem
    kwargs: Dict[str, Any] = {
        "name": name,
        "source_file": scad_path,
        "description": described.description,
        "category": described.category,
        "tags": list(described.tags),
        "sidecar_path": sidecar_path,
        "source": described.source,
    }
    readme = scad_path.parent / "README.md"
    if readme.is_file():
        kwargs["readme_path"] = readme
    if described.preview_color and len(described.preview_color) == 3:
        r, g, b = described.preview_color
        kwargs["preview_color"] = Color(r=r, g=g, b=b)
    if described.display_rotation and len(described.display_rotation) == 3:
        rx, ry, rz = described.display_rotation
        kwargs["display_rotation"] = Vector3D(x=rx, y=ry, z=rz)
    if described.bounds and "min" in described.bounds and "max" in described.bounds:
        lo, hi = described.bounds["min"], described.bounds["max"]
        kwargs["default_bounds"] = BoundingBox3D(
            min_point=Vector3D(x=lo[0], y=lo[1], z=lo[2]),
            max_point=Vector3D(x=hi[0], y=hi[1], z=hi[2]),
        )
    return DescribedPart(**kwargs)


def module_name_for(part_name: str) -> str:
    """The wrapper name the registry gives a described part."""
    from ..registry import _sanitize_module_name

    return f"{PACKAGE}.{_sanitize_module_name(part_name)}"


class _DescribedFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Resolves ``apothecary.projects.parts.described.<name>`` to a module built
    from the part's sidecar, found through the registry by name."""

    def find_spec(self, fullname, path=None, target=None):
        prefix = PACKAGE + "."
        if not fullname.startswith(prefix) or "." in fullname[len(prefix) :]:
            return None
        return importlib.machinery.ModuleSpec(fullname, self, origin="part.json")

    def create_module(self, spec):
        return types.ModuleType(spec.name)

    def exec_module(self, module):
        from ..registry import _sanitize_module_name, scan_projects
        from .skeleton import ROOT

        wanted = module.__name__.rsplit(".", 1)[1]
        for item in scan_projects(ROOT):
            if item.kind != "part" or item.wrapper != module.__name__:
                continue
            if _sanitize_module_name(item.name) != wanted:
                continue
            module.DEFAULT = part_from_sidecar(item.path)
            module.__file__ = str(item.path.parent / SIDECAR)
            return
        raise ModuleNotFoundError(
            f"no part described under parts/ as {wanted!r}", name=module.__name__
        )


def install_finder() -> None:
    """Put the importer on ``sys.meta_path`` once; the registry does this when it
    first names a described part's wrapper."""
    if not any(isinstance(finder, _DescribedFinder) for finder in sys.meta_path):
        sys.meta_path.append(_DescribedFinder())


__all__ = [
    "SIDECAR",
    "DescribedPart",
    "Description",
    "Provenance",
    "install_finder",
    "module_name_for",
    "part_from_sidecar",
    "read_description",
    "sidecar_for",
]
