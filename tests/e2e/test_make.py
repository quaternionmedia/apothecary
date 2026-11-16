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
        finally:
            http.delete(f"/sites/garage/nodes/{BOARD}/device")
    assert errors == []
