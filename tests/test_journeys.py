"""The journeys' registry (apothecary/journeys.py) and what reads it: each journey's
view, laid out from ⊞ Windows and the ring's Panels › Windows after the systems'.
That a view lays its windows out on the page is tests/e2e/test_journeys.py's."""

from __future__ import annotations

import json
import re

from apothecary.demo import DEVKIT
from apothecary.example_hierarchy import create_example_site
from apothecary.journeys import JOURNEYS, PUTS, by_id, manifest
from apothecary.menu import PANEL_GROUPS, VIEWS
from apothecary.projects.parts.skeleton import ROOT
from apothecary.systems import SYSTEMS
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


def test_a_stage_is_put_on_by_verbs_the_page_has_on_pieces_the_demo_s_site_has():
    """What the tour does to stand on a stage is from the page's own short list, and its
    subjects are pieces of the demo's site."""
    pieces = {child.name for child in create_example_site().children}  # the demo's garage
    for journey in JOURNEYS:
        for verb, subject in [*journey.staged_on, *(p for s in journey.steps for p in s.puts)]:
            assert verb in PUTS, (journey.id, verb)
            piece, _, what = subject.partition(":")
            if verb == "pin":
                assert what == DEVKIT  # the demo's devkit, which stands unpinned
            assert piece in pieces or (verb == "working" and not piece), (journey.id, subject)
    page = PAGE.read_text(encoding="utf-8")
    for verb in PUTS:
        assert f"verb === '{verb}'" in page, verb


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
    """Panels › Windows is full, so Make a thing's view alone has a cell there; the other
    journeys are entered from ⊞ Windows › Journeys and the tour."""
    assert VIEWS[len(SYSTEMS) :] == (("make", "Make view"),)
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
            assert 0 < len(step.label) <= 8, step.label  # on the rail, after its number
            assert step.hint and step.forward, step.id
            assert set(step.forward) | set(step.owns) <= named, (journey.id, step.id)


def test_make_a_thing_goes_from_the_part_to_the_job():
    make = by_id("make")
    assert make.name == "Make a thing"
    assert [s.label for s in make.steps] == ["Choose", "Shape", "Slice", "See", "Print"]
    assert make.steps[0].forward[0] == "site"
    assert make.steps[2].forward == ("machine-print",)
    assert [s.id for s in make.steps if s.draws] == ["see"]
    assert make.steps[-1].owns == ("machine", "jobs")
