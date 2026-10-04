"""One Machine per board: the one surface a board has, and the one poller behind it.

The consolidation plan's Phase 4 (docs/plans/consolidation-2026-10-03.md): a
board's Machine is the one place for it -- its state, one log with one query
box, its controls, its pin -- printer or devkit; everything that draws a board
reads it from one model (static/boards.js) that polls it once; Selected's
Device section is one line and Open; Watch and Monitor on the ring are one
cell that opens the Machine; a refusal says so in the status bar; the serial
overlay is gone. Phase 5 (and the owner's decisions after Phase 4): a board's
flashing joins its Machine, Device › Flash in the cell Monitor freed, so every
cell after it is back where it was before Phase 4; a devkit's port is opened
only when asked (Listen); a Machine's ring is its device ring.

Runs against servers of its own from the conftest's ``start_server``: the
scripted ``arduino-cli`` (``/dev/ttyFAKE0`` an Uno, ``/dev/ttyFAKE1``
unmatched), the simulated printer mid-print, firmware state in a temp dir.
Nothing here opens a real port.
"""

from __future__ import annotations

import re
import time

import httpx
import pytest
from playwright.sync_api import Page, expect

PRINTER = "/dev/ttyFAKE1"
UNO = "/dev/ttyFAKE0"
BOARD = "printer_1.frame_system.mainboard"
POLL_MS = 2000  # the Machine's default interval
STATUS = "/firmware/printers/status"


@pytest.fixture(scope="module")
def url(start_server):
    """The printer identified and its mainboard pinned: printer_1 wears its badge."""
    url = start_server()
    with httpx.Client(base_url=url, timeout=15.0) as http:
        http.post("/firmware/devices/identify", json={"port": PRINTER}).raise_for_status()
        http.put(
            f"/sites/garage/nodes/{BOARD}/device", json={"identity": PRINTER}
        ).raise_for_status()
    return url


@pytest.fixture(autouse=True)
def _disarmed(request):
    """Every test starts with the latch disarmed, however the last one ended."""
    if "url" in request.fixturenames:
        url = request.getfixturevalue("url")
        httpx.post(
            f"{url}/firmware/printers/control", json={"port": PRINTER, "armed": False}, timeout=15.0
        )


def _open_viewer(page: Page, url: str) -> None:
    page.goto(f"{url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)


def _select(page: Page, path: str) -> None:
    page.locator(f"#contents-list .contents-item[data-path='{path}']").click()
    expect(page.locator("#selected-body .prop-row", has_text="Name")).to_be_visible(timeout=5000)


def _wedges(page: Page) -> dict:
    """label -> cell of every wedge of the open ring that holds something."""
    return page.evaluate(
        """() => Object.fromEntries([...document.querySelectorAll('#ring-overlay .wedge')]
            .filter((w) => !w.classList.contains('empty'))
            .map((w) => [w.getAttribute('aria-label'), w.dataset.cell]))"""
    )


def _choose(page: Page, *labels: str) -> None:
    """From the ring open on the selected piece, the cells named, by their labels."""
    for label in labels:
        cells = _wedges(page)
        assert label in cells, f"no {label!r} in this ring: {sorted(cells)}"
        page.keyboard.press(cells[label])


def _ring_on(page: Page, path: str) -> None:
    page.locator(f"#contents-list .contents-item[data-path='{path}']").click(button="right")
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)


MACHINE = ".panel[data-panel='machine']"


