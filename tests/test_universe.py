"""The universe (apothecary/universe.py), a prototype: every registered part a leaf
Assembly node on a spherical shell of its composition depth, and every other registered
site one piece of it on the outermost shell, drawn in miniature from its top-level
pieces' extents.
"""

import itertools
import math
import subprocess

import pytest
from fastapi.testclient import TestClient

from apothecary import api, sites
from apothecary.hierarchy import Assembly, LayoutReport, Site, Structure
from apothecary.models.bounds import BoundingBox3D
from apothecary.models.vectors import Vector3D
from apothecary.orbitals import GAP, turned
from apothecary.projects.parts.skeleton import ROOT
from apothecary.projects.registry import load_parts, scan_projects
from apothecary.site_names import UNIVERSE
from apothecary.site_store import SiteStore
from apothecary.universe import (
    PIECE_SPAN,
    boxes_of,
    create_universe_site,
    parts_held,
    piece_name,
    real_size,
    represent,
    validate_universe,
)

client = TestClient(api.app)


def _registered_part_names():
    return {p.name for p in scan_projects(ROOT) if p.kind == "part" and p.has_part}


def _others():
    """The other registered sites, as the universe is given them."""
    return sites.store.others()


def _leaves(universe: Assembly):
    return [child for child in universe.children if child.part_ref]


def _pieces(universe: Assembly):
    return [child for child in universe.children if child.site_ref]


def _unrepresented(universe: Assembly, sites) -> set:
    """The parts that load and are neither a leaf of ``universe`` nor inside a site
    one of its pieces stands for."""
    leaves = {leaf.part_ref for leaf in _leaves(universe)}
    stood_for = {piece.site_ref for piece in _pieces(universe)}
    inside = set().union(*(parts_held(sites[name]) for name in stood_for)) if stood_for else set()
    return {item.name for item, _part in load_parts(ROOT).parts} - leaves - inside


# --- the parts ---------------------------------------------------------------------------


def test_every_registered_part_is_a_leaf_but_a_building_a_site_holds():
    """A building is tens of metres across: the theatre's site stands for the theatre,
    which is no cell of the bench's catalog."""
    universe = create_universe_site(_others())
    assert {leaf.name for leaf in _leaves(universe)} == _registered_part_names() - {"theatre"}


def test_a_building_no_site_holds_is_a_leaf():
    """Off the grid for its size only while a site's piece stands for it."""
    alone = create_universe_site({})
    assert "theatre" in {leaf.name for leaf in _leaves(alone)}
    without_the_theatre = {n: s for n, s in _others().items() if n != "theatre"}
    assert "theatre" in {leaf.name for leaf in _leaves(create_universe_site(without_the_theatre))}


@pytest.mark.parametrize("held", ["every site", "the garage alone", "no site"])
def test_every_part_that_loads_is_a_leaf_or_inside_a_represented_site(held):
    sites = _others()
    if held == "the garage alone":
        sites = {"garage": sites["garage"]}
    elif held == "no site":
        sites = {}
    assert _unrepresented(create_universe_site(sites), sites) == set()


def test_the_served_universe_leaves_no_part_out():
    universe = sites.store.get(UNIVERSE)
    assert _unrepresented(universe, _others()) == set()


def test_every_leaf_is_a_part_role_with_part_ref_and_footprint():
    for leaf in _leaves(create_universe_site(_others())):
        assert leaf.role == "part"
        assert leaf.part_ref == leaf.name
        assert leaf.footprint is not None
        # a leaf has no geometry/children of its own -- it's addressed by
        # part_ref, not composed like a Structure/Substructure/Feature
        assert leaf.children == []
        assert leaf.additions == []
        assert leaf.subtractions == []
        assert leaf.base is None


def _middle(node):
    box = node.world_bounds().center
    return (box.x, box.y, box.z)


def _reach(node):
    box = node.footprint
    return 0.5 * math.sqrt(box.width**2 + box.height**2 + box.depth**2)


