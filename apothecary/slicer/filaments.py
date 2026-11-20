"""The filament loaded on a printer: chosen among the slicer's own profiles of the
printer's vendor that fit its machine, kept for the printer, and what its next slices
are made with.

A printer whose profile names the filament piece ``choose`` (compose.py) slices with
the filament loaded on it; one whose profile names ``printer`` slices with the one its
profile names, as before. Until a filament is loaded, ``choose`` takes the profile's
own (``orcaslicer.filament`` in ``slicer.json``): nothing changes for a printer until
a person says what is on its spool holder.

**The choices** are OrcaSlicer's filament profiles of the vendor the printer's profile
names, read from the installed release: each that can be chosen (its ``instantiation``)
and whose ``compatible_printers`` names the printer's machine profile, or names none.
Each says its type and the temperatures its profile prints at.

**Where it is kept**: the state folder's ``filaments/<site>/<printer>.json``, written
whole: the filament loaded, a person's note of it (the spool: its brand, its colour),
when, and every filament loaded before, newest last. A printer's tuning is kept per
filament already (slicer/tuning.py), so loading another filament changes which
corrections its next slices take, and loading the first one back takes its own again.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

from ..state_folder import state_dir, write_whole
from .modules import SlicerError
from .profiles import PrinterProfile

MODULE = "orcaslicer"
NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]{0,199}$")
HISTORY = 50


class Refused(ValueError):
    """A filament that is not loaded, and why."""


class Choice(BaseModel):
    """One filament profile a printer can load."""

    name: str
    type: Optional[str] = None
    nozzle_temperature: Optional[str] = None
    nozzle_temperature_range: Optional[List[str]] = None
    bed_temperature: Optional[str] = None  # the cool plate's, the bed this printer's profile uses
    profile_default: bool = False  # the one the printer's profile names


class Loaded(BaseModel):
    filament: str
    note: str = Field("", max_length=200)
    at: datetime


class LoadedFile(BaseModel):
    site: str
    printer: str
    loaded: Loaded
    before: List[Loaded] = Field(default_factory=list)


def _first(value):
    return value[0] if isinstance(value, list) and value else value


def _section(profile: PrinterProfile) -> dict:
    found = profile.sections.get(MODULE)
    if not isinstance(found, dict):
        raise SlicerError(f"{profile.file}: the printer {profile.part} has no OrcaSlicer profile")
    return found


def chooses(profile: PrinterProfile) -> bool:
    """Whether the printer's slices take the filament loaded on it."""
    return list(profile.filament.modules) == ["choose"]


def choices(profile: PrinterProfile, resources: Optional[Path] = None) -> List[Choice]:
    """Every filament profile the printer can load, its profile's own first."""
    from .modules.orcaslicer import flatten, vendor_index

    if resources is None:
        from .modules import get_module

        resources = get_module(MODULE)._resources()  # type: ignore[attr-defined]
    section = _section(profile)
    index = vendor_index(resources, section.get("vendor"))
    machine = str(section.get("machine") or "")
    default = str(section.get("filament") or "")
    out: List[Choice] = []
    for name, path in sorted(index.items()):
        if "filament" not in path.parts:
            continue
        try:
            flat, _chain = flatten(index, name, "filament")
        except SlicerError:
            continue
        if str(_first(flat.get("instantiation")) or "true").lower() == "false":
            continue
        fits = flat.get("compatible_printers") or []
        if fits and machine not in fits:
            continue
        low, high = (
            flat.get("nozzle_temperature_range_low"),
            flat.get("nozzle_temperature_range_high"),
        )
        out.append(
            Choice(
                name=name,
                type=_first(flat.get("filament_type")),
                nozzle_temperature=_first(flat.get("nozzle_temperature")),
                nozzle_temperature_range=[_first(low), _first(high)] if low and high else None,
                bed_temperature=_first(flat.get("cool_plate_temp")),
                profile_default=name == default,
            )
        )
    out.sort(key=lambda c: (not c.profile_default, c.name))
    return out


def _path(site: str, printer: str) -> Path:
    if not NAME.match(site or "") or not NAME.match(printer or ""):
        raise Refused(f"no filament can be kept for {site!r}, {printer!r}")
    return state_dir() / "filaments" / site / f"{printer}.json"


def loaded(site: Optional[str], printer: Optional[str]) -> Optional[LoadedFile]:
    """What is loaded on ``printer`` of ``site``; None where nothing was said."""
    if not site or not printer:
        return None
    try:
        path = _path(site, printer)
    except Refused:
        return None
    if not path.is_file():
        return None
    return LoadedFile.model_validate_json(path.read_text(encoding="utf-8"))


def load(
    profile: PrinterProfile,
    site: str,
    printer: str,
    filament: str,
    note: str = "",
    resources: Optional[Path] = None,
) -> LoadedFile:
    """``filament`` loaded on ``printer`` of ``site``: one of its choices, kept."""
    if not chooses(profile):
        raise Refused(
            f"{profile.file} names the filament piece {profile.filament.modules!r}: the "
            "printer slices with the filament its profile names, not one loaded on it"
        )
    names = [c.name for c in choices(profile, resources)]
    if filament not in names:
        raise Refused(f"{filament!r} is no filament {profile.part} can load: " + ", ".join(names))
    now = Loaded(filament=filament, note=note.strip(), at=datetime.now(timezone.utc))
    kept = loaded(site, printer)
    before = ([*kept.before, kept.loaded] if kept else [])[-HISTORY:]
    record = LoadedFile(site=site, printer=printer, loaded=now, before=before)
    write_whole(_path(site, printer), record.model_dump_json(indent=2))
    return record


def chosen(
    profile: PrinterProfile, site: Optional[str], printer: Optional[str], module: str
) -> PrinterProfile:
    """``profile`` with the filament its next slice takes: the one loaded on the printer
    where its profile names ``choose`` and one is loaded, said with when and what was
    noted of it; the profile as it is otherwise."""
    if module != MODULE or not chooses(profile):
        return profile
    section = json.loads(json.dumps(_section(profile)))
    kept = loaded(site, printer)
    if kept is None:
        section["filament_chosen"] = (
            f"the profile's own, {section.get('filament')}: no filament loaded on "
            f"{printer or profile.part} has been said"
        )
    else:
        section["filament"] = kept.loaded.filament
        note = f" ({kept.loaded.note})" if kept.loaded.note else ""
        section["filament_chosen"] = (
            f"loaded on {site}'s {printer} {kept.loaded.at:%Y-%m-%d %H:%M} UTC{note}"
        )
    return profile.model_copy(update={"sections": {**profile.sections, MODULE: section}})
