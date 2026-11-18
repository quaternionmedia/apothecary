"""Make: a part sent to a machine from wherever a person is looking at it.

A printer's Machine opens with its Print window in front, under it, and its makes
lists the site's pieces and then every part of the apothecary. The part selected, or
the part stepped into, has ⚒ Make in the header, naming the first of every site's
machines that make it -- one whose board is connected first, then this site's:
pressed, it opens that machine's Machine -- in another site, that site first --
chooses the part under makes and slices it there. Nothing is armed, started or sent.

Runs against a server of its own with nothing pinned but where a test pins the
simulated printer (idle on ``/dev/ttyFAKE1``) to printer_1's mainboard, and takes it
back; elsewhere printer_1 is opened as the garage plans it, with no board connected.
No real port is opened. The slicer is the scripted OrcaSlicer of the unit tests
(tests/slicer_helpers.py).
"""

from __future__ import annotations

import re

import httpx
import pytest
import windows
from boards import BOARD, PRINTER
from garage import open_garage, row, select, to_site
from playwright.sync_api import Page, expect
from slicer_helpers import write_fake_orcaslicer

SLICED_MS = 30000
# A piece drawn about the middle of the world: framed.
IN_THE_MIDDLE = """(key) => {
    const v = window.fractalViewer, node = v.renderNodeByKey[key];
    if (!node || !node.world_bounds) return false;
    const b = node.world_bounds;
    const s = v.sceneAt(...b.min.map((m, i) => (m + b.max[i]) / 2)).project(v.camera);
    return Math.abs(s.x) < 0.35 && Math.abs(s.y) < 0.35;
}"""


@pytest.fixture(scope="module")
def url(base_url, start_server, tmp_path_factory):
    """This module's own server, the scripted OrcaSlicer its slicer. ``base_url`` is
    asked for only so that with no server to run against this is skipped, as every
    browser test is."""
    orca = write_fake_orcaslicer(tmp_path_factory.mktemp("orca"))
    return start_server(
        {"APOTHECARY_ORCASLICER": str(orca), "APOTHECARY_SIMULATED_PRINTER": "idle"}
    )


def _machines_known(page: Page) -> None:
    page.wait_for_function(
        "() => window.fractalViewer.machinesHere.some((m) => m.path === 'printer_1')",
        timeout=15000,
    )


@pytest.mark.e2e
def test_a_printer_opens_with_its_print_window_and_makes_any_part(page: Page, url: str):
    errors: list = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    open_garage(page, url, settle=False)
    _machines_known(page)
    assert page.evaluate("() => window.fractalViewer.openMachine('printer_1')") is True
    expect(page.locator(f"{windows.MACHINE} > .machine.kind-printer")).to_be_attached(timeout=15000)
    # Its Print, open and in front, in a stack of its own under the Machine, so the
    # Machine's head stays in view beside it.
    page.wait_for_function("() => window.apothecaryPanels.isShown('machine-print')", timeout=10000)
    assert page.evaluate("() => window.apothecaryPanels.isShown('machine')") is True
    # makes: the garage's pieces, then every part of the apothecary by its name.
    groups = windows.in_machine(page, "#print-part optgroup")
    expect(groups).to_have_count(2, timeout=10000)
    assert [groups.nth(i).get_attribute("label") for i in range(2)] == [
        "in garage",
        "every part of the apothecary",
    ]
    here = windows.in_machine(page, "#print-part optgroup[label='in garage'] option")
    every = windows.in_machine(page, "#print-part optgroup[label^='every'] option")
    assert "footpedal" in here.all_inner_texts()
    assert "calibration_cube" in every.all_inner_texts()
    assert "footpedal" not in every.all_inner_texts()
    # Closed, and the Machine opened again: its Print is back.
    windows.close(page, "machine-print")
    assert page.evaluate("() => window.fractalViewer.openMachine('printer_1')") is True
    page.wait_for_function("() => window.apothecaryPanels.isShown('machine-print')", timeout=10000)
    assert errors == []


