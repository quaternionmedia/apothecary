"""A machine renamed in the page: printer_1's Name in Selected typed over and Enter, the
site drawn again with it at its new name and selected there, its board still pinned to
it, and the name typed back (templates/fractal_viewer.html.j2 renameMachine,
apothecary/renames.py; docs/firmware.md, A machine renamed).

Runs against ``apothecary serve --simulated``, started as a person starts it, on a state
folder of its own: the rename moves what that folder keeps under printer_1, and no other
test's server sees it. Nothing is armed or sent to a board."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import windows
from garage import open_garage
from playwright.sync_api import Page, expect
from simulated_process import guarded_env, start_simulated, still_folder, stop


@pytest.fixture(scope="module")
def simulated(base_url):
    folder = still_folder("rename-a-machine")
    env = guarded_env(folder)
    url, proc = start_simulated(folder, env)
    yield {"url": url, "touched": Path(env["APOTHECARY_TEST_SERIAL_GUARD"])}
    stop(proc)


def _pins(http: httpx.Client) -> set:
    """The garage's nodes a board is pinned to by hand."""
    rows = http.get("/sites/garage/devices").json()["bindings"]
    return {r["path"] for r in rows if r.get("binding_source") == "manual"}


def _rename(page: Page, name: str) -> None:
    field = windows.panel(page, "selected").locator("#name-input")
    expect(field).to_be_visible(timeout=10000)
    field.fill(name)
    field.press("Enter")


@pytest.mark.e2e
def test_a_machine_renamed_in_selected_keeps_its_board(page: Page, simulated):
    url = simulated["url"]
    http = httpx.Client(base_url=url, timeout=15.0)
    open_garage(page, url)
    page.locator("#contents-list .contents-item[data-path='printer_1']").click()
    windows.show(page, "selected")
    field = windows.panel(page, "selected").locator("#name-input")
    expect(field).to_have_value("printer_1")

    # A name with a dot is no node's: refused, and printer_1 stays.
    _rename(page, "big.ender")
    expect(page.locator("#status")).to_contain_text("printer_1 not renamed: ", timeout=10000)
    expect(field).to_have_value("printer_1")

    _rename(page, "big_ender")
    expect(page.locator("#status")).to_contain_text("printer_1 is big_ender now", timeout=15000)
    expect(page.locator("#status")).to_contain_text(
        "the board pinned to big_ender.frame_system.mainboard"
    )
    row = page.locator("#contents-list .contents-item[data-path='big_ender']")
    expect(row).to_be_visible(timeout=10000)
    expect(page.locator("#contents-list .contents-item[data-path='printer_1']")).to_have_count(0)
    expect(windows.panel(page, "selected").locator("#name-input")).to_have_value("big_ender")
    assert "big_ender.frame_system.mainboard" in _pins(http)
    assert http.get("/sites/garage/machines/big_ender").status_code == 200

    # The ring's Panels › Machine › Rename is the same field; typed back, printer_1 again.
    _rename(page, "printer_1")
    expect(page.locator("#status")).to_contain_text("big_ender is printer_1 now", timeout=15000)
    expect(page.locator("#contents-list .contents-item[data-path='printer_1']")).to_be_visible()
    assert "printer_1.frame_system.mainboard" in _pins(http)

    # Nothing left armed, and no real port touched.
    assert http.get("/firmware/printers/armed").json() == {"armed": {}}
    touched = simulated["touched"]
    assert not touched.exists() or not touched.read_text().strip()