@pytest.mark.e2e
def test_watch_and_monitor_are_one_cell_that_opens_the_machine(page: Page, url: str):
    """The Device ring holds one cell for a board's Machine, where Watch was; Monitor is
    gone. Chosen, the Machine opens in front of the world, tethered to the printer."""
    _open_viewer(page, url)
    _ring_on(page, "printer_1")
    _choose(page, "Device")
    cells = _wedges(page)
    assert "Watch" not in cells and "Monitor" not in cells, cells
    assert cells["Open"] == "8"  # the cell Watch had
    assert cells["Flash"] == "2"  # the cell Monitor had
    page.keyboard.press("8")
    expect(page.locator("#ring-overlay")).to_have_count(0)
    machine = page.locator(MACHINE)
    expect(machine).to_be_visible(timeout=5000)
    expect(machine.locator("#c-state")).to_contain_text("printing", timeout=10000)
    assert page.evaluate("() => window.apothecaryPanels.state('machine').where") == {
        "tether": "printer_1"
    }
    expect(page.locator("#status")).to_contain_text("Opened printer_1")


@pytest.mark.e2e
def test_selected_says_one_line_and_open_opens_the_machine(page: Page, url: str):
    """Selected's Device section is one line -- the port and what the board is doing --
    with Open, which opens its Machine; the printer's row speaks for the board inside it."""
    _open_viewer(page, url)
    _select(page, "printer_1")
    section = page.locator("#selected-body .device-section")
    expect(section.locator(".device-line")).to_have_count(1, timeout=8000)
    expect(section).to_contain_text(PRINTER)
    expect(section.locator(".dev-open")).to_be_visible()
    for gone in (".dev-watch", ".dev-poll", ".dev-monitor"):
        expect(section.locator(gone)).to_have_count(0)
    section.locator(".dev-open").click()
    expect(page.locator(MACHINE)).to_be_visible(timeout=5000)
    expect(page.locator(MACHINE).locator("#ident")).to_contain_text("Marlin", timeout=10000)


@pytest.mark.e2e
def test_one_poller_per_board_whatever_draws_it(page: Page, url: str):
    """The badge, Site's row, Selected's line and the Machine all draw printer_1, and the
    ring's Open is chosen as well: one status request each period, and every drawer
    says what that one poll said."""
    page.clock.install()
    _open_viewer(page, url)
    badge = page.locator(".world-badge[data-path='printer_1']")
    expect(badge).to_be_visible(timeout=15000)
    _select(page, "printer_1")
    expect(page.locator("#selected-body .device-section")).to_contain_text(PRINTER, timeout=8000)
    # The badge, and then Device's first cell -- Watch, once: whatever each opened
    # polls the board, and the ring's Machine is the badge's, never a second one.
    badge.click()
    _ring_on(page, "printer_1")
    _choose(page, "Device")
    page.keyboard.press("8")
    machine = page.locator(MACHINE)
    expect(machine).to_have_count(1)
    expect(machine.locator("#c-state")).to_contain_text("printing", timeout=10000)

    asked = []
    page.on("request", lambda r: asked.append(r.url) if STATUS in r.url else None)
    page.clock.pause_at(page.evaluate("Date.now()") + 1000)
    page.wait_for_timeout(500)  # whatever was in flight has landed
    asked.clear()
    periods = 4
    for n in range(1, periods + 1):
        page.clock.fast_forward(POLL_MS)
        deadline = time.monotonic() + 5
        while len(asked) < n and time.monotonic() < deadline:
            page.wait_for_timeout(50)
        page.wait_for_timeout(300)  # a second poller's request would be in by now
    assert len(asked) == periods, f"{len(asked)} status requests in {periods} periods: {asked}"
    page.clock.resume()
    # What the one poll said is what each drawer shows.
    hot = page.evaluate(
        "() => window.fractalViewer.boards.board('/dev/ttyFAKE1').status.hotends[0].actual"
    )
    expect(badge).to_contain_text(f"{hot:.0f}°/")
    expect(page.locator("#selected-body .device-section .temps")).to_contain_text(f"{hot:.1f}/")
    expect(machine.locator("#c-hot")).to_contain_text(f"{hot:.1f}")


