from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple, Type

from pydantic import BaseModel, Field, computed_field, field_validator

from apothecary.core import OpenSCADObject
from apothecary.models import (
    GRAY,
    BoundingBox3D,
    Color,
    PrintSettings,
    Vector3D,
)

from .stl_renderer import find_openscad, openscad_meets, parse_openscad_version


class ContestedValue(BaseModel):
    """One source's answer for a parameter that sources disagree about.

    A number two documents state differently is not a detail to be settled by
    whoever edits last. Recording the candidates with their provenance puts the
    disagreement somewhere a person can see it -- and, through the part
    dashboard, turn instead of argue about.
    """

    value: float
    source: str
    note: str = ""


def scad_variables(path: Path) -> Set[str]:
    """Every top-level assignment in a SCAD file: the names `-D` can override."""
    return set(re.findall(r"^(\w+)\s*=", Path(path).read_text(encoding="utf-8"), re.M))


class BasePart(BaseModel):
    """Base metadata wrapper for a single SCAD part."""

    name: str
    source_file: Path
    description: Optional[str] = None
    params_model: Optional[Type[BaseModel]] = None
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    readme_path: Optional[Path] = None
    module_name: Optional[str] = None

    # Geometry metadata
    default_bounds: Optional[BoundingBox3D] = None
    preview_color: Color = Field(default_factory=lambda: GRAY)
    print_settings: Optional[PrintSettings] = None

    # Display orientation: rotation [rx, ry, rz] in degrees to apply
    # for preferred "up" orientation (Z-up, sitting on ground plane)
    display_rotation: Vector3D = Field(default_factory=Vector3D)

    # Parameters whose value is genuinely in dispute, keyed by parameter name.
    # Empty for a part nobody disagrees about, which is most of them.
    contested: Dict[str, List[ContestedValue]] = Field(default_factory=dict)

    # The oldest OpenSCAD that renders the part, as `openscad --version` numbers
    # it (2021.01, or a snapshot's 2025.03.15); None when any will do.
    openscad_min_version: Optional[str] = None

    @field_validator("openscad_min_version")
    @classmethod
    def _names_a_version(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and parse_openscad_version(value) is None:
            raise ValueError(f"{value!r} is not an OpenSCAD version such as 2021.01")
        return value

    @property
    def exists(self) -> bool:
        return self.source_file.exists()

    @property
    def part_dir(self) -> Path:
        """Get the part's directory (parent of source file)."""
        return self.source_file.parent

    @computed_field
    @property
    def stl_file(self) -> Optional[Path]:
        """Get the STL file path if it exists."""
        stl_path = self.get_stl_output_path()
        return stl_path if stl_path.exists() else None

    def get_stl_output_path(self) -> Path:
        """
        Get the path where STL should be written.

        Override in subclasses for custom STL locations (e.g., submodule parts).
        Default is same directory as source file with .stl extension.
        """
        return self.source_file.with_suffix(".stl")

    @computed_field
    @property
    def jscad_file(self) -> Optional[Path]:
        """Get the JSCAD file path if it exists."""
        jscad_path = self.source_file.with_suffix(".jscad")
        return jscad_path if jscad_path.exists() else None

    def can_generate_stl(self, openscad: Optional[Path] = None) -> Tuple[bool, str]:
        """Whether this part's STL can be built on this machine, and if not,
        why: with ``openscad`` when the caller names one, else with the first
        install that meets ``openscad_min_version``. A part with checks of its
        own overrides this and ends with ``super().can_generate_stl(openscad)``."""
        if self.openscad_min_version is None:
            return True, ""
        if openscad is not None:
            return openscad_meets(openscad, self.openscad_min_version)
        found, reason = find_openscad(self.openscad_min_version)
        return found is not None, reason

    def get_openscad_path(self) -> Optional[Path]:
        """The OpenSCAD this part needs, or None for whichever is installed."""
        if self.openscad_min_version is None:
            return None
        return find_openscad(self.openscad_min_version)[0]

    def validate_overrides(self, params: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
        """Parameter overrides checked against ``params_model``, as it coerced them.

        OpenSCAD accepts any ``-D`` name, defined or not, so a misspelled one
        would render the defaults and look like success. Raises ValueError
        (a pydantic ValidationError for a bad value).
        """
        if not params:
            return {}
        if self.params_model is None:
            # No Python model: the SCAD's own top-level variables are what -D reaches.
            declared = scad_variables(self.source_file) if self.source_file.exists() else set()
            unknown = sorted(set(params) - declared)
            if unknown:
                raise ValueError(
                    f"unknown parameter(s): {', '.join(unknown)}. {self.name} declares "
                    f"{', '.join(sorted(declared)) or 'no top-level variables'} in its SCAD"
                )
            return dict(params)
        known = set(self.params_model.model_fields)
        unknown = sorted(set(params) - known)
        if unknown:
            raise ValueError(
                f"unknown parameter(s): {', '.join(unknown)}. "
                f"{self.name} declares: {', '.join(sorted(known))}"
            )
        validated = self.params_model(**params)
        return {name: getattr(validated, name) for name in params}

    def scad_overrides(self, params: Mapping[str, Any]) -> Dict[str, Any]:
        """What ``-D`` receives for already-validated ``params``: by default the
        params themselves. A part whose model names things differently from its
        SCAD translates here; the params sidecar still records ``params``."""
        return dict(params)

    def geometry(self, params: Mapping[str, Any]) -> Optional[OpenSCADObject]:
        """The part built in Python for already-validated ``params``, or None:
        the SCAD file is the source. A part that returns an object is rendered
        from that object's SCAD, and its SCAD file is only what a reader sees."""
        return None

    def get_bounds(self, params: Optional[Dict] = None) -> Optional[BoundingBox3D]:
        """
        Calculate bounding box for the part with given parameters.

        Override in subclasses for accurate bounds calculation.
        Falls back to default_bounds if not overridden.
        """
        return self.default_bounds

    def to_geometry_dict(self, params: Optional[Dict] = None) -> Dict:
        """Export geometry metadata for API/viewer."""
        bounds = self.get_bounds(params)
        return {
            "bounds": (
                {
                    "min": bounds.min_point.to_list() if bounds else None,
                    "max": bounds.max_point.to_list() if bounds else None,
                    "size": bounds.size.to_list() if bounds else None,
                    "center": bounds.center.to_list() if bounds else None,
                }
                if bounds
                else None
            ),
            "color": self.preview_color.to_openscad(),
            "color_hex": self.preview_color.to_hex(),
        }
