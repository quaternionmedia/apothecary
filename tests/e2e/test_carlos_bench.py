"""The garage's bench, held in carlos by an apothecary server and followed as it changes.

An apothecary test server, its bench the scripted one (an Uno on /dev/ttyFAKE0,
an unmatched port on /dev/ttyFAKE1, the simulated printer mid-print), is started
with ``APOTHECARY_CARLOS`` naming a carlos run from ``CARLOS_CHECKOUT``
(``carlos_app.py``), as ``apothecary serve --carlos`` starts one. Its follower
sends the garage's wiring to carlos at the start, and an open rack tab draws it
with each board's and lead's state. Then a sketch is flashed through apothecary's
own route, as the Machine's Upload does, and the tab draws the bench as it now is,
without a reload: the board that was absent is present, and the port that no node
named is the board's. And the printer, pinned to printer_1's mainboard and polled
as its Machine polls it, is said in carlos as each poll found it: printing, how
far through its job, and its heaters.

Without ``CARLOS_CHECKOUT`` it skips, saying so: carlos is another repository.
"""

from __future__ import annotations

import time

import httpx
import pytest
from boards import BOARD, PRINTER

# The fixtures these tests stand on: carlos itself, and a page of its.
from carlos_app import (  # noqa: F401
    _chromium_here,
    _verify_url,
    browser_context_args,
    carlos_server,  # the fixture `carlos`
    family_state,
)
from playwright.sync_api import Page

# A browser test, deselected where nothing can serve it.
pytestmark = pytest.mark.e2e

THE_UNO = "/dev/ttyFAKE0"


@pytest.fixture(scope="module")
def apothecary(start_server, carlos):
    """An apothecary server of the module's own, sending its garage to carlos."""
    return start_server({"APOTHECARY_CARLOS": carlos})


def _held(url: str, timeout: float = 20.0) -> dict:
    """The rig carlos holds from apothecary, once it holds one."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = family_state(url)
        if state["state"]["held"] and (state["cue"] or {}).get("name") == "apothecary: garage":
            return state["state"]["held"]
        time.sleep(0.25)
    pytest.fail("carlos was sent no garage")


def _module_of(held: dict, device: str) -> str:
    return next(m["id"] for m in held["patch"]["modules"] if m["type"] == device)


def test_the_bench_is_held_in_carlos_and_followed_through_a_flash(carlos, apothecary, page: Page):
    held = _held(carlos)
    pedal = _module_of(held, "quaternionmedia.footpedal")
    states = held["states"]["modules"]
    # The footpedal names its sketch and is on no port yet; the Uno's port is no node's.
    assert states[pedal]["level"] == "fault"
    assert "absent: expected, and not answering" in states[pedal]["says"]
    assert f"usb:{THE_UNO}" in states and states[f"usb:{THE_UNO}"]["level"] == "warn"

    page.goto(f"{carlos}/rack")
    module = page.locator(f'.module[data-module-id="{pedal}"]')
    page.wait_for_function(
        "(id) => document.querySelector(`.module[data-module-id=\"${id}\"]`)?.dataset.held === 'fault'",
        arg=pedal,
    )
    assert page.locator(f'.module[data-module-id="usb:{THE_UNO}"]').count() == 1
    assert "absent: expected, and not answering" in module.locator(".held-says").first.inner_text()

    # Flash the footpedal's sketch onto the Uno through apothecary, as Upload does.
    started = httpx.post(
        f"{apothecary}/firmware/sketches/footpedal/upload",
        json={"port": THE_UNO, "fqbn": "arduino:avr:uno"},
        timeout=10,
    )
    assert started.status_code == 202, started.text
    task = started.json()["id"]
    deadline = time.monotonic() + 30
    while (status := httpx.get(f"{apothecary}/firmware/tasks/{task}").json()["status"]) not in (
        "succeeded",
        "failed",
        "cancelled",
    ):
        assert time.monotonic() < deadline, "the upload did not finish"
        time.sleep(0.25)
    assert status == "succeeded"

    # The follower's next look sends the bench as it is, and the open tab draws it.
    page.wait_for_function(
        "(id) => document.querySelector(`.module[data-module-id=\"${id}\"]`)?.dataset.held === 'ok'",
        arg=pedal,
        timeout=20_000,
    )
    says = module.locator(".held-says").first.inner_text()
    assert f"present: answering on {THE_UNO}" in says and "firmware: footpedal, as flashed" in says
    # The port is the footpedal's now: no module stands for it unclaimed.
    assert page.locator(f'.module[data-module-id="usb:{THE_UNO}"]').count() == 0
    lead = page.locator(f'path.cable[data-cable^="{pedal}:usb->"]')
    assert lead.count() > 0 and "is-held-ok" in (lead.first.get_attribute("class") or "")
    held = family_state(carlos)["state"]["held"]
    assert held["states"]["modules"][pedal]["level"] == "ok"


def test_printer_monitoring_reaches_carlos_as_the_mainboard_s_lines(carlos, apothecary, page: Page):
    """The printer pinned and polled, as its Machine polls it: each poll's state,
    progress and heaters are said under the mainboard in carlos."""
    with httpx.Client(base_url=apothecary, timeout=15.0) as http:
        http.post("/firmware/devices/identify", json={"port": PRINTER}).raise_for_status()
        http.put(
            f"/sites/garage/nodes/{BOARD}/device", json={"identity": PRINTER}
        ).raise_for_status()
        polled = http.get("/firmware/printers/status", params={"port": PRINTER})
        polled.raise_for_status()
    assert polled.json()["state"] == "printing"

    page.goto(f"{carlos}/rack")
    board = page.locator(f'.module[data-module-id="{BOARD}"]')
    page.wait_for_function(
        '(id) => (document.querySelector(`.module[data-module-id="${id}"] .held-says`)'
        "?.textContent || '').includes('printer: printing')",
        arg=BOARD,
        timeout=20_000,
    )
    says = board.locator(".held-says").first.inner_text()
    assert f"present: answering on {PRINTER}" in says
    assert "heaters: hotend" in says and "known by: pinned" in says
    assert board.get_attribute("data-held") == "ok"