@pytest.mark.e2e
def test_one_log_with_one_query_box_in_the_machine(page: Page, url: str):
    """The board's log is in its Machine, with the one box that asks it for a report:
    no log panel of its own, no second box; a report answered lands there, poll
    traffic stays out until asked for, and a refused code says so."""
    _open_viewer(page, url)
    page.locator(".world-badge[data-path='printer_1']").click()
    machine = page.locator(MACHINE)
    expect(machine.locator("#c-state")).to_contain_text("printing", timeout=10000)
    expect(page.locator(".panel[data-panel='log']")).to_have_count(0)
    expect(page.locator(".panel-tab[data-panel='log']")).to_have_count(0)
    expect(page.locator("#log")).to_have_count(1)
    expect(machine.locator("#log")).to_have_count(1)
    boxes = page.locator("input[list]")  # a box that suggests report codes
    expect(boxes).to_have_count(1)
    expect(machine.locator("#q")).to_be_visible()
    machine.locator("#q").fill("M119")
    machine.locator("#qform button").click()
    expect(machine.locator("#log")).to_contain_text("y_min: TRIGGERED", timeout=8000)
    expect(machine.locator("#log .tx", has_text="M105")).to_have_count(0)  # polls hidden
    machine.locator("#show-polls").check()
    expect(machine.locator("#log .tx", has_text="M105").first).to_be_visible(timeout=8000)
    machine.locator("#show-polls").uncheck()
    machine.locator("#q").fill("G28")
    machine.locator("#qform button").click()
    expect(machine.locator("#log")).to_contain_text("query refused", timeout=5000)


@pytest.mark.e2e
def test_a_refusal_reaches_the_status_bar(page: Page, url: str):
    """A verb the Machine refuses -- a jog while control is not armed, chosen from the
    ring -- is said in the status bar as an error, with its address, and in the log."""
    _open_viewer(page, url)
    page.locator(".world-badge[data-path='printer_1']").click()
    machine = page.locator(MACHINE)
    expect(machine.locator("#c-state")).to_contain_text("printing", timeout=10000)
    _ring_on(page, "printer_1")
    _choose(page, "Device", "Control", "Jog", "Y+")
    expect(page.locator("#ring-overlay")).to_have_count(0)
    status = page.locator("#status")
    expect(status).to_contain_text("not armed", timeout=5000)
    expect(status).to_have_class(re.compile(r"\berror\b"))
    expect(status).to_contain_text("⌗2")
    expect(machine.locator("#log .sys", has_text="not armed").last).to_be_visible()
    # A refused report code from the Machine's own box says so too.
    machine.locator("#q").fill("G28")
    machine.locator("#qform button").click()
    expect(status).to_contain_text("query refused", timeout=5000)
    expect(status).to_have_class(re.compile(r"\berror\b"))


@pytest.mark.e2e
def test_no_serial_overlay_and_no_scan_on_a_schedule(page: Page, url: str):
    """The serial overlay, its toolbar toggle and the toolbar's look-for-boards tick-box
    are gone, and a browser that remembered the overlay open opens none."""
    page.add_init_script(
        "try { localStorage.setItem('apothecary.serial.open', '1');"
        " localStorage.setItem('apothecary.devices.auto', '1'); } catch (e) {}"
    )
    scans = []
    page.on("request", lambda r: scans.append(r.url) if "/devices?fresh=1" in r.url else None)
    _open_viewer(page, url)
    for gone in ("#serial-overlay", "#serial-toggle", "#devices-auto", "#devices-interval"):
        expect(page.locator(gone)).to_have_count(0)
    expect(page.locator(".world-badge[data-path='printer_1']")).to_be_visible(timeout=15000)
    page.wait_for_timeout(1000)
    assert scans == [], "the page looked for boards on a schedule"


def _flash(url: str, sketch: str, port: str) -> None:
    """Upload a sketch with the scripted arduino-cli, so the port should run it."""
    with httpx.Client(base_url=url, timeout=15.0) as http:
        task = http.post(
            f"/firmware/sketches/{sketch}/upload", json={"fqbn": "arduino:avr:uno", "port": port}
        )
        task.raise_for_status()
        for _ in range(300):
            done = http.get(f"/firmware/tasks/{task.json()['id']}").json()
            if done["status"] != "running":
                break
            time.sleep(0.05)
    assert done["status"] == "succeeded", done


