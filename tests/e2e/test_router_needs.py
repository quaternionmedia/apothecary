"""What the router's state asks of a person, read in its Machine and not in its log: a
controller in alarm says what it needs before anything moves, a line that did not go
stays in the Needs you card until one goes, and each axis's home says beside its button
which way it will seek and what the port must show first.

Runs against a server of its own with the simulated router on ``/dev/ttyFAKE3``, started
in alarm and held to the homing proof as a real one is
(``APOTHECARY_SIMULATED_ROUTER_UNPROVED``). A switch pressed by hand is the bench's
(docs/bench-checklist.md, section I). Nothing here opens a real port.
"""

from __future__ import annotations

import os

import httpx
import pytest
import windows
from boards import wears
from garage import open_garage
from garage import select as _select
from playwright.sync_api import Page, expect

ROUTER = "/dev/ttyFAKE3"
CONTROLLER = "cnc_router.frame_system.controller"
WITHIN_A_POLL = 6000


@pytest.fixture(scope="module")
def url(start_server):
    url = start_server(
        env_overrides={
            "APOTHECARY_SIMULATED_ROUTER": ROUTER,
            "APOTHECARY_SIMULATED_ROUTER_STATE": "alarm",
            "APOTHECARY_SIMULATED_ROUTER_UNPROVED": "1",
            "APOTHECARY_SIMULATED_SPEED": "0.05",
            "FAKE_ROUTER": "1",
        }
    )
    with httpx.Client(base_url=url, timeout=15.0) as http:
        http.post("/firmware/devices/identify", json={"port": ROUTER}).raise_for_status()
        http.put(
            f"/sites/garage/nodes/{CONTROLLER}/device", json={"identity": ROUTER}
        ).raise_for_status()
    return url


def _position(url: str) -> dict:
    return httpx.get(f"{url}/firmware/printers/status", params={"port": ROUTER}).json()["position"]


@pytest.mark.e2e
def test_the_machine_says_what_it_needs_and_what_did_not_go(page: Page, url: str):
    open_garage(page, url, settle=False)
    wears(page, "cnc_router")
    _select(page, "cnc_router")
    page.locator("#selected-body .device-section .dev-open").click()
    windows.machine_ready(page, "router")
    machine = windows.machine(page)
    needs = machine.locator("#c-needs-card")

    # 1. In alarm: the card is there before anything is asked, saying what clears it.
    expect(needs).to_be_visible(timeout=WITHIN_A_POLL)
    expect(needs).to_contain_text("In alarm")
    expect(needs).to_contain_text("until Unlock ($X) or a home")

    # 2. A jog in alarm: the controller's own objection, kept in the card.
    machine.locator("#ctl").check()
    pad = page.locator("#control")
    expect(pad).to_be_visible(timeout=5000)
    pad.locator("button[data-step='1']").click()
    pad.locator("button[data-jog='Z+']").click()
    expect(needs).to_contain_text("$J=G91 G21 Z1", timeout=WITHIN_A_POLL)
    expect(needs).to_contain_text("did not go")
    expect(needs.locator(".need.bad .why")).to_contain_text("error:")

    # 3. Each axis's home beside its button: not proved, and what to do first.
    z = pad.locator("#ctl-homing .home-axis[data-axis='Z']")
    expect(z).to_contain_text("seeks +Z · switch ✗ · way ✗", timeout=WITHIN_A_POLL)
    expect(z).to_contain_text("first: jog Z 1 mm toward +Z")
    expect(pad.locator("button[data-cmd='HOME-Z']")).to_have_class("unproved")

    # 4. Unlock: nothing is asked of the person any more, and the line that went clears
    #    the one that did not.
    needs.locator(".needs-unlock").click()  # the card's own Unlock: where it says so
    expect(needs).to_be_hidden(timeout=WITHIN_A_POLL)

    # 5. A home not proved does not go, and the card says why in the controller's figures.
    before = _position(url)
    pad.locator("button[data-cmd='HOME-Z']").click()
    expect(needs).to_be_visible(timeout=WITHIN_A_POLL)
    expect(needs).to_contain_text("$HZ did not go")
    expect(needs.locator(".need.bad .why")).to_contain_text("home refused: Z will seek +Z at")
    assert _position(url) == before

    # 6. Jogged the way it homes, the axis has shown its way; its switch is the bench's.
    pad.locator("button[data-jog='Z+']").click()
    expect(z).to_contain_text("switch ✗ · way ✓", timeout=WITHIN_A_POLL)
    expect(needs).to_be_hidden(timeout=WITHIN_A_POLL)  # the jog went
    expect(pad.locator("button[data-cmd='HOME-Z']")).to_have_class("unproved")

    shot = os.environ.get("APOTHECARY_NEEDS_PICTURE")
    if shot:
        pad.locator("button[data-cmd='HOME-Z']").click()
        expect(needs).to_contain_text("$HZ did not go", timeout=WITHIN_A_POLL)
        page.screenshot(path=shot)
