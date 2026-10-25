"""Every focused system the registry names (apothecary/systems.py), in the viewer: one
test each, parameterized over the registry, so a system or a section added there is
held here with no test of its own.

For each system: opened, its main window shows alone and every section is a window
closed until asked for; each section opened from the header's ⊞ Windows shows its part
of the subject; its view, a cell of Panels › Windows, lays out every window of it; and
a reload keeps the sections of a system that lasts and forgets those of one made for
the moment. How each system is opened, and what each section shows, are the two
tables below: a system or a section the registry gains without a line there fails
`test_every_system_and_section_has_a_line_here`, which is where a new one is said.

What the window manager does with any window -- homes, views, memory -- is
test_window_manager.py's; what each system does with its subject is its own tests'.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import httpx
import pytest
import rings
import windows
from playwright.sync_api import Page, expect

from apothecary.systems import SYSTEMS, by_id

PRINTER = "/dev/ttyFAKE1"
RING_MS = 15000


@dataclass(frozen=True)
class Opening:
    """Where a system's subject is, how a person opens it there, and what kind of
    subject it is: a system whose sections are for one kind (a board's Machine) shows
    that kind's alone."""

    system: str
    url: str
    open: Callable[[Page], None]
    kind: str | None = None


def _ring(page: Page, *labels: str) -> None:
    page.locator("#viewer-canvas").click(
        button="right", modifiers=["Control"], position={"x": 40, "y": 40}
    )
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=RING_MS)
    for label in labels:
        wedge = page.locator(f"#ring-overlay .wedge[aria-label='{label}']")
        expect(wedge).to_be_visible(timeout=RING_MS)
        page.keyboard.press(wedge.get_attribute("data-cell"))


UNO = "/dev/ttyFAKE0"

# Each subject a test opens, by case: a system with subjects of more than one kind has a
# case for each.
OPENING = {
    # A part from the library, selected by its address: Selected, its main window,
    # shows it. (Part › Edit asks for the editor, so it opens Parameters too.)
    "part": Opening(
        "part",
        "/viewer/parts/calibration_cube",
        lambda page: page.evaluate("() => window.apothecaryPanels.open('selected')"),
    ),
    # printer_1's board, pinned at the start: a printer's Machine, once the page has
    # read where its boards are pinned.
    "machine-printer": Opening(
        "machine",
        "/viewer/sites/garage",
        lambda page: page.wait_for_function(
            "() => window.fractalViewer.openMachine('printer_1')", timeout=RING_MS
        ),
        kind="printer",
    ),
    # The scripted Uno, pinned nowhere: a devkit's Machine, by its port.
    "machine-devkit": Opening(
        "machine",
        "/viewer/sites/garage",
        lambda page: page.evaluate(f"() => window.fractalViewer.openMachineFor('{UNO}')"),
        kind="devkit",
    ),
    # The Airgap, Panels › Airgap › Airgap.
    "airgap": Opening(
        "airgap", "/viewer/parts/airgap", lambda page: _ring(page, "Panels", "Airgap", "Airgap")
    ),
}


# What a section's window shows once its subject is open: a selector inside it that is
# visible. A printer's Machine shows a devkit's sections as a line saying so.
SHOWS = {
    "part-parameters": "#part-params input",
    "part-scad": ".scad-editor .cm-content",
    "part-variants": "#part-saved",
    "part-history": "#part-history-none",
    "part-readiness": "#part-checklist",
    "machine-status": "#c-hot",
    "machine-temperature": "#chart",
    "machine-print": "#print-start",
    "machine-level": "#level-read",
    "machine-sketch": "#c-sketch",
    "machine-flashing": "#flash-form",
    "machine-log": "#log",
    "airgap-metrics": "[data-airgap='readouts'] .metric",
    "airgap-field": "canvas[data-airgap='mmf']",
    "airgap-gap-map": "canvas[data-airgap='gapmap']",
    "airgap-inductance": "canvas[data-airgap='induct']",
    "airgap-torque": "canvas[data-airgap='energy']",
    "airgap-harmonics": "canvas[data-airgap='spectra']",
    "airgap-run-up": "canvas[data-airgap='dynSpeed']",
    "airgap-orbit": "canvas[data-airgap='dynOrbit']",
    "airgap-vibration": "canvas[data-airgap='dynSpec']",
    "airgap-rig": ".airgap-rig",
    "airgap-sweep": ".airgap-sweep",
}

# A verb on a ring that acts on a section, carried as a person carries it: the ring
# opened on a piece's row (or on the world, for ""), its cells pressed in turn.
VERB = {
    "part": ("calibration_cube", ("Part", "Edit"), "part-parameters"),
    "machine-printer": ("printer_1", ("Device", "Poll"), "machine-status"),
    "airgap": ("", ("Panels", "Airgap", "Sweep"), "airgap-sweep"),
}

CASES = list(OPENING)