@pytest.mark.e2e
def test_a_devkit_has_a_machine_with_what_it_should_run_and_what_it_says(page: Page, start_server):
    """The Uno was flashed footpedal, so the footpedal node is bound to it by its sketch.
    Its badge opens a Machine of its own: the port and the board, what it should run
    and what it was heard saying (the scripted monitor says fake_blink, so they differ),
    its serial output in the one log once Listen opens the port, and its Flashing card."""
    url = start_server()
    _flash(url, "footpedal", UNO)
    _open_viewer(page, url)
    _select(page, "footpedal")
    section = page.locator("#selected-body .device-section")
    expect(section).to_contain_text(UNO, timeout=8000)
    expect(section).to_contain_text("footpedal")
    badge = page.locator(".world-badge[data-path='footpedal']")
    expect(badge).to_be_visible(timeout=15000)
    badge.click()
    machine = page.locator(MACHINE)
    expect(machine).to_be_visible(timeout=5000)
    assert page.evaluate("() => window.apothecaryPanels.state('machine').where") == {
        "tether": "footpedal"
    }
    expect(machine.locator("#c-board")).to_contain_text(UNO)
    expect(machine.locator("#c-board")).to_contain_text("Arduino Uno")
    sketch = machine.locator("#c-sketch")
    expect(sketch).to_contain_text("should run footpedal")
    # Listen: the board's serial output, and the hello it says, in the one log.
    log = machine.locator("#log")
    machine.locator("#listen").click()
    expect(log).to_contain_text("may reset the board", timeout=5000)
    expect(log).to_contain_text("blink", timeout=10000)
    expect(log).to_contain_text("apothecary fake_blink: hello")
    expect(sketch).to_contain_text("observed fake_blink", timeout=5000)
    expect(sketch).to_contain_text("differs")
    expect(machine.locator("#qform")).to_be_hidden()  # a devkit takes no report codes
    expect(machine.locator("#control")).to_be_hidden()
    expect(machine.locator("#flash-card")).to_contain_text("Flashing")
    expect(machine.locator("#flash-card .upload-btn")).to_be_visible()
    # The drawers agree with the Machine: what it was heard saying is on the badge.
    expect(badge).to_contain_text("fake_blink")
    expect(section).to_contain_text("fake_blink")
    # Identify listens for the hello again, from the head or the ring's Query.
    _ring_on(page, "footpedal")
    _choose(page, "Device", "Query")
    expect(page.locator("#status")).to_contain_text("Query", timeout=15000)
    expect(page.locator("#status")).not_to_have_class(re.compile(r"\berror\b"))
    # Closed, it stops listening: the stream goes with it.
    page.evaluate("() => window.fractalViewer.closeMachine()")
    expect(machine).to_have_count(0)
    page.wait_for_function(
        "() => !window.fractalViewer.boards.board('/dev/ttyFAKE0').stream", timeout=5000
    )