def test_a_leaf_stands_on_the_shell_its_composition_depth_gives_it():
    universe = sites.store.get(UNIVERSE)
    leaves = _leaves(universe)
    by_depth = {}
    for leaf in leaves:
        by_depth.setdefault(leaf.depth, set()).add(leaf.shell)
    # one shell for each depth, outward as the depth is, and no shell empty
    assert all(len(shells) == 1 for shells in by_depth.values())
    ranked = [next(iter(by_depth[d])) for d in sorted(by_depth)]
    assert ranked == list(range(len(ranked)))
    depth = {leaf.name: leaf.depth for leaf in leaves}
    # built from nothing is innermost; what is built from another registered part is not
    assert depth["webcam"] == 0 and depth["webcam_desk_stand"] == 1
    assert depth["creality_v422"] == 0 and depth["ender3"] == 1


def test_a_leaf_carries_its_parts_category_and_the_leaves_it_is_built_from():
    universe = create_universe_site(_others())
    parts = {item.name: part for item, part in load_parts(ROOT).parts}
    leaves = {leaf.name: leaf for leaf in _leaves(universe)}
    for name, leaf in leaves.items():
        assert leaf.category == parts[name].category, name
        assert set(leaf.built_from or ()) <= set(leaves), name
    assert leaves["ender3"].built_from == ["creality_v422"]
    assert leaves["webcam"].built_from is None
    assert all(piece.built_from is None for piece in _pieces(universe))


def _angle(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True)) / (math.hypot(*a) * math.hypot(*b))
    return math.acos(max(-1.0, min(1.0, dot)))


def test_the_leaves_of_a_category_are_one_piece_of_their_shell():
    """Each leaf joined to those of its category among its six nearest on its shell,
    the neighbours a point of the lattice has about it: every category of every shell
    is one piece."""
    universe = sites.store.get(UNIVERSE)
    by_shell = {}
    for leaf in _leaves(universe):
        by_shell.setdefault(leaf.shell, []).append(leaf)
    clusters = 0
    for leaves in by_shell.values():
        nearest = {
            a.name: [
                b.name
                for b in sorted(
                    (b for b in leaves if b is not a), key=lambda b: _angle(_middle(a), _middle(b))
                )[:6]
            ]
            for a in leaves
        }
        kind = {leaf.name: leaf.category for leaf in leaves}
        for category in set(kind.values()):
            members = [n for n in kind if kind[n] == category]
            seen, stack = {members[0]}, [members[0]]
            while stack:
                for m in nearest[stack.pop()]:
                    if kind[m] == category and m not in seen:
                        seen.add(m)
                        stack.append(m)
            assert seen == set(members), (category, sorted(members), sorted(seen))
            clusters += len(members) > 1
    assert clusters >= 3


def test_a_leaf_stands_under_the_first_by_name_of_the_leaves_built_from_it():
    """Of every node on the shell of the leaves built from it, the first of them by name
    is the nearest above it: the webcam under webcam_ceiling_mount, of its three."""
    universe = sites.store.get(UNIVERSE)
    nodes = universe.children
    into = {}
    for leaf in _leaves(universe):
        for child in leaf.built_from or ():
            into.setdefault(child, []).append(leaf)
    assert len(into["webcam"]) == 3
    for child, parents in into.items():
        first = min(parents, key=lambda p: p.name)
        around = [n for n in nodes if n.shell == first.shell]
        below = _middle(next(n for n in nodes if n.name == child))
        nearest = min(around, key=lambda n: _angle(_middle(n), below))
        assert nearest.name == first.name, (child, nearest.name, first.name)


