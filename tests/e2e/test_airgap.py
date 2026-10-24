"""The Airgap: the airgap part as a field, torque and dynamics model, as a panel in
front of the world, following the part's text in the SCAD editor.

The panel is a window, a tab beside Pictures, closed until asked for; its verbs are
cells of the canvas ring's Panels › Airgap, and each of its sections (Metrics, the gap
field, the torque, the run, the rig, the sweep...) is a window of its own, opened from
the header's ⊞ Windows or a stack's +, all of them together by the Airgap view
(Panels › Windows › Airgap view). Opened, it reads the part's own SCAD and computes;
with the part in the editor (Part › Edit) it follows every edit of the text, and a
preset chosen in it is written into the text, which the editor then checks and renders
as any edit. The metrics it says are one document, ``airgap/metrics/1``, which
``POST /airgap/metrics/validate`` reads back.

Runs against a server of its own from the conftest's ``start_server``, with this
machine's OpenSCAD; nothing here reaches the network.
"""

from __future__ import annotations

import functools

import pytest
import windows
from playwright.sync_api import Page, expect
from rings import RING_MS, on_world
from rings import press as _press

# The airgap's world, clear of its pieces.
_canvas_ring = functools.partial(on_world, at=(60, 60))


PART = "airgap"
PANEL = ".panel[data-panel='airgap']"
SECTIONS = windows.AIRGAP_SECTIONS


def _section(page: Page, sid: str):
    """An Airgap section's window: its body."""
    return windows.panel(page, f"airgap-{sid}")


@pytest.fixture(scope="module")
def url(start_server):
    return start_server({})


def _open(page: Page, url: str) -> None:
    page.goto(f"{url}/viewer/sites/parts_library")
    expect(page.locator("#status")).to_contain_text("Loaded", timeout=20000)
    page.evaluate("() => localStorage.removeItem('apothecary.layout')")
    page.wait_for_function(
        "() => !!window.apothecaryRing && !!window.apothecaryPanels", timeout=15000
    )


def _part_ring(page: Page, *labels: str) -> None:
    page.locator(f"#contents-list .contents-item[data-path='{PART}']").click(
        button="right", modifiers=["Control"]
    )
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=RING_MS)
    _press(page, *labels)


def _metrics(page: Page) -> dict:
    page.wait_for_function(
        "() => window.apothecaryAirgap && window.apothecaryAirgap.metrics()"
        " && window.apothecaryAirgap.metrics().groups.length === 4",
        timeout=30000,
    )
    return page.evaluate("() => window.apothecaryAirgap.metrics()")


def _values(page: Page) -> dict:
    return page.evaluate("() => window.apothecaryAirgap.values()")


@pytest.mark.e2e
def test_the_airgap_is_a_window_that_computes_the_parts_own_text(page: Page, url: str):
    """Registered at start and closed until asked for; Panels › Airgap › Airgap opens it
    as a tab beside Pictures, where it reads the part's own SCAD and says its figures as
    the metrics document, which the server reads back."""
    _open(page, url)
    expect(windows.tab(page, "airgap")).to_have_count(0)
    assert windows.state(page, "airgap")["open"] is False
    _canvas_ring(page, "Panels", "Airgap", "Airgap")
    expect(page.locator(PANEL)).to_be_visible(timeout=2000)
    assert windows.state(page, "airgap")["stack"] == ["pictures", "bench", "settings", "airgap"]
    doc = _metrics(page)
    assert doc["schema"] == "airgap/metrics/1"
    assert [g["id"] for g in doc["groups"]] == ["geometry", "windings", "field", "dynamics"]
    values = _values(page)
    assert values["r0"] == 30 and values["stator_teeth_n"] == 12 and values["topology"] == "tooth"
    flat = {f"{g['id']}.{m['key']}": m["value"] for g in doc["groups"] for m in g["metrics"]}
    assert flat["windings.conductors"] == 24 and flat["geometry.stator_cover"] == 100
    assert isinstance(flat["field.mean_torque"], float)
    expect(page.locator(PANEL).locator(".airgap-source")).to_have_text("the panel's own values")
    # The document the panel says is one the server accepts, and renders.
    read = page.request.post(f"{url}/airgap/metrics/validate?format=md", data=doc)
    assert read.ok and read.text().startswith("# Airgap metrics")
    # The metrics are a window of their own, opened from ⊞ Windows beside the Airgap: a
    # grouped readout, each addressed by group and key.
    expect(windows.tab(page, "airgap-metrics")).to_have_count(0)
    windows.from_the_windows_menu(page, "airgap-metrics")
    assert windows.state(page, "airgap-metrics")["stack"][-2:] == ["airgap", "airgap-metrics"]
    expect(
        _section(page, "metrics").locator(".metric[data-key='field.mean_torque'] dd")
    ).to_contain_text("N·m")