@pytest.mark.e2e
def test_make_on_the_part_selected_slices_it_on_this_site_s_printer(page: Page, url: str):
    errors: list = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    open_garage(page, url, settle=False)
    _machines_known(page)
    make = page.locator("#make-here")
    expect(make).to_be_hidden()
    # A board is bought, not made: nothing to make.
    select(page, "esp32_blink")
    expect(make).to_be_hidden()
    # The garage's printer, planned, ahead of the universe's: the router does not cut
    # the footpedal.
    select(page, "footpedal")
    expect(make).to_have_text("⚒ Make footpedal on printer_1", timeout=15000)
    assert page.evaluate("() => window.fractalViewer.makeNow().then((d) => d.said)") == (
        "footpedal goes to printer_1: chosen in its Print window, sliced, then ▶ Print"
        " with control armed"
    )
    page.wait_for_function("() => window.apothecaryPanels.isShown('machine-print')", timeout=10000)
    expect(windows.in_machine(page, "#print-part")).to_have_value("footpedal")
    expect(page.locator("#status")).to_contain_text("kept and chosen", timeout=SLICED_MS)
    expect(windows.in_machine(page, "#print-pick")).to_have_value(re.compile("footpedal"))
    # Nothing armed: ▶ Print is the board's, and there is none.
    expect(windows.in_machine(page, "#print-start")).to_be_disabled()
    # The coupon says how it is cut: the router first.
    select(page, "router_coupon")
    expect(make).to_have_text("⚒ Make router_coupon on cnc_router", timeout=15000)
    assert errors == []


@pytest.mark.e2e
def test_make_on_the_part_stepped_into_takes_it_to_the_printer_whose_board_is_connected(
    page: Page, url: str
):
    """In the universe, the calibration cube stepped into: the banner's ⚒ Make names
    garage's printer_1, whose board is connected, ahead of the universe's own printer,
    which is only planned; pressed, it opens the garage, chooses the cube there by its
    name among every part of the apothecary, and slices it for the board's port."""
    errors: list = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    with httpx.Client(base_url=url, timeout=15.0) as http:
        http.post("/firmware/devices/identify", json={"port": PRINTER}).raise_for_status()
        http.put(
            f"/sites/garage/nodes/{BOARD}/device", json={"identity": PRINTER}
        ).raise_for_status()
        try:
            open_garage(page, url, settle=False)
            to_site(page, "apothecary")
            make = page.locator("#make-here")
            expect(make).to_be_hidden()
            row(page, "calibration_cube").dblclick()
            page.wait_for_function(
                "() => window.fractalViewer.focusPath.join('.') === 'calibration_cube'"
            )
            expect(make).to_have_text(
                "⚒ Make calibration_cube on printer_1 in garage", timeout=15000
            )
            make.click()
            page.wait_for_function(
                "() => window.fractalViewer.siteName === 'garage'", timeout=15000
            )
            page.wait_for_function(
                "() => window.apothecaryPanels.isShown('machine-print')", timeout=10000
            )
            expect(windows.in_machine(page, "#print-part")).to_have_value("calibration_cube")
            expect(page.locator("#status")).to_contain_text("kept and chosen", timeout=SLICED_MS)
            # Landed in the Machine view: the Machine's head beside its Print, each a
            # stack of its own, nothing the garage opened on the way left -- its
            # Procedure -- and the printer framed in the world.
            page.wait_for_function(
                "() => window.apothecaryPanels.state('machine').stack.length === 1",
                timeout=10000,
            )
            assert windows.state(page, "machine-print")["stack"] == ["machine-print"]
            assert windows.state(page, "machine-print")["shown"] is True
            assert windows.state(page, "procedure")["open"] is False
            page.wait_for_function(IN_THE_MIDDLE, arg="printer_1", timeout=5000)
        finally:
            http.delete(f"/sites/garage/nodes/{BOARD}/device")
    assert errors == []


