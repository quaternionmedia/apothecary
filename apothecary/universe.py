"""The universe: a sphere of nested shells, every registered part a leaf on one and
every other site one piece on the outermost.

A prototype, under hierarchy.py's draft record. The universe is a Site in the same
``Assembly`` shape the garage example uses, so the fractal viewer reaches a part by
navigating down to it and a site by stepping into its piece:

- every registered part is a leaf (``role="part"``). Its **shell** is its composition
  depth (``composition.py``, ``orbitals.py``): a part built from no other registered
  part is innermost, and each shell outward holds the parts compounded from the shells
  inside it. The shells are dense, so none is empty. A leaf stands on its shell facing
  outward: its ``turn`` stands its up along the ray from the middle of the universe,
  and its footprint's middle is on the shell. A leaf carries its part's ``category``,
  and the leaves of one category sit together on their shell; it carries what it is
  ``built_from``, and each of those stands as nearly under it as its shell allows --
  under the first by name, of the leaves that are built from one. The layout is a
  catalog, not a build: nothing constrains it (``validate_universe``);
- every other registered site is one piece (``role="site"``, ``site_ref`` naming it),
  on the shell outside every part's, upright. It is drawn in miniature: its site's
  top-level pieces as boxes, scaled to fit, never larger than they are. The boxes are
  read from the site as it stands, so a piece follows its site (``represent``), and
  nothing is rendered to draw one.

The layout is the whole answer to where anything stands: it is made again, from the
footprints and depths, whenever the universe is drawn, so a piece moved by hand
returns, and a site added that nests no part moves only what is on the outermost shell, and one that
nests a part in another moves that one to the shell its depth then gives it.

A site's piece is not a level: a step into it goes to its site. The universe does not
hold itself.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, NamedTuple, Optional, Set

from pydantic import PrivateAttr

from .composition import nesting_fingerprint, nesting_of, scad_children, with_nesting
from .hierarchy import Assembly, LayoutReport
from .models.bounds import BoundingBox3D
from .models.vectors import Vector3D
from .orbitals import composition_depths, dense_shells, lay_out, turned
from .primitives import Cube
from .projects.parts.skeleton import ROOT
from .projects.registry import load_parts
from .site_names import UNIVERSE_SHOWN

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


def _bounding_radius(box: BoundingBox3D) -> float:
    """The radius of the sphere about a footprint's middle that holds the footprint."""
    return 0.5 * math.sqrt(box.width**2 + box.height**2 + box.depth**2)


def arrange(universe: Assembly) -> None:
    """Every leaf and every piece of ``universe`` on its shell, from their footprints.

    A leaf's shell is its ``depth`` ranked among the depths that occur; the pieces
    stand on the shell outside the last. On a shell the nodes of one ``category`` sit
    together, and a leaf another is ``built_from`` stands under it -- under the first by
    name, where several are built from it (``orbitals.lay_out``). Nothing already placed
    is read, so a hand-moved node goes back, and the pieces, being outermost and built
    into nothing, move no leaf."""
    leaves = [c for c in universe.children if c.part_ref and c.footprint is not None]
    pieces = [c for c in universe.children if c.site_ref and c.footprint is not None]
    shells = dense_shells({leaf.name: leaf.depth or 0 for leaf in leaves})
    outermost = max(shells.values(), default=-1) + 1
    shell_of = {**shells, **{piece.name: outermost for piece in pieces}}
    size_of = {node.name: _bounding_radius(node.footprint) for node in (*leaves, *pieces)}
    category_of = {node.name: node.category for node in (*leaves, *pieces)}
    built_into: dict = {}
    for leaf in leaves:
        for child in leaf.built_from or ():
            built_into.setdefault(child, []).append(leaf.name)
    parent_of = {child: min(parents) for child, parents in built_into.items()}
    placed = lay_out(shell_of, size_of, category_of=category_of, parent_of=parent_of)
    for node in (*leaves, *pieces):
        where = placed[node.name]
        # The middle of the footprint, turned with the node, lands on the shell's point.
        turn = (
            Vector3D(x=where.turn[0], y=where.turn[1], z=where.turn[2]) if node.part_ref else None
        )
        middle = node.footprint.center
        carried = (
            turned((turn.x, turn.y, turn.z), (middle.x, middle.y, middle.z))
            if turn is not None
            else (middle.x, middle.y, middle.z)
        )
        node.turn = turn
        node.shell = where.shell
        node.position = Vector3D(
            x=where.point[0] - carried[0],
            y=where.point[1] - carried[1],
            z=where.point[2] - carried[2],
        )


