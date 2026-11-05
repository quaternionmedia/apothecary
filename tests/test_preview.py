"""A toolpath, previewed: one core instantiated for a print and for a cut.

The first section runs the same invariants over both instantiations, each on a file of
its own kind: a sliced print's G-code and the router coupon's toolpath. Then what the
core reads, whichever machine it is for; then what each process makes of it; then the
core held to the two things that already said what a file does, the toolpath's writer
and the slicer's bounds; then the route.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apothecary import jobs
from apothecary.api import app
from apothecary.cam import toolpath
from apothecary.firmware import devices, gcode, grbl
from apothecary.preview import ADDITIVE, BY_MACHINE, SUBTRACTIVE, for_machine, of, reach
from apothecary.preview.moves import Comment, Dwell, Move, read, split_comments
from apothecary.projects.parts.router_coupon import DEFAULT as COUPON
from apothecary.projects.parts.router_coupon import Params

# As OrcaSlicer writes a print: its start, a mark per layer, walls that lay material, and
# the head parked at the end.
PRINT = """; EXECUTABLE_BLOCK_START
G90
M83
M140 S60
M104 S220
G28
G1 Z0.28 F240
;LAYER_CHANGE
G1 Z0.2 F600
G1 X105 Y105 F3000
G1 X115 Y105 E0.5
G1 X115 Y115 E0.5
G4 P500
G1 X105 Y115 E0.5
;LAYER_CHANGE
G1 Z0.4 F600
G1 X105 Y105 F3000
G1 X115 Y105 E0.5
G1 X5 Y176 F3000 ; present print
M104 S0
M84 X Y E
""".splitlines()

CUT = toolpath.write(COUPON.cuts(), "router_coupon")

BOTH = pytest.mark.parametrize(
    ("process", "lines"),
    [(ADDITIVE, PRINT), (SUBTRACTIVE, CUT.lines)],
    ids=["additive-on-a-printer", "subtractive-on-a-router"],
)


# --- the core, with each instantiation ---------------------------------------------------


@BOTH
def test_every_move_is_one_segment_of_a_kind_the_process_names(process, lines):
    p = of(lines, process)
    assert p.machine == process.machine and p.word == process.word
    assert p.kinds == list(process.kinds)
    assert len(p.points) == 6 * len(p.kind_of) == 6 * p.moves > 0
    assert set(p.kind_of) <= set(range(len(p.kinds)))
    assert p.within_mm == 0


@BOTH
def test_the_groups_cover_every_segment_in_order(process, lines):
    p = of(lines, process)
    assert p.groups, "a file that moves has a group"
    at = 0
    for group in p.groups:
        assert group.first == at and group.count > 0 and group.sent >= 0
        at += group.count
    assert at == len(p.kind_of)
    assert [g.sent for g in p.groups] == sorted(g.sent for g in p.groups)


@BOTH
def test_a_segment_starts_where_the_last_one_ended(process, lines):
    p = of(lines, process)
    for i in range(1, len(p.kind_of)):
        assert p.points[i * 6 : i * 6 + 3] == p.points[(i - 1) * 6 + 3 : (i - 1) * 6 + 6]


@BOTH
def test_what_it_adds_up_to_is_each_kind_s_own(process, lines):
    p = of(lines, process)
    assert set(p.length_mm) == set(p.bounds) <= set(p.kinds)
    for box in p.bounds.values():
        assert all(low <= high for low, high in zip(box.min, box.max, strict=True))
    assert p.time_s > 0
    assert p.lines == sum(1 for ln in lines if ln.strip() and ln.strip()[0] not in ";(")


@BOTH
def test_it_is_the_same_each_time(process, lines):
    assert of(lines, process) == of(lines, process)


@BOTH
def test_reach_is_what_the_preview_says_of_the_part_s_kind(process, lines):
    assert reach(lines, process) == of(lines, process).bounds[process.kinds[0]]


@BOTH
def test_a_file_that_moves_nothing_is_an_empty_preview(process, lines):
    p = of(["; nothing here", "M104 S0", "G4 P1"], process)
    assert p.points == [] and p.groups == [] and p.moves == 0 and p.bounds == {}
    assert reach(["M104 S0"], process) is None


@BOTH
def test_a_long_file_is_thinned_and_its_sums_stay_the_file_s(process, lines):
    """More moves than the page is given: short runs of one kind become one, the distance
    said, every group still drawn; what it adds up to is read before any of that."""
    # A long zigzag of tiny moves of the part's kind, after the file's own.
    if process is ADDITIVE:
        tail = [f"G1 X{100 + (i % 2) * 0.01:.3f} Y{100 + i * 0.01:.3f} E0.01" for i in range(4000)]
    else:
        tail = [
            "G1 Z-1 F300",
            *[f"G1 X{i * 0.01:.3f} Y{(i % 2) * 0.01:.3f} F800" for i in range(4000)],
        ]
    long = [*lines, *tail]
    whole = of(long, process, max_segments=10**9)
    thin = of(long, process, max_segments=500)
    assert whole.within_mm == 0 and thin.within_mm > 0
    assert len(thin.kind_of) <= 500 < len(whole.kind_of)
    assert thin.moves == whole.moves and thin.length_mm == whole.length_mm
    assert thin.bounds == whole.bounds and thin.time_s == whole.time_s
    assert [g.label for g in thin.groups] == [g.label for g in whole.groups]
    assert sum(g.count for g in thin.groups) == len(thin.kind_of)
    # The path still ends where the file does.
    assert thin.points[-3:] == whole.points[-3:]


def test_the_core_is_one_only_the_meaning_differs():
    """The same lines give the same segments under either process: what differs is what
    each says a move is, and how moves group."""
    lines = ["G21 G90", "G0 X10 Y10", "G1 Z-1 F300", "G1 X20 F800", "G0 Z5"]
    additive, subtractive = of(lines, ADDITIVE), of(lines, SUBTRACTIVE)
    assert additive.points == subtractive.points and additive.moves == subtractive.moves == 4
    assert [additive.kinds[k] for k in additive.kind_of] == ["travel"] * 4
    assert [subtractive.kinds[k] for k in subtractive.kind_of] == [
        "rapid",
        "plunge",
        "cut",
        "rapid",
    ]


def test_every_kind_of_machine_that_runs_a_file_has_a_process():
    assert set(BY_MACHINE) == set(jobs.machine_kinds())
    with pytest.raises(KeyError):
        for_machine("loom")


# --- the interpreter, whichever machine it is for ----------------------------------------


def _moves(*lines):
    return [e for e in read(lines) if isinstance(e, Move)]


def _ends(*lines):
    return [m.end for m in _moves(*lines)]


def test_absolute_and_relative_moves():
    assert _ends("G90", "G1 X10 Y10", "G91", "G1 X5", "G90", "G1 X1") == [
        (10.0, 10.0, 0.0),
        (15.0, 10.0, 0.0),
        (1.0, 10.0, 0.0),
    ]


def test_a_motion_word_carries_over_and_words_need_no_spaces():
    assert _ends("G1X10Y5F800", "X20", "G0 Z5", "X1") == [
        (10.0, 5.0, 0.0),
        (20.0, 5.0, 0.0),
        (20.0, 5.0, 5.0),
        (1.0, 5.0, 5.0),
    ]
    assert [m.rapid for m in _moves("G00 X1", "G01 X2 F100", "X3")] == [True, False, False]


def test_inches_are_read_in_millimetres():
    assert _ends("G20", "G1 X1 F10", "G21", "G1 X2") == [(25.4, 0.0, 0.0), (2.0, 0.0, 0.0)]
    assert _moves("G20", "G1 X1 F10")[0].feed == 254.0


def test_g92_moves_the_file_s_zero_and_not_the_tool():
    assert _ends("G1 X10", "G92 X0", "G1 X5") == [(10.0, 0.0, 0.0), (15.0, 0.0, 0.0)]


def test_a_move_to_where_the_tool_is_is_no_move():
    assert _ends("G1 X10", "G1 X10", "G1 Y0") == [(10.0, 0.0, 0.0)]


def test_a_machine_word_s_letters_are_not_a_move():
    assert _moves("M104 S200", "M84 X Y E", "M106 S255", "G4 P100", "G10 L20 P1 X5") == []


def test_what_a_file_cannot_place_is_not_drawn():
    """Homing, probing and machine coordinates end where the file does not say."""
    lines = ("G1 X10", "G28", "$H", "G38.2 Z-5 F100", "G53 G0 Z0", "G1 X20")
    ends = _ends(*lines)
    assert ends[0] == (10.0, 0.0, 0.0) and len(ends) == 2 and ends[-1][0] == 20.0
    # Each still counts among the lines a job would send.
    assert _moves(*lines)[-1].sent == 5


def test_extrusion_absolute_and_relative():
    pushed = [m.extruded for m in _moves("M82", "G92 E0", "G1 X1 E1", "G1 X2 E1", "G1 X3 E0.5")]
    assert pushed == [1.0, 0.0, -0.5]
    assert [m.extruded for m in _moves("M83", "G1 X1 E1", "G1 X2 E1")] == [1.0, 1.0]
    # G91 makes E relative too, and G90 absolute, unless M82 or M83 said otherwise after.
    assert [m.extruded for m in _moves("G91", "G1 X1 E1", "G1 X1 E1")] == [1.0, 1.0]


def test_an_arc_is_written_as_chords_that_end_where_it_does():
    # A quarter circle from (10, 0) round the origin, anticlockwise: I and J from the start.
    moves = _moves("G1 X10 F100", "G3 X0 Y10 I-10 J0")[1:]
    assert len(moves) == 9
    assert moves[-1].end == (0.0, 10.0, 0.0)
    for m in moves:
        assert abs((m.end[0] ** 2 + m.end[1] ** 2) ** 0.5 - 10) < 1e-6
    # Clockwise the long way round is the other three quarters, and R says the same arc.
    assert len(_moves("G1 X10 F100", "G2 X0 Y10 I-10 J0")[1:]) == 27
    by_radius = _moves("G1 X10 F100", "G3 X0 Y10 R10")[1:]
    assert by_radius[-1].end == (0.0, 10.0, 0.0) and len(by_radius) == 9
    # A whole circle, its start its end.
    assert len(_moves("G1 X10 F100", "G2 X10 Y0 I-10 J0")[1:]) == 36
    # In another plane it is a straight line: this reads the XY plane's alone.
    assert _ends("G18", "G2 X5 Z5 I5") == [(5.0, 0.0, 5.0)]


def test_a_line_is_read_as_a_job_sends_it():
    """A job and a preview must count the same lines, so they split a comment alike."""
    assert split_comments("(a; b) G1 X1 ; c (d)") == ("G1 X1", ["a; b", "c (d)"])
    for line in [*PRINT, *CUT.lines, "G1 X1 (mid) Y2", "; only", "(only)", "", "g1 x1"]:
        assert split_comments(line)[0] == gcode.strip_gcode(line), line


def test_comments_and_pauses_are_said_in_order():
    events = list(read(["; a", "G1 X1 F100 (b)", "G4 P2", "(c) ; d"]))
    kinds = [(type(e).__name__, getattr(e, "text", None)) for e in events]
    assert kinds == [
        ("Comment", "a"),
        ("Comment", "b"),
        ("Move", None),
        ("Dwell", None),
        ("Comment", "c"),
        ("Comment", "d"),
    ]
    assert isinstance(events[0], Comment) and isinstance(events[3], Dwell)
    assert events[3].p == 2


# --- additive ---------------------------------------------------------------------------


def test_a_print_lays_material_and_travels_between():
    p = of(PRINT, ADDITIVE)
    said = [p.kinds[k] for k in p.kind_of]
    assert said.count("extrude") == 4 and said.count("travel") == 6
    assert p.length_mm["extrude"] == 40.0
    assert p.bounds["extrude"].min == [105.0, 105.0, 0.2]
    assert p.bounds["extrude"].max == [115.0, 115.0, 0.4]


def test_a_print_s_layers_are_its_slicer_s_marks():
    p = of(PRINT, ADDITIVE)
    assert [(g.label, g.z) for g in p.groups] == [
        ("before the first layer", None),
        ("layer 1", 0.2),
        ("layer 2", 0.4),
    ]
    cura = ["G1 X1 F100", ";LAYER:0", "G1 Z0.2 F100", "G1 X5 E1", ";LAYER:1", "G1 Z0.4", "G1 X1 E1"]
    assert [g.label for g in of(cura, ADDITIVE).groups][1:] == ["layer 1", "layer 2"]


def test_a_file_with_no_marks_starts_a_layer_at_each_higher_z_that_lays_material():
    lines = ["M83", "G1 Z0.2 F100", "G1 X5 E1", "G1 X9 E1", "G1 Z5", "G1 X1", "G1 Z0.4", "G1 X5 E1"]
    p = of(lines, ADDITIVE)
    assert [(g.label, g.z) for g in p.groups] == [
        ("before the first layer", None),
        ("layer 1", 0.2),
        ("layer 2", 0.4),
    ]


def test_a_spiral_that_a_slicer_marks_once_is_one_layer():
    lines = [
        ";LAYER_CHANGE",
        "G1 Z0.2 F100",
        *[f"G1 X{i} Z{0.2 + i / 100:.2f} E0.1" for i in range(1, 9)],
    ]
    assert [g.label for g in of(lines, ADDITIVE).groups] == ["layer 1"]


def test_a_print_s_time_reads_marlin_s_dwell():
    """P in milliseconds, S in seconds."""
    assert of(["G4 P500", "G4 S2"], ADDITIVE).time_s == 2.5
    assert of(["G1 X100 F600"], ADDITIVE).time_s == 10.0


# --- subtractive ------------------------------------------------------------------------


def test_a_cut_is_rapids_plunges_and_cuts():
    p = of(CUT.lines, SUBTRACTIVE)
    said = [p.kinds[k] for k in p.kind_of]
    assert {"rapid", "plunge", "cut"} == set(said)
    assert p.bounds["plunge"].min[2] == -10.5
    assert p.bounds["rapid"].max[2] == COUPON.cuts().safe_z


def test_a_cut_s_passes_are_the_toolpath_s_own_names():
    p = of(CUT.lines, SUBTRACTIVE)
    assert p.groups[0].label == "before the first pass"
    pocket = p.groups[1]
    assert pocket.label == "op 1/4 pass 1/2: pocket 40 x 30 at 30,35 to z -2" and pocket.z == -2.0
    named = [g for g in p.groups if g.label.startswith("op ")]
    assert len(named) == sum(o.passes for o in CUT.operations)
    assert named[-1].label.startswith("op 4/4 pass 6/6: outline") and named[-1].z == -10.5


def test_a_cam_post_s_file_starts_a_pass_at_each_new_depth():
    """It names no operations: each plunge to another depth is a pass."""
    lines = [
        "G0 X1 Y1",
        "G1 Z-1 F100",
        "G1 X9 F800",
        "G0 Z5",
        "G0 X0",
        "G1 Z-1",
        "G1 X9",
        "G1 Z-2",
        "G1 X0",
    ]
    p = of(lines, SUBTRACTIVE)
    assert [(g.label, g.z) for g in p.groups] == [
        ("before the first pass", None),
        ("depth -1", -1.0),
        ("depth -2", -2.0),
    ]


def test_a_cut_s_time_reads_grbl_s_dwell_and_goes_at_its_rapid():
    """P in seconds, and a G0 at the machine's own rapid, whatever the last feed said."""
    assert of(["G4 P2"], SUBTRACTIVE).time_s == 2.0
    assert of(["G1 F100", "G0 X4000"], SUBTRACTIVE).time_s == 60.0
    assert SUBTRACTIVE.rapid == grbl.FEED_MAX


