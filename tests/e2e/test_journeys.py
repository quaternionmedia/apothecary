"""The journeys (apothecary/journeys.py) on the page, as a person goes through them.

The Make view: the windows a part is made through on a machine laid out together from
⊞ Windows, with printer_1's Machine open and the footpedal chosen -- Site with its own
windows, Selected, Parameters, and the Machine sharing a stack with its Print window,
Print in front, the Machine's sections open before it kept behind them. Greyed while
no Machine is open and the piece chosen has no board.
"""

from __future__ import annotations

import re

import httpx
import pytest
import windows
from boards import PRINTER, wears
from garage import open_garage, status
from garage import select as _select
from playwright.sync_api import Page, expect

MAINBOARD = "printer_1.frame_system.mainboard"
MAKE = ".windows-menu-body .view-item[data-view='make']"


@pytest.fixture(scope="module")
def url(start_server):
    """printer_1's board identified and pinned, as the demo's is."""
    url = start_server({})
    with httpx.Client(base_url=url, timeout=15.0) as http:
        http.post("/firmware/devices/identify", json={"port": PRINTER}).raise_for_status()
        http.put(
            f"/sites/garage/nodes/{MAINBOARD}/device", json={"identity": PRINTER}
        ).raise_for_status()
    return url


@pytest.fixture(autouse=True)
def no_page_errors(page: Page):
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    yield
    assert errors == [], errors


@pytest.mark.e2e
def test_the_make_view_is_greyed_until_a_machine_is_there(page: Page, url: str):
    """The footpedal chosen and no Machine open: Make says what it needs."""
    open_garage(page, url, settle=False)
    _select(page, "footpedal")
    page.locator("#windows-menu > summary").click()
    entry = page.locator(MAKE)
    expect(entry).to_have_class(re.compile(r"\bmissing\b"))
    expect(entry).to_have_attribute("title", re.compile(r"^Not now: .*footpedal"))
    entry.click(timeout=5000)
    said = status(page)
    expect(said).to_contain_text("Make view: ")
    expect(said).to_contain_text("footpedal")
    expect(said).to_have_class(re.compile(r"\berror\b"))
    assert page.evaluate("() => window.fractalViewer.machine") is None


@pytest.mark.e2e
def test_the_make_view_lays_out_the_windows_a_part_is_made_through(page: Page, url: str):
    open_garage(page, url, settle=False)
    wears(page, "printer_1")
    _select(page, "printer_1")
    page.locator("#selected-body .device-section .dev-open").click()
    windows.machine_ready(page, "printer")
    _select(page, "footpedal")
    page.locator("#windows-menu > summary").click()
    entry = page.locator(MAKE)
    expect(entry).not_to_have_class(re.compile(r"\bmissing\b"))
    expect(entry).to_have_text("Make")
    entry.click(timeout=5000)
    expect(page.locator(".windows-menu-body")).to_be_hidden()
    expect(status(page)).to_contain_text("The Make view: its windows laid out together")

    # Print comes in front of the Machine's stack once its card has drawn.
    page.wait_for_function(
        "() => window.apothecaryPanels.state('machine-print').shown", timeout=10000
    )
    stacks = {pid: windows.state(page, pid)["stack"] for pid in ("site", "machine", "selected")}
    assert stacks["site"] == ["site", "problems", "pinned", "jobs", "scad"]
    assert stacks["selected"] == ["selected"]
    assert windows.state(page, "part-parameters")["stack"] == ["part-parameters"]
    assert stacks["machine"][:5] == ["machine", "machine-print", "pictures", "bench", "settings"]
    assert windows.state(page, "machine")["shown"] is False
    assert windows.world_width(page) > page.viewport_size["width"] / 2
