"""The universe (apothecary/universe.py), a prototype: every registered part a leaf
Assembly node under one Site, and every other registered site one piece of it, drawn
in miniature from its top-level pieces' extents.
"""

import subprocess

import pytest
from fastapi.testclient import TestClient

from apothecary import api
from apothecary.hierarchy import Assembly, LayoutReport, Site, Structure
from apothecary.models.bounds import BoundingBox3D
from apothecary.models.vectors import Vector3D
from apothecary.projects.parts.skeleton import ROOT
from apothecary.projects.registry import load_parts, scan_projects
from apothecary.site_names import UNIVERSE
from apothecary.site_store import SiteStore
from apothecary.universe import (
    CELL_PITCH,
    GRID_COLUMNS,
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
    return api._site_store.others()


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
    universe = api._site_store.get(UNIVERSE)
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


def test_leaves_are_arranged_on_a_non_overlapping_grid():
    leaves = _leaves(create_universe_site(_others()))
    positions = {(leaf.position.x, leaf.position.y) for leaf in leaves}
    # every leaf got a distinct grid slot -- no two parts stacked at the same spot
    assert len(positions) == len(leaves)
    for leaf in leaves:
        assert leaf.position.x % CELL_PITCH == 0
        assert leaf.position.y % CELL_PITCH == 0
        assert 0 <= leaf.position.x < GRID_COLUMNS * CELL_PITCH
        assert leaf.position.y >= 0


def test_validate_universe_is_always_valid():
    report = validate_universe(create_universe_site(_others()))
    assert report.is_valid
    assert report.violations == []


# --- the other sites, one piece each -------------------------------------------------------


def test_every_other_site_is_one_piece_in_a_cell_of_its_own_named_for_it():
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
    # Each in a cell of the sites' rows, in front of the parts', and no two in one.
    cells = {(piece.position.x, piece.position.y) for piece in pieces}
    assert len(cells) == len(pieces)
    for piece in pieces:
        assert piece.position.x % CELL_PITCH == 0 and piece.position.y % CELL_PITCH == 0
        assert piece.position.y < 0
        assert piece.footprint.width <= PIECE_SPAN + 1e-6
        assert piece.footprint.height <= PIECE_SPAN + 1e-6


def test_the_universe_does_not_hold_itself():
    assert UNIVERSE in api._site_store.names()
    assert UNIVERSE not in api._site_store.others()
    universe = api._site_store.get(UNIVERSE)
    assert UNIVERSE not in {piece.site_ref for piece in _pieces(universe)}
    assert {piece.site_ref for piece in _pieces(universe)} == set(api._site_store.names()) - {
        UNIVERSE
    }


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
    bench_at = store.get("all").children[0].position

    store.add("attic", _bench, lambda _site: LayoutReport())
    pieces = _pieces(store.get("all"))
    assert [p.site_ref for p in pieces] == ["attic", "bench"]
    # The piece that was there keeps its cell; the new one takes a free one.
    assert pieces[1].position == bench_at
    assert (pieces[0].position.x, pieces[0].position.y) != (bench_at.x, bench_at.y)
    parts = len(_leaves(store.get("all")))

    store.remove("attic")
    assert [p.site_ref for p in _pieces(store.get("all"))] == ["bench"]
    assert len(_leaves(store.get("all"))) == parts


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


def test_a_piece_keeps_the_place_it_was_moved_to():
    store = _store()
    _pieces(store.get("all"))[0].position = Vector3D(x=900, y=-600, z=0)
    assert _pieces(store.get("all"))[0].position == Vector3D(x=900, y=-600, z=0)


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
    real = real_size(api._site_store.get("garage"))
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
