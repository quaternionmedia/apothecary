"""Making a part on a machine, from wherever a person is looking at it.

A printer's Machine opens with its Print window in front, under it, and its makes
lists the site's pieces and then every part of the apothecary.

Runs against a server of its own with nothing pinned: printer_1 is opened as the garage
plans it, with no board connected. No real port is opened.
"""

from __future__ import annotations

import pytest
import windows
from garage import open_garage
from playwright.sync_api import Page, expect


@pytest.fixture(scope="module")
def url(base_url, start_server):
    """This module's own server. ``base_url`` is asked for only so that with no server
    to run against this is skipped, as every browser test is."""
    return start_server({})


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
