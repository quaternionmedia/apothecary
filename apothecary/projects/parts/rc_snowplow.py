from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from pydantic import BaseModel, Field

from apothecary.core import OpenSCADObject
from apothecary.models import BoundingBox3D, Vector3D
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


class SnowplowPart(BasePart):
    """Python-parametric snowplow assembly (blade + chassis mount).

    Geometry is produced by ``apothecary.projects.parts.rc.snowplow.snowplow_assembly``
    rather than by the ``.scad`` file, so bounds are computed from the same
    parameters that drive that assembly.
    """

    def geometry(self, params: Mapping[str, Any]) -> OpenSCADObject:
        # Imported here: that package imports this module for its DEFAULT.
        from .rc.snowplow import snowplow_assembly

        return snowplow_assembly(**Params(**params).model_dump())

    def get_bounds(self, params: Optional[Dict] = None) -> BoundingBox3D:
        p = Params(**(params or {}))
        # Blade: centered cube (w, t, h) rotated about X by blade_angle, then
        # lifted by h/2 so it sits on z=0 before rotation.
        a = math.radians(p.blade_angle)
        half_y = (p.blade_thickness / 2) * abs(math.cos(a)) + (p.blade_height / 2) * abs(
            math.sin(a)
        )
        half_z = (p.blade_thickness / 2) * abs(math.sin(a)) + (p.blade_height / 2) * abs(
            math.cos(a)
        )
        blade_min = Vector3D(x=-p.blade_width / 2, y=-half_y, z=p.blade_height / 2 - half_z)
        blade_max = Vector3D(x=p.blade_width / 2, y=half_y, z=p.blade_height / 2 + half_z)
        # Mount: cube (mw, mt, mh) on the bed, its front face where
        # snowplow_assembly puts it, against the blade's back face.
        from .rc.snowplow import mount_front_y

        front = mount_front_y(p.blade_height, p.blade_thickness, p.blade_angle, p.mount_height)
        mount_min = Vector3D(x=-p.mount_width / 2, y=front - p.mount_thickness, z=0)
        mount_max = Vector3D(x=p.mount_width / 2, y=front, z=p.mount_height)
        return BoundingBox3D(
            min_point=Vector3D(
                x=min(blade_min.x, mount_min.x),
                y=min(blade_min.y, mount_min.y),
                z=min(blade_min.z, mount_min.z),
            ),
            max_point=Vector3D(
                x=max(blade_max.x, mount_max.x),
                y=max(blade_max.y, mount_max.y),
                z=max(blade_max.z, mount_max.z),
            ),
        )


def create(metadata_root: Path) -> SnowplowPart:
    # The .scad is geometry() at the default parameters, for readers and the
    # registry; `apothecary parts render rc.snowplow -o <this file>` rewrites it.
    scad = metadata_root / "parts" / "rc" / "snowplow" / "snowplow.scad"
    return SnowplowPart(
        name="rc.snowplow",
        source_file=scad,
        description="Modular RC snowplow (Python parametric)",
        params_model=Params,
        category="rc",
        tags=["rc", "snowplow", "modular", "python"],
        readme_path=metadata_root / "parts" / "README.md",
    )


DEFAULT = create(ROOT)
