"""A machine whose pinned board is not connected: printer_1 pinned to a bridge by its serial
number, A106ZTEU, with no such board plugged in. Its Machine opens as its plan, and says
how far the board got -- not on USB -- and what to try; once a board it is pinned to
comes up, its own Machine opens in the plan's place.

Runs against a server of its own; its serial engine is the simulated one, which reads no
USB, so what is plugged into the computer running the test is never read. The board
that comes up is the simulated printer on /dev/ttyFAKE1, pinned in the other's place.
"""

from __future__ import annotations

import httpx
import pytest
import windows
from boards import BOARD, PRINTER
from garage import open_garage
from playwright.sync_api import Page, expect

NOT_HERE = "A106ZTEU"


@pytest.fixture(scope="module")
def url(start_server):
    return start_server()


def _pin(url: str, identity: str) -> None:
    r = httpx.put(
        f"{url}/sites/garage/nodes/{BOARD}/device", json={"identity": identity}, timeout=10
    )
    r.raise_for_status()


@pytest.mark.e2e
def test_a_printer_whose_board_is_not_found_says_what_to_try_and_opens_when_it_comes(
    page: Page, url: str
):
    errors: list = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    _pin(url, NOT_HERE)
    open_garage(page, url, settle=False)
    page.wait_for_function(
        "() => window.fractalViewer.bindingsLoaded"
        " && window.fractalViewer.machinesHere.some((m) => m.path === 'printer_1')",
        timeout=15000,
    )
    assert page.evaluate("() => window.fractalViewer.openMachine('printer_1')") is True
    expect(windows.in_machine(page, "#ident")).to_contain_text("not connected")
    card = windows.in_machine(page, "#c-missing-card")
    expect(card).to_be_visible(timeout=10000)
    expect(card).to_contain_text(f"pinned at {BOARD}")
    # Named by what is known of it: a serial number never seen on USB, that alone.
    expect(card.locator(".expected b")).to_have_text(NOT_HERE)
    checks = card.locator(".check")
    expect(checks).to_have_count(4)
    expect(checks.nth(0)).to_have_class("check off")
    expect(checks.nth(0)).to_contain_text(f"On USB — nothing on USB is {NOT_HERE}")
    expect(checks.nth(1)).to_have_class("check after")
    expect(card.locator(".todo")).to_contain_text(
        "Switch the printer on and seat its USB cable at both ends"
    )
    expect(card.locator(".plugged")).to_contain_text("Plugged in now:")
    expect(card.locator("#missing-said")).to_contain_text("checked again every few seconds")
    # The board comes up: the pin now names one the scan finds, and its own Machine
    # opens in the plan's place, by itself.
    _pin(url, PRINTER)
    page.wait_for_function(
        "(port) => { const m = window.fractalViewer.machine; return !!(m && !m.plan && m.port === port); }",
        arg=PRINTER,
        timeout=20000,
    )
    expect(windows.in_machine(page, "#ident")).not_to_contain_text("not connected")
    assert not errors, errors
