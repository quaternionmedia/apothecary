"""The universe: every registered part a leaf, and every other site one piece.

A prototype, under hierarchy.py's draft record. The universe is a Site in the same
``Assembly`` shape the garage example uses, so the fractal viewer reaches a part by
navigating down to it and a site by stepping into its piece:

- every registered part is a leaf (``role="part"``), on a catalog grid. The layout is
  a catalog, not a build: nothing constrains where a leaf sits (``validate_universe``);
- every other registered site is one piece (``role="site"``, ``site_ref`` naming it),
  in a cell of its own in the row in front of the grid. It is drawn in miniature: its
  site's top-level pieces as boxes, scaled into the cell, never larger than they are.
  The boxes are read from the site as it stands, so a piece follows its site
  (``represent``), and nothing is rendered to draw one.

A site's piece is not a level: a step into it goes to its site. The universe does not
hold itself.
"""

from __future__ import annotations

from typing import List, Mapping, NamedTuple, Optional, Set, Tuple

from .hierarchy import Assembly, LayoutReport, Site
from .models.bounds import BoundingBox3D
from .models.vectors import Vector3D
from .primitives import Cube
from .projects.parts.skeleton import ROOT
from .projects.registry import load_parts
from .site_names import UNIVERSE_SHOWN

# Catalog grid layout (mm) -- generous fixed pitch so parts of varying size
# don't need individual placement; visual sensibility only, since layout
# validity isn't a meaningful constraint for a browsing catalog (see
# validate_universe).
GRID_COLUMNS = 5
CELL_PITCH = 300.0

# Fallback footprint for a part whose wrapper has no default_bounds set, and for
# the piece of a site that holds nothing with a size -- still gives it a real,
# clickable box in the catalog view rather than a zero-size one.
FALLBACK_BOUNDS = BoundingBox3D.for_cube(40.0)

# The longest a site's piece is across the floor: its site is scaled to fit, and
# a site smaller than this is drawn the size it is.
PIECE_SPAN = 240.0

# A site's piece is named for its site, behind this: a site and a part may share
# a name (datum_core is both), and a part's name holds no dash.
PIECE_PREFIX = "site-"

# A building is tens of metres across: the site that holds it stands for it, and
# it is left off the grid of benchtop cells. One no site holds is a leaf like any other.
NOT_ON_THE_BENCH = {"building"}


def piece_name(site_name: str) -> str:
    """The name of ``site_name``'s piece in the universe."""
    return f"{PIECE_PREFIX}{site_name}"


def _grid_position(index: int) -> Vector3D:
    row, col = divmod(index, GRID_COLUMNS)
    return Vector3D(x=col * CELL_PITCH, y=row * CELL_PITCH, z=0)


def _site_cell(index: int) -> Vector3D:
    """The ``index``-th cell of the sites' rows, in front of the parts' (-y)."""
    row, col = divmod(index, GRID_COLUMNS)
    return Vector3D(x=col * CELL_PITCH, y=-(row + 1) * CELL_PITCH, z=0)


class Box(NamedTuple):
    """One piece of a site as a box, in the site's own frame."""

    name: str
    category: Optional[str]
    bounds: BoundingBox3D


def _envelope(node: Assembly, origin: Vector3D) -> Optional[BoundingBox3D]:
    """``node``'s footprint where it stands, ``origin`` being its parent's place; for
    a node with none of its own, the extent of what it holds; None for neither."""
    at = origin + node.position
    if node.footprint is not None:
        return BoundingBox3D(
            min_point=node.footprint.min_point + at, max_point=node.footprint.max_point + at
        )
    held = [
        box
        for child in (*node.children, *node.additions)
        if (box := _envelope(child, at)) is not None
    ]
    return _around(held)


def _around(boxes: List[BoundingBox3D]) -> Optional[BoundingBox3D]:
    if not boxes:
        return None
    return BoundingBox3D.from_points([p for b in boxes for p in (b.min_point, b.max_point)])


def boxes_of(site: Assembly) -> List[Box]:
    """A site's top-level pieces as boxes: each one's footprint where it stands. A
    piece with none of its own -- a building's shell around its walls, a rig by its
    hanging positions -- gives one box for each thing it holds."""
    found: List[Box] = []
    for piece in site.children:
        if piece.footprint is not None:
            found.append(Box(piece.name, piece.category, piece.world_bounds()))
            continue
        for held in (*piece.children, *piece.additions):
            box = _envelope(held, piece.position)
            if box is not None:
                found.append(Box(held.name, held.category or piece.category, box))
    return found


