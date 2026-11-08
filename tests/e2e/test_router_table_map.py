"""The router's table map in the page: taken through the route with the latch armed,
listed for the router's port, drawn as a relief over its table in the world where its
points were probed, and shown in its Machine's Level card in a router's words, from
which a second map is taken.

Runs against a server of its own with the simulated router on ``/dev/ttyFAKE3``
(``APOTHECARY_SIMULATED_ROUTER``) and the scripted arduino-cli listing it
(``FAKE_ROUTER``), as ``test_router_ui.py`` does, its moves taking a little time so
the map's stages show. The simulated plate is flat, so the relief is flat; what is
held is that it is the router's, lies where the map says, and is the card's. Nothing
here opens a real port.
"""

from __future__ import annotations

import re
import time

import httpx
import pytest
import windows
from boards import wears
from garage import open_garage
from garage import select as _select
from playwright.sync_api import Page, expect

ROUTER = "/dev/ttyFAKE3"
CONTROLLER = "cnc_router.frame_system.controller"
POINTS = 9  # three by three, the grid left out
PROBE = "G38.2 Z-77.00 F200"  # from the top of Z, the rest of the travel

# A printer's bed reading under the router's port name, kept before readings named
# their board, as one was on the bench: never the router's, however it reaches the page.
A_PRINTER_S_READING = {
    "id": "20260920T132512.468-dev_ttyFAKE3",
    "port": ROUTER,
    "at": "2026-09-20T13:25:12.468000Z",
    "method": "read",
    "mesh": [[0.0, 0.4, 0.9], [0.1, 0.5, 1.2], [0.2, 0.7, 1.6]],
    "stats": {"range": 1.6, "mean": 0.62},
    "firmware": "Marlin made up",
}


@pytest.fixture(scope="module")
def url(start_server):
    """The router identified and its controller pinned: cnc_router wears its badge."""
    url = start_server(
        env_overrides={
            "APOTHECARY_SIMULATED_ROUTER": ROUTER,
            "APOTHECARY_SIMULATED_SPEED": "0.02",
            "FAKE_ROUTER": "1",
        }
    )
    with httpx.Client(base_url=url, timeout=15.0) as http:
        http.post("/firmware/devices/identify", json={"port": ROUTER}).raise_for_status()
        http.put(
            f"/sites/garage/nodes/{CONTROLLER}/device", json={"identity": ROUTER}
        ).raise_for_status()
    return url


def _map_the_table(url: str, note: str | None = None) -> str:
    """A table map taken through the route as a printer's bed is read -- armed, started,
    waited for, disarmed -- and the id of the record it keeps."""
    with httpx.Client(base_url=url, timeout=15.0) as http:
        http.post(
            "/firmware/printers/control", json={"port": ROUTER, "armed": True, "ttl_s": 300}
        ).raise_for_status()
        r = http.post("/firmware/printers/level", json={"port": ROUTER, "note": note})
        assert r.status_code == 202, r.text
        assert r.json()["what"] == "a table map" and r.json()["points"]["total"] == POINTS
        deadline = time.monotonic() + 90
        job = r.json()
        while time.monotonic() < deadline and job["running"]:
            time.sleep(0.5)
            job = http.get("/firmware/printers/level", params={"port": ROUTER}).json()
        assert job["stage"] == "saved", job
        http.post("/firmware/printers/control", json={"port": ROUTER, "armed": False})
        return job["record_id"]


@pytest.mark.e2e
def test_the_map_is_drawn_over_the_router_s_table_where_it_was_probed(page: Page, url: str):
    """A map kept for the router's port is what the world lays over its table: a three
    by three relief whose points lie where the map says they were probed, from the
    working area's front-left corner, its floor on the table."""
    record_id = _map_the_table(url, note="before surfacing the spoilboard")
    with httpx.Client(base_url=url, timeout=15.0) as http:
        listed = http.get("/firmware/printers/leveling", params={"port": ROUTER}).json()
    assert [r["id"] for r in listed] == [record_id] and listed[0]["method"] == "G38.2"
    open_garage(page, url, settle=False)
    wears(page, "cnc_router")
    marks = "window.fractalViewer.marks['cnc_router']"
    shown = f"() => {marks} && {marks}.marks && {marks}.marks.mesh()"
    page.wait_for_function(
        f"(id) => ({shown})() && ({shown})().record_id === id", arg=record_id, timeout=15000
    )
    mesh = page.evaluate(f"() => {marks}.marks.mesh()")
    assert mesh["rows"] == 3 and mesh["cols"] == 3
    assert mesh["bounds"] == {"min": {"x": 20.0, "y": 20.0}, "max": {"x": 380.0, "y": 580.0}}
    volume = page.evaluate(f"() => {marks}.marks.volume()")
    assert mesh["z"]["min"] == pytest.approx(volume["min"]["z"] + 0.4)
    assert mesh["range"] == 0.0  # the simulated plate is flat

    # A printer's reading never reaches the router's table: the route answered one
    # anyway (as a server listing readings by port name alone would), and the page's
    # own event told one, the map stays and the reading is not drawn.
    asked: list[str] = []

    def a_printers_reading(route):
        asked.append(route.request.url)
        route.fulfill(json=[A_PRINTER_S_READING])

    page.route(re.compile(r".*/firmware/printers/leveling\?port=.*ttyFAKE3.*"), a_printers_reading)
    page.evaluate(
        "() => { const v = window.fractalViewer; v.marks['cnc_router'].readingAt = 0;"
        " v.refreshReading('cnc_router'); }"
    )
    page.wait_for_function("() => window.fractalViewer.marks['cnc_router'].readingAt > 0")
    page.wait_for_timeout(1000)
    page.evaluate(
        "(reading) => window.dispatchEvent(new CustomEvent('apothecary:mesh', { detail: reading }))",
        A_PRINTER_S_READING,
    )
    page.wait_for_timeout(500)
    assert len(asked) == 1
    assert page.evaluate(f"() => {marks}.marks.mesh().record_id") == record_id
    page.unroute(re.compile(r".*/firmware/printers/leveling\?port=.*ttyFAKE3.*"))


