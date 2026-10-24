"""Worked example: the registered ``parts/`` library as a fractal tree.

PROTOTYPE — every registered part as a leaf (``role="part"``) under one Site,
in the same ``Assembly`` shape the garage example uses, so the fractal viewer
reaches a part by navigating down to it. The layout is a catalog grid, not a
build: nothing constrains where a leaf sits (see ``validate_parts_library``).
"""

from __future__ import annotations

from importlib import import_module

from .hierarchy import Assembly, LayoutReport, Site
from .models.bounds import BoundingBox3D
from .models.vectors import Vector3D
from .projects.parts.skeleton import ROOT
from .projects.registry import scan_projects

# Catalog grid layout (mm) -- generous fixed pitch so parts of varying size
# don't need individual placement; visual sensibility only, since layout
# validity isn't a meaningful constraint for a browsing catalog (see
# validate_parts_library).
GRID_COLUMNS = 5
CELL_PITCH = 300.0

# Fallback footprint for a part whose wrapper has no default_bounds set --
# still gives it a real, clickable box in the catalog view rather than a
# zero-size one.
FALLBACK_BOUNDS = BoundingBox3D.for_cube(40.0)


def _registered_wrappers() -> dict[str, str]:
    """Every registered part that has a wrapper module, by name (the same filter
    as api.py's ``_available_part_names``; not imported, so an example does not
    depend on the API layer)."""
    return {p.name: p.wrapper for p in scan_projects(ROOT) if p.kind == "part" and p.wrapper}


def _load_part_bounds(wrapper_module: str) -> BoundingBox3D:
    module = import_module(wrapper_module)
    part = module.DEFAULT
    return part.get_bounds() or FALLBACK_BOUNDS


def _grid_position(index: int) -> Vector3D:
    row, col = divmod(index, GRID_COLUMNS)
    return Vector3D(x=col * CELL_PITCH, y=row * CELL_PITCH, z=0)


def create_parts_library_site() -> Assembly:
    """A Site made entirely of part leaves -- one per registered ``parts/`` entry."""
    wrappers = _registered_wrappers()
    leaves = [
        Assembly(
            name=name,
            role="part",
            part_ref=name,
            position=_grid_position(index),
            footprint=_load_part_bounds(wrappers[name]),
        )
        for index, name in enumerate(sorted(wrappers))
    ]
    return Site(name="Parts Library", structures=leaves)


def validate_parts_library(site: Assembly) -> LayoutReport:
    """Always valid: a browsing catalog has no "must not overlap" constraint
    the way a physical build layout does -- a deliberate no-op, not a missing
    check.
    """
    return LayoutReport()
