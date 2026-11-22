"""The journeys' registry (apothecary/journeys.py) and what reads it: each journey's
view, laid out from ⚙ View and the ring's Panels › Windows after the systems'.
That a view lays its windows out on the page is tests/e2e/test_journeys.py's."""

from __future__ import annotations

import json
import re

from apothecary.example_hierarchy import create_example_site
from apothecary.journeys import JOURNEYS, PUTS, by_id, manifest
from apothecary.machine_plans import kind_of_part, kinds_that_make
from apothecary.menu import PANEL_GROUPS, VIEWS
from apothecary.projects.parts.skeleton import ROOT
from apothecary.simulated import DEVKIT
from apothecary.site_names import UNIVERSE
from apothecary.systems import SYSTEMS
from apothecary.universe import create_universe_site
from apothecary.viewer import render_fractal_viewer_page

PAGE = ROOT / "templates" / "fractal_viewer.html.j2"
SYSTEMS_JS = ROOT / "apothecary" / "static" / "systems.js"


def _layout_windows(layout) -> set:
    if isinstance(layout, str):
        return {layout}
    if layout.get("world"):
        return {"world"}
    if "stack" in layout:
        return set(layout["stack"])
    return set().union(*(_layout_windows(child) for child in layout.get("row") or layout["column"]))


def _page_windows() -> set:
    """Every window the page has: the world's, those it registers or marks, and each
    system's, a board's Machine among them."""
    page = PAGE.read_text(encoding="utf-8")
    marked = set(re.findall(r'class="panel-section"[^>]*data-panel="([\w-]+)"', page))
    registered = set(re.findall(r"panels\.register\('([\w-]+)'", page))
    return {"world"} | marked | registered | {w for s in SYSTEMS for w in s.windows()}


def test_each_journey_is_named_once_and_apart_from_the_systems():
    ids = [j.id for j in JOURNEYS]
    assert len(ids) == len(set(ids))
    assert not set(ids) & {s.id for s in SYSTEMS}
    groups = set(PANEL_GROUPS.values()) | {s.group for s in SYSTEMS}
    for journey in JOURNEYS:
        assert re.fullmatch(r"[a-z][a-z0-9-]*", journey.id)
        assert len(journey.cell) <= 12, journey.cell  # a ring label, where it has one
        assert journey.group in groups, journey.group  # a colour the palette has
        assert journey.name and journey.title, journey.id
        # One scheme: what a person does, and to one thing. The title is the verb.
        verb, article, thing = journey.name.partition(" a ")
        assert verb == journey.title and article and " " not in thing, journey.name


def test_the_page_is_taken_to_a_stage_by_verbs_it_has_on_pieces_the_simulated_server_s_site_has():
    """What the tour does to stand on a stage is from the page's own short list, and its
    subjects are pieces of the site each journey names -- the garage, or the universe,
    where every part stands -- each the simulated server's, so the tour opens it from
    any other. What a machine makes, its file and its cabinet may name a part no piece
    stands for, where the machine the journey is staged on is of a kind that makes it:
    the router's 😮, chosen under makes as a person chooses it."""
    garage = create_example_site()  # the simulated server's garage
    universe = create_universe_site()  # every part, and every other site, one piece each
    sites = {garage.name.lower(): garage, UNIVERSE: universe}
    for journey in JOURNEYS:
        assert journey.site in sites, journey.id
        pieces = {child.name for child in sites[journey.site].children}
        machines = [subject for verb, subject in journey.staged_on if verb == "machine"]
        kinds = {kind_of_part(_part_of(sites[journey.site], m)) for m in machines}
        for verb, subject in [*journey.staged_on, *(p for s in journey.steps for p in s.puts)]:
            assert verb in PUTS, (journey.id, verb)
            piece, _, what = subject.partition(":")
            if verb == "pin":
                assert what == DEVKIT  # the simulated server's devkit, which stands unpinned
            made = verb in ("makes", "file", "feedback") and bool(
                kinds & set(kinds_that_make(piece))
            )
            assert piece in pieces or made or (verb == "working" and not piece), (
                journey.id,
                subject,
            )
    page = PAGE.read_text(encoding="utf-8")
    for verb in PUTS:
        assert f"verb === '{verb}'" in page, verb


