"""The focused systems' registry (apothecary/systems.py) and what reads it.

Each system is one entry, and the ring, the page and the widgets read that entry
rather than keeping a list of their own: the ring's view cells, the windows the
page registers and its views, and each widget's sections.
"""

from __future__ import annotations

import json
import re

from apothecary.menu import VIEWS
from apothecary.projects.parts.skeleton import ROOT
from apothecary.systems import SYSTEMS, by_id, manifest
from apothecary.viewer import render_fractal_viewer_page

PAGE = ROOT / "templates" / "fractal_viewer.html.j2"
SYSTEMS_JS = ROOT / "apothecary" / "static" / "systems.js"
# The windows panels.js makes of its own (the world's), and those the page makes
# for the moment: a board's Machine, the pad, the SCAD editor popped out, a rig's
# lighting.
OWN = {"world"}
FOR_THE_MOMENT = {"machine", "control", "scad-editor", "lighting"}


def _layout_windows(layout) -> set:
    if isinstance(layout, str):
        return {layout}
    if layout.get("world"):
        return {"world"}
    if "stack" in layout:
        return set(layout["stack"])
    return set().union(*(_layout_windows(child) for child in layout.get("row") or layout["column"]))


def _page_windows() -> set:
    page = PAGE.read_text(encoding="utf-8")
    marked = set(re.findall(r'class="panel-section"[^>]*data-panel="([\w-]+)"', page))
    registered = set(re.findall(r"panels\.register\('([\w-]+)'", page))
    return OWN | marked | registered | {w for s in SYSTEMS for w in s.windows()}


def test_each_system_and_window_is_named_once():
    ids = [s.id for s in SYSTEMS]
    assert len(ids) == len(set(ids))
    windows = [w for s in SYSTEMS for w in s.windows()]
    assert len(windows) == len(set(windows))
    for system in SYSTEMS:
        assert all(re.fullmatch(r"[a-z][a-z0-9-]*", sec.id) for sec in system.sections)
        assert all(sec.title and sec.holds for sec in system.sections)
        assert 0 < len(system.cell) <= 12, system.cell  # a ring label


def test_the_ring_has_a_cell_for_each_systems_view_in_the_registrys_order():
    assert VIEWS == tuple((s.id, s.cell) for s in SYSTEMS)


def test_every_window_a_view_lays_out_is_one_the_page_has():
    known = _page_windows()
    for system in SYSTEMS:
        named = _layout_windows(system.view)
        assert named <= known, (system.id, named - known)
        # A view lays out its own main window and every section of its own.
        assert set(system.windows()) <= named | FOR_THE_MOMENT, system.id


def test_the_page_is_given_the_registry_as_it_is_rendered():
    html = render_fractal_viewer_page(["garage"], "http://127.0.0.1:8000")
    given = re.search(
        r'<script type="application/json" id="apothecary-systems">(.*?)</script>', html, re.S
    )
    assert given is not None
    assert json.loads(given.group(1)) == manifest()
    assert manifest()[-1]["sections"][0]["window"] == f"{by_id('airgap').id}-metrics"


def test_the_page_registers_systems_from_the_registry_alone():
    page = PAGE.read_text(encoding="utf-8")
    assert (
        "const SYSTEMS = JSON.parse(document.getElementById('apothecary-systems').textContent);"
        in page
    )
    assert "known: knownWindows(SYSTEMS)" in page
    assert "this.systems = mountSystems(this.panels, SYSTEMS, {" in page
    # No view and no system window is made by hand beside the registry's.
    assert "defineView(" not in page
    for system in SYSTEMS:
        for section in system.sections:
            assert f"register('{system.window(section.id)}'" not in page
    module = SYSTEMS_JS.read_text(encoding="utf-8")
    assert "export function knownWindows(systems)" in module
    assert "export function mountSystems(panels, systems, hooks = {})" in module
    assert "panels.defineView(system.id, { title: system.title, layout: system.view });" in module
