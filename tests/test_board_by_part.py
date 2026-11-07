"""A node is a board because its part is one (``apothecary.api.is_board``): the boards
library's ``board`` tag decides, for the router's controller as for a printer's
mainboard, and no shape of a node stands in for it."""

from apothecary.api import _assembly_tree
from apothecary.example_hierarchy import create_example_site
from apothecary.hierarchy import Assembly


def _node(tree: dict, path: str) -> dict:
    node = tree
    for name in path.split("."):
        node = next(child for child in node["children"] if child["name"] == name)
    return node


def test_the_garage_s_boards_are_boards_by_their_parts():
    tree = _assembly_tree(create_example_site())
    assert _node(tree, "printer_1.frame_system.mainboard")["board"] is True
    assert _node(tree, "cnc_router.frame_system.controller")["board"] is True
    assert _node(tree, "cnc_router")["board"] is False


def test_an_electrical_leaf_with_no_part_inside_a_machine_is_not_a_board():
    """A board a maker publishes no drawing of is a described part under parts/boards,
    tagged ``board``; a leaf's category and its place say nothing of it."""
    brain = Assembly(name="brain", role="feature", category="electrical")
    box = Assembly(name="box", role="substructure", category="electrical", children=[brain])
    mill = Assembly(name="mill", role="structure", status="idle", children=[box])
    tree = _assembly_tree(Assembly(name="shop", role="site", children=[mill]))
    assert _node(tree, "mill.box.brain")["board"] is False