def _part_of(site, piece: str) -> str:
    """The part a piece of the site is built from, by its name."""
    node = next(child for child in site.children if child.name == piece)
    return node.part_ref


def test_every_window_a_journeys_view_lays_out_is_one_the_page_has():
    known = _page_windows()
    for journey in JOURNEYS:
        named = _layout_windows(journey.view)
        assert named <= known, (journey.id, named - known)
        assert "world" in named and journey.requires in named, journey.id


def test_the_make_view_holds_the_window_set_a_part_is_made_through():
    """The part chosen in Site, its numbers in Parameters, the machine's window and its
    Print window together at the column's foot, Print in front."""
    named = _layout_windows(by_id("make").view)
    assert {"site", "selected", "part-parameters", "machine", "machine-print"} <= named
    column = by_id("make").view["row"][1]["column"]
    assert column[-1]["stack"][:2] == ["machine", "machine-print"]
    assert column[-1]["active"] == "machine-print"


def test_the_ring_has_a_cell_for_the_first_journey_s_view_after_the_systems():
    """Panels › Windows is full, so Print a part's view alone has a cell there; the other
    journeys' views are laid out by the tour alone."""
    assert VIEWS[len(SYSTEMS) :] == (("make", "Print view"),)
    assert [j.id for j in JOURNEYS if j.cell] == ["make"]


def test_the_page_is_given_the_journeys_and_defines_their_views_from_them_alone():
    html = render_fractal_viewer_page(["garage"], "http://127.0.0.1:8000")
    given = re.search(
        r'<script type="application/json" id="apothecary-journeys">(.*?)</script>', html, re.S
    )
    assert given is not None
    assert json.loads(given.group(1)) == manifest()
    page = PAGE.read_text(encoding="utf-8")
    assert "defineJourneyViews(this.panels, JOURNEYS);" in page
    module = SYSTEMS_JS.read_text(encoding="utf-8")
    assert "export function defineJourneyViews(" in module
    assert "panels.defineView(journey.id," in module


def test_each_step_brings_forward_and_owns_windows_its_journeys_view_lays_out():
    """A step's windows are its journey's: entering it brings forward windows the view
    laid out, and a window chosen says one step at most."""
    for journey in JOURNEYS:
        named = _layout_windows(journey.view)
        ids = [s.id for s in journey.steps]
        assert journey.steps and len(ids) == len(set(ids)), journey.id
        owned = [w for s in journey.steps for w in s.owns]
        assert len(owned) == len(set(owned)), journey.id
        for step in journey.steps:
            assert re.fullmatch(r"[a-z][a-z0-9-]*", step.id)
            assert 0 < len(step.label) <= 8, step.label  # in the Tour box, after its number
            assert step.hint and step.forward, step.id
            assert set(step.forward) | set(step.owns) <= named, (journey.id, step.id)