@pytest.mark.e2e
def test_the_panel_follows_the_editors_text_and_a_preset_is_written_into_it(page: Page, url: str):
    """Part › Edit on the airgap part, and its SCAD window from ⊞ Windows: the panel
    follows the text as it is typed -- a
    tooth count changed in the text is the panel's within the frame -- and a preset
    chosen in the panel is written into the text, where the editor's check sees it;
    the panel says it is following."""
    _open(page, url)
    page.evaluate("() => window.apothecaryPanels.open('airgap')")
    _metrics(page)
    _part_ring(page, "Part", "Edit")
    windows.from_the_windows_menu(page, "part-scad")
    expect(page.locator(".scad-editor .cm-content")).to_be_visible(timeout=20000)
    page.wait_for_function(
        "() => window.apothecaryAirgap.values().stator_teeth_n === 12 && "
        "document.querySelector('.airgap-source').classList.contains('following')",
        timeout=15000,
    )
    # A line of the text changed: the panel's figure follows within the frame.
    page.evaluate(
        """() => { const ed = window.fractalViewer.scadEditor;
            ed.replaceText(ed.text().replace('stator_teeth_n = 12;', 'stator_teeth_n = 15;')); }"""
    )
    page.wait_for_function(
        "() => window.apothecaryAirgap.values().stator_teeth_n === 15", timeout=5000
    )
    doc = _metrics(page)
    flat = {f"{g['id']}.{m['key']}": m["value"] for g in doc["groups"] for m in g["metrics"]}
    assert flat["windings.conductors"] == 30  # fifteen tooth coils, two stations each
    # A preset chosen in the panel goes into the text, not into the panel alone.
    page.locator(PANEL).locator(".airgap-preset").select_option("srm")
    page.wait_for_function(
        "() => window.fractalViewer.scadEditor.text().includes('stator_teeth_n = 6;')"
        " && window.fractalViewer.scadEditor.text().includes('rotor_teeth_n = 4;')",
        timeout=5000,
    )
    page.wait_for_function(
        "() => window.apothecaryAirgap.values().stator_teeth_n === 6", timeout=5000
    )
    expect(page.locator("#status")).to_contain_text("written into the editor", timeout=5000)
    # The text the editor holds is what OpenSCAD checks: six teeth, four poles, it reads.
    page.wait_for_function(
        "() => (window.fractalViewer.scadEditor?.marked ?? []).every((m) => m.severity !== 'error')",
        timeout=15000,
    )