@pytest.mark.e2e
def test_the_machine_s_level_card_is_a_router_s_and_takes_a_map(page: Page, url: str):
    """The router's Machine has the Level card in a router's words -- Table map, Probe
    table, no stored mesh to read and no corner moves -- showing the map kept.
    Disarmed, a map is refused before the port; armed, the page asks in the router's
    words, then homes and probes point by point, and the record appears when it is
    done, shown in the card and laid over the table."""
    with httpx.Client(base_url=url, timeout=15.0) as http:
        kept = http.get("/firmware/printers/leveling", params={"port": ROUTER}).json()
    if not kept:  # run alone: a map of its own to show, as the test above leaves one
        _map_the_table(url)
        kept = [None]
    open_garage(page, url, settle=False)
    wears(page, "cnc_router")
    _select(page, "cnc_router")
    page.locator("#selected-body .device-section .dev-open").click()
    windows.machine_ready(page, "router")
    machine = windows.machine(page)
    windows.from_the_windows_menu(page, "machine-level")
    expect(windows.tab(page, "machine-level")).to_contain_text("Table map")
    card = machine.locator("#level-card")
    expect(card).to_be_visible()
    expect(card.locator("#level-title")).to_have_text("Table map")
    expect(card.locator("#level-probe")).to_have_text("▦ Probe table")
    expect(card.locator("#level-read")).to_be_hidden()
    expect(card.locator("button[data-corner='FL']")).to_be_hidden()
    expect(machine.locator("#mesh .cell")).to_have_count(POINTS)
    stats = machine.locator("#level-stats")
    expect(stats).to_contain_text("G38.2 ·")
    expect(stats).to_contain_text("across the table")
    expect(stats).to_contain_text("Z in machine coordinates")
    expect(stats).not_to_contain_text("leveling")
    expect(machine.locator("#level-history > div")).to_have_count(len(kept))
    # The log is the port's whole history: the map taken through the route above is
    # in it already, so what this test sends is counted from there.
    log = windows.in_machine(page, "#log")
    probes = log.locator(".tx.control", has_text=PROBE)
    homings = log.locator(".tx.control", has_text="$H")
    saved = log.locator(".sys", has_text="a table map saved")
    probed_before, homed_before, saved_before = probes.count(), homings.count(), saved.count()

    # Disarmed: the probe is not offered, and one asked for all the same is refused on
    # the page, nothing sent.
    expect(card.locator("#level-probe")).to_be_hidden()
    page.evaluate("() => window.apothecaryMachine.level.start(true)")
    expect(log.locator(".sys", has_text="arm control first")).to_be_visible(timeout=3000)
    expect(probes).to_have_count(probed_before)

    # Armed: the question in the router's words, then the map, point by point.
    machine.locator("#ctl").check()
    expect(page.locator("#control")).to_be_visible(timeout=5000)
    asked: list[str] = []
    page.once("dialog", lambda d: (asked.append(d.message), d.accept()))
    card.locator("#level-probe").click()
    # The simulated probe touches at once, so the map takes a second or two here and
    # its stages (homing, probing k/9) may pass between two polls of the card: what is
    # held is what the map leaves.
    expect(saved).to_have_count(saved_before + 1, timeout=90000)
    expect(card.locator("#level-job")).to_have_text("", timeout=10000)
    assert asked and "probe the table" in asked[0] and "lead" in asked[0]
    expect(machine.locator("#level-history > div")).to_have_count(len(kept) + 1, timeout=10000)
    expect(probes).to_have_count(probed_before + POINTS)
    expect(homings).to_have_count(homed_before + 1)
    shown_id = page.evaluate("() => window.apothecaryMachine.level.shown().id")
    marks = "window.fractalViewer.marks['cnc_router']"
    page.wait_for_function(
        f"(id) => {marks} && {marks}.marks && {marks}.marks.mesh() && {marks}.marks.mesh().record_id === id",
        arg=shown_id,
        timeout=10000,
    )
    machine.locator("#ctl").uncheck()