@pytest.mark.e2e
def test_flash_takes_monitor_s_old_cell_and_every_cell_after_it_is_back(page: Page, url: str):
    """Device › Flash is in the cell Monitor had; Query, Unpin, Rescan, Link and Control
    are where hands learned them before Phase 4 -- Control at 7, so from a printer's
    node 2 7 2 8 is Control › Jog › Y+. A printer keeps its own firmware: its Flash
    holds the cell and cannot be chosen."""
    _open_viewer(page, url)
    _ring_on(page, "printer_1")
    _choose(page, "Device")
    assert _wedges(page) == {
        "Open": "8",
        "Poll": "6",
        "Flash": "2",
        "Query": "4",
        "Unpin": "9",
        "Rescan": "3",
        "Link": "1",
        "Control": "7",
    }
    flash = page.locator("#ring-overlay .wedge[data-cell='2']")
    expect(flash).to_have_class(re.compile(r"\bdisabled\b"))
    page.keyboard.press("2")  # nothing: the ring stays on Device
    expect(page.locator("#ring-overlay .title")).to_have_text("Device")
    for digit in ("7", "2", "8"):
        page.keyboard.press(digit)
    expect(page.locator("#ring-overlay")).to_have_count(0)
    status = page.locator("#status")
    expect(status).to_contain_text("⌗2728", timeout=8000)
    expect(status).to_contain_text("not armed")
    # Selected's buttons wear the same cells.
    _select(page, "printer_1")
    section = page.locator("#selected-body .device-section")
    expect(section.locator(".dev-open")).to_have_attribute("data-address", "28", timeout=5000)


@pytest.mark.e2e
def test_a_machine_s_ring_is_its_device_ring(page: Page, url: str):
    """Right-click inside a printer's Machine: the device ring on its port, the monitor
    page's ring -- Control at 7 -- and the Machine's buttons wear its cells: Control ›
    Arm ⌗77, E-STOP ⌗71, Link › Reconnect ⌗18; armed, Jog › Y+ ⌗728, Pause ⌗796."""
    _open_viewer(page, url)
    page.locator(".world-badge[data-path='printer_1']").click()
    machine = page.locator(MACHINE)
    expect(machine.locator("#c-state")).to_contain_text("printing", timeout=10000)
    expect(machine.locator("#ctl")).to_have_attribute("data-address", "77", timeout=5000)
    expect(machine.locator("#estop")).to_have_attribute("data-address", "71")
    expect(machine.locator("#reconnect")).to_have_attribute("data-address", "18")
    expect(machine.locator("#poll")).to_have_attribute("data-address", "6")
    machine.locator(".kv").first.click(button="right")
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    expect(page.locator("#ring-overlay .title")).to_have_text("ttyFAKE1")
    cells = _wedges(page)
    assert cells["Control"] == "7" and cells["Link"] == "1" and cells["Flash"] == "2", cells
    for digit in ("7", "7"):  # Control › Arm
        page.keyboard.press(digit)
    expect(machine.locator("#control")).to_be_visible(timeout=5000)
    expect(machine.locator("#control button[data-jog='Y+']")).to_have_attribute(
        "data-address", "728", timeout=5000
    )
    expect(machine.locator("#control button[data-cmd='M25']")).to_have_attribute(
        "data-address", "796"
    )
    assert (
        machine.locator("#control button[data-jog='Y+']").get_attribute("title") or ""
    ).endswith(" · ⌗728")
    machine.locator("#ctl-disarm").click()
    expect(machine.locator("#control")).to_be_hidden(timeout=5000)


PORT_OPENERS = (
    "/firmware/devices/stream",
    "/firmware/devices/listen",
    "/firmware/devices/identify",
    "/firmware/devices/probe",
    "/firmware/printers/status",
)