def test_make_a_thing_goes_from_the_part_to_the_job_and_back_to_the_printer():
    make = by_id("make")
    assert make.name == "Print a part"
    assert [s.label for s in make.steps] == ["Choose", "Shape", "Slice", "See", "Print", "Measure"]
    assert make.steps[0].forward[0] == "site"
    assert make.steps[2].forward == ("machine-print",)
    assert [s.id for s in make.steps if s.draws] == ["see"]
    assert make.steps[4].owns == ("machine", "jobs")
    # Print names ▶ Print, a button of the Print window: that tab is the one in front,
    # not the Machine's beside it. The stage's part is under makes wherever it is entered.
    assert make.steps[4].forward[0] == "machine-print"
    assert ("makes", "footpedal") in make.staged_on
    # The piece made, read in its part's cabinet, Part › Feedback, as a turn of the
    # printer's tuning: a file of it kept, whose plan (or box) gives the rows to read, and
    # the cabinet opened on the part.
    assert make.steps[-1].forward == ("part-feedback",)
    assert make.steps[-1].owns == ("part-feedback",)
    assert make.steps[-1].puts == (("file", "footpedal"), ("feedback", "footpedal"))
    assert by_id("cut").steps[-1].forward == ("part-feedback",)
    assert make.steps[-1].shown_by == (
        "46-a-printer-tuned-from-its-prints.md",
        "50-a-printer-tuned-from-what-it-shows.md",
        "55-a-printed-piece-checked-against-its-design.md",
    )


def test_print_a_part_and_cut_a_part_name_the_same_act_the_same_way():
    """The two are one path through two machines: the stages that are the same act --
    Choose, See, Measure -- carry the same id and label in both, the stage that starts
    the job is named for its machine's ▶ button and brings that window and Jobs forward,
    and what is one machine's alone (Shape and Slice, Toolpath and Needs) is the rest."""
    make, cut = by_id("make"), by_id("cut")
    printed = {s.id: s for s in make.steps}
    cuts = {s.id: s for s in cut.steps}
    assert set(printed) & set(cuts) == {"choose", "see", "measure"}
    for shared in ("choose", "see", "measure"):
        assert printed[shared].label == cuts[shared].label, shared
        assert printed[shared].forward == cuts[shared].forward, shared
    assert [s.id for s in (make.steps[0], make.steps[-1])] == ["choose", "measure"]
    assert [s.id for s in (cut.steps[0], cut.steps[-1])] == ["choose", "measure"]
    for journey, starts in ((make, "print"), (cut, "cut")):
        stage = journey.steps[-2]
        assert (stage.id, stage.label) == (starts, journey.title), journey.id
        assert f"▶ {journey.title}" in stage.hint, journey.id
        assert stage.forward == ("machine-print", "jobs"), journey.id
        assert stage.owns == ("machine", "jobs"), journey.id
    # One line each in the Tour box: neither Measure is many times the other's length.
    lengths = sorted(len(j.steps[-1].hint) for j in (make, cut))
    assert lengths[1] < 1.5 * lengths[0], lengths


def test_calibrate_a_router_goes_from_the_face_chosen_to_the_allowance_kept():
    """The router's 😮, a part no piece of the garage stands for, chosen under makes in its
    Cut window as a person chooses it; its toolpath written and drawn, saying what to
    measure; cut as Cut a part cuts; measured in its cabinet; and the allowance kept, which
    the next toolpath takes. It follows Cut a part in the chain."""
    calibrate = by_id("calibrate")
    assert (calibrate.name, calibrate.title, calibrate.group) == (
        "Calibrate a router",
        "Calibrate",
        "Machine",
    )
    ids = [j.id for j in JOURNEYS]
    assert ids.index("calibrate") == ids.index("cut") + 1
    assert calibrate.staged_on == (("machine", "cnc_router"), ("makes", "router_emoji"))
    assert [(s.id, s.label) for s in calibrate.steps] == [
        ("choose", "Choose"),
        ("toolpath", "Toolpath"),
        ("cut", "Cut"),
        ("measure", "Measure"),
        ("kept", "Kept"),
    ]
    steps = {s.id: s for s in calibrate.steps}
    assert "😮" in steps["choose"].hint and "makes" in steps["choose"].hint
    assert [s.id for s in calibrate.steps if s.draws] == ["toolpath"]
    for named in ("an eye", "the mouth", "the face"):
        assert named in steps["toolpath"].hint, named
    # The cut is Cut a part's act, said the same way and in the same windows.
    cut = {s.id: s for s in by_id("cut").steps}["cut"]
    assert steps["cut"].hint.startswith(cut.hint)
    assert (steps["cut"].forward, steps["cut"].owns) == (cut.forward, cut.owns)
    assert steps["measure"].puts == (("file", "router_emoji"), ("feedback", "router_emoji"))
    assert steps["measure"].forward == ("part-feedback",)
    assert "tool_allowance measured" in steps["kept"].hint
    # Each stage has its step of the page the browser walks it on.
    for step in calibrate.steps:
        assert f"56-a-router-calibrated-by-a-face.md#{calibrate.steps.index(step) + 1}" in (
            step.shown_by
        ), step.id


