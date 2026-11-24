"""A button whose command the server would refuse now is greyed, with the reason in
its title; the emergency stop is never greyed.

A host print holds a printer's port, so the pad's jog, the header's Reboot and the
pad's Quickstop (M410: the stream would go on after it, so a print is cancelled, not
quick-stopped) are refused by the server (409); each is greyed with the server's words
(``can`` on the status, ``firmware/can.py``), while E-STOP and the pad's E-STOP are not,
nor Break wait (M108), which a print lets through. When the print is cancelled the jog
and Quickstop are allowed again.

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
            for pin in http.get("/firmware/pins").json()["pins"]:
                http.delete(f"/firmware/pins/{pin['site']}/{pin['path']}")
            http.post("/firmware/devices/identify", json={"port": PRINTER}).raise_for_status()

    start_over()
    yield
    start_over()


@pytest.mark.e2e
def test_a_print_greys_the_jog_the_reboot_and_the_quickstop_and_never_the_stop(
    page: Page, url: str
):
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

    quickstop = pad.locator("button[data-cmd='M410']")
    expect(quickstop).to_be_disabled()
    expect(quickstop).to_have_attribute("title", re.compile(r"^Disabled: .*a print holds the port"))
    for live in (
        windows.in_machine(page, "#estop"),
        pad.locator("#pad-estop"),
        pad.locator("button[data-cmd='M108']"),
    ):
        expect(live).to_be_enabled()
        expect(live).not_to_have_attribute("aria-disabled", "true")

    # The bed level's corner moves are control lines like the pad's: greyed the same way,
    # and the same word on the print's button as on the pad's and the ring's.
    corner = page.locator("#level-card button[data-corner='FL']")
    expect(corner).to_be_disabled(timeout=WITHIN_A_POLL)
    expect(corner).to_have_attribute("title", re.compile(r"^Disabled: .*a print holds the port"))
    expect(page.locator("#print-cancel")).to_have_text("⏏ Abort")
    # The file the print sends is not forgotten under it: what only the page knows is
    # said in the same shape as the server's reasons.
    forget = page.locator("#print-delete")
    expect(forget).to_be_disabled()
    expect(forget).to_have_attribute(
        "title", "Disabled: the print from here is sending it. Forget the chosen file"
    )
    # A reason names the machine its board is pinned to, as its window does, not the
    # port's path: pinned, the next poll's answer says printer_1.
    with httpx.Client(base_url=url, timeout=15.0) as http:
        http.put(
            "/sites/garage/nodes/printer_1.frame_system.mainboard/device",
            json={"identity": PRINTER},
        ).raise_for_status()
    expect(corner).to_have_attribute(
        "title", re.compile(r"^Disabled: printer_1: a print holds the port"), timeout=WITHIN_A_POLL
    )
    assert PRINTER not in (corner.get_attribute("title") or "")
    # A refused line stays in the Machine's needs until an act of the machine goes: it is
    # named by its button's label, and the print cancelled below lets it go.
    with httpx.Client(base_url=url, timeout=15.0) as http:
        assert http.post(
            "/firmware/printers/command", json={"port": PRINTER, "command": "M84"}
        ).status_code in (409, 422)
    needs = windows.in_machine(page, "#c-needs")
    expect(needs).to_contain_text("Motors off did not go", timeout=WITHIN_A_POLL)
    expect(needs).not_to_contain_text("M84")

    # The print cancelled, the jog is the server's to take again and the page says so.
    page.locator("#print-cancel").click()
    expect(page.locator("#print-cancel")).to_have_text("Again to abort")
    page.locator("#print-cancel").click()
    expect(jog).to_be_enabled(timeout=WITHIN_A_POLL * 2)
    expect(jog).not_to_have_attribute("title", re.compile(r"^Disabled"))
    expect(quickstop).to_be_enabled()
    expect(needs).not_to_contain_text("Motors off did not go", timeout=WITHIN_A_POLL)
    expect(forget).to_be_enabled()
    expect(forget).to_have_attribute("title", "Forget the chosen file")


@pytest.mark.e2e
def test_the_control_pad_buttons_say_what_they_do(page: Page, url: str):
    """Every pad button has a description of its own as its tip, so the ring's address
    written after it is never the whole of a title."""
    with httpx.Client(base_url=url, timeout=15.0) as http:
        http.post("/firmware/printers/control", json={"port": PRINTER, "armed": True})
    page.goto(f"{url}/firmware/monitor?port={PRINTER}")
    windows.machine_ready(page, "printer")
    expect(page.locator("#control")).to_be_visible(timeout=WITHIN_A_POLL)
    bare = page.evaluate(
        r"""() => [...document.querySelectorAll('#control button, #ctl, #ctl-disarm')]
            .filter((b) => !b.hidden && b.offsetParent !== null)
            .filter((b) => !(b.getAttribute('title') || '').replace(/\s*·?\s*⌗\d+/g, '').trim())
            .map((b) => b.id || b.textContent.trim())"""
    )
    assert bare == [], bare


@pytest.mark.e2e
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