@pytest.mark.e2e
def test_a_devkit_s_machine_opens_no_port_until_listen(page: Page, start_server):
    """Opening a devkit's Machine shows what is known of it and opens no port: no
    stream, no listen, no M115, no poll. Listen opens it, says it may reset the board,
    and streams what the board says; Release closes it again."""
    url = start_server()
    _flash(url, "footpedal", UNO)
    opened = []
    page.on(
        "request",
        lambda r: opened.append(r.url) if any(p in r.url for p in PORT_OPENERS) else None,
    )
    _open_viewer(page, url)
    badge = page.locator(".world-badge[data-path='footpedal']")
    expect(badge).to_be_visible(timeout=15000)
    badge.click()
    machine = page.locator(MACHINE)
    expect(machine.locator("#c-sketch")).to_contain_text("should run footpedal", timeout=8000)
    expect(machine.locator("#c-board")).to_contain_text("not listening")
    expect(machine.locator("#c-board")).to_contain_text("Listen opens it")
    page.wait_for_timeout(2500)  # a stream opened on its own would have been asked for by now
    assert opened == [], opened
    assert not page.evaluate("() => !!window.fractalViewer.boards.board('/dev/ttyFAKE0').stream")
    # Reconnect does not open it either: there is nothing to reconnect.
    machine.locator("#reconnect").click()
    expect(page.locator("#status")).to_contain_text("not listening", timeout=5000)
    assert opened == [], opened

    machine.locator("#listen").click()
    log = machine.locator("#log")
    expect(log).to_contain_text("may reset the board", timeout=5000)
    expect(log).to_contain_text("apothecary fake_blink: hello", timeout=10000)
    assert any("/firmware/devices/stream" in u for u in opened), opened
    expect(machine.locator("#c-board b.ok")).to_have_text("listening", timeout=5000)
    expect(machine.locator("#listen")).to_be_disabled()
    machine.locator("#release").click()
    page.wait_for_function(
        "() => !window.fractalViewer.boards.board('/dev/ttyFAKE0').stream", timeout=5000
    )
    expect(machine.locator("#listen")).to_be_enabled()
    # Listen is a ring verb too: Link › Listen, appended after Release.
    _ring_on(page, "footpedal")
    _choose(page, "Device", "Link")
    assert _wedges(page)["Listen"] == "4" and _wedges(page)["Probe"] == "9"
    page.keyboard.press("4")
    expect(page.locator("#status")).to_contain_text("⌗214", timeout=5000)
    page.wait_for_function(
        "() => !!window.fractalViewer.boards.board('/dev/ttyFAKE0').stream", timeout=5000
    )


@pytest.mark.e2e
def test_device_flash_opens_the_machine_at_its_card_and_uploads_then_identifies(
    page: Page, start_server
):
    """Device › Flash (⌗22 from the devkit's node) opens its Machine at the Flashing card,
    the sketch it should run chosen and its board filled in. Compile & upload asks, then
    runs the upload as a task whose output is in the card; it ends, and Identify listens
    for the hello -- and asks no M115, which is a person's to press for."""
    url = start_server()
    _flash(url, "footpedal", UNO)
    asked = []
    page.on("request", lambda r: asked.append(r.url) if "/firmware/devices/" in r.url else None)
    _open_viewer(page, url)
    expect(page.locator(".world-badge[data-path='footpedal']")).to_be_visible(timeout=15000)
    _ring_on(page, "footpedal")
    _choose(page, "Device")
    assert _wedges(page)["Flash"] == "2"
    page.keyboard.press("2")
    expect(page.locator("#ring-overlay")).to_have_count(0)
    machine = page.locator(MACHINE)
    card = machine.locator("#flash-card")
    expect(card).to_be_visible(timeout=8000)
    expect(page.locator("#status")).to_contain_text("⌗22")
    expect(card.locator(".sketch-select")).to_have_value("footpedal", timeout=10000)
    expect(card.locator(".fqbn-input")).to_have_value("arduino:avr:uno")
    expect(card.locator(".port-select")).to_be_hidden()  # this board's port, no other
    expect(card.locator(".upload-btn")).to_be_enabled(timeout=5000)

    dialogs = []
    page.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
    card.locator(".upload-btn").click()
    expect(card.locator(".task-title")).to_contain_text("Upload footpedal", timeout=10000)
    expect(card.locator(".task-title")).to_contain_text("succeeded", timeout=10000)
    expect(card.locator(".task-log")).to_contain_text("fake upload")
    assert dialogs == ['Compile and upload "footpedal" to /dev/ttyFAKE0?'], dialogs
    log = machine.locator("#log")
    expect(log).to_contain_text("upload of footpedal (arduino:avr:uno): succeeded", timeout=5000)
    expect(log).to_contain_text("listening 6 s for the sketch's hello", timeout=5000)
    expect(log).to_contain_text("heard fake_blink say hello", timeout=20000)
    expect(machine.locator("#c-sketch")).to_contain_text("observed fake_blink")
    assert any("/firmware/devices/listen" in u for u in asked), asked
    assert not [u for u in asked if "/firmware/devices/identify" in u], asked


