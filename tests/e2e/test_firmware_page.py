"""End-to-end test for the firmware page (templates/firmware.html.j2).

Runs whether or not a real arduino-cli is installed on the host: the page
must load and be honest about toolchain state either way.
"""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
def test_firmware_page_loads_and_reports_toolchain(page: Page, base_url: str):
    page.goto(f"{base_url}/firmware")
    expect(page).to_have_title("Apothecary Firmware")
    expect(page.locator(".toolbar h1")).to_contain_text("Apothecary")

    pill = page.locator("#status-pill")
    expect(pill).not_to_have_text("checking…", timeout=10000)
    assert pill.inner_text().startswith("arduino-cli") or "missing" in pill.inner_text()

    # The repo's own sketches are discovered regardless of toolchain state; picking
    # one fills its firmware.json default FQBN.
    expect(page.locator("#sketches li.selected")).to_be_visible()
    page.locator("#sketches li[data-name='footpedal']").click()
    expect(page.locator("#sketches li.selected")).to_contain_text("footpedal")
    expect(page.locator("#fqbn-input")).to_have_value("arduino:avr:uno")
    page.locator("#sketches li[data-name='esp32_blink']").click()
    expect(page.locator("#fqbn-input")).to_have_value("esp32:esp32:esp32")

    # Suggested cores are always offered; the toolchain card names the tool either way.
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
    page.goto(f"{base_url}/firmware")
    expect(page.locator("#devices")).not_to_have_text("–", timeout=10000)
    text = page.locator("#devices").inner_text()
    assert "No devices detected" in text or "Probe" in text