def parts_held(site: Assembly) -> Set[str]:
    """Every registered part a node of ``site`` is, at any depth."""
    found: Set[str] = set()

    def visit(node: Assembly) -> None:
        if node.part_ref:
            found.add(node.part_ref)
        for child in (*node.children, *node.additions, *node.subtractions):
            visit(child)

    visit(site)
    return found


def _draw(piece: Assembly, site: Assembly) -> None:
    """``piece`` drawn from ``site`` as it stands: its boxes scaled about the middle
    of the piece's cell and stood on the floor, and its footprint their extent."""
    boxes = boxes_of(site)
    extent = _around([box.bounds for box in boxes])
    if extent is None:
        piece.children = []
        piece.base = Cube(size=FALLBACK_BOUNDS.size, center=False)
        piece.footprint = FALLBACK_BOUNDS
        return
    across = max(extent.width, extent.height)  # along x, along y
    scale = min(1.0, PIECE_SPAN / across) if across > 0 else 1.0
    middle = extent.center
    # The site's frame, in the piece's: its middle over the cell's, its lowest point on the floor.
    origin = Vector3D(x=middle.x, y=middle.y, z=extent.min_point.z)

    def placed(point: Vector3D) -> Vector3D:
        return (point - origin) * scale

    piece.base = None
    piece.children = [
        Assembly(
            name=box.name,
            role="structure",
            category=box.category,
            position=placed(box.bounds.min_point),
            footprint=BoundingBox3D(min_point=Vector3D(), max_point=box.bounds.size * scale),
            base=Cube(size=box.bounds.size * scale, center=False),
        )
        for box in boxes
    ]
    piece.footprint = BoundingBox3D(
        min_point=placed(extent.min_point), max_point=placed(extent.max_point)
    )


def real_size(site: Assembly) -> Optional[Vector3D]:
    """How large ``site`` is, by its top-level pieces' extents; None for one that
    holds nothing with a size."""
    extent = _around([box.bounds for box in boxes_of(site)])
    return extent.size if extent is not None else None


def represent(universe: Assembly, sites: Mapping[str, Assembly]) -> None:
    """One piece in ``universe`` for each of ``sites``, drawn from it as it stands.

    A site new to the register gets its piece, in the first cell of the sites' rows
    no piece stands in; a site that left it loses its piece; a piece already there
    keeps its place and is drawn again, so it follows a site whose pieces moved. The
    pieces come first among the universe's own, by their sites' names."""
    standing = {child.site_ref: child for child in universe.children if child.site_ref}
    kept = {name: piece for name, piece in standing.items() if name in sites}
    taken: Set[Tuple[float, float]] = {(p.position.x, p.position.y) for p in kept.values()}
    pieces: List[Assembly] = []
    for name in sorted(sites):
        piece = kept.get(name)
        if piece is None:
            cell = next(
                c
                for c in map(_site_cell, range(len(sites) + len(taken)))
                if (c.x, c.y) not in taken
            )
            taken.add((cell.x, cell.y))
            piece = Assembly(name=piece_name(name), role="site", site_ref=name, position=cell)
        _draw(piece, sites[name])
        pieces.append(piece)
    universe.children = [*pieces, *(c for c in universe.children if not c.site_ref)]


def create_universe_site(sites: Optional[Mapping[str, Assembly]] = None) -> Assembly:
    """The universe: one leaf for each registered ``parts/`` entry, and one piece for
    each of ``sites``, the other registered sites by their names. A building one of
    ``sites`` holds is that site's, and no leaf."""
    sites = sites or {}
    theirs = set().union(*(parts_held(site) for site in sites.values())) if sites else set()
    # A part that does not load is left off the grid; `apothecary problems` reports it.
    parts = {
        item.name: part
        for item, part in load_parts(ROOT).parts
        if not (part.category in NOT_ON_THE_BENCH and item.name in theirs)
    }
    leaves = [
        Assembly(
            name=name,
            role="part",
            part_ref=name,
            position=_grid_position(index),
            footprint=parts[name].get_bounds() or FALLBACK_BOUNDS,
        )
        for index, name in enumerate(sorted(parts))
    ]
    universe = Site(name=UNIVERSE_SHOWN, structures=leaves)
    represent(universe, sites)
    return universe


def validate_universe(site: Assembly) -> LayoutReport:
    """Always valid: a browsing catalog has no "must not overlap" constraint
    the way a physical build layout does -- a deliberate no-op, not a missing
    check.
    """
    return LayoutReport()
