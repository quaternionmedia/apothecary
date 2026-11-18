"""What a part is built from: SCAD include/use between registered parts, the sites that
nest one part in another, and a part's own list, which wins."""

import json

from apothecary.composition import nested_parts, part_children, scad_uses
from apothecary.example_hierarchy import create_example_site
from apothecary.hierarchy import Assembly
from apothecary.orbitals import composition_depths
from apothecary.projects.parts.base import BasePart
from apothecary.projects.parts.described import part_from_sidecar
from apothecary.projects.parts.skeleton import ROOT
from apothecary.projects.registry import load_parts


def _scad(path, text=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _parts(tmp_path, files, **explicit):
    """Registered parts named for the folders of ``files``, each {name: scad text}."""
    out = {}
    for name, text in files.items():
        scad = _scad(tmp_path / name / f"{name}.scad", text)
        out[name] = BasePart(name=name, source_file=scad, parts=explicit.get(name))
    return out


def test_an_include_of_another_registered_part_is_its_child(tmp_path):
    parts = _parts(tmp_path, {"base": "cube(1);", "arm": "include <../base/base.scad>\n"})
    assert part_children(parts) == {"base": [], "arm": ["base"]}


def test_use_counts_as_include_and_a_space_before_the_bracket_is_optional(tmp_path):
    parts = _parts(
        tmp_path,
        {"a": "", "b": "", "c": "use<../a/a.scad>\ninclude<../b/b.scad>\n"},
    )
    assert part_children(parts)["c"] == ["a", "b"]


def test_a_file_that_is_no_part_adds_no_depth_but_is_followed_to_one_that_is(tmp_path):
    _scad(tmp_path / "common.scad", "include <base/base.scad>\n")
    parts = _parts(
        tmp_path,
        {"base": "", "board": "include <../common.scad>\n", "plain": "include <../common.scad>\n"},
    )
    assert part_children(parts)["board"] == ["base"]
    shared = _scad(tmp_path / "board_common.scad", "cube(1);")
    assert shared.exists()
    alone = _parts(tmp_path / "x", {"board": "include <../board_common.scad>\n"})
    _scad(tmp_path / "x" / "board_common.scad", "cube(1);")
    assert part_children(alone) == {"board": []}


def test_an_include_that_resolves_to_nothing_registered_is_dropped(tmp_path):
    parts = _parts(tmp_path, {"a": "include <V-Slot.scad>\ninclude <MCAD/gears.scad>\n"})
    assert part_children(parts) == {"a": []}


def test_a_circular_include_ends_and_a_part_is_never_its_own_child(tmp_path):
    _scad(tmp_path / "x.scad", "include <y.scad>\n")
    _scad(tmp_path / "y.scad", "include <x.scad>\ninclude <a/a.scad>\n")
    parts = _parts(tmp_path, {"a": "include <../x.scad>\n"})
    assert scad_uses(parts["a"].source_file, {parts["a"].source_file.resolve(): "a"}) == set()
    assert part_children(parts) == {"a": []}


def test_nesting_in_a_site_makes_the_held_part_a_child_at_any_depth():
    site = Assembly(
        name="s",
        children=[
            Assembly(
                name="printer",
                part_ref="printer",
                children=[
                    Assembly(name="box", children=[Assembly(name="board", part_ref="board")])
                ],
            ),
            Assembly(name="lone", part_ref="lone"),
        ],
    )
    held = nested_parts(site)
    assert held["printer"] == {"board"}
    assert held["lone"] == set() and held["board"] == set()


def test_nesting_counts_only_registered_parts(tmp_path):
    parts = _parts(tmp_path, {"printer": "", "board": ""})
    site = Assembly(
        name="s",
        children=[
            Assembly(
                name="printer",
                part_ref="printer",
                children=[
                    Assembly(name="b", part_ref="board"),
                    Assembly(name="g", part_ref="ghost"),
                ],
            )
        ],
    )
    assert part_children(parts, [site])["printer"] == ["board"]


def test_a_parts_own_list_wins_over_the_inference_and_an_empty_one_is_an_answer(tmp_path):
    files = {"a": "", "b": "", "c": "include <../a/a.scad>\n", "d": "include <../a/a.scad>\n"}
    parts = _parts(tmp_path, files, c=["b"], d=[])
    assert part_children(parts)["c"] == ["b"]
    assert part_children(parts)["d"] == []


def test_a_list_names_only_registered_parts_and_not_itself(tmp_path):
    parts = _parts(tmp_path, {"a": "", "b": ""}, a=["a", "b", "ghost"])
    assert part_children(parts)["a"] == ["b"]


def test_part_json_says_parts(tmp_path):
    scad = _scad(tmp_path / "p" / "p.scad", "cube(1);")
    (tmp_path / "p" / "part.json").write_text(json.dumps({"parts": ["x", "y"]}))
    assert part_from_sidecar(scad).parts == ["x", "y"]
    (tmp_path / "p" / "part.json").write_text(json.dumps({}))
    assert part_from_sidecar(scad).parts is None


def test_the_registered_parts_depths():
    """The depth each real part has: two shells, and sites outside them."""
    parts = {item.name: part for item, part in load_parts(ROOT).parts}
    sites = [create_example_site()]
    children = part_children(parts, sites)
    depths = composition_depths(children)
    assert set(depths) == set(parts)
    # webcam_* use webcam.scad; star_cookiecutter uses parametric_star; the Ender 3
    # holds its board in the garage
    for mount in ("webcam_ceiling_mount", "webcam_desk_stand", "webcam_clamp_arm"):
        assert children[mount] == ["webcam"] and depths[mount] == 1
    assert children["star_cookiecutter"] == ["parametric_star"]
    assert children["ender3"] == ["creality_v422"] and depths["ender3"] == 1
    # board_common.scad is shared code and no part: boards are built from nothing
    for board in ("arduino_uno", "teensy_40", "raspberry_pi_4", "esp32_devkitc"):
        assert depths[board] == 0
    # the mount subtracts v_slot's own `extrusion` profile at v_slot's `tolerance`; its
    # include names the library's upstream file, which resolves to nothing, so the
    # relation is the part's own to declare
    assert parts["matboard_cutter_mount"].parts == ["v_slot"]
    assert children["matboard_cutter_mount"] == ["v_slot"] and depths["matboard_cutter_mount"] == 1
    assert {n for n, p in parts.items() if p.parts is not None} == {"matboard_cutter_mount"}