def test_run_a_site_is_the_site_brought_up_through_its_procedure_then_watched():
    """One journey where Drive a machine hands on: the procedure, the family's members
    and the hub's audit, then the Workspace on the site and on one machine's hour, in a
    view that holds each half's windows -- the Workspace behind the Procedure in the tall
    stack, so each is in front in its own stages. No board's Machine is in it."""
    run = by_id("run")
    assert (run.name, run.title, run.group, run.requires) == (
        "Run a site",
        "Run",
        "Family",
        "procedure",
    )
    assert [j.id for j in JOURNEYS].index("run") == [j.id for j in JOURNEYS].index("hands") + 1
    assert [(s.id, s.label) for s in run.steps] == [
        ("steps", "Steps"),
        ("members", "Members"),
        ("audit", "Audit"),
        ("space", "Space"),
        ("hour", "Hour"),
    ]
    assert run.steps[0].forward == (run.requires,)
    named = _layout_windows(run.view)
    assert {
        "world",
        "procedure",
        "family-members",
        "family-deliveries",
        "jobs",
        "working",
        "site",
        "selected",
    } <= named
    assert not any(w == "machine" or w.startswith("machine-") for w in named)
    tall = run.view["row"][1]
    assert tall["stack"] == ["procedure", "working"] and tall["active"] == "procedure"
    assert run.steps[3].puts == (("working", ""),)
    assert run.steps[4].puts == (("fit", "printer_1"), ("working", "printer_1"))


def test_join_a_hose_stands_in_the_universe_on_the_port_and_the_adapter():
    """Two ends, then the adapter between them, then whether it is ready: the port part
    and the adapter are the universe's leaves, which is where the tour opens it."""
    join = by_id("join")
    assert (join.name, join.site) == ("Join a hose", UNIVERSE)
    assert [s.label for s in join.steps] == ["Ends", "Adapter", "Ready"]
    assert join.steps[0].puts == (("edit", "dust_port"),)
    # The Adapter stage's words are "⇄ Adapter again at the other end's numbers": ⇄ Adapter
    # is a port's button (the adapter has no round end of its own), so the port stays chosen;
    # the adapter is chosen by pressing it, and is what Ready is about.
    assert join.steps[1].puts == (("edit", "dust_port"),)
    assert join.steps[2].puts == (("edit", "hose_adapter"),)
    assert JOURNEYS[-1] is join  # last in the chain: no other journey's place moves


def test_design_s_ready_says_readiness_is_the_part_s_and_layout_valid_the_site_s():
    """The header's Layout valid and Problems are the site's layout; Ready's words say
    so, so a part not ready beside a valid layout reads as two things."""
    ready = next(s for s in by_id("design").steps if s.id == "ready")
    assert "Readiness" in ready.hint and "Layout valid" in ready.hint, ready.hint
    assert ready.forward[0] == "part-readiness"


def test_only_flash_a_board_s_bench_stands_without_its_journey_s_staging():
    """A board missing stops Pin, Flash and Hear, which need it, and not the Bench,
    which builds a sketch with none."""
    alone = [(j.id, s.id) for j in JOURNEYS for s in j.steps if s.stands_alone]
    assert alone == [("board", "bench")]
    assert all("stands_alone" in s for j in manifest() for s in j["steps"])