@pytest.mark.e2e
def test_make_opens_the_board_s_machine_though_the_universe_s_boards_answer_late(
    page: Page, url: str
):
    """The universe's scan of its boards still in flight when ⚒ Make opens the garage:
    the garage's boards are asked for themselves, and the universe's answer, coming after
    the garage has loaded, is no answer for it -- printer_1's Machine is its board's,
    not its plan."""
    errors: list = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    held: list = []
    with httpx.Client(base_url=url, timeout=15.0) as http:
        http.post("/firmware/devices/identify", json={"port": PRINTER}).raise_for_status()
        http.put(
            f"/sites/garage/nodes/{BOARD}/device", json={"identity": PRINTER}
        ).raise_for_status()
        try:
            open_garage(page, url, settle=False)
            page.route(
                re.compile(r"/sites/apothecary/devices$"),
                lambda route: held.append(route) if not held else route.continue_(),
            )
            to_site(page, "apothecary")
            page.wait_for_function("() => window.fractalViewer.bindingsInFlight")
            assert len(held) == 1
            row(page, "calibration_cube").dblclick()
            page.wait_for_function(
                "() => window.fractalViewer.focusPath.join('.') === 'calibration_cube'"
            )
            make = page.locator("#make-here")
            expect(make).to_have_text(
                "⚒ Make calibration_cube on printer_1 in garage", timeout=15000
            )
            make.click()
            page.wait_for_function(
                "() => window.fractalViewer.siteName === 'garage'", timeout=15000
            )
            held[0].continue_()
            page.wait_for_function(
                "() => window.apothecaryPanels.isShown('machine-print')", timeout=15000
            )
            opened = page.evaluate(
                "() => { const m = window.fractalViewer.machine;"
                " return m && { port: m.port, plan: !!m.plan }; }"
            )
            assert opened == {"port": PRINTER, "plan": False}
            pinned = page.evaluate(
                "(path) => window.fractalViewer.bindings[path]?.device?.port ?? null", BOARD
            )
            assert pinned == PRINTER
        finally:
            http.delete(f"/sites/garage/nodes/{BOARD}/device")
    assert errors == []


@pytest.mark.e2e
def test_the_part_made_read_is_a_turn_of_the_printers_tuning(page: Page, url: str):
    """The footpedal made on printer_1, then read in its Print window: a row for each
    size of its box, kept as the first turn of printer_1's tuning, which says a box's
    sizes separate no error from another, so Apply is greyed and the next slice takes
    the profile's own walls; Undo turn drops the turn."""
    errors: list = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    open_garage(page, url, settle=False)
    _machines_known(page)
    select(page, "footpedal")
    expect(page.locator("#make-here")).to_have_text(re.compile("on printer_1"), timeout=15000)
    page.locator("#make-here").click()
    expect(page.locator("#status")).to_contain_text("kept and chosen", timeout=SLICED_MS)
    said = windows.in_machine(page, "#print-measure-said")
    expect(said).to_contain_text("of 3 features of its box", timeout=10000)
    record = next(
        r
        for r in page.request.get(f"{url}/slicer/slices").json()
        if r["made"]["name"] == "footpedal"
    )
    x, y, _ = record["size"]
    rows = '#print-measure-plan input[data-feature="{}"]'
    windows.in_machine(page, rows.format("x")).fill(f"{x + 0.2:.3f} {x + 0.22:.3f}")
    windows.in_machine(page, rows.format("y")).fill(f"{y + 0.1:.3f}")
    windows.in_machine(page, "#print-measure-keep").click()
    expect(page.locator("#status")).to_contain_text(
        "turn-1 kept for printer_1: footpedal read at 2 features: no term determined",
        timeout=10000,
    )
    apply = windows.in_machine(page, "#print-tune-apply")
    expect(apply).to_be_disabled()
    expect(apply).to_have_attribute("title", re.compile("turn-1 proposes no change"))
    expect(windows.in_machine(page, "#print-tune-history")).to_contain_text(
        "turn-1, footpedal: no term determined; not separated: contour, foot, scale_x, "
        "scale_y; proposed: nothing"
    )
    # The next slice for printer_1 takes the profile's own walls: nothing was applied.
    windows.in_machine(page, "#print-slice").click()
    expect(page.locator("#status")).to_contain_text("kept and chosen", timeout=SLICED_MS)
    expect(windows.in_machine(page, "#print-slice-said")).not_to_contain_text(
        "xy_contour_compensation -"
    )
    windows.in_machine(page, "#print-tune-undo").click()
    expect(page.locator("#status")).to_contain_text("turn-1 undone", timeout=10000)
    assert errors == []
