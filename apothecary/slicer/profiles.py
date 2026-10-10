"""A printer's slicer profile, kept with the printer's part, and a part's declared print settings.

**The printer's profile** is ``slicer.json`` in its part's folder --
``parts/ender3/slicer.json`` for printer_1, an Ender 3 -- as the owner decided on
2026-10-10 (docs/plans/slicer-2026-10-10.md). It holds:

- ``slicer``: the module a slice of this printer uses (see
  ``apothecary/slicer/modules/__init__.py`` for how the owner switches);
- one section per slicer module, in that slicer's own terms: for OrcaSlicer, the
  names of the base profiles it starts from (OrcaSlicer's own, read from the
  installed release at each slice -- none of them is copied here) and, under
  ``set``, each value the printer holds over them, with its ``source``;
- ``measured``: what the bench measured of this machine, each with its source and
  how a slice uses it -- or why it does not.

**A part's print settings** are what its wrapper declares: ``print_settings``, a
``PrintSettings`` (apothecary/models/units.py) -- the shape the readiness check
*Print settings declared* reads (apothecary/projects/parts/readiness.py). Only
the fields the wrapper set are the part's (``model_fields_set``); the model's own
defaults are not a declaration, and the printer's profile fills those, as it
fills every value the shape has no field for. A piece made from a picture
declares none today, so its slice is the printer's throughout.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

from .modules import SlicerError

PROFILE_FILE = "slicer.json"


class Measured(BaseModel):
    """One thing the bench measured of the machine: its value, where it was measured,
    and how a slice uses it."""

    value: Any
    unit: Optional[str] = None
    source: str
    used: str


class PrinterProfile(BaseModel):
    """A printer's slicer profile, as its part keeps it."""

    part: str  # the printer's part
    file: str  # where it is kept, from the repository's root
    about: str = ""
    slicer: str
    sections: Dict[str, dict] = Field(default_factory=dict)  # each module's own
    measured: Dict[str, Measured] = Field(default_factory=dict)

    def section(self, module_id: str) -> dict:
        found = self.sections.get(module_id)
        if not isinstance(found, dict):
            raise SlicerError(
                f"{self.file} has no {module_id!r} section: the printer {self.part} has no "
                f"profile for that slicer"
            )
        return found


def _root() -> Path:
    from ..projects.parts.skeleton import ROOT

    return ROOT


def profile_file(part) -> Path:
    """Where a part keeps its slicer profile: beside its SCAD."""
    return Path(part.source_file).parent / PROFILE_FILE


def read_profile(part_name: str, path: Path) -> PrinterProfile:
    """The profile in ``path``, the printer ``part_name``'s; SlicerError when it
    cannot be read as one."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SlicerError(f"{path}: not a slicer profile ({exc})") from exc
    if not isinstance(data, dict):
        raise SlicerError(f"{path}: not a slicer profile (not an object)")
    try:
        rel = path.resolve().relative_to(_root().resolve()).as_posix()
    except ValueError:
        rel = str(path)
    known = {"about", "slicer", "measured"}
    try:
        return PrinterProfile(
            part=part_name,
            file=rel,
            about=str(data.get("about", "")),
            slicer=str(data.get("slicer", "")),
            sections={k: v for k, v in data.items() if k not in known and isinstance(v, dict)},
            measured=data.get("measured") or {},
        )
    except ValidationError as exc:
        raise SlicerError(f"{path}: not a slicer profile ({exc.errors()[0]['msg']})") from exc


def load_part(name: str):
    """A registered part by its registry name, or SlicerError. A name is matched
    against the registry and never turned into an import path."""
    from importlib import import_module

    from ..projects.registry import scan_projects

    for item in scan_projects(_root()):
        if item.kind == "part" and item.wrapper and item.name == name:
            return getattr(import_module(item.wrapper), "DEFAULT", None) or _no_default(name)
    raise SlicerError(f"no part named {name!r}")


def _no_default(name: str):
    raise SlicerError(f"the part {name!r} has no DEFAULT in its wrapper")


def load_profile(part_name: str) -> PrinterProfile:
    """The slicer profile the printer ``part_name`` keeps, or SlicerError."""
    part = load_part(part_name)
    path = profile_file(part)
    if not path.is_file():
        raise SlicerError(f"the part {part_name!r} keeps no slicer profile ({PROFILE_FILE})")
    return read_profile(part_name, path)


def printers() -> List[str]:
    """Every part that keeps a slicer profile: the printers a slice can be for."""
    from importlib import import_module

    from ..projects.registry import scan_projects

    found = []
    for item in scan_projects(_root()):
        if item.kind != "part" or not item.wrapper:
            continue
        try:
            part = getattr(import_module(item.wrapper), "DEFAULT", None)
        except Exception:  # noqa: BLE001 - a broken wrapper is `apothecary check`'s to report
            continue
        if part is not None and profile_file(part).is_file():
            found.append(item.name)
    return sorted(found)


@dataclass
class Declared:
    """A part's or a piece's declared print settings: only what it declared."""

    by: str  # in words: "part calibration_cube", "piece box_1"
    values: Dict[str, float] = field(default_factory=dict)

    @classmethod
    def of(cls, settings, by: str) -> "Declared":
        """What ``settings`` (a ``PrintSettings``, or None) declares: the fields set
        on it, not the model's defaults."""
        if settings is None:
            return cls(by=by)
        return cls(
            by=by, values={name: getattr(settings, name) for name in settings.model_fields_set}
        )
