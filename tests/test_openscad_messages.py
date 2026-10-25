"""OpenSCAD's stderr, read into errors and warnings by file and line.

Each sample below is what OpenSCAD 2021.01 and the 2026.09.27 snapshot
printed for the same SCAD, cache and timing report included.
"""

from pathlib import Path

import pytest

from apothecary.projects.parts.openscad_messages import (
    OpenSCADMessage,
    TraceStep,
    parse_openscad_messages,
    place_messages,
)
from apothecary.projects.parts.stl_renderer import get_renderer

# size = 10;
# cube([size, size, 3])
# sphere(2)
SYNTAX = {
    "2021.01": (
        "ERROR: Parser error: syntax error in file syntax.scad, line 5\n"
        "Can't parse file '/home/someone/parts/syntax.scad'!\n\n"
    ),
    "snapshot": (
        "ERROR: Parser error: syntax error in file syntax.scad, line 5\n"
        "Can't parse file '/home/someone/parts/syntax.scad'!\n\n"
    ),
}

# boards/board/board.scad: include <../common.scad> / width = 5; / pcb(width);
# boards/common.scad: module pcb(w) { assert(w > 0, "a board has width"); ... }
# rendered with -D width=-1
IN_AN_INCLUDE = {
    "2021.01": (
        "ERROR: Assertion '(w > 0)' failed: \"a board has width\" in file ../common.scad, line 2\n"
        "TRACE: called by 'assert' in file ../common.scad, line 2\n"
        "TRACE: called by 'pcb' in file board.scad, line 3\n"
        "Geometries in cache: 1\nGeometry cache size in bytes: 0\n"
        "CGAL Polyhedrons in cache: 0\nCGAL cache size in bytes: 0\n"
        "Total rendering time: 0:00:00.000\n"
        "Current top level object is empty.\n"
    ),
    "snapshot": (
        "ERROR: Assertion '(w > 0)' failed: \"a board has width\" in file ../common.scad, line 2\n"
        "TRACE: called by 'assert' in file ../common.scad, line 2\n"
        "TRACE: call of 'pcb(w = -1)' in file ../common.scad, line 1\n"
        "TRACE: called by 'pcb' in file board.scad, line 3\n"
        "Current top level object is empty.\n"
    ),
}

# runtime.scad: include <lib.scad> / echo(foo); / x = 1 / 0; / thing();
WARNED = {
    "2021.01": (
        "WARNING: Ignoring unknown variable 'foo' in file runtime.scad, line 2\n"
        "ECHO: undef\n"
        "WARNING: Ignoring unknown variable 'undefined_var' in file lib.scad, line 2\n"
    ),
    "snapshot": (
        'WARNING: Ignoring unknown variable "foo" in file runtime.scad, line 2\n'
        "ECHO: undef\n"
        'WARNING: Ignoring unknown variable "undefined_var" in file lib.scad, line 2\n'
    ),
}

# badinc.scad: include <nope.scad> / cube(1);
MISSING_INCLUDE = {
    "2021.01": (
        "WARNING: Can't open include file 'nope.scad'.\n"
        "Geometries in cache: 1\nGeometry cache size in bytes: 728\n"
        "CGAL Polyhedrons in cache: 0\nCGAL cache size in bytes: 0\n"
        "Total rendering time: 0:00:00.000\n"
        "   Top level object is a 3D object:\n   Facets:          6\n"
    ),
    "snapshot": (
        "WARNING: Can't find include file 'nope.scad'. in file badinc.scad, line 1\n"
        "Geometries in cache: 1\nGeometry cache size in bytes: 856\n"
        "CGAL Polyhedrons in cache: 0\nCGAL cache size in bytes: 0\n"
        "Total rendering time: 0:00:00.003\n"
        "Top level object is a 3D object (PolySet):\n   Convex:       yes\n"
        "   Facets:         6\nBounding box:\n   Min:  0.00, 0.00, 0.00\n"
        "   Max:  1.00, 1.00, 1.00\n   Size: 1.00, 1.00, 1.00\nCamera:\n"
        "   Translation: 0.00, 0.00, 0.00\n   Rotation:    55.00, 0.00, 25.00\n"
        "   Distance:    140.00\n   FOV:         22.50\n"
    ),
}


@pytest.mark.parametrize("version", ["2021.01", "snapshot"])
def test_a_syntax_error_is_one_error_at_its_line(version):
    assert parse_openscad_messages(SYNTAX[version]) == [
        OpenSCADMessage(
            level="error", message="Parser error: syntax error", file="syntax.scad", line=5
        )
    ]


@pytest.mark.parametrize("version", ["2021.01", "snapshot"])
def test_an_error_in_an_include_carries_the_calls_that_led_there(version):
    error, empty = parse_openscad_messages(IN_AN_INCLUDE[version])
    assert (error.level, error.file, error.line) == ("error", "../common.scad", 2)
    assert error.message == "Assertion '(w > 0)' failed: \"a board has width\""
    # The part's own line is the last call: where a person changes something.
    assert error.trace[-1] == TraceStep(message="called by 'pcb'", file="board.scad", line=3)
    assert empty == OpenSCADMessage(level="error", message="Current top level object is empty.")