@pytest.mark.e2e
def test_the_verbs_are_cells_of_panels_airgap(page: Page, url: str):
    """Panels › Airgap on the canvas ring: Play spins the rotor and pauses it, Sweep maps
    the metric the sweep line names, Reset puts the panel back on the part's own text;
    each is also the panel's button of the same name, which the ring annotates."""
    _open(page, url)
    _canvas_ring(page, "Panels", "Airgap", "Play")
    expect(page.locator(PANEL)).to_be_visible(timeout=5000)
    _metrics(page)
    expect(page.locator(PANEL).locator(".airgap-play")).to_have_attribute("aria-label", "Pause")
    expect(page.locator(PANEL).locator(".airgap-play")).to_have_attribute("data-address", "476")
    _canvas_ring(page, "Panels", "Airgap", "Play")
    expect(page.locator(PANEL).locator(".airgap-play")).to_have_attribute("aria-label", "Play")
    # Sweep opens the Sweep window, whose default line maps mean torque over the
    # stator's teeth and the rotor's ribbon.
    expect(windows.tab(page, "airgap-sweep")).to_have_count(0)
    _canvas_ring(page, "Panels", "Airgap", "Sweep")
    sweep = _section(page, "sweep")
    expect(sweep).to_be_visible(timeout=5000)
    expect(sweep.locator(".airgap-sweep")).to_have_value(
        "stator_teeth_n 3..24 × rotor_rib_k 0..12 → mean_torque"
    )
    expect(sweep.locator("[data-airgap='swMsg']")).to_contain_text("cells", timeout=60000)
    # A sweep line that names nothing is refused with the shape it wants.
    sweep.locator(".airgap-sweep").fill("nothing here")
    sweep.locator(".airgap-sweep").press("Enter")
    expect(sweep.locator("[data-airgap='swMsg']")).to_contain_text("x from..to")
    # The rig, one document in a window of its own: an unknown setting is refused, a
    # value past its range clamped and said.
    windows.from_the_windows_menu(page, "airgap-rig")
    rig = _section(page, "rig")
    rig.locator(".airgap-rig").fill('{"loadT": 9999, "bogus": 1}')
    rig.locator(".airgap-rig").press("Tab")
    expect(rig.locator("[data-airgap='rigMsg']")).to_contain_text("unknown setting bogus")
    expect(rig.locator("[data-airgap='rigMsg']")).to_contain_text("loadT: 0 to 500")
    _canvas_ring(page, "Panels", "Airgap", "Reset")
    expect(page.locator("#status")).to_contain_text("reset to the part's own text", timeout=5000)
    expect(rig.locator("[data-airgap='rigMsg']")).to_have_text("")


@pytest.mark.e2e
def test_the_airgap_view_lays_out_every_section_and_is_remembered(page: Page, url: str):
    """Panels › Windows › Airgap view: the Airgap, each of its sections in a window and
    the world among them, every section drawn at its window's size; a reload finds them
    where they were, and Reset layout puts the page's own layout back, the sections
    closed."""
    _open(page, url)
    _canvas_ring(page, "Panels", "Windows", "Airgap view")
    expect(page.locator("#status")).to_contain_text("The Airgap view")
    _metrics(page)
    stacks = {sid: windows.state(page, f"airgap-{sid}")["stack"] for sid in SECTIONS}
    assert stacks["metrics"] == ["airgap-metrics", "airgap-rig", "airgap-sweep", "selected"]
    assert stacks["field"] == ["airgap-field", "airgap-gap-map"]
    assert stacks["torque"] == ["airgap-torque", "airgap-inductance", "airgap-harmonics"]
    assert stacks["run-up"] == ["airgap-run-up", "airgap-orbit", "airgap-vibration"]
    assert windows.state(page, "airgap")["stack"] == ["airgap"]
    expect(page.locator(windows.WORLD_HEADER)).to_be_hidden()
    # The section in front of each stack draws its picture across its window.
    for sid, canvas in (("field", "mmf"), ("torque", "energy"), ("run-up", "dynSpeed")):
        drawn = _section(page, sid).locator(f"canvas[data-airgap='{canvas}']")
        expect(drawn).to_be_visible()
        assert drawn.bounding_box()["height"] > 150
    page.wait_for_timeout(400)  # the layout is remembered a moment after it changes
    page.reload()
    expect(page.locator("#status")).to_contain_text("Loaded", timeout=20000)
    expect(_section(page, "field").locator("canvas[data-airgap='mmf']")).to_be_visible(
        timeout=15000
    )
    assert windows.state(page, "airgap-run-up")["stack"] == stacks["run-up"]
    _canvas_ring(page, "Panels", "Windows", "Reset layout")
    expect(page.locator("#status")).to_contain_text("The page's own layout again")
    assert not any(windows.state(page, f"airgap-{sid}")["open"] for sid in SECTIONS)