def test_a_shell_is_a_sphere_about_the_origin_and_each_clears_the_one_inside():
    leaves = _leaves(sites.store.get(UNIVERSE))
    radius = {}
    for leaf in leaves:
        radius.setdefault(leaf.shell, []).append(math.dist((0, 0, 0), _middle(leaf)))
    for shell, found in radius.items():
        assert max(found) - min(found) < 1e-6, shell
    ordered = [radius[shell][0] for shell in sorted(radius)]
    assert ordered == sorted(set(ordered))
    reach = {}
    for leaf in leaves:
        reach[leaf.shell] = max(reach.get(leaf.shell, 0), _reach(leaf))
    for inner, outer in zip(sorted(radius), sorted(radius)[1:], strict=False):
        assert radius[outer][0] - radius[inner][0] >= reach[inner] + reach[outer] + GAP - 1e-6


def test_no_two_nodes_of_the_universe_overlap():
    universe = sites.store.get(UNIVERSE)
    nodes = [*_leaves(universe), *_pieces(universe)]
    for a, b in itertools.combinations(nodes, 2):
        gap = math.dist(_middle(a), _middle(b)) - _reach(a) - _reach(b)
        assert gap >= GAP - 1e-6, (a.name, b.name)


def test_a_leaf_faces_outward_and_a_piece_is_upright():
    universe = sites.store.get(UNIVERSE)
    for leaf in _leaves(universe):
        x, y, z = _middle(leaf)
        length = math.dist((0, 0, 0), (x, y, z))
        up = turned((leaf.turn.x, leaf.turn.y, leaf.turn.z), (0, 0, 1))
        assert up == pytest.approx((x / length, y / length, z / length), abs=1e-9), leaf.name
    assert all(piece.turn is None for piece in _pieces(universe))


def test_a_turned_leaf_holds_nothing_so_the_trees_frame_is_right_for_it():
    # api._assembly_tree carries a turn for the node and not into what it holds
    universe = sites.store.get(UNIVERSE)
    for leaf in _leaves(universe):
        assert leaf.turn is not None
        assert not (leaf.children or leaf.additions or leaf.subtractions)


def test_the_universe_is_the_same_each_time_it_is_drawn():
    first = create_universe_site(_others())
    second = create_universe_site(_others())
    assert [(c.name, c.position, c.turn, c.shell) for c in first.children] == [
        (c.name, c.position, c.turn, c.shell) for c in second.children
    ]


def test_validate_universe_is_always_valid():
    report = validate_universe(create_universe_site(_others()))
    assert report.is_valid
    assert report.violations == []


# --- the other sites, one piece each -------------------------------------------------------


def test_every_other_site_is_one_piece_on_the_outermost_shell_named_for_it():
    sites = _others()
    universe = create_universe_site(sites)
    pieces = _pieces(universe)
    assert [piece.site_ref for piece in pieces] == sorted(sites)
    assert [piece.name for piece in pieces] == [piece_name(name) for name in sorted(sites)]
    assert all(piece.role == "site" for piece in pieces)
    # The pieces come first, and no part has a piece's name: datum_core is a site and a part.
    assert universe.children[: len(pieces)] == pieces
    names = [child.name for child in universe.children]
    assert len(set(names)) == len(names)
    # Outside every part's shell, all on one, and no two at one place.
    outside = max(leaf.shell for leaf in _leaves(universe)) + 1
    assert {piece.shell for piece in pieces} == {outside}
    assert len({_middle(piece) for piece in pieces}) == len(pieces)
    for piece in pieces:
        assert piece.footprint.width <= PIECE_SPAN + 1e-6
        assert piece.footprint.height <= PIECE_SPAN + 1e-6


def test_a_universe_of_sites_alone_has_them_on_the_first_shell():
    universe = Site("all")
    represent(universe, {"a": _bench(), "b": _bench()})
    assert {piece.shell for piece in _pieces(universe)} == {0}


def test_the_universe_does_not_hold_itself():
    assert UNIVERSE in sites.store.names()
    assert UNIVERSE not in sites.store.others()
    universe = sites.store.get(UNIVERSE)
    assert UNIVERSE not in {piece.site_ref for piece in _pieces(universe)}
    assert {piece.site_ref for piece in _pieces(universe)} == set(sites.store.names()) - {UNIVERSE}


