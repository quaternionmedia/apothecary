"""A button whose command the server would refuse now is greyed, with the reason in
its title; the buttons that stop are never greyed.

A host print holds a printer's port, so the pad's jog and the header's Reboot are
refused by the server (409); both are greyed with the server's words
(``can`` on the status, ``firmware/can.py``), while E-STOP, the pad's E-STOP and
Quickstop are not. When the print is cancelled the jog is allowed again.

Runs against a server of its own with the simulated printer idle on ``/dev/ttyFAKE1``
(not printing from its card, which the server would name first), slowed so a print
lasts; nothing here opens a real port.
"""

from __future__ import annotations

import re

import httpx
import pytest
import windows
from boards import PRINTER
from playwright.sync_api import Page, expect

WITHIN_A_POLL = 5000
SLOW_PRINT = "G28\n" + "G4 P500\n" * 40 + "G1 X1\n"


@pytest.fixture(scope="module")
def url(start_server):
    return start_server(
        env_overrides={"APOTHECARY_SIMULATED_PRINTER": "idle", "APOTHECARY_SIMULATED_SPEED": "0.5"}
    )


@pytest.fixture(autouse=True)
def _as_it_starts(url):
    def start_over():
        with httpx.Client(base_url=url, timeout=15.0) as http:
            http.post("/firmware/printers/print/cancel", json={"port": PRINTER})
            http.post("/firmware/printers/control", json={"port": PRINTER, "armed": False})
            http.post("/firmware/printers/release", json={"port": PRINTER})
            http.post("/firmware/devices/identify", json={"port": PRINTER}).raise_for_status()

    start_over()
    yield
    start_over()


@pytest.mark.e2e  # UNRUN when written: a browser test, run with --start-server
def test_a_print_greys_the_jog_and_the_reboot_and_never_the_stops(page: Page, url: str):
    with httpx.Client(base_url=url, timeout=15.0) as http:
        kept = http.post(
            "/firmware/printers/prints",
            params={"name": "slow.gcode", "machine": "printer"},
            content=SLOW_PRINT.encode(),
        )
        kept.raise_for_status()
        http.post("/firmware/printers/control", json={"port": PRINTER, "armed": True})
        http.post(
            "/firmware/printers/print", json={"port": PRINTER, "file_id": kept.json()["id"]}
        ).raise_for_status()
    page.goto(f"{url}/firmware/monitor?port={PRINTER}")
    windows.machine_ready(page, "printer")
    expect(windows.in_machine(page, "#c-state")).not_to_have_text("—", timeout=10000)
    pad = page.locator("#control")
    expect(pad).to_be_visible(timeout=WITHIN_A_POLL)

    jog = pad.locator("button[data-jog='Y+']")
    expect(jog).to_be_disabled(timeout=WITHIN_A_POLL)
    expect(jog).to_have_attribute("aria-disabled", "true")
    expect(jog).to_have_attribute("title", re.compile(r"^Disabled: .*a print holds the port"))
    reboot = windows.in_machine(page, "#reset")
    expect(reboot).to_be_disabled()
    expect(reboot).to_have_attribute("title", re.compile(r"^Disabled: .*a print holds the port"))

    for stop in (
        windows.in_machine(page, "#estop"),
        pad.locator("#pad-estop"),
        pad.locator("button[data-cmd='M410']"),
    ):
        expect(stop).to_be_enabled()
        expect(stop).not_to_have_attribute("aria-disabled", "true")

    # The print cancelled, the jog is the server's to take again and the page says so.
    page.locator("#print-cancel").click()
    expect(jog).to_be_enabled(timeout=WITHIN_A_POLL * 2)
    expect(jog).not_to_have_attribute("title", re.compile(r"^Disabled"))


@pytest.mark.e2e  # UNRUN when written: a browser test, run with --start-server
def test_send_asks_the_server_whether_a_chosen_file_fits(page: Page, url: str):
    """A file kept for a router, chosen on a printer, greys Send with the server's
    words (GET /firmware/printers/can-start); the page holds no rule of its own."""
    with httpx.Client(base_url=url, timeout=15.0) as http:
        http.post(
            "/firmware/printers/prints",
            params={"name": "cut.nc", "machine": "router"},
            content=b"G21 G90\nM3 S12000\nM5\n",
        ).raise_for_status()
        http.post("/firmware/printers/control", json={"port": PRINTER, "armed": True})
    page.goto(f"{url}/firmware/monitor?port={PRINTER}")
    windows.machine_ready(page, "printer")
    kept = page.locator("#print-pick option", has_text="cut.nc")
    expect(kept).to_have_count(1, timeout=WITHIN_A_POLL)
    page.locator("#print-pick").select_option(kept.get_attribute("value"))
    send = page.locator("#print-start")
    expect(send).to_be_disabled(timeout=WITHIN_A_POLL)
    expect(send).to_have_attribute("title", re.compile(r"^Disabled: cut\.nc was kept for a router"))