@pytest.mark.e2e
def test_the_monitor_address_opens_the_board_s_machine_where_it_is_pinned(page: Page, url: str):
    """/firmware/monitor?port=, the printer monitor's address, is the viewer on the site
    the port is pinned in, with its Machine open and tethered to the printer -- on a fresh
    load, the port kept in the address, so a reload opens it again."""
    page.goto(f"{url}/firmware/monitor?port={PRINTER}")
    expect(page).to_have_url(re.compile(r"/viewer/sites/garage\?machine=%2Fdev%2FttyFAKE1$"))
    machine = page.locator(MACHINE)
    expect(machine.locator("#c-state")).to_contain_text("printing", timeout=15000)
    assert page.evaluate("() => window.apothecaryPanels.state('machine').where") == {
        "tether": "printer_1"
    }
    page.reload()
    expect(machine.locator("#c-state")).to_contain_text("printing", timeout=15000)
    # Closed, the address lets go of it; a port of the wrong shape opens nothing.
    page.evaluate("() => window.fractalViewer.closeMachine()")
    expect(page).to_have_url(re.compile(r"/viewer/sites/garage$"))
    page.goto(f"{url}/firmware/monitor?port=%3Cscript%3E")
    expect(page).to_have_url(re.compile(r"/viewer/sites/garage$"))
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
    expect(machine).to_have_count(0)


@pytest.mark.e2e
def test_a_board_pinned_nowhere_floats_on_the_default_site(page: Page, start_server):
    """The monitor's address for a board pinned nowhere: the default site, its Machine
    floating over the world. The Uno, never asked, is a devkit's Machine -- Probe and
    Listen, no Poll, its port closed -- and the printer, asked M115, a printer's: Poll,
    and nothing that would take its port. (The firmware page's device cards, each a
    board's Machine now.)"""
    url = start_server()
    opened = []
    page.on(
        "request",
        lambda r: opened.append(r.url) if any(p in r.url for p in PORT_OPENERS) else None,
    )
    page.goto(f"{url}/firmware/monitor?port={UNO}")
    expect(page).to_have_url(re.compile(r"/viewer/sites/garage\?machine=%2Fdev%2FttyFAKE0$"))
    machine = page.locator(MACHINE)
    expect(machine.locator("#c-board")).to_contain_text("Arduino Uno", timeout=15000)
    assert page.evaluate("() => window.apothecaryPanels.state('machine').where") == "free"
    expect(machine.locator(".panel-name")).to_contain_text("pinned nowhere in garage")
    for shown in ("#probe", "#listen", "#identify", "#flash-card"):
        expect(machine.locator(shown)).to_be_visible()
    for hidden in ("#poll", "#qform", "#ctl-label", "#estop"):
        expect(machine.locator(hidden)).to_be_hidden()
    page.wait_for_timeout(1500)
    assert opened == [], opened
    # Its ring, with nothing selected, is its own device ring.
    page.keyboard.press("m")
    expect(page.locator("#ring-overlay .title")).to_have_text("ttyFAKE0", timeout=5000)
    assert _wedges(page)["Flash"] == "2" and "Control" not in _wedges(page)
    page.keyboard.press("Escape")

    httpx.post(f"{url}/firmware/devices/identify", json={"port": PRINTER}, timeout=15.0)
    page.goto(f"{url}/firmware/monitor?port={PRINTER}")
    expect(machine.locator("#c-state")).to_contain_text("printing", timeout=15000)
    expect(machine.locator("#poll")).to_be_visible()
    for hidden in ("#probe", "#listen", "#flash-card"):
        expect(machine.locator(hidden)).to_be_hidden()
