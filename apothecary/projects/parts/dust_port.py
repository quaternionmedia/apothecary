"""A round end of a dust system: a hose's end, a tool's port, a collector's inlet.

One part, whose parameters say which end it is: whether it takes a spigot in (a
socket: a hose's bore, a port's bore) or goes into one (a spigot: a tool's outlet
stub); ``diameter``, what calipers read at the end -- a socket's bore at its mouth,
a spigot's outside at its tip; how far it holds; how far a hose's bore opens when
pushed; how much a spigot tapers; and whether those numbers were measured. The
sizes people meet are its presets (``hose_40``, ``port_32``, ``port_25``,
``outlet_35``), chosen as ``dust_port@port_32`` at the command line, and a
measured end is the part with the caliper's numbers typed over one.

It is drawn as a stand-in: a tube standing on the bed with its end at the top,
``wall`` thick, built in Python from one profile (``apothecary.fittings``) so its
solid and the interface it declares, ``end``, come from the same numbers.
parts/dust/dust_port/dust_port.scad is that solid at the defaults, rewritten by
``apothecary parts render dust_port -o parts/dust/dust_port/dust_port.scad``.
docs/connections.md is the reference.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from pydantic import BaseModel, Field, model_validator

from apothecary.core import OpenSCADObject
from apothecary.fittings import Profile, Section, facets
from apothecary.models import BoundingBox3D, Color, Vector3D
from apothecary.models.interfaces import InterfaceBase
from apothecary.projects.parts.base import BasePart, Preset
from apothecary.projects.parts.skeleton import ROOT

MM = {"unit": "mm"}


class Params(BaseModel):
    """Which end it is, as calipers and a hand find it. Every default is a guess
    until ``measured`` is ticked."""

    socket: bool = Field(
        True,
        description="it takes a spigot in, a hose's or a port's bore; off: it is a spigot "
        "that goes into one, a tool's outlet stub",
    )
    diameter: float = Field(
        32.0,
        gt=0,
        json_schema_extra=MM,
        description="what calipers read at the end: a socket's bore at its mouth, a "
        "spigot's outside at its tip",
    )
    length: float = Field(
        30.0,
        gt=0,
        json_schema_extra=MM,
        description="how deep a socket's bore holds at that diameter, or how long a spigot is",
    )
    stretch: float = Field(
        0.0,
        ge=0,
        lt=100,
        json_schema_extra={"unit": "%"},
        description="how far a socket's bore opens when a spigot is pushed in: a hose's "
        "give, 0 for anything rigid",
    )
    taper: float = Field(
        0.0,
        ge=0,
        json_schema_extra=MM,
        description="how much wider a spigot is at its base than at its tip; 0 for a "
        "straight one",
    )
    wall: float = Field(
        3.0, gt=0, json_schema_extra=MM, description="the stand-in's wall round the end"
    )
    measured: bool = Field(
        False, description="these numbers were measured on the real end; off: guessed"
    )

    @model_validator(mode="after")
    def _prints(self) -> "Params":
        if not self.socket and self.diameter - 2 * self.wall <= 0:
            raise ValueError(
                f"a spigot {self.diameter:g} across leaves no bore inside a {self.wall:g} wall"
            )
        problems = profile(self).problems()
        if problems:
            raise ValueError("it would not print: " + "; ".join(problems))
        return self


def profile(p: Params) -> Profile:
    """The stand-in as one section standing on the bed, its end at the top."""
    if p.socket:
        outer = p.diameter + 2 * p.wall
        section = Section(
            name="end", length=p.length, outer=(outer, outer), bore=(p.diameter, p.diameter)
        )
    else:
        bore = p.diameter - 2 * p.wall
        section = Section(
            name="end",
            length=p.length,
            outer=(p.diameter + p.taper, p.diameter),
            bore=(bore, bore),
        )
    return Profile(sections=[section], fn=facets(max(section.outer)))


# What a person measures, by the kind of end it is.
MEASURE = {
    True: "measure the bore at the mouth and 20 mm in, how deep it holds, and, for a "
    "hose, how far it opens by hand",
    False: "measure the outside at the tip and at the base, and how long the stub is",
}


class DustPortPart(BasePart):
    """One end, built from its profile."""

    def geometry(self, params: Mapping[str, Any]) -> OpenSCADObject:
        return profile(Params(**params)).solid()

    def interfaces(self, params: Optional[Mapping[str, Any]] = None) -> List[InterfaceBase]:
        p = Params(**(params or {}))
        shape = profile(p)
        said = {
            "source": "measured" if p.measured else "stub",
            "notes": "Measured." if p.measured else f"Guessed: {MEASURE[p.socket]}.",
        }
        if p.socket:
            return [shape.socket("end", top=True, stretch=p.stretch / 100, **said)]
        return [shape.spigot("end", "end", up=True, **said)]

    def get_bounds(self, params: Optional[Dict] = None) -> BoundingBox3D:
        shape = profile(Params(**(params or {})))
        r = shape.widest / 2
        return BoundingBox3D(
            min_point=Vector3D(x=-r, y=-r, z=0.0),
            max_point=Vector3D(x=r, y=r, z=shape.height),
        )


# The sizes people meet. Every number in them is a guess: a person measures the real
# end and types it over the preset, ticking measured.
PRESETS = {
    "hose_40": Preset(
        description="a smooth 40 mm bore dust hose, rubber or PVC: 100 mm of it, opening "
        "5% when pushed",
        params={"socket": True, "diameter": 40.0, "length": 100.0, "stretch": 5.0, "wall": 4.0},
    ),
    "port_32": Preset(
        description="a rigid port with a 32 mm bore, a tool's or a collector's",
        params={"socket": True, "diameter": 32.0, "length": 30.0, "wall": 3.0},
    ),
    "port_25": Preset(
        description="a rigid port with a 25 mm bore",
        params={"socket": True, "diameter": 25.0, "length": 25.0, "wall": 3.0},
    ),
    "outlet_35": Preset(
        description="a tool's outlet stub, 35 mm across, that a hose's cuff goes over",
        params={"socket": False, "diameter": 35.0, "length": 30.0, "wall": 3.0},
    ),
}


def create(metadata_root: Path) -> DustPortPart:
    folder = metadata_root / "parts" / "dust" / "dust_port"
    return DustPortPart(
        name="dust_port",
        source_file=folder / "dust_port.scad",
        description="A round end of a dust system -- a hose's end, a tool's port, a "
        "collector's inlet -- its parameters which end it is (Python parametric)",
        params_model=Params,
        category="dust",
        tags=["dust", "port", "hose", "stub", "python"],
        readme_path=metadata_root / "parts" / "dust" / "README.md",
        preview_color=Color(r=0.55, g=0.55, b=0.6),
        presets=PRESETS,
    )


DEFAULT = create(ROOT)

__all__ = ["DEFAULT", "DustPortPart", "MEASURE", "PRESETS", "Params", "create", "profile"]
