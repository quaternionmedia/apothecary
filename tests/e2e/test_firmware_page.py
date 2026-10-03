"""End-to-end test for the firmware page (templates/firmware.html.j2).

The test server runs the scripted arduino-cli (tests/firmware_helpers.py):
version 9.9.9, an Uno on /dev/ttyFAKE0 and an unnamed board on /dev/ttyFAKE1,
which the simulated serial engine answers as a Marlin printer mid-print.
"""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
def test_firmware_page_loads_and_reports_toolchain(page: Page, base_url: str):
    page.goto(f"{base_url}/firmware")
    expect(page).to_have_title("Apothecary Firmware")
    expect(page.locator(".toolbar h1")).to_contain_text("Apothecary")

    expect(page.locator("#status-pill")).to_have_text("arduino-cli 9.9.9", timeout=10000)

    # The repo's own sketches are listed; picking one fills its firmware.json default FQBN.
    expect(page.locator("#sketches li.selected")).to_be_visible()
    page.locator("#sketches li[data-name='footpedal']").click()
    expect(page.locator("#sketches li.selected")).to_contain_text("footpedal")
    expect(page.locator("#fqbn-input")).to_have_value("arduino:avr:uno")
    page.locator("#sketches li[data-name='esp32_blink']").click()
    expect(page.locator("#fqbn-input")).to_have_value("esp32:esp32:esp32")

    # Suggested cores are offered; the toolchain card names the tool.
    assert page.locator("#cores li").count() >= 5
    expect(page.locator("#toolchain")).to_contain_text("arduino-cli")


@pytest.mark.e2e
def test_viewer_toolbar_links_to_firmware_and_monitor(page: Page, base_url: str):
    page.goto(f"{base_url}/viewer/sites/garage")
    links = page.locator(".toolbar a.toolbar-link")
    expect(links).to_have_count(2)
    expect(links.nth(0)).to_contain_text("Firmware")
    expect(links.nth(1)).to_contain_text("Monitor")
    links.nth(1).click()
    expect(page).to_have_title("Apothecary Printer Monitor")
    expect(page.locator("#port option").first).to_contain_text("pick a port")
    # And the two pages link back and forth.
    page.locator(".top .links a", has_text="Firmware").click()
    expect(page).to_have_title("Apothecary Firmware")
    page.locator(".toolbar a", has_text="Printer monitor").click()
    expect(page).to_have_title("Apothecary Printer Monitor")


@pytest.mark.e2e
def test_viewer_serial_overlay_toggle(page: Page, base_url: str):
    """The serial-log overlay floats over the 3D view, toggles from the toolbar, and persists."""
    page.goto(f"{base_url}/viewer/sites/garage")
    overlay = page.locator("#serial-overlay")
    expect(overlay).to_be_hidden()
    page.locator("#serial-toggle").check()
    expect(overlay).to_be_visible()
    # Whether or not a board is attached, the header explains the situation.
    expect(page.locator("#serial-meta")).not_to_have_text("—", timeout=10000)
    page.reload()
    expect(page.locator("#serial-overlay")).to_be_visible()
    page.locator("#serial-close").click()
    expect(page.locator("#serial-overlay")).to_be_hidden()
    assert not page.locator("#serial-toggle").is_checked()


@pytest.mark.e2e
def test_firmware_page_devices_panel(page: Page, base_url: str):
    """Each detected board has a card: a devkit can be probed; a printer, once asked,
    has Poll and Monitor and nothing that would take its port (it is monitored, never
    probed or flashed)."""
    page.goto(f"{base_url}/firmware")
    expect(page.locator("#devices .device")).to_have_count(2, timeout=10000)

    uno = page.locator(".device[data-port='/dev/ttyFAKE0']")
    expect(uno).to_contain_text("Arduino Uno")
    expect(uno.locator(".dev-probe")).to_be_visible()

    # "Printer?" asks M115, or "Poll" if an earlier test already asked: a printer either way.
    printer = page.locator(".device[data-port='/dev/ttyFAKE1']")
    printer.locator(".dev-printer").click()
    expect(printer.locator(".printer-status")).to_contain_text("printing", timeout=10000)
    expect(printer.locator(".dev-monitor")).to_be_visible()
    expect(printer.locator(".dev-probe")).to_have_count(0)
    expect(printer.locator(".dev-live")).to_have_count(0)