# A link to each case's subject: what it opens is the registry's (each section's
# `on_link`), for the subject's kind.
LINK = {
    "part": "/viewer/parts/calibration_cube",
    "machine-printer": f"/firmware/monitor?port={PRINTER}",
    "machine-devkit": f"/firmware/monitor?port={UNO}",
}

# How a case's sections come to have nothing to show, on the page given: a system
# whose sections can be empty has a line here.
EMPTY = {
    # The parts library, nothing selected: no part is being edited.
    "part": (
        "/viewer/sites/parts_library",
        lambda page: page.evaluate("() => window.fractalViewer.deselect()"),
    ),
}


def _sections(case: str):
    """The sections a case's subject has: its system's, those for another kind of
    subject left out."""
    opening = OPENING[case]
    system = by_id(opening.system)
    return system, [s for s in system.sections if s.kind in (None, opening.kind)]


@pytest.fixture(autouse=True)
def no_page_errors(page: Page):
    """Nothing the page runs throws, in any of these tests."""
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    yield
    assert errors == [], errors


@pytest.fixture(scope="module")
def url(start_server):
    url = start_server()
    # The simulated printer identified and pinned to printer_1, so it has a Machine.
    httpx.post(f"{url}/firmware/devices/identify", json={"port": PRINTER}, timeout=15.0)
    r = httpx.put(
        f"{url}/sites/garage/nodes/printer_1/device", json={"identity": PRINTER}, timeout=15.0
    )
    assert r.status_code == 200, r.text
    return url


def _linked(page: Page, case: str) -> list[str]:
    """The windows a link to the case's subject asks for, waited for until open."""
    system, sections = _sections(case)
    linked = [system.window(s.id) for s in sections if s.on_link]
    for window in linked:
        page.wait_for_function(
            "(id) => window.apothecaryPanels.isOpen(id)", arg=window, timeout=RING_MS
        )
    return linked


def _opened(page: Page, url: str, case: str) -> None:
    opening = OPENING[case]
    page.goto(f"{url}{opening.url}")
    _loaded(page)
    if opening.url == LINK.get(case):
        _linked(page, case)  # the link's request answered before the layout is reset
    page.evaluate(
        "() => { localStorage.removeItem('apothecary.layout'); window.apothecaryPanels.reset(); }"
    )
    opening.open(page)
    main = by_id(opening.system).main
    page.wait_for_function("(id) => window.apothecaryPanels.isShown(id)", arg=main, timeout=RING_MS)


def _loaded(page: Page) -> None:
    """The page up, its site's rows drawn: what a person sees before acting. (The
    status line may be saying something else: a Machine the address reopened.)"""
    page.wait_for_function(
        "() => !!window.apothecaryPanels && !!window.fractalViewer", timeout=20000
    )
    expect(page.locator("#contents-list .contents-item").first).to_be_attached(timeout=20000)


@pytest.mark.e2e
def test_every_system_and_section_has_a_line_here():
    """A system the registry gains says how it is opened, and each section what its
    window shows: the two tables above."""
    assert {o.system for o in OPENING.values()} == {system.id for system in SYSTEMS}
    # A system with sections for kinds of subject has a case for each kind.
    for system in SYSTEMS:
        kinds = {s.kind for s in system.sections if s.kind}
        assert kinds <= {o.kind for o in OPENING.values() if o.system == system.id}, system.id
    assert {OPENING[c].system for c in VERB} == {
        system.id for system in SYSTEMS if any(s.verbs for s in system.sections)
    }
    assert set(SHOWS) == {system.window(s.id) for system in SYSTEMS for s in system.sections}
    # A system with sections a link asks for has a link for each kind of its subject.
    for system in SYSTEMS:
        kinds = {s.kind for s in system.sections if s.on_link}
        if kinds:
            linked = {OPENING[c].kind for c in LINK if OPENING[c].system == system.id}
            assert linked and kinds - {None} <= linked, system.id


@pytest.mark.e2e
@pytest.mark.parametrize("case", CASES)
def test_a_system_opens_its_main_window_alone(page: Page, url: str, case: str):
    _opened(page, url, case)
    system, sections = _sections(case)
    for section in sections:
        state = windows.state(page, system.window(section.id))
        assert state is not None and state["open"] is False, (section.id, state)
        assert state["group"] == system.group, section.id
    # A section for another kind of subject is no window of this one.
    for section in system.sections:
        if section not in sections:
            assert windows.state(page, system.window(section.id)) is None, section.id


@pytest.mark.e2e
@pytest.mark.parametrize("case", CASES)
def test_each_section_opened_from_windows_shows_its_part_of_the_subject(
    page: Page, url: str, case: str
):
    _opened(page, url, case)
    system, sections = _sections(case)
    for section in sections:
        window = system.window(section.id)
        windows.from_the_windows_menu(page, window)
        expect(windows.panel(page, window), window).to_be_visible(timeout=RING_MS)
        expect(windows.panel(page, window).locator(SHOWS[window]).first, window).to_be_visible(
            timeout=RING_MS
        )


