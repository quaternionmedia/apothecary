from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple, Type

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from apothecary.core import OpenSCADObject
from apothecary.models import (
    GRAY,
    BoundingBox3D,
    Color,
    PrintSettings,
)

from .stl_renderer import find_openscad, openscad_meets, parse_openscad_version, scad_definitions


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


# A part is never turned after it renders: a wrapper or a part.json that says
# display_rotation is refused when the part loads, saying what to do instead.
TURN_REFUSED = (
    "display_rotation turns nothing: a part's SCAD lays it the way up it prints, which is "
    "its STL. Lay it so in the SCAD, and declare rest, the -D definitions that draw it as "
    "it stands in use, for how it rests (docs/parts-authoring.md#how-it-rests)"
)


def scad_variables(path: Path, text: Optional[str] = None) -> Set[str]:
    """Every top-level assignment in a SCAD file, or in ``text`` standing in for
    it (a draft): the names `-D` can override, a special variable such as
    ``$fn`` among them."""
    if text is None:
        text = Path(path).read_text(encoding="utf-8")
    return set(re.findall(r"^(\$?\w+)\s*=", text, re.M))


class BasePart(BaseModel):
    """Base metadata wrapper for a single SCAD part."""

    name: str
    source_file: Path
    description: Optional[str] = None
    params_model: Optional[Type[BaseModel]] = None
    category: Optional[str] = None
    # The kind of machine the part is, when it is one: "printer" or "router" (the
    # job registry's machine kinds, apothecary/jobs.py). A node drawn from it is a
    # machine of that kind, and can be planned before a board is pinned to it
    # (apothecary/machine_plans.py).
    machine: Optional[str] = None
    # A machine whose bed (or table) carries the work along Y under a tool that stands
    # still along Y: how far into its volume, along Y, the tool stands. None: the tool
    # moves along Y over a bed that stays (a gantry machine), or the part is no machine.
    bed_moves_y: Optional[float] = None
    # A machine drawn as what stands still and what moves, so a scene can move each with
    # the axes rather than render a pose: the parameter that picks a piece, the value
    # that draws all that stands still, where the axes stand when each piece is drawn
    # (the part's defaults), and for each moving piece how far it moves along each
    # axis of the part's frame per millimetre of each machine axis, e.g. a table that
    # carries Y: {"piece": "table", "follows": {"y": -1}}. None: drawn as one.
    kinematics: Optional[Dict[str, Any]] = None
    tags: List[str] = Field(default_factory=list)
    # The registered parts this one is built from, when that is not what its SCAD's
    # include/use lines and the sites that hold it say (apothecary/composition.py).
    # None: inferred. A list, an empty one included, is the answer, and wins.
    parts: Optional[List[str]] = None
    readme_path: Optional[Path] = None
    module_name: Optional[str] = None

    # Geometry metadata
    default_bounds: Optional[BoundingBox3D] = None
    preview_color: Color = Field(default_factory=lambda: GRAY)
    print_settings: Optional[PrintSettings] = None

    # How it rests, where that is not how it prints: the -D definitions that make
    # its SCAD draw it as it stands in use (the footpedal's {"print": False}). The
    # world draws that; its STL, what is sliced, stays the print pose. None: it
    # rests as it prints.
    rest: Optional[Dict[str, Any]] = None

    # Parameters whose value is genuinely in dispute, keyed by parameter name.
    # Empty for a part nobody disagrees about, which is most of them.
    contested: Dict[str, List[ContestedValue]] = Field(default_factory=dict)

    # The oldest OpenSCAD that renders the part, as `openscad --version` numbers
    # it (2021.01, or a snapshot's 2025.03.15); None when any will do.
    openscad_min_version: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _not_turned(cls, data: Any) -> Any:
        if isinstance(data, Mapping) and "display_rotation" in data:
            raise ValueError(TURN_REFUSED)
        return data

    @field_validator("openscad_min_version")
    @classmethod
    def _names_a_version(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and parse_openscad_version(value) is None:
            raise ValueError(f"{value!r} is not an OpenSCAD version such as 2021.01")
        return value

    @field_validator("rest")
    @classmethod
    def _definable(cls, value: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if value is not None:
            try:
                scad_definitions(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"rest: {exc}") from None
        return value

    @model_validator(mode="after")
    def _rests_by_its_own_names(self) -> "BasePart":
        # A -D name the SCAD does not assign draws nothing, so a rest that names one
        # would rest as it prints and say nothing: it is refused with what is assigned.
        if self.rest and self.source_file.exists():
            assigned = scad_variables(self.source_file)
            unknown = sorted(set(self.rest) - assigned)
            if unknown:
                raise ValueError(
                    f"rest: {', '.join(unknown)} is not assigned in {self.source_file.name}, "
                    "so it would draw nothing; rest names the SCAD's own variables"
                )
        return self

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

    def validate_overrides(
        self, params: Optional[Mapping[str, Any]], scad_text: Optional[str] = None
    ) -> Dict[str, Any]:
        """Parameter overrides checked against ``params_model``, as it coerced them.

        OpenSCAD accepts any ``-D`` name, defined or not, so a misspelled one
        would render the defaults and look like success. Raises ValueError
        (a pydantic ValidationError for a bad value). Without a model the
        names are checked against the SCAD's top-level variables: its file's,
        or ``scad_text``'s when a draft of it is what renders.
        """
        if not params:
            return {}
        resting = sorted(set(params) & set(self.rest or {}))
        if resting:
            raise ValueError(
                f"{', '.join(resting)} says how {self.name} rests, in its rest, and is no "
                "parameter: set by hand, it would turn what a slice reads"
            )
        if self.params_model is None:
            # No Python model: the SCAD's own top-level variables are what -D reaches.
            if scad_text is not None:
                declared = scad_variables(self.source_file, text=scad_text)
            elif self.source_file.exists():
                declared = scad_variables(self.source_file)
            else:
                declared = set()
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

    def cuts(self, params: Optional[Mapping[str, Any]] = None):
        """The cuts that make this part from its stock, for a part cut on the router
        (``apothecary.cam.models.Cuts``, from ``params`` as ``Params`` reads them);
        None for a part that is printed, bought or only drawn."""
        return None

    @property
    def has_cuts(self) -> bool:
        """Whether this part says how it is cut: its wrapper defines ``cuts``."""
        return type(self).cuts is not BasePart.cuts

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
