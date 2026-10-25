"""Discover the sketches that live alongside parts under ``parts/``.

Every toolchain module is asked of every folder (``ToolchainModule.sketch_in``):
an Arduino sketch is ``<folder>/<folder>.ino``; a Rust one is a Cargo project
whose ``firmware.json`` names its module. A folder may hold one sketch and
another inside it -- ``parts/esp32_blink/`` is the Arduino ``esp32_blink`` and
``parts/esp32_blink/rust/`` the Rust one -- and each is its own sketch.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from ..projects.parts.skeleton import ROOT
from .models import ARDUINO, SketchInfo

SIDECAR = "firmware.json"
DEFAULT_BAUD = 115200


def _read_sidecar(folder: Path) -> dict:
    sidecar = folder / SIDECAR
    if not sidecar.is_file():
        return {}
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _visit(folder: Path, parts_dir: Path, out: List[SketchInfo]) -> None:
    if (folder / ".git").exists():  # vendored submodule: not our firmware
        return
    if folder.name == "target" and (folder.parent / "Cargo.toml").is_file():
        return  # what cargo leaves in a project run by hand
    meta = _read_sidecar(folder)
    from .modules import modules

    for module in modules():
        sketch = module.sketch_in(folder, meta, parts_dir)
        if sketch is not None:
            out.append(sketch)
            break
    for child in sorted(p for p in folder.iterdir() if p.is_dir()):
        _visit(child, parts_dir, out)


def discover_sketches(root: Path = ROOT) -> List[SketchInfo]:
    """Every sketch under ``parts/``, by name, an Arduino sketch before another
    module's of the same name."""
    parts_dir = root / "parts"
    out: List[SketchInfo] = []
    if not parts_dir.is_dir():
        return out
    for child in sorted(p for p in parts_dir.iterdir() if p.is_dir()):
        _visit(child, parts_dir, out)
    return sorted(out, key=lambda s: (s.name, s.toolchain != ARDUINO, s.toolchain))


def nested_sketch_folders(sketch: SketchInfo, root: Path = ROOT) -> List[Path]:
    """The folders of other sketches inside ``sketch``'s: not its sources."""
    return [
        s.path
        for s in discover_sketches(root)
        if s.path != sketch.path and s.path.is_relative_to(sketch.path)
    ]


class SketchAmbiguous(ValueError):
    """A name two sketches share: say which, by its id."""


def find_sketch(name: str, root: Path = ROOT) -> Optional[SketchInfo]:
    """A discovered sketch by its id (``esp32_blink@arduino``), by its name when one
    sketch alone has it, or by a path to its folder or ``.ino``. A name two share
    is refused with their ids (``SketchAmbiguous``)."""
    found = discover_sketches(root)
    for sketch in found:
        if sketch.id == name:
            return sketch
    named = [s for s in found if s.name == name]
    if len(named) == 1:
        return named[0]
    if named:
        raise SketchAmbiguous(
            f"{name} is {len(named)} sketches: " + ", ".join(s.id for s in named) + "; name one"
        )
    candidate = Path(name).expanduser()
    if candidate.suffix == ".ino":
        candidate = candidate.parent
    if candidate.is_dir():
        try:
            resolved = candidate.resolve()
            resolved.relative_to((root / "parts").resolve())
        except ValueError:
            return None
        for sketch in found:
            if sketch.path.resolve() == resolved:
                return sketch
    return None