# --- held to what already said what a file does ----------------------------------------------


def test_the_core_agrees_with_the_toolpath_that_wrote_the_file():
    """Two readings of one file, neither knowing the other: what apothecary.cam counted
    as it wrote each move, and what the interpreter reads back from the text."""
    p = of(toolpath.text(CUT).splitlines(), SUBTRACTIVE)
    assert round(p.length_mm["cut"] + p.length_mm["plunge"], 1) == CUT.length_mm
    assert p.length_mm["rapid"] == CUT.rapid_mm
    assert p.time_s == CUT.time_s
    # The writer's bounds are the tool's edge; the preview's its centre, a radius inside.
    r = COUPON.cuts().tool.diameter / 2
    assert CUT.bounds is not None
    assert p.bounds["cut"].min[:2] == [v + r for v in CUT.bounds.min[:2]]
    assert p.bounds["cut"].max[:2] == [v - r for v in CUT.bounds.max[:2]]


def test_a_design_change_shows_in_the_preview():
    """The hole the tool can only plunge is bored in circles once it is wider."""
    plunged = of(CUT.lines, SUBTRACTIVE)
    wider = of(toolpath.write(COUPON.cuts(Params(hole_diameter=8).model_dump())).lines, SUBTRACTIVE)
    assert wider.moves > plunged.moves
    assert wider.length_mm["cut"] > plunged.length_mm["cut"]


