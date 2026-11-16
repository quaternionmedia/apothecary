"""A printer's correction, fed back from a part it made: measured by a person, checked
against what was sliced, and held for that printer's next slices.

A slice records the size of the model it sliced (``SliceRecord.size``: its STL's box,
the way up it prints). A person measures the part the printer made from that slice --
its X, its Y, its Z, any of them -- and the measurement is checked before anything is
kept: each size is within ``WITHIN`` of the size sliced, or it is not of that slice's
part and is refused, saying so.

What is fed back is OrcaSlicer's ``xy_contour_compensation``, which moves each outer
wall in or out: the mean of X's and Y's errors is two walls' worth, so the correction
is half of it, taken from the value the measured slice used. A correction past
``MOST`` is refused: that far off is the steps per millimetre or the flow, which a
contour does not correct. Z is checked and recorded, not applied: its error is the
layers' and the firmware's.

The correction is the printer's, not its part's: two Enders differ, so it is kept per
machine node in the state folder (``corrections/<site>/<node>.json``), with every
measurement that made it, newest last, and the printer's part's profile is left as it
is. Every later slice for that printer takes it, as a value whose origin is
``measured`` and whose source names the measurement (``applied``); a slice for a
printer part with no site, or by another slicer module, takes none.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

from ..state_folder import state_dir, write_whole
from .models import SliceRecord
from .profiles import PrinterProfile

SETTING = "xy_contour_compensation"
KIND = "process"
MODULE = "orcaslicer"
# A size measured further than this share from the size sliced is not that part's.
WITHIN = 0.05
# Millimetres: a contour moved further than this is not what the contour is off by.
MOST = 0.5
AXES = ("x", "y", "z")
NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]{0,199}$")


class Refused(ValueError):
    """A measurement that is not kept, and why."""


class Measurement(BaseModel):
    """One part measured: what was sliced, what was measured, and what came of it."""

    at: datetime
    file_id: str  # the kept file whose slice made the part
    part: str  # what was sliced: the part's name, or the piece's
    sliced: List[float]  # x, y, z of the model sliced, mm
    measured: List[Optional[float]]  # x, y, z as measured, mm; None where not measured
    used: float  # the correction the measured slice was made with, mm
    correction: float  # the correction after it, mm


class Correction(BaseModel):
    """A printer's correction, and the measurements that made it, newest last."""

    site: str
    printer: str  # the printer's node in the site
    setting: str = SETTING
    value: float
    measurements: List[Measurement] = Field(default_factory=list)


def _kept_at(site: str, printer: str) -> Path:
    if not NAME.match(site) or not NAME.match(printer):
        raise Refused(f"no correction can be kept for {site!r}, {printer!r}")
    return state_dir() / "corrections" / site / f"{printer}.json"


def load(site: Optional[str], printer: Optional[str]) -> Optional[Correction]:
    """The correction kept for the printer node ``printer`` of ``site``, or None."""
    if not site or not printer:
        return None
    try:
        path = _kept_at(site, printer)
    except Refused:
        return None
    if not path.is_file():
        return None
    return Correction.model_validate_json(path.read_text(encoding="utf-8"))


def used_by(record: SliceRecord) -> float:
    """The correction a slice was made with, as its settings say it; 0 where none."""
    for setting in record.settings:
        if setting.name == SETTING:
            try:
                return float(setting.value)
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def measure(record: SliceRecord, measured: List[Optional[float]]) -> Correction:
    """``measured`` (x, y, z, None where not measured) checked against ``record``'s
    model, and the correction it makes kept for the printer the slice was for.
    ``Refused`` says why, and nothing is kept."""
    at = record.printer
    if not at.site or not at.path:
        raise Refused(
            f"{record.name} was sliced for {at.name}, a printer of no site: "
            "a correction is kept for a printer standing in one"
        )
    if record.size is None:
        raise Refused(
            f"{record.name}'s slice does not say the size of what it sliced: slice "
            f"{record.made.name} again, print it, and measure that"
        )
    if len(measured) != 3:
        raise Refused("a measurement is x, y and z, each or none")
    if measured[0] is None and measured[1] is None:
        raise Refused("measure X or Y: the correction is the walls', which those two show")
    for axis, value, size in zip(AXES, measured, record.size, strict=True):
        if value is None:
            continue
        if not value > 0:
            raise Refused(f"{axis.upper()} {value} mm is no size")
        if abs(value - size) > WITHIN * size:
            raise Refused(
                f"{axis.upper()} {value:g} mm against {size:.2f} mm sliced is more than "
                f"{WITHIN:.0%} off: not this slice's part, or measured across something "
                "else -- measure it again, or choose the file it was printed from"
            )
    errors = [
        value - size
        for value, size in zip(measured[:2], record.size[:2], strict=True)
        if value is not None
    ]
    used = used_by(record)
    correction = round(used - (sum(errors) / len(errors)) / 2, 3)
    if abs(correction) > MOST:
        raise Refused(
            f"a correction of {correction:+.3f} mm is past {MOST} mm: that far off is the "
            "steps per millimetre or the flow, which moving the walls does not correct"
        )
    kept = load(at.site, at.path) or Correction(site=at.site, printer=at.path, value=0.0)
    kept.value = correction
    kept.measurements.append(
        Measurement(
            at=datetime.now(timezone.utc),
            file_id=record.file_id,
            part=record.made.name,
            sliced=list(record.size),
            measured=list(measured),
            used=used,
            correction=correction,
        )
    )
    write_whole(_kept_at(at.site, at.path), kept.model_dump_json(indent=2))
    return kept


def said(measurement: Measurement) -> str:
    """What a measurement found, in words: each axis's error and the correction."""
    parts = []
    for axis, value, size in zip(AXES, measurement.measured, measurement.sliced, strict=True):
        if value is not None:
            parts.append(f"{axis.upper()} {value - size:+.2f}")
    return (
        f"{measurement.part} measured {', '.join(parts)} mm against what was sliced; "
        f"{SETTING} {measurement.used:+.3f} -> {measurement.correction:+.3f} mm"
    )


def applied(
    profile: PrinterProfile, site: Optional[str], printer: Optional[str], module: str
) -> PrinterProfile:
    """``profile`` with the printer's kept correction held in its ``set``, origin
    ``measured``: what every slice for that printer takes. The profile as it is where
    none is kept, or the slice is by another slicer module."""
    kept = load(site, printer)
    if kept is None or module != MODULE:
        return profile
    section = json.loads(json.dumps(profile.sections.get(MODULE) or {}))
    held = section.setdefault("set", {}).setdefault(KIND, {})
    newest = kept.measurements[-1] if kept.measurements else None
    held[SETTING] = {
        "value": f"{kept.value:g}",
        "source": f"{site}'s {printer}, measured: "
        + (said(newest) + f" ({newest.at:%Y-%m-%d})" if newest else "kept"),
        "origin": "measured",
    }
    return profile.model_copy(update={"sections": {**profile.sections, MODULE: section}})
