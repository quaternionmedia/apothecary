"""A printer's first-layer offset: how far its nozzle stands on the first layer from
where its probe puts it, kept for the printer, and what its next slices are made with.

A printer whose profile names the start piece ``first-layer-offset`` (compose.py) slices
with the offset kept for it, as OrcaSlicer's ``z_offset``: added to every Z the slicer
writes, so a negative offset lowers the nozzle and a positive one raises it. Until one
is kept it is 0, and nothing changes. The probe's own offset (``M851``, which the board
applies when ``G28`` homes Z with the probe) is the board's and is not touched: this one
stands on top of it, a value of the printer's that its slices say with their source.

**How one is found**: a one-layer square (``parts/first_layer_square``) printed with the
bed probed first, and looked at. Lines that stay round and stand apart, or do not hold,
say the nozzle is high: an offset lower. Lines thin and see-through, ridged, or no
plastic at all say it is low: an offset higher. The Print window's first layer row keeps
the next one to try, and the next square says whether it was right.

**Where it is kept**: the state folder's ``first-layer-offset/<site>/<printer>.json``,
written whole: the offset, a person's note of what was seen, when, and every offset kept
before, newest last.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

from ..state_folder import state_dir, write_whole
from .profiles import PrinterProfile

MODULE = "orcaslicer"
PIECE = "first-layer-offset"
NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]{0,199}$")
HISTORY = 50
# The steps the Print window's row offers, and how far either way an offset may be kept,
# mm: a probe's offset found by paper is within a few tenths, and an offset past this is
# a probe offset to measure again, not a first layer to tune.
STEP = 0.05
MOST = 0.5
NOTE_MOST = 200


class Refused(ValueError):
    """An offset that is not kept, and why."""


class Kept(BaseModel):
    offset: float
    note: str = Field("", max_length=NOTE_MOST)
    at: datetime


class KeptFile(BaseModel):
    site: str
    printer: str
    kept: Kept
    before: List[Kept] = Field(default_factory=list)


def names(profile: PrinterProfile) -> bool:
    """Whether the printer's slices take the offset kept for it."""
    return PIECE in profile.start.modules


def words(offset: float) -> str:
    """An offset as the nozzle's move: ``0.05 mm lower``, ``as the probe puts it``."""
    if abs(offset) < 1e-9:
        return "as the probe puts it"
    return f"{abs(offset):.2f} mm {'lower' if offset < 0 else 'higher'}"


def choices() -> List[float]:
    """The offsets the Print window's row offers, lowest first: MOST either way, by STEP."""
    n = round(MOST / STEP)
    return [round(i * STEP, 2) for i in range(-n, n + 1)]


def _path(site: str, printer: str) -> Path:
    if not NAME.match(site or "") or not NAME.match(printer or ""):
        raise Refused(f"no first-layer offset can be kept for {site!r}, {printer!r}")
    return state_dir() / "first-layer-offset" / site / f"{printer}.json"


def kept(site: Optional[str], printer: Optional[str]) -> Optional[KeptFile]:
    """The offset kept for ``printer`` of ``site``; None where none was."""
    if not site or not printer:
        return None
    try:
        path = _path(site, printer)
    except Refused:
        return None
    if not path.is_file():
        return None
    return KeptFile.model_validate_json(path.read_text(encoding="utf-8"))


def keep(
    profile: PrinterProfile, site: str, printer: str, offset: float, note: str = ""
) -> KeptFile:
    """``offset`` kept for ``printer`` of ``site``: its next slices are made with it."""
    if not names(profile):
        raise Refused(
            f"{profile.file} names no start piece {PIECE!r}: the printer's slices take no "
            "first-layer offset, so none is kept for it"
        )
    if not isinstance(offset, (int, float)) or isinstance(offset, bool) or offset != offset:
        raise Refused(f"a first-layer offset is a number of mm, not {offset!r}")
    value = round(float(offset), 2)
    if abs(value) > MOST + 1e-9:
        raise Refused(
            f"a first-layer offset is within {MOST:g} mm either way, not {value:g}: an offset "
            "further out is the probe's own offset (M851) to measure again"
        )
    if abs(value - float(offset)) > 1e-9:
        raise Refused(f"a first-layer offset is kept to a hundredth of a mm, not {offset!r}")
    value = 0.0 if value == 0 else value  # never -0.0
    now = Kept(offset=value, note=(note or "").strip(), at=datetime.now(timezone.utc))
    held = kept(site, printer)
    before = ([*held.before, held.kept] if held else [])[-HISTORY:]
    record = KeptFile(site=site, printer=printer, kept=now, before=before)
    write_whole(_path(site, printer), record.model_dump_json(indent=2))
    return record


def _said(held: Kept, site: str, printer: str) -> str:
    note = f" ({held.note})" if held.note else ""
    return f"{site}'s {printer}, kept {held.at:%Y-%m-%d %H:%M} UTC in its Print window{note}"


def applied(
    profile: PrinterProfile, site: Optional[str], printer: Optional[str], module: str
) -> PrinterProfile:
    """``profile`` with the offset its next slice takes as OrcaSlicer's ``z_offset``, in
    its ``set``: the offset kept for the printer, origin ``measured``, where its profile
    names the piece; 0 where none is kept, said as none. The profile as it is where it
    names no such piece, or the slice is by another slicer module."""
    if module != MODULE or not names(profile):
        return profile
    section = json.loads(json.dumps(profile.sections.get(MODULE) or {}))
    held = kept(site, printer)
    if held is None:
        whose = f"{site}'s {printer}" if site and printer else "a printer in no site"
        entry = {
            "value": "0",
            "source": f"{PIECE}: no first-layer offset kept for {whose} yet",
            "note": "the nozzle as the probe puts it",
        }
    else:
        entry = {
            "value": f"{held.kept.offset:g}",
            "source": f"{PIECE}: {_said(held.kept, held.site, held.printer)}",
            "origin": "measured",
            "note": f"the nozzle {words(held.kept.offset)} than the probe puts it",
        }
    section.setdefault("set", {}).setdefault("machine", {})["z_offset"] = entry
    return profile.model_copy(update={"sections": {**profile.sections, MODULE: section}})


def answer(profile: PrinterProfile, site: Optional[str], printer: Optional[str]) -> dict:
    """What the Print window's row shows: whether the printer's slices take an offset,
    the one kept (0 where none), when and why, and the row's choices."""
    held = kept(site, printer) if names(profile) else None
    value = held.kept.offset if held else 0.0
    return {
        "named": names(profile),
        "value": value,
        "words": words(value),
        "kept": held.kept.model_dump(mode="json") if held else None,
        "choices": choices(),
    }