class Universe(Assembly):
    """The universe's root: an ``Assembly`` that also keeps what its leaves' composition
    was read from, so the depths can follow the sites as they stand (``represent``).
    Not part of what is sent: a private attribute is no field."""

    _own: Dict[str, Set[str]] = PrivateAttr(default_factory=dict)
    _explicit: Set[str] = PrivateAttr(default_factory=set)
    _nesting: Any = PrivateAttr(default=None)


def follow_nesting(universe: Assembly, sites: Mapping[str, Assembly]) -> bool:
    """Read each leaf's depth from the sites as they stand now, when what they nest has
    changed since it was last read. True when it was read again.

    Walking the sites for the parts they hold costs a pass over their nodes, which a
    fetch pays each time; the depths, the leaves' ``built_from`` and so the layout change
    only when that fingerprint does, so a site that nests nothing new moves no part.
    A universe not made by ``create_universe_site`` has no composition to read and keeps
    the depths it was given."""
    if not isinstance(universe, Universe) or not universe._own:
        return False
    nesting = nesting_of(sites.values())
    fingerprint = nesting_fingerprint(nesting)
    if fingerprint == universe._nesting:
        return False
    children = with_nesting(universe._own, universe._explicit, nesting)
    depths = composition_depths(children)
    for leaf in universe.children:
        if leaf.part_ref in children:
            leaf.depth = depths[leaf.part_ref]
            leaf.built_from = children[leaf.part_ref] or None
    universe._nesting = fingerprint
    return True


def represent(universe: Assembly, sites: Mapping[str, Assembly]) -> None:
    """One piece in ``universe`` for each of ``sites``, drawn from it as it stands.

    A site new to the register gets its piece; a site that left it loses its piece; a
    piece already there is drawn again, so it follows a site whose pieces moved. Then
    the universe is arranged (``arrange``): the pieces on the outermost shell, wherever
    a piece stood before. The pieces come first among the universe's own, by their
    sites' names."""
    follow_nesting(universe, sites)
    standing = {child.site_ref: child for child in universe.children if child.site_ref}
    pieces: List[Assembly] = []
    for name in sorted(sites):
        piece = standing.get(name) or Assembly(name=piece_name(name), role="site", site_ref=name)
        _draw(piece, sites[name])
        pieces.append(piece)
    universe.children = [*pieces, *(c for c in universe.children if not c.site_ref)]
    arrange(universe)


def create_universe_site(sites: Optional[Mapping[str, Assembly]] = None) -> Assembly:
    """The universe: one leaf for each registered ``parts/`` entry, on the shell its
    composition depth gives it, and one piece for each of ``sites``, the other
    registered sites by their names, outside them. A building one of ``sites`` holds
    is that site's, and no leaf. The depths follow the sites each time the universe is
    arranged (``follow_nesting``)."""
    sites = sites or {}
    theirs = set().union(*(parts_held(site) for site in sites.values())) if sites else set()
    # A part that does not load is left off the grid; `apothecary problems` reports it.
    parts = {
        item.name: part
        for item, part in load_parts(ROOT).parts
        if not (part.category in NOT_ON_THE_BENCH and item.name in theirs)
    }
    own = scad_children(parts)
    explicit = {name for name, part in parts.items() if part.parts is not None}
    children = with_nesting(own, explicit, nesting_of(sites.values()))
    depths = composition_depths(children)
    leaves = [
        Assembly(
            name=name,
            role="part",
            part_ref=name,
            category=parts[name].category,
            depth=depths[name],
            built_from=children[name] or None,
            footprint=parts[name].get_bounds() or FALLBACK_BOUNDS,
        )
        for name in sorted(parts)
    ]
    universe = Universe(name=UNIVERSE_SHOWN, role="site", children=leaves)
    universe._own, universe._explicit = own, explicit
    universe._nesting = nesting_fingerprint(nesting_of(sites.values()))
    represent(universe, sites)
    return universe


def validate_universe(site: Assembly) -> LayoutReport:
    """Always valid: a browsing catalog has no "must not overlap" constraint
    the way a physical build layout does -- a deliberate no-op, not a missing
    check.
    """
    return LayoutReport()