def _bench() -> Assembly:
    return Site(
        "bench",
        structures=[
            Structure(
                "table",
                footprint=BoundingBox3D(max_point=Vector3D(x=2000, y=1000, z=800)),
                category="furniture",
            ),
            Structure(
                "lamp",
                position=Vector3D(x=500, y=200, z=800),
                footprint=BoundingBox3D(max_point=Vector3D(x=100, y=100, z=400)),
            ),
        ],
    )


def _store(registry=None) -> SiteStore:
    def valid(_site):
        return LayoutReport()

    held = {} if registry is None else registry
    store = SiteStore(held, universe="all")
    held["all"] = (lambda: create_universe_site(store.others()), valid)
    held.setdefault("bench", (_bench, valid))
    return store


def test_a_site_added_to_the_register_gets_its_piece_and_one_taken_off_loses_it():
    """With no hand work: the register is what the universe is drawn from."""
    store = _store()
    assert [p.site_ref for p in _pieces(store.get("all"))] == ["bench"]
    leaves = {c.name: (c.position, c.turn, c.shell) for c in _leaves(store.get("all"))}

    store.add("attic", _bench, lambda _site: LayoutReport())
    pieces = _pieces(store.get("all"))
    assert [p.site_ref for p in pieces] == ["attic", "bench"]
    assert len({_middle(p) for p in pieces}) == 2
    # No part moved: the pieces stand outside them.
    assert {c.name: (c.position, c.turn, c.shell) for c in _leaves(store.get("all"))} == leaves

    store.remove("attic")
    assert [p.site_ref for p in _pieces(store.get("all"))] == ["bench"]
    assert {c.name: (c.position, c.turn, c.shell) for c in _leaves(store.get("all"))} == leaves


def test_a_site_that_cannot_be_built_now_has_no_piece():
    """A photo arrangement whose picture left the shelf since the names were read."""

    def gone():
        raise KeyError("attic")

    store = _store()
    store.add("attic", gone, lambda _site: LayoutReport())
    assert [p.site_ref for p in _pieces(store.get("all"))] == ["bench"]


def test_a_piece_is_its_sites_top_level_pieces_scaled_into_its_cell():
    store = _store()
    piece = _pieces(store.get("all"))[0]
    assert real_size(store.get("bench")) == Vector3D(x=2000, y=1000, z=1200)
    scale = PIECE_SPAN / 2000
    assert [box.name for box in piece.children] == ["table", "lamp"]
    table, lamp = piece.children
    assert table.footprint.size == Vector3D(x=2000, y=1000, z=800) * scale
    assert table.category == "furniture"
    # About the middle of its cell, on the floor: the lamp stands on the table.
    assert piece.footprint.min_point == Vector3D(x=-1000, y=-500, z=0) * scale
    assert piece.footprint.max_point == Vector3D(x=1000, y=500, z=1200) * scale
    assert lamp.position == Vector3D(x=500 - 1000, y=200 - 500, z=800) * scale


def test_a_piece_follows_its_site():
    """Drawn from the site as it stands, each time the universe is fetched."""
    store = _store()
    lamp = store.get("bench").children[1]
    lamp.position = Vector3D(x=3900, y=200, z=800)
    piece = _pieces(store.get("all"))[0]
    assert real_size(store.get("bench")).x == 4000
    assert piece.footprint.width == pytest.approx(PIECE_SPAN)


def test_the_layout_wins_over_a_piece_or_a_leaf_moved_by_hand():
    store = _store()
    laid = store.get("all")
    piece, leaf = _pieces(laid)[0], _leaves(laid)[0]
    piece_at, leaf_at = piece.position, leaf.position
    piece.position = Vector3D(x=900, y=-600, z=0)
    leaf.position = Vector3D(x=1, y=2, z=3)
    again = store.get("all")
    assert _pieces(again)[0].position == piece_at
    assert _leaves(again)[0].position == leaf_at


