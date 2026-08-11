"""Worked example: the registered ``parts/`` library as a fractal tree.

PROTOTYPE — migrates the existing ``parts/`` registry (``elephant_walk``,
``star-cookiecutter``, ...) into the same ``Assembly`` shape the garage
example uses, as leaf (``role="part"``) nodes under one Site. This is what
lets the fractal zoom viewer reach "the old part-viewer experience" by
navigating down to a leaf, rather than keeping parts browsing as a separate
page: a part leaf is not spatially laid out for any physical constraint (see
``validate_parts_library`` below) -- it's a catalog, not a build -- but it is
still just an ``Assembly``, addressable and zoomable the same way every other
node in this codebase is.
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


def _registered_part_names() -> list[str]:
    """Every part name with a loadable wrapper module (same filter as api.py's
    ``_available_part_names``, duplicated rather than imported from api.py
    to avoid an example module depending on the API layer).
    """
    return sorted({p.name for p in scan_projects(ROOT) if p.kind == "part" and p.wrapper})


def _load_part_bounds(wrapper_module: str) -> BoundingBox3D:
    module = import_module(wrapper_module)
    part = module.DEFAULT
    return part.get_bounds() or FALLBACK_BOUNDS


def _grid_position(index: int) -> Vector3D:
    row, col = divmod(index, GRID_COLUMNS)
    return Vector3D(x=col * CELL_PITCH, y=row * CELL_PITCH, z=0)


def create_parts_library_site() -> Assembly:
    """A Site made entirely of part leaves -- one per registered ``parts/`` entry."""
    entries_by_name = {p.name: p for p in scan_projects(ROOT) if p.kind == "part" and p.wrapper}

    leaves = []
    for index, name in enumerate(_registered_part_names()):
        wrapper_module = entries_by_name[name].wrapper
        leaves.append(
            Assembly(
                name=name,
                role="part",
                part_ref=name,
                position=_grid_position(index),
                footprint=_load_part_bounds(wrapper_module),
            )
        )

    return Site(name="Parts Library", structures=leaves)


def validate_parts_library(site: Assembly) -> LayoutReport:
    """Always valid: a browsing catalog has no "must not overlap" constraint
    the way a physical build layout does -- a deliberate no-op, not a missing
    check.
    """
    return LayoutReport()
