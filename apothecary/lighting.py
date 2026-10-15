"""A lighting rig read from a console's patch export, and what its DMX says.

The export names each fixture's channels (``ADDRESS``) and parameters, but not
which DMX slot holds which parameter: ``PARAMETER_ADDRESS_OFFSET`` is 0 for
every row. ``DMX_MAPS`` supplies that order per fixture type, and
``validate_rig`` checks each map against the address span the patch uses, so a
wrong map shows up as a report rather than as colours on the wrong lamp.

Nothing here knows about any one venue. A venue is a folder of exports handed
to ``load_rig``.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Tuple

from pydantic import BaseModel, Field

from .hierarchy import LayoutReport, LayoutViolation
from .models.vectors import Vector3D

DMX_CHANNELS = 512

# DMX slot order per fixture type, by parameter name. None marks a slot whose
# meaning is not known yet; it is still counted against the address span.
DMX_MAPS: Dict[str, List[Optional[str]]] = {
    "ColorSource_SPOT_5ch": ["Intens", "Red", "Green", "Blue", "Shutter_Strobe"],
    "ColorSource_PAR_DB_5ch": ["Intens", "Red", "Green", "Blue", "Shutter_Strobe"],
    "Slimpar_64_3ch": ["Red", "Green", "Blue"],
    "UV_Light": ["Intens", "UV", "UV_2", "UV_3", "Shutter_Strobe", "Locked_Value"],
    "Dimmer": ["Intens"],
    # shortcut: slots 6-15 unnamed until the PLCYC1 DMX chart is read; upgrade when it is
    "PLCYC1_MKII_16B": ["Intens", "Red", "Green", "Blue", "White"] + [None] * 10,
}


class FixtureType(BaseModel):
    name: str
    manufacturer: str = ""
    params: List[str] = Field(default_factory=list)


class Patch(BaseModel):
    """One patched channel: where it is in DMX and in the room, if known."""

    channel: int
    fixture_type: str
    label: str = ""
    universe: Optional[int] = None
    addresses: List[int] = Field(default_factory=list)
    location: Optional[Vector3D] = None
    orientation: Optional[Vector3D] = None


class LightingRig(BaseModel):
    types: Dict[str, FixtureType] = Field(default_factory=dict)
    patches: List[Patch] = Field(default_factory=list)

    @property
    def universes(self) -> List[int]:
        return sorted({p.universe for p in self.patches if p.universe is not None})

    def unplaced(self) -> List[Patch]:
        """Patches with no position in the room. Listed, not an error."""
        return [p for p in self.patches if p.location is None]


def parse_address(text: str) -> Tuple[Optional[int], List[int]]:
    """``'2/400<404,406'`` -> ``(2, [400, 401, 402, 403, 404, 406])``. Blank -> ``(None, [])``."""
    text = text.strip()
    if not text:
        return None, []
    universe, _, spans = text.partition("/")
    addresses: List[int] = []
    for span in spans.split(","):
        first, _, last = span.strip().partition("<")
        addresses.extend(range(int(first), int(last or first) + 1))
    return int(universe), addresses


def _vector(x: str, y: str, z: str) -> Optional[Vector3D]:
    if not (x.strip() and y.strip() and z.strip()):
        return None
    return Vector3D(x=float(x), y=float(y), z=float(z))


def load_rig(patches_csv: Path, params_csv: Path) -> LightingRig:
    """Read an Eos patch export and its fixture-parameter export."""
    types: Dict[str, FixtureType] = {}
    with open(params_csv, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            name = row["FIXTURE_TYPE_NAME"]
            fixture = types.setdefault(
                name,
                FixtureType(name=name, manufacturer=row["FIXTURE_TYPE_MANUFACTURER"]),
            )
            fixture.params.append(row["PARAMETER_TYPE_TEXT_SHORT"])

    patches: List[Patch] = []
    with open(patches_csv, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            universe, addresses = parse_address(row["ADDRESS"])
            patches.append(
                Patch(
                    channel=int(row["CHANNEL"]),
                    fixture_type=row["FIXTURE_TYPE"],
                    label=row["LABEL"],
                    universe=universe,
                    addresses=addresses,
                    location=_vector(row["LOCATION_X"], row["LOCATION_Y"], row["LOCATION_Z"]),
                    orientation=_vector(row["ORIENTATION_X"], row["ORIENTATION_Y"], row["ORIENTATION_Z"]),
                )
            )
    return LightingRig(types=types, patches=patches)


def validate_rig(rig: LightingRig) -> LayoutReport:
    """Unknown types, maps that do not fit their address span, and DMX clashes."""
    violations: List[LayoutViolation] = []
    claimed: Dict[Tuple[int, int], str] = {}
    for p in rig.patches:
        where = f"ch{p.channel} {p.label or p.fixture_type}"
        if p.fixture_type not in rig.types:
            violations.append(LayoutViolation(
                kind="unknown_type", structures=[where],
                message=f"{where}: fixture type {p.fixture_type!r} is not in the parameter export",
            ))
        dmx = DMX_MAPS.get(p.fixture_type)
        if dmx is not None and p.addresses and len(dmx) != len(p.addresses):
            violations.append(LayoutViolation(
                kind="dmx_map_length", structures=[where],
                message=f"{where}: DMX map has {len(dmx)} slots but the patch spans {len(p.addresses)}",
            ))
        for address in p.addresses:
            if not 1 <= address <= DMX_CHANNELS:
                violations.append(LayoutViolation(
                    kind="address_range", structures=[where],
                    message=f"{where}: address {address} is outside 1-{DMX_CHANNELS}",
                ))
            key = (p.universe, address)
            if key in claimed:
                violations.append(LayoutViolation(
                    kind="address_overlap", structures=[claimed[key], where],
                    message=f"universe {p.universe} address {address} is used by {claimed[key]} and {where}",
                ))
            else:
                claimed[key] = where
    return LayoutReport(violations=violations)


def decode(rig: LightingRig, universes: Mapping[int, bytes]) -> Dict[int, Dict[str, float]]:
    """DMX slots -> ``{channel: {param: 0..1}}`` for every patch whose type has a map.

    Patches with no map, no address, or no universe packet are left out; the
    console may still reach them by channel number.
    """
    out: Dict[int, Dict[str, float]] = {}
    for p in rig.patches:
        dmx = DMX_MAPS.get(p.fixture_type)
        slots = universes.get(p.universe) if p.universe is not None else None
        if not dmx or not p.addresses or slots is None:
            continue
        levels: Dict[str, float] = {}
        for name, address in zip(dmx, p.addresses, strict=False):  # validate_rig reports a length mismatch
            if name is not None:
                levels[name] = slots[address - 1] / 255 if address <= len(slots) else 0.0
        out[p.channel] = levels
    return out


def fixture_color(levels: Mapping[str, float]) -> Tuple[int, int, int]:
    """0-255 RGB for a fixture: its colour scaled by Intens. No colour -> white at Intens."""
    intens = levels.get("Intens", 1.0)
    rgb = [levels.get(c) for c in ("Red", "Green", "Blue")]
    if all(v is None for v in rgb):
        rgb = [1.0, 1.0, 1.0]
    return tuple(round(255 * intens * (v or 0.0)) for v in rgb)  # type: ignore[return-value]