def test_the_slicer_s_bounds_are_the_core_s(tmp_path):
    from apothecary.slicer.service import gcode_bounds

    path = tmp_path / "print.gcode"
    path.write_text("\n".join(PRINT))
    found = gcode_bounds(path)
    assert found is not None
    assert (found.min, found.max) == ([105.0, 105.0, 0.2], [115.0, 115.0, 0.4])
    assert gcode_bounds(tmp_path / "no-such.gcode") is None


# --- the route ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("machine", "lines", "word"),
    [("printer", PRINT, "layer"), ("router", CUT.lines, "pass")],
    ids=["a-printer-s-file", "a-router-s-file"],
)
def test_the_route_previews_a_kept_file_for_a_machine(tmp_path, monkeypatch, machine, lines, word):
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    kept = devices.save_print_file(f"{machine}.gcode", "\n".join(lines).encode())
    c = TestClient(app)
    answer = c.get(f"/firmware/printers/prints/{kept.id}/preview", params={"machine": machine})
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["machine"] == machine and body["word"] == word and body["groups"]
    assert body["lines"] == kept.lines
    # A kept file is read once for a machine.
    again = c.get(f"/firmware/printers/prints/{kept.id}/preview", params={"machine": machine})
    assert again.json() == body


def test_the_route_refuses_what_it_cannot_preview(tmp_path, monkeypatch):
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    kept = devices.save_print_file("a.gcode", b"G1 X1 F100\n")
    c = TestClient(app)
    assert c.get("/firmware/printers/prints/nope/preview").status_code == 404
    refused = c.get(f"/firmware/printers/prints/{kept.id}/preview", params={"machine": "loom"})
    assert refused.status_code == 422 and "loom" in refused.json()["detail"]
    # A file forgotten is no longer previewed, though it was read before.
    assert c.get(f"/firmware/printers/prints/{kept.id}/preview").status_code == 200
    devices.delete_print_file(kept.id)
    assert c.get(f"/firmware/printers/prints/{kept.id}/preview").status_code == 404
