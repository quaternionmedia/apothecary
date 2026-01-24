from __future__ import annotations

from pathlib import Path
from pydantic import BaseModel, Field

from apothecary.projects.parts.base import BasePart
from apothecary.projects.parts.skeleton import ROOT

class Params(BaseModel):
    blade_width: float = Field(120.0, gt=0)
    blade_height: float = Field(45.0, gt=0)
    blade_thickness: float = Field(3.0, gt=0)
    blade_angle: float = Field(10.0)
    mount_width: float = Field(40.0, gt=0)
    mount_height: float = Field(12.0, gt=0)
    mount_thickness: float = Field(4.0, gt=0)
    bolt_diameter: float = Field(3.0, gt=0)
    bolt_spacing: float = Field(24.0, gt=0)


def create(metadata_root: Path) -> BasePart:
    # Provide a dummy .scad path to satisfy BasePart validation
    dummy_scad = metadata_root / "parts" / "rc" / "snowplow" / "snowplow.scad"
    return BasePart(
        name="rc.snowplow",
        source_file=dummy_scad,
        description="Modular RC snowplow (Python parametric)",
        params_model=Params,
        category="rc",
        tags=["rc", "snowplow", "modular", "python"],
        readme_path=metadata_root / "parts" / "README.md",
    )


DEFAULT = create(ROOT)