@pytest.mark.e2e
@pytest.mark.parametrize("case", CASES)
def test_a_systems_view_lays_out_every_window_of_it(page: Page, url: str, case: str):
    _opened(page, url, case)
    system, sections = _sections(case)
    _ring(page, "Panels", "Windows", system.cell)
    expect(page.locator("#status")).to_contain_text(f"The {system.title} view")
    for window in [system.main, *(system.window(s.id) for s in sections)]:
        assert windows.state(page, window)["open"] is True, window
    expect(page.locator(windows.WORLD_HEADER)).to_be_hidden()


@pytest.mark.e2e
@pytest.mark.parametrize("case", CASES)
def test_a_reload_keeps_a_lasting_systems_sections_and_forgets_a_passing_ones(
    page: Page, url: str, case: str
):
    _opened(page, url, case)
    system, sections = _sections(case)
    # A section no link asks for: an address that keeps the subject (a board's Machine,
    # ?machine=) is a link a reload follows, and opens what a link asks for.
    first = system.window(next((s for s in sections if not s.on_link), sections[0]).id)
    windows.from_the_windows_menu(page, first)
    page.wait_for_timeout(400)  # the layout is remembered a moment after it changes
    page.reload()
    _loaded(page)
    state = windows.state(page, first)
    if system.transient:
        # Not remembered: what was open of it is not, whatever the address asks for.
        assert state is None or state["open"] is False
    else:
        # Open again, and showing its part of the subject, not an empty window.
        assert state["open"] is True
        expect(windows.panel(page, first).locator(SHOWS[first]).first).to_be_visible(
            timeout=RING_MS
        )


@pytest.mark.e2e
@pytest.mark.parametrize("case", [c for c in CASES if c in VERB])
def test_a_verb_on_the_ring_opens_the_section_it_acts_on(page: Page, url: str, case: str):
    _opened(page, url, case)
    row, labels, window = VERB[case]
    assert windows.state(page, window)["open"] is False
    if row:
        rings.on_row(page, row, *labels)
    else:
        rings.on_world(page, *labels)
    page.wait_for_function(
        "(id) => window.apothecaryPanels.isOpen(id)", arg=window, timeout=RING_MS
    )


@pytest.mark.e2e
@pytest.mark.parametrize("system", [s.id for s in SYSTEMS if s.transient])
def test_a_view_asked_for_without_its_subject_says_how_to_open_it(
    page: Page, url: str, system: str
):
    """A system whose subject is open only while it is (a board's Machine): its view,
    asked for with none open, lays nothing out and says how to open one."""
    page.goto(f"{url}/viewer/sites/garage")
    _loaded(page)
    s = by_id(system)
    before = windows.state(page, "site")
    _ring(page, "Panels", "Windows", s.cell)
    expect(page.locator("#status")).to_contain_text(f"open {s.title} first ({s.opened_by})")
    assert windows.state(page, "site") == before


@pytest.mark.e2e
@pytest.mark.parametrize("case", list(LINK))
def test_a_link_to_a_subject_opens_what_it_asks_for(page: Page, url: str, case: str):
    """A link is a request: the subject's sections the registry names for a link open,
    the first in front showing its part, and no other."""
    page.goto(f"{url}{LINK[case]}")
    _loaded(page)
    linked = _linked(page, case)
    assert linked, case
    expect(windows.panel(page, linked[0]).locator(SHOWS[linked[0]]).first).to_be_visible(
        timeout=RING_MS
    )
    system, sections = _sections(case)
    for section in sections:
        window = system.window(section.id)
        if window not in linked:
            assert windows.state(page, window)["open"] is False, window


@pytest.mark.e2e
@pytest.mark.parametrize("case", list(EMPTY))
def test_sections_with_nothing_to_show_are_minimised_until_they_have(
    page: Page, url: str, case: str
):
    """Laid out by its view with its subject gone, every section says it is empty and
    its stack is minimised; the subject back, they have their height again."""
    where, emptied = EMPTY[case]
    page.goto(f"{url}{where}")
    _loaded(page)
    system, sections = _sections(case)
    _ring(page, "Panels", "Windows", system.cell)
    emptied(page)
    for section in sections:
        state = windows.state(page, system.window(section.id))
        assert state["empty"] and state["minimised"], (section.id, state)
    # Emptied one by one, a stack keeps the window its view put in front.
    assert windows.state(page, system.window(sections[0].id))["shown"] is True
    opening = OPENING[case]
    page.goto(f"{url}{opening.url}")
    _loaded(page)
    first = _linked(page, case)[0]
    assert windows.state(page, first)["minimised"] is False
    expect(windows.panel(page, first).locator(SHOWS[first]).first).to_be_visible(timeout=RING_MS)
