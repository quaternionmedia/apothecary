"""Discover Arduino sketches that live alongside parts under ``parts/``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from pydantic import ValidationError

from ..projects.parts.skeleton import ROOT
from .models import DisplaySpec, SketchInfo

SIDECAR = "firmware.json"
DEFAULT_BAUD = 115200


def _display(meta: dict) -> Optional[DisplaySpec]:
    """A malformed ``display`` is dropped, like any other bad sidecar value."""
    raw = meta.get("display")
    if not isinstance(raw, dict):
        return None
    try:
        return DisplaySpec(**raw)
    except ValidationError:
        return None


def _baud(meta: dict) -> int:
    raw = meta.get("baud")
    return raw if isinstance(raw, int) and 300 <= raw <= 2_000_000 else DEFAULT_BAUD


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
    ino = folder / f"{folder.name}.ino"
    if ino.is_file():
        meta = _read_sidecar(folder)
        rel = folder.relative_to(parts_dir)
        out.append(
            SketchInfo(
                name=folder.name,
                path=folder,
                ino=ino,
                part=rel.parts[0] if rel.parts else None,
                fqbn=meta.get("fqbn") or None,
                cores=[str(c) for c in meta.get("cores", [])],
                libraries=[str(lib) for lib in meta.get("libraries", [])],
                note=meta.get("note") or None,
                baud=_baud(meta),
                display=_display(meta),
            )
        )
    for child in sorted(p for p in folder.iterdir() if p.is_dir()):
        _visit(child, parts_dir, out)


def discover_sketches(root: Path = ROOT) -> List[SketchInfo]:
    """Every ``<folder>/<folder>.ino`` under ``parts/`` (arduino-cli's sketch layout)."""
    parts_dir = root / "parts"
    out: List[SketchInfo] = []
    if not parts_dir.is_dir():
        return out
    for child in sorted(p for p in parts_dir.iterdir() if p.is_dir()):
        _visit(child, parts_dir, out)
    return sorted(out, key=lambda s: s.name)


def find_sketch(name: str, root: Path = ROOT) -> Optional[SketchInfo]:
    """A discovered sketch by name, or by a path to its folder or ``.ino``."""
    for sketch in discover_sketches(root):
        if sketch.name == name:
            return sketch
    candidate = Path(name).expanduser()
    if candidate.suffix == ".ino":
        candidate = candidate.parent
    if candidate.is_dir():
        try:
            resolved = candidate.resolve()
            resolved.relative_to((root / "parts").resolve())
        except ValueError:
            return None
        for sketch in discover_sketches(root):
            if sketch.path.resolve() == resolved:
                return sketch
    return None