def test_a_site_smaller_than_a_cell_is_drawn_the_size_it_is():
    sites = _others()
    piece = next(p for p in _pieces(create_universe_site(sites)) if p.site_ref == "datum_core")
    assert piece.footprint.size == real_size(sites["datum_core"])


def test_a_piece_with_no_footprint_of_its_own_gives_what_it_holds():
    """The garage's building is a shell round its walls: each wall is a box."""
    garage = _others()["garage"]
    building = next(c for c in garage.children if c.name == "garage_building")
    assert building.footprint is None
    names = [box.name for box in boxes_of(garage)]
    assert "garage_building" not in names
    assert {wall.name for wall in building.children} <= set(names)


def test_a_site_that_holds_nothing_with_a_size_is_still_a_piece():
    universe = Site("all")
    represent(universe, {"empty": Site("empty")})
    (piece,) = universe.children
    assert piece.footprint is not None and piece.children == []
    assert "Site: site-empty" in universe.render()
    assert real_size(Site("empty")) is None


# --- as the page is sent it ---------------------------------------------------------------


def test_the_tree_carries_a_pieces_miniature_and_no_level_beneath_it():
    tree = client.get(f"/sites/{UNIVERSE}").json()["tree"]
    pieces = {child["site_ref"]: child for child in tree["children"] if child["site_ref"]}
    assert set(pieces) == {"datum_core", "garage", "theatre"}
    garage = pieces["garage"]
    assert garage["name"] == "site-garage" and garage["role"] == "site"
    assert garage["children"] == [] and garage["part_ref"] is None
    real = real_size(sites.store.get("garage"))
    assert garage["site_size"] == [real.x, real.y, real.z]
    # Each box inside the piece's own bounds, where the piece stands.
    low, high = garage["world_bounds"]["min"], garage["world_bounds"]["max"]
    assert garage["miniature"]
    for box in garage["miniature"]:
        for axis in range(3):
            assert low[axis] - 1e-6 <= box["bounds"]["min"][axis]
            assert box["bounds"]["max"][axis] <= high[axis] + 1e-6
    assert {"workbench", "printer_1", "cnc_router"} <= {b["name"] for b in garage["miniature"]}
    # A part's leaf says nothing of a site.
    leaf = next(child for child in tree["children"] if child["part_ref"])
    assert "miniature" not in leaf and leaf.get("site_ref") is None
    # ... but where it stands: its shell, its depth, and the turn that faces it outward.
    assert isinstance(leaf["shell"], int) and isinstance(leaf["depth"], int)
    assert len(leaf["turn"]) == 3
    assert garage["turn"] is None and garage["shell"] > leaf["shell"]


def test_reading_the_universe_starts_no_process(monkeypatch):
    """A piece is drawn from boxes the tree carries: no OpenSCAD render on the load."""

    def refused(*args, **kwargs):
        raise AssertionError(f"a process was started to read the universe: {args}")

    monkeypatch.setattr(subprocess, "run", refused)
    monkeypatch.setattr(subprocess, "Popen", refused)
    body = client.get(f"/sites/{UNIVERSE}").json()
    assert body["is_valid"] and "Site: site-garage" in body["scad"]


def test_the_ring_lists_the_universe_among_the_sites_by_the_name_the_page_gives_it():
    ring = client.post(
        "/menu/resolve", json={"context": {"pointing": "canvas"}, "site": "garage"}
    ).json()
    sites = next(o for o in ring["options"] if o["label"] == "Site")
    listed = {cell["action"]: cell["label"] for cell in sites["children"]}
    assert listed["site:apothecary"] == "Apothecary"
    assert {"site:garage", "site:datum_core", "site:theatre"} <= set(listed)
