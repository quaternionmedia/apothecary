"""A stepped dust hose adapter: a 40 mm hose onto a 32 mm or a 25 mm fitting.

Each end pushes in. The hose end is a spigot the hose is pushed onto and clamped
over: smooth rubber or PVC takes a plain taper. The other end is stepped: a 32
step, then a 25 tip, each a spigot that goes into a fitting of that bore, one at a
time. Built in Python from one profile (``apothecary.fittings``), so the solid and
the three interfaces it declares come from the same numbers;
parts/dust/hose_adapter/hose_adapter.scad is that solid at the defaults, rewritten
by ``apothecary parts render hose_adapter -o parts/dust/hose_adapter/hose_adapter.scad``.

It prints as it is drawn: hose end on the bed, axis up. Every outside narrows
going up but the collar's underside, at 45 degrees, and every bore widens going up
but the two cones that close it in, at 45 degrees or less: nothing needs support.
parts/dust/README.md says what each number is and what the 25 tip costs a 32
fitting in airflow.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from pydantic import BaseModel, Field, model_validator

from apothecary.core import OpenSCADObject
from apothecary.fittings import WALL, Profile, Section
from apothecary.models import BoundingBox3D, Color, PrintSettings, Vector3D
from apothecary.models.interfaces import InterfaceBase
from apothecary.projects.parts.base import BasePart
from apothecary.projects.parts.skeleton import ROOT

MM = {"unit": "mm"}


class Params(BaseModel):
    """Each spigot is its nominal bore, wider by half its taper at its base and
    narrower by half at its tip; its bore leaves a wall of ``wall`` at the tip."""

    hose_d: float = Field(40.0, gt=0, json_schema_extra=MM, description="the hose's bore")
    fitting_d: float = Field(
        32.0, gt=0, json_schema_extra=MM, description="the larger fitting's bore"
    )
    tip_d: float = Field(25.0, gt=0, json_schema_extra=MM, description="the smaller fitting's bore")
    tip: bool = Field(True, description="the 25 tip past the 32 step; off: a plain 40 to 32")
    hose_length: float = Field(40.0, gt=0, json_schema_extra=MM)
    step_length: float = Field(25.0, gt=0, json_schema_extra=MM)
    tip_length: float = Field(20.0, gt=0, json_schema_extra=MM)
    hose_taper: float = Field(
        2.0, ge=0, json_schema_extra=MM, description="how much wider the hose end is at its base"
    )
    taper: float = Field(
        1.2,
        ge=0,
        json_schema_extra=MM,
        description="how much wider each fitting's spigot is at its base than at its tip",
    )
    wall: float = Field(WALL, gt=0, json_schema_extra=MM)
    collar: float = Field(
        5.0,
        gt=0,
        json_schema_extra=MM,
        description="how much wider the collar the hose stops against is than the hose end's base",
    )
    collar_length: float = Field(2.5, gt=0, json_schema_extra=MM)
    transition_length: float = Field(8.0, gt=0, json_schema_extra=MM)

    @model_validator(mode="after")
    def _prints(self) -> "Params":
        problems = profile(self).problems(wall=self.wall)
        if problems:
            raise ValueError("it would not print: " + "; ".join(problems))
        return self


def _spigot(d: float, taper: float) -> tuple:
    """(base, tip) outer diameters of a spigot for a bore of ``d``."""
    return (d + taper / 2, d - taper / 2)


def profile(p: Params) -> Profile:
    """The adapter as a stack of sections, hose end on the bed."""
    hose = _spigot(p.hose_d, p.hose_taper)
    step = _spigot(p.fitting_d, p.taper)
    hose_bore = hose[1] - 2 * p.wall
    step_bore = step[1] - 2 * p.wall
    collar = hose[0] + p.collar
    sections = [
        # The hose end points down: its tip is on the bed and its base at the top.
        Section(
            name="hose", length=p.hose_length, outer=(hose[1], hose[0]), bore=(hose_bore, hose_bore)
        ),
        Section(
            name="flare", length=p.collar / 2, outer=(hose[0], collar), bore=(hose_bore, hose_bore)
        ),
        Section(
            name="collar",
            length=p.collar_length,
            outer=(collar, collar),
            bore=(hose_bore, hose_bore),
        ),
        Section(
            name="transition",
            length=p.transition_length,
            outer=(collar, step[0]),
            bore=(hose_bore, step_bore),
        ),
        Section(name="step_32", length=p.step_length, outer=step, bore=(step_bore, step_bore)),
    ]
    if p.tip:
        tip = _spigot(p.tip_d, p.taper)
        tip_bore = tip[1] - 2 * p.wall
        sections += [
            # As short as a bore may close in, at 45 degrees.
            Section(
                name="shoulder",
                length=max((step_bore - tip_bore) / 2, p.wall),
                outer=(step[1], tip[0]),
                bore=(step_bore, tip_bore),
            ),
            Section(name="tip_25", length=p.tip_length, outer=tip, bore=(tip_bore, tip_bore)),
        ]
    return Profile(sections=sections)


class HoseAdapterPart(BasePart):
    """The adapter, built from its profile."""

    def geometry(self, params: Mapping[str, Any]) -> OpenSCADObject:
        return profile(Params(**params)).solid()

    def interfaces(self, params: Optional[Mapping[str, Any]] = None) -> List[InterfaceBase]:
        p = Params(**(params or {}))
        shape = profile(p)
        drawn = {"source": "drawn", "version": "1"}
        found = [
            shape.spigot(
                "hose",
                "hose",
                up=False,
                notes="the hose pushes on to the collar and is clamped over it",
                **drawn,
            ),
            shape.spigot(
                "fitting_32", "step_32", excludes=["fitting_25"] if p.tip else [], **drawn
            ),
        ]
        if p.tip:
            found.append(shape.spigot("fitting_25", "tip_25", excludes=["fitting_32"], **drawn))
        return found

    def get_bounds(self, params: Optional[Dict] = None) -> BoundingBox3D:
        shape = profile(Params(**(params or {})))
        r = shape.widest / 2
        return BoundingBox3D(
            min_point=Vector3D(x=-r, y=-r, z=0.0),
            max_point=Vector3D(x=r, y=r, z=shape.height),
        )


def create(metadata_root: Path) -> HoseAdapterPart:
    folder = metadata_root / "parts" / "dust" / "hose_adapter"
    return HoseAdapterPart(
        name="hose_adapter",
        source_file=folder / "hose_adapter.scad",
        description="A stepped dust hose adapter: a 40 mm hose onto a 32 mm or a 25 mm "
        "fitting, every end pushing in (Python parametric)",
        params_model=Params,
        category="dust",
        tags=["dust", "hose", "adapter", "python"],
        readme_path=metadata_root / "parts" / "dust" / "README.md",
        preview_color=Color(r=0.85, g=0.45, b=0.1),
        # printer_1's nozzle and layers; a wall of five lines.
        print_settings=PrintSettings(
            nozzle_diameter=0.4, layer_height=0.2, wall_thickness=WALL, tolerance=0.2
        ),
    )


DEFAULT = create(ROOT)

__all__ = ["DEFAULT", "HoseAdapterPart", "Params", "create", "profile"]
