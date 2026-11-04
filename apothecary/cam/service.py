"""A part's toolpath written for a router, kept where the Cut card keeps a file,
and recorded beside it: the slicer's ``slice_into`` on the subtractive side."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from ..firmware import devices
from ..slicer.profiles import load_part
from . import toolpath
from .models import CutFor, CutRecord


class CamError(Exception):
    """Why no toolpath was written: the part, its variant, or its cuts."""


def cuts_dir() -> Path:
    return devices.state_dir() / "cuts"


def part_cuts(name: str, variant: Optional[str] = None):
    """The part named, and its cuts at its defaults or at the parameters of the
    cached variant ``variant`` (the one a page drew). CamError when the part does
    not say how it is cut, or the variant is not cached."""
    part = load_part(name)
    params: Dict[str, object] = {}
    if variant is not None:
        from ..projects.parts.variants import KEY_PATTERN, read_variant

        record = read_variant(part, variant) if KEY_PATTERN.match(variant) else None
        if record is None:
            raise CamError(
                f"no variant {variant!r} of the part {name} is cached: Apply it again, then Toolpath"
            )
        params = dict(record.get("params") or {})
    if not part.has_cuts:
        raise CamError(f"the part {name} does not say how it is cut: it has no cuts to write")
    return part, params, part.cuts(params)


def cut_into(name: str, router: CutFor, variant: Optional[str] = None) -> CutRecord:
    """Write the part's toolpath for ``router``, keep it as a cut file and record it."""
    part, params, cuts = part_cuts(name, variant)
    written = toolpath.write(cuts, name)
    kept = devices.save_print_file(
        f"{name}-{router.name}.nc", toolpath.text(written).encode("utf-8")
    )
    record = CutRecord(
        file_id=kept.id,
        name=kept.name,
        at=datetime.now(timezone.utc),
        part=name,
        variant=variant,
        params=params,
        router=router,
        stock=cuts.stock,
        tool=cuts.tool,
        feeds=cuts.feeds,
        operations=written.operations,
        lines=kept.lines,
        length_mm=written.length_mm,
        time_s=written.time_s,
        bounds=written.bounds,
        messages=written.messages,
        problems=kept.problems,
    )
    folder = cuts_dir()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{record.file_id}.json").write_text(
        record.model_dump_json(indent=2), encoding="utf-8"
    )
    return record


def get_record(file_id: str) -> Optional[CutRecord]:
    path = cuts_dir() / f"{file_id}.json"
    if not path.is_file():
        return None
    return CutRecord.model_validate(json.loads(path.read_text(encoding="utf-8")))


def records() -> List[CutRecord]:
    """Every toolpath recorded, newest first, those whose file is still kept."""
    folder = cuts_dir()
    if not folder.is_dir():
        return []
    kept = {f.id for f in devices.print_files()}
    found = []
    for path in folder.glob("*.json"):
        try:
            record = CutRecord.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
        if record.file_id in kept:
            found.append(record)
    return sorted(found, key=lambda r: r.at, reverse=True)