def test_the_snapshot_traces_the_module_it_failed_inside():
    error = parse_openscad_messages(IN_AN_INCLUDE["snapshot"])[0]
    assert TraceStep(message="call of 'pcb(w = -1)'", file="../common.scad", line=1) in error.trace


@pytest.mark.parametrize("version", ["2021.01", "snapshot"])
def test_warnings_are_kept_and_echoes_are_not(version):
    messages = parse_openscad_messages(WARNED[version])
    assert [(m.level, m.file, m.line) for m in messages] == [
        ("warning", "runtime.scad", 2),
        ("warning", "lib.scad", 2),
    ]
    assert "foo" in messages[0].message


def test_a_missing_include_has_no_line_in_2021_01_and_one_in_a_snapshot():
    (old,) = parse_openscad_messages(MISSING_INCLUDE["2021.01"])
    (new,) = parse_openscad_messages(MISSING_INCLUDE["snapshot"])
    assert (old.level, old.file, old.line) == ("warning", None, None)
    assert old.message == "Can't open include file 'nope.scad'."
    assert (new.level, new.file, new.line) == ("warning", "badinc.scad", 1)
    assert new.message == "Can't find include file 'nope.scad'."


def test_nothing_is_said_of_a_clean_render():
    assert parse_openscad_messages(MISSING_INCLUDE["snapshot"].split("\n", 1)[1]) == []
    assert parse_openscad_messages("") == parse_openscad_messages(None) == []


class TestPlacing:
    """Files named from the checkout; a line past the end is the file's end."""

    @pytest.fixture
    def board(self, tmp_path):
        (tmp_path / "boards" / "board").mkdir(parents=True)
        common = tmp_path / "boards" / "common.scad"
        common.write_text("module pcb(w) {\n  assert(w > 0);\n  cube([w, 10, 1]);\n}\n")
        board = tmp_path / "boards" / "board" / "board.scad"
        board.write_text("include <../common.scad>\nwidth = 5;\npcb(width);\n")
        return tmp_path, board

    def _show(self, root):
        return lambda path: path.relative_to(root.resolve()).as_posix()

    def test_an_include_is_named_from_the_checkout(self, board):
        root, scad = board
        (placed, _) = place_messages(
            parse_openscad_messages(IN_AN_INCLUDE["2021.01"]), scad.parent, self._show(root)
        )
        assert placed.file == "boards/common.scad"
        assert placed.trace[-1].file == "boards/board/board.scad"

    def test_a_line_past_the_end_of_the_parts_scad_is_its_last_line(self, board):
        root, scad = board
        said = "ERROR: Parser error: syntax error in file board.scad, line 5\n"
        (placed,) = place_messages(
            parse_openscad_messages(said), scad.parent, self._show(root), own=scad
        )
        assert (placed.file, placed.line) == ("boards/board/board.scad", 3)

    def test_a_scratch_file_keeps_its_own_name(self, board):
        root, scad = board
        said = "ERROR: something in file rotate.scad, line 1\n"
        (placed,) = place_messages(parse_openscad_messages(said), scad.parent, self._show(root))
        assert (placed.file, placed.line) == ("rotate.scad", 1)

    def test_with_no_base_a_relative_name_is_not_resolved(self, board):
        root, scad = board
        said = "ERROR: something in file board.scad, line 9\n"
        (placed,) = place_messages(parse_openscad_messages(said), None, self._show(root))
        assert (placed.file, placed.line) == ("board.scad", 9)

    def test_a_file_outside_the_checkout_is_named_by_its_name(self, board, tmp_path_factory):
        root, scad = board
        elsewhere = tmp_path_factory.mktemp("elsewhere") / "lib.scad"
        elsewhere.write_text("x = 1;\n")
        said = f"WARNING: thing in file {elsewhere}, line 1\n"
        (placed,) = place_messages(
            parse_openscad_messages(said),
            scad.parent,
            lambda p: None if root.resolve() not in p.parents else self._show(root)(p),
        )
        assert placed.file == "lib.scad"


@pytest.mark.skipif(not get_renderer().is_available, reason="OpenSCAD not installed")
def test_the_installed_openscad_is_read_by_line(tmp_path: Path):
    scad = tmp_path / "part.scad"
    scad.write_text('w = 5;\nassert(w > 10, "w must exceed 10");\ncube(w);\n')
    result = get_renderer().render_stl(scad, tmp_path / "part.stl")
    assert not result.success
    error = parse_openscad_messages(result.stderr)[0]
    assert (error.level, error.file, error.line) == ("error", "part.scad", 2)
    assert '"w must exceed 10"' in error.message
