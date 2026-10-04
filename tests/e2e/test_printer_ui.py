"""Printer UI end to end, with timing bounds: the viewer must stay snappy while it polls.

Runs against a server of its own from the conftest's ``start_server``: the
scripted ``arduino-cli`` (``/dev/ttyFAKE0`` an Uno, ``/dev/ttyFAKE1``
unmatched), the in-process ``SimulatedPrinter`` mid-way through an SD print,
and firmware state in a temp dir, so pins never touch ``~/.apothecary``.

The printer monitor's address (``/firmware/monitor?port=``) opens the viewer
with the board's Machine in front of the world, floating when the port is pinned
nowhere: the tests that drove the monitor page drive that Machine, by the same ids.

Every test starts with nothing pinned, no file kept, the garage rebuilt and
both links released (the simulator mid-print again, control disarmed), and
identifies and pins what it needs through the API. A test that needs a
machine nothing has touched -- no port identified, no bed reading, an empty
comms log -- gets a server of its own.

Cadences are counted on the page's own clock (``page.clock``), held still and
moved one period at a time: each period brings exactly one poll or scan.

The bounds are deliberately loose enough for CI and tight enough to catch
the failure modes they name: a blocked event loop, stacked polls, a panel
rebuilt under the user's cursor.
"""

import json
import re
import time

import httpx
import pytest
from playwright.sync_api import Page, expect
from viewer_ready import FRAMES

PRINTER = "/dev/ttyFAKE1"
UNO = "/dev/ttyFAKE0"
BOARD = "printer_1.frame_system.mainboard"
POLL_MS = 2000  # the Machine's default interval
WITHIN_A_POLL = POLL_MS + 3000  # an expect's timeout: the next poll and its round trip
MONITOR = "window.apothecaryMachine.state"  # the open Machine's polling state
MACHINE = ".panel[data-panel='machine']"  # a board's Machine, in front of the world


@pytest.fixture(scope="module")
def printer_url(start_server):
    return start_server()


@pytest.fixture
def fresh_url(start_server):
    """A server nothing has touched: no port identified, no bed reading, an empty log."""
    return start_server()


@pytest.fixture(autouse=True)
def _as_it_starts(printer_url):
    """Nothing pinned or kept, the garage rebuilt, both links released: the simulator
    starts over, mid-print and disarmed."""
    with httpx.Client(base_url=printer_url, timeout=15.0) as http:
        for pin in http.get("/firmware/pins").json()["pins"]:
            http.delete(f"/firmware/pins/{pin['site']}/{pin['path']}").raise_for_status()
        for kept in http.get("/firmware/printers/prints").json():
            http.delete(f"/firmware/printers/prints/{kept['id']}").raise_for_status()
        http.post("/sites/garage/reset").raise_for_status()
        for port in (UNO, PRINTER):
            http.post("/firmware/printers/release", json={"port": port}).raise_for_status()


def _identify(url: str, port: str = PRINTER):
    """Ask the port what it is (M115), as the Machine's M115 does."""
    r = httpx.post(f"{url}/firmware/devices/identify", json={"port": port}, timeout=15.0)
    r.raise_for_status()


def _pin(url: str, path: str, port: str = PRINTER):
    r = httpx.put(f"{url}/sites/garage/nodes/{path}/device", json={"identity": port}, timeout=15.0)
    r.raise_for_status()


def _read_the_bed(url: str, probe: bool = False) -> str:
    """A bed reading on the printer, read or (armed) probed; returns its record's id."""
    with httpx.Client(base_url=url, timeout=15.0) as http:
        if probe:
            arm = http.post("/firmware/printers/control", json={"port": PRINTER, "armed": True})
            arm.raise_for_status()
        http.post(
            "/firmware/printers/level", json={"port": PRINTER, "probe": probe}
        ).raise_for_status()
        for _ in range(600):  # 30 s
            job = http.get("/firmware/printers/level", params={"port": PRINTER}).json()
            if not job["running"]:
                break
            time.sleep(0.05)
        else:
            raise AssertionError(f"the bed reading did not finish: {job}")
    assert job["record_id"], job
    return job["record_id"]


def _keep(url: str, name: str, gcode: str) -> str:
    """Keep a G-code file on the host, as the page's file picker does; returns its id."""
    r = httpx.post(
        f"{url}/firmware/printers/prints", params={"name": name}, content=gcode, timeout=15.0
    )
    r.raise_for_status()
    return r.json()["id"]


def _hold_clock(page: Page):
    """From here the page's timers fire only when the test moves its clock.

    Needs page.clock.install() before the page loads. The clock is moved with
    fast_forward, which fires each due timer once: run_for would also draw every
    animation frame in between, seconds of software GL on the viewer."""
    page.clock.pause_at(page.evaluate("Date.now()") + 1000)


def _select(page: Page, name: str):
    page.locator("#contents-list .contents-item", has_text=name).first.click()


def _expand_to(page: Page, path: str):
    """Open the Contents tree carets down to ``path`` and select its row."""
    parts = path.split(".")
    for depth in range(1, len(parts)):
        row = page.locator(f"#contents-list .contents-item[data-path='{'.'.join(parts[:depth])}']")
        caret = row.locator(".tree-caret")
        if caret.text_content() == "▸":
            caret.click()
    page.locator(f"#contents-list .contents-item[data-path='{path}']").click()


@pytest.mark.e2e
def test_panel_opens_before_devices_finish_loading(page: Page, printer_url: str):
    """Selecting a node never waits for the device scan: the panel is up within 1 s."""
    page.goto(f"{printer_url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
    # dispatch_event, not click(): the bound must cover the viewer's own work,
    # not Playwright's actionability wait on a page still streaming STLs
    # through headless software GL.
    page.locator("#contents-list .contents-item", has_text="printer_1").first.dispatch_event(
        "click"
    )
    expect(page.locator("#selected-body .prop-row", has_text="Name")).to_be_visible(timeout=1000)
    # The Device section is part of the panel from the first render, and
    # settles (scan done) within a bounded time rather than blocking it.
    expect(page.locator("#selected-body .device-section")).to_be_visible(timeout=1000)
    expect(page.locator("#selected-body .device-section .dev-pick")).to_be_visible(timeout=8000)
    options = page.locator("#selected-body .dev-pick option").all_text_contents()
    assert any("/dev/ttyFAKE1" in o for o in options)


def _polls_in_the_chart(page: Page, n: int):
    """The open Machine's chart holds this many polls."""
    expect(page.locator(f"{MACHINE} #chart-span")).to_have_text(
        f"last {n} poll{'' if n == 1 else 's'}", timeout=WITHIN_A_POLL
    )


@pytest.mark.e2e
def test_pin_identify_open_poll_and_sync(page: Page, fresh_url: str):
    """Pin → Open → M115: a poll each period, never stacked, and the node follows. The
    board was pinned before anyone asked it what it is, so its Machine opens as a
    devkit's, its port closed until Listen; listened to, it says a hello (the scripted
    monitor says one on every port). Pinned again once Query has said it is a printer,
    its Machine is a printer's, polling."""
    page.clock.install()
    page.goto(f"{fresh_url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
    _select(page, "printer_1")
    section = page.locator("#selected-body .device-section")
    pick = page.locator("#selected-body .dev-pick")
    expect(pick).to_be_visible(timeout=8000)
    pick.select_option("/dev/ttyFAKE1")

    page.locator("#selected-body .dev-pin").click()
    expect(section.locator(".dev-unpin")).to_be_visible(timeout=5000)
    expect(section.locator(".device-line")).to_contain_text("/dev/ttyFAKE1")
    expect(
        page.locator("#contents-list .contents-item[data-path='printer_1'] .dev-badge")
    ).to_be_visible()
    # Not asked what it is: its Machine is a devkit's, and Listen opens its port.
    section.locator(".dev-open").click()
    machine = page.locator(MACHINE)
    expect(machine.locator("#c-sketch")).to_be_visible(timeout=5000)
    machine.locator("#listen").click()
    expect(machine.locator("#log")).to_contain_text("blink", timeout=10000)
    page.evaluate("() => window.fractalViewer.closeMachine()")
    section.locator(".dev-unpin").click()

    # Query says it is a printer (M115); pinned, its link held, it is polled once.
    expect(pick).to_be_visible(timeout=5000)
    pick.select_option("/dev/ttyFAKE1")
    section.locator(".dev-query").click()
    expect(section.locator(".device-query")).to_contain_text("Marlin", timeout=8000)
    section.locator(".dev-pin").click()
    expect(section.locator(".temps")).to_be_visible(timeout=8000)

    # Open: one poll at once, then one each period, each after the last has answered.
    _hold_clock(page)
    section.locator(".dev-open").click()
    expect(machine.locator("#ident")).to_contain_text("Marlin Apothecary Simulator", timeout=8000)
    _polls_in_the_chart(page, 1)
    for n in (2, 3, 4):
        page.clock.fast_forward(POLL_MS)
        _polls_in_the_chart(page, n)
    page.clock.resume()

    # What the polls said reached the panel, the badge and the node's status.
    expect(section).to_contain_text("printing")
    expect(section.locator(".temps")).to_contain_text("/210°")
    badge = page.locator("#contents-list .contents-item[data-path='printer_1'] .dev-badge")
    expect(badge).to_contain_text("🖨 210°/60°")
    assert "printing" in badge.get_attribute("class")
    expect(page.locator("#status-select")).to_have_value("printing", timeout=WITHIN_A_POLL)

    # The other printer is untouched, and the pinned port is no longer offered to it.
    _select(page, "printer_2")
    expect(page.locator("#status-select")).to_have_value("idle")
    expect(page.locator("#selected-body .device-section")).not_to_contain_text("/dev/ttyFAKE1")


@pytest.mark.e2e
def test_editing_survives_polling(page: Page, printer_url: str):
    """A position edit in progress is not wiped by the 2 s poll re-render."""
    _identify(printer_url)
    _pin(printer_url, "printer_1")
    page.clock.install()
    page.goto(f"{printer_url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
    _select(page, "printer_1")
    expect(page.locator("#selected-body .device-section .dev-open")).to_be_visible(timeout=8000)
    _hold_clock(page)
    page.locator("#selected-body .dev-open").click()
    _polls_in_the_chart(page, 1)

    x = page.locator("#pos-x")
    x.click()
    x.fill("")
    x.type("123")
    for n in (2, 3):  # two polls land while the field is being edited
        page.clock.fast_forward(POLL_MS)
        _polls_in_the_chart(page, n)
    assert page.evaluate("document.activeElement && document.activeElement.id") == "pos-x"
    expect(x).to_have_value("123")
    # And the panel's device section did keep updating underneath.
    expect(page.locator("#selected-body .device-section .temps")).to_contain_text("/210°")
    page.clock.resume()

    # Unpin from the panel: immediate (no second scan), badge gone, node keeps its last status.
    page.locator("#selected-body .dev-unpin").click()
    expect(page.locator("#selected-body .dev-pick")).to_be_visible(timeout=3000)
    expect(
        page.locator("#contents-list .contents-item[data-path='printer_1'] .dev-badge")
    ).to_have_count(0)


@pytest.mark.e2e
def test_a_printer_s_machine_polls_it_within_a_bound(page: Page, printer_url: str):
    """⟳ Poll in an identified printer's Machine -- the firmware page's card's Poll, which
    went with the card -- polls it within a bound."""
    _identify(printer_url)
    page.goto(f"{printer_url}/firmware/monitor?port=/dev/ttyFAKE1")
    machine = page.locator(MACHINE)
    expect(machine.locator("#poll")).to_be_visible(timeout=15000)
    expect(machine.locator("#poll")).to_have_text("⟳ Poll")  # identified: a printer's Machine
    machine.locator("#auto").uncheck()
    machine.locator("#poll").click()
    expect(machine.locator("#c-state")).to_contain_text("printing", timeout=5000)
    expect(machine.locator("#c-hot")).to_contain_text("/210°")  # the simulator wobbles ±0.3°


@pytest.mark.e2e
def test_query_from_panel_and_the_machine(page: Page, printer_url: str):
    """Query asks M115 without pinning; the Machine's query box runs allowlisted codes only."""
    _identify(printer_url)
    _pin(printer_url, "printer_1")
    page.goto(f"{printer_url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
    _select(page, "printer_3")
    section = page.locator("#selected-body .device-section")
    # printer_1 holds /dev/ttyFAKE1; FAKE0 (the Uno) is free.
    expect(section.locator(".dev-pick")).to_be_visible(timeout=8000)
    section.locator(".dev-pick").select_option("/dev/ttyFAKE0")
    section.locator(".dev-query").click()
    expect(section.locator(".device-query")).to_contain_text("/dev/ttyFAKE0", timeout=8000)
    # The simulated engine answers M115 on any port, so FAKE0 identifies as a printer too --
    # and querying did not pin it.
    expect(section.locator(".device-query")).to_contain_text("Marlin Apothecary Simulator")
    expect(section.locator(".dev-unpin")).to_have_count(0)
    expect(section.locator(".dev-pick")).to_be_visible()

    # The Machine's query box: a printer's; refuses non-report codes via the API.
    _select(page, "printer_1")
    page.locator("#selected-body .dev-open").click()
    machine = page.locator(MACHINE)
    expect(machine.locator("#qform")).to_be_visible(timeout=8000)
    machine.locator("#q").fill("M119")
    machine.locator("#qform button").click()
    expect(machine.locator("#log")).to_contain_text("y_min: TRIGGERED", timeout=5000)
    machine.locator("#q").fill("M104 S200")
    machine.locator("#qform button").click()
    expect(machine.locator("#log")).to_contain_text("query refused", timeout=5000)
    expect(machine.locator("#qcodes option")).not_to_have_count(0)
    assert machine.locator("#qcodes option").count() >= 10


@pytest.mark.e2e
def test_manual_pin_poll_and_rescan(page: Page, printer_url: str):
    """Pin by typed identity; a poll lands in the badge without a Machine; Rescan scans
    once, and nothing scans on a schedule."""
    _identify(printer_url)
    _pin(printer_url, "printer_1")
    page.clock.install()
    page.goto(f"{printer_url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)

    # A typed identity that nothing detects pins as "not connected" and offers Rescan.
    _select(page, "printer_2")
    section = page.locator("#selected-body .device-section")
    expect(section.locator(".dev-manual")).to_be_visible(timeout=8000)
    section.locator(".dev-manual").fill("/dev/ender")
    section.locator(".dev-manual").press("Enter")
    expect(section).to_contain_text("not connected", timeout=5000)
    expect(section.locator(".dev-rescan")).to_be_visible()
    section.locator(".dev-unpin").click()
    expect(section.locator(".dev-pick")).to_be_visible(timeout=5000)

    # A poll of the bound printer, through the board model, updates the badge with no
    # Machine open.
    _select(page, "printer_1")
    expect(page.locator("#selected-body .dev-open")).to_be_visible(timeout=8000)
    page.evaluate("() => window.fractalViewer.pollNow('/dev/ttyFAKE1')")
    badge = page.locator("#contents-list .contents-item[data-path='printer_1'] .dev-badge")
    expect(badge).to_contain_text("/", timeout=5000)  # temps, not the bare 🖨
    expect(page.locator(MACHINE)).to_have_count(0)

    # Rescan is one fresh scan; time passing is none.
    scans = []
    page.on("request", lambda r: scans.append(r.url) if "/devices?fresh=1" in r.url else None)
    scan_done = "() => !window.fractalViewer.bindingsInFlight"
    _hold_clock(page)
    page.wait_for_function(scan_done)
    _select(page, "printer_2")
    section.locator(".dev-rescan").click()
    expect(page.locator("#status")).to_contain_text("device(s) detected", timeout=8000)
    page.wait_for_function(scan_done)
    assert len(scans) == 1
    page.clock.fast_forward(30000)
    page.wait_for_function(scan_done)
    assert len(scans) == 1, "the page looked for boards on a schedule"


@pytest.mark.e2e
def test_focused_monitor_page(page: Page, fresh_url: str):
    """The printer monitor's address: the printer's Machine, pinned nowhere, floating in
    front of the world on the default site, its port kept in the address -- status within
    a bound, cadence, log, query, reconnect, reset. A server of its own, so the log holds
    only this test's lines."""
    _identify(fresh_url)
    page.clock.install()
    page.goto(f"{fresh_url}/firmware/monitor?port=/dev/ttyFAKE1")
    expect(page).to_have_url(re.compile(r"/viewer/sites/garage\?machine=%2Fdev%2FttyFAKE1$"))
    expect(page.locator("#c-state")).to_contain_text("printing", timeout=15000)
    expect(page.locator("#ident")).to_contain_text("Marlin Apothecary Simulator")
    assert page.evaluate("() => window.apothecaryPanels.state('machine').where") == "free"
    expect(page.locator("#c-board")).to_contain_text("held", timeout=5000)
    expect(page.locator("#c-hot")).to_contain_text("/210°")

    # Cadence: from a fresh schedule, each period brings one poll -- charted, logged, and
    # the next one scheduled, which is when the timer changes -- never two.
    _hold_clock(page)
    page.evaluate("() => window.apothecaryMachine.schedule()")
    polls = page.evaluate(f"() => {MONITOR}.history.length")
    for n in (1, 2, 3):
        timer = page.evaluate(f"() => {MONITOR}.timer")
        page.clock.fast_forward(POLL_MS)
        page.wait_for_function(f"(t) => {MONITOR}.timer !== t", arg=timer)
        count = polls + n  # the history this file's earlier tests left, if any, then one per poll
        expect(page.locator("#chart-span")).to_have_text(
            f"last {count} poll{'' if count == 1 else 's'}"
        )
    expect(page.locator("#chart path")).to_have_count(4)  # two series + two targets

    # Poll traffic shows when asked for; hidden, only the story is left: open, M115,
    # queries, sys lines.
    sends = page.locator("#log .tx", has_text="M105")
    page.locator("#show-polls").check()
    expect(sends.first).to_be_visible()
    page.locator("#show-polls").uncheck()
    expect(sends).to_have_count(0)
    page.locator("#q").fill("M119")
    page.locator("#qform button").click()
    expect(page.locator("#log")).to_contain_text("y_min: TRIGGERED", timeout=5000)
    page.locator("#q").fill("G28")
    page.locator("#qform button").click()
    expect(page.locator("#log")).to_contain_text("query refused", timeout=5000)

    # Reconnect keeps the log and comes back polling; reset shows the boot banner.
    page.locator("#reconnect").click()
    expect(page.locator("#log .sys", has_text="closed /dev/ttyFAKE1")).to_be_visible(timeout=6000)
    expect(page.locator("#log .sys", has_text="opened /dev/ttyFAKE1").last).to_be_visible()
    expect(page.locator("#log")).to_contain_text("y_min: TRIGGERED")  # earlier entries survived
    page.once("dialog", lambda d: d.accept())
    page.locator("#reset").click()
    expect(page.locator("#log .boot", has_text="start")).to_be_visible(timeout=8000)

    # Release drops the link and stops auto-poll: no poll is left scheduled to reopen it.
    page.locator("#release").click()
    expect(page.locator("#c-board")).to_contain_text("not held", timeout=5000)
    assert not page.locator("#auto").is_checked()
    assert page.evaluate(f"() => {MONITOR}.timer") is None
    n1 = page.locator("#log .sys").count()
    page.clock.fast_forward(3 * POLL_MS)
    expect(page.locator("#c-board")).to_contain_text("not held")
    assert page.locator("#log .sys").count() == n1


@pytest.mark.e2e
def test_board_inside_the_printer_drives_it(page: Page, printer_url: str):
    """Pin the port to the mainboard: the printer row and panel speak for it; its status follows."""
    page.clock.install()
    page.goto(f"{printer_url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
    section = page.locator("#selected-body .device-section")
    _expand_to(page, BOARD)
    expect(page.locator("#selected-body .prop-row", has_text="Name")).to_contain_text("mainboard")
    expect(section.locator(".dev-pick")).to_be_visible(timeout=8000)
    section.locator(".dev-pick").select_option("/dev/ttyFAKE1")
    section.locator(".dev-query").click()  # identifies the port (M115) without pinning
    expect(section.locator(".device-query")).to_contain_text("Marlin", timeout=8000)
    section.locator(".dev-pin").click()
    expect(section.locator(".dev-unpin")).to_be_visible(timeout=5000)

    # The printer's row carries the board's badge (dimmed, "via"), and its panel says so.
    badge = page.locator("#contents-list .contents-item[data-path='printer_1'] .dev-badge")
    expect(badge).to_be_visible()
    assert "via" in badge.get_attribute("class")
    assert badge.get_attribute("title").startswith("via frame_system.mainboard")
    _select(page, "printer_1")
    expect(section).to_contain_text("via frame_system.mainboard")
    expect(section.locator(".dev-unpin")).to_have_count(
        0
    )  # unpin from the board, not through the printer
    section.locator(".dev-open").click()
    expect(page.locator(MACHINE)).to_be_visible(timeout=5000)
    # The poll's sync lands on the tree even though an earlier request had already
    # moved the server's node, so printer_1 turns "printing" without a refresh.
    expect(page.locator("#status-select")).to_have_value("printing", timeout=5000)
    page.evaluate("() => window.fractalViewer.closeMachine()")

    # The via link jumps to the board's own row and panel.
    section.locator(".dev-via").click()
    expect(page.locator("#selected-body .prop-row", has_text="Name")).to_contain_text("mainboard")
    expect(section.locator(".dev-unpin")).to_be_visible()
    section.locator(".dev-unpin").click()
    expect(section.locator(".dev-manual")).to_be_visible(timeout=5000)
    expect(
        page.locator("#contents-list .contents-item[data-path='printer_1'] .dev-badge")
    ).to_have_count(0)


# A node's body as the world draws it, in apothecary's frame (z up; three.js's y is
# apothecary's z): the real geometry, centred on the node's envelope. None while the
# placeholder box stands in for it.
DRAWN_BODY = """(key) => {
    const mesh = window.fractalViewer.meshByName[key];
    if (!mesh || mesh.userData.isPlaceholder || mesh.userData.isDot) return null;
    mesh.geometry.computeBoundingBox();
    const b = mesh.geometry.boundingBox, p = mesh.position;
    return { min: { x: b.min.x + p.x, y: b.min.z + p.z, z: b.min.y + p.y },
             max: { x: b.max.x + p.x, y: b.max.z + p.z, z: b.max.y + p.y } };
}"""

# The world's wire box for a printer's build volume: a unit box scaled and placed.
WIRE_VOLUME = """(name) => {
    const box = window.fractalViewer.buildVolumeMeshByName[name];
    if (!box) return null;
    const c = box.position, s = box.scale;
    return { min: { x: c.x - s.x / 2, y: c.z - s.z / 2, z: c.y - s.y / 2 },
             max: { x: c.x + s.x / 2, y: c.z + s.z / 2, z: c.y + s.y / 2 } };
}"""

# The build volume the board's port lays its marks in (the bed, the nozzle, a reading),
# in the printer's frame and placed at the printer.
MARKED_VOLUME = """(path) => {
    const m = window.fractalViewer.marks[path];
    if (!m || !m.marks) return null;
    const v = m.marks.volume(), g = m.marks.group.position;
    const at = { x: g.x, y: g.z, z: g.y };
    const add = (p) => ({ x: p.x + at.x, y: p.y + at.y, z: p.z + at.z });
    return { min: add(v.min), max: add(v.max) };
}"""


@pytest.mark.e2e
def test_the_printer_s_drawing_encloses_its_board_and_its_build_volume(
    page: Page, printer_url: str
):
    """The bodies land where the site puts them, in the world: printer_1 drawn at the
    garage's root encloses its mainboard, drawn inside its frame, and its build volume,
    both the world's wire box and the marks its board's port lays on the bed. (A node's
    STL arrives in its parent's frame; drawn untranslated, the printer sat a bench-width
    away.) The monitor page's board view held this; the world that replaced it holds it
    now."""
    _pin(printer_url, BOARD)
    _identify(printer_url)
    page.goto(f"{printer_url}/viewer/sites/garage")
    contents = page.locator("#contents-list .contents-item")
    expect(contents.first).to_be_visible(timeout=15000)
    page.wait_for_function(
        "() => { const m = window.fractalViewer.marks['printer_1']; return m && m.marks; }",
        timeout=15000,
    )
    page.evaluate("() => window.fractalViewer.waveDone")
    printer = page.evaluate(DRAWN_BODY, "printer_1")
    assert printer, "printer_1 is drawn from its part's STL"
    wire = page.evaluate(WIRE_VOLUME, "printer_1")
    marked = page.evaluate(MARKED_VOLUME, "printer_1")
    origin = page.evaluate("() => window.fractalViewer.nodeByPath('printer_1').position")

    page.evaluate("() => { const v = window.fractalViewer; v.zoomIn('printer_1'); }")
    page.evaluate("() => window.fractalViewer.zoomIn('frame_system')")
    expect(contents.filter(has_text="mainboard")).to_be_visible(timeout=10000)
    page.evaluate("() => window.fractalViewer.waveDone")
    board = page.evaluate(DRAWN_BODY, BOARD)
    assert board, "the mainboard is drawn from its part's STL"

    drawn = {"printer": printer, "board": board, "wire": wire, "marked": marked}
    for name in ("board", "wire", "marked"):
        inner = drawn[name]
        for axis in "xyz":
            assert printer["min"][axis] - 1 <= inner["min"][axis], (name, axis, drawn)
            assert inner["max"][axis] <= printer["max"][axis] + 1, (name, axis, drawn)
    # An Ender 3, drawn as it is: 472 wide with the PSU and the spool tube, and its
    # board on the floor of the electronics box (21 up, the board 5 in it).
    assert printer["max"]["x"] - printer["min"]["x"] == pytest.approx(472, abs=1)
    assert board["min"]["z"] - origin["z"] == pytest.approx(26, abs=1)


@pytest.mark.e2e
def test_a_poll_answered_after_arming_does_not_disarm_the_page(page: Page, printer_url: str):
    """A poll asked before Control is armed carries the latch as it was then
    (disarmed). If its answer lands after the arm's, the page must not take it:
    the server is armed, and the pad stays open."""
    _identify(printer_url)
    page.goto(f"{printer_url}/firmware/monitor?port=/dev/ttyFAKE1")
    expect(page.locator("#c-state")).not_to_have_text("—", timeout=10000)
    page.locator("#auto").uncheck()  # only the poll this test sends

    # The poll's answer is read at once (disarmed) and handed to the page late,
    # after the arm has answered: inside the page, so the arm is not held up.
    page.evaluate(
        """() => {
            const real = window.fetch;
            window.__held = 0;
            window.fetch = async (url, opts) => {
                const r = await real(url, opts);
                if (String(url).includes('/firmware/printers/status')) {
                    window.__held++;
                    await new Promise((ok) => setTimeout(ok, 1500));
                }
                return r;
            };
        }"""
    )
    page.locator("#poll").click()
    page.locator("#ctl").click()
    expect(page.locator("#control")).to_be_visible(timeout=5000)
    page.wait_for_timeout(2500)  # the held answer has landed by now
    assert page.evaluate("() => window.__held") >= 1, "the poll was not held"
    assert page.locator("#ctl").is_checked()
    expect(page.locator("#control")).to_be_visible()
    page.locator("#ctl-disarm").click()


def test_control_overlay_is_latched(page: Page, printer_url: str):
    """Nothing heats or moves until Control is armed; armed, the effect shows within a poll."""
    _identify(printer_url)
    page.goto(f"{printer_url}/firmware/monitor?port=/dev/ttyFAKE1")
    expect(page.locator("#c-state")).not_to_have_text("—", timeout=10000)
    expect(page.locator("#control")).to_be_hidden()
    assert not page.locator("#ctl").is_checked()
    # The API refuses control while disarmed; only the emergency stop would go.
    r = page.request.post(
        f"{printer_url}/firmware/printers/command",
        data={"port": "/dev/ttyFAKE1", "command": "M140 S60"},
    )
    assert r.status == 409

    page.locator("#ctl").check()
    expect(page.locator("#control")).to_be_visible(timeout=5000)
    expect(page.locator("#ctl-ttl")).to_contain_text(":")
    page.locator("#h-bed").fill("45")
    page.locator("#control button[data-cmd='M140 S{h-bed}']").click()
    expect(page.locator("#c-bed")).to_contain_text("/45°", timeout=WITHIN_A_POLL)
    expect(page.locator("#log .tx.control", has_text="M140 S45")).to_be_visible()

    # An out-of-bounds value never reaches the board.
    page.locator("#h-hot").fill("900")
    page.locator("#control button[data-cmd='M104 S{h-hot}']").click()
    expect(page.locator("#ctl-sent")).to_contain_text("above 300", timeout=5000)
    assert page.locator("#log .tx.control", has_text="M104 S900").count() == 0

    # Pause the SD print, then a jog: three lines, relative mode restored, the
    # position card follows; resume afterwards.
    page.locator("#control button[data-cmd='M25']").click()
    expect(page.locator("#c-state")).to_contain_text("idle", timeout=WITHIN_A_POLL)
    page.locator("#control button[data-step='10']").click()
    page.locator("#control button[data-jog='Y+']").click()
    expect(page.locator("#log .tx.control", has_text="G90").last).to_be_visible(timeout=8000)
    expect(page.locator("#c-pos")).to_contain_text("Y10.0", timeout=WITHIN_A_POLL)
    page.locator("#control button[data-cmd='M24']").click()
    expect(page.locator("#c-state")).to_contain_text("printing", timeout=WITHIN_A_POLL)

    # Disarm: overlay gone, commands refused again; the latch state survives a reload.
    page.locator("#ctl-disarm").click()
    expect(page.locator("#control")).to_be_hidden(timeout=3000)
    assert not page.locator("#ctl").is_checked()
    page.locator("#ctl").check()
    expect(page.locator("#control")).to_be_visible(timeout=5000)
    page.reload()
    expect(page.locator("#c-state")).not_to_have_text("—", timeout=10000)
    expect(page.locator("#control")).to_be_visible(timeout=5000)
    page.locator("#ctl-disarm").click()
    expect(page.locator("#control")).to_be_hidden(timeout=3000)


@pytest.mark.e2e
def test_a_bed_reading_needs_no_latch_and_a_probe_does(page: Page, fresh_url: str):
    """Read mesh needs no latch and fills the heatmap; Probe bed needs it, shows its stage
    while the port is held, and saves a record the history lists. A server of its own:
    no reading yet, and a log that holds only this test's lines."""
    _identify(fresh_url)
    page.goto(f"{fresh_url}/firmware/monitor?port=/dev/ttyFAKE1")
    expect(page.locator("#c-state")).not_to_have_text("—", timeout=10000)
    expect(page.locator("#level-stats")).to_contain_text("no reading yet")
    expect(page.locator("#level-history > div")).to_have_count(0)

    # A read: no latch, no movement, a 5x5 mesh from the simulator within a few seconds.
    page.locator("#level-read").click()
    expect(page.locator("#mesh .cell")).to_have_count(25, timeout=15000)
    expect(page.locator("#level-stats")).to_contain_text("read ·")
    expect(page.locator("#level-stats")).to_contain_text("probe offset X-44 Y-10 Z-3.15")
    expect(page.locator("#level-history > div")).to_have_count(1)
    expect(page.locator("#level-history .pick.on")).to_contain_text("read")
    assert page.locator("#log .tx.control", has_text="G29").count() == 0

    # A probe is refused while disarmed and never reaches the board.
    page.locator("#level-probe").click()
    expect(page.locator("#log .sys", has_text="arm control first")).to_be_visible(timeout=3000)
    assert page.locator("#log .tx.control", has_text="G29").count() == 0

    # Armed, the page asks, then homes and probes; the state card says the port is
    # held for the duration, and the record appears when it is done.
    page.locator("#ctl").check()
    expect(page.locator("#control")).to_be_visible(timeout=5000)
    page.once("dialog", lambda d: d.accept())
    page.locator("#level-probe").click()
    expect(page.locator("#level-job")).to_contain_text("…", timeout=5000)
    expect(page.locator("#level-job")).to_have_text("", timeout=30000)
    expect(page.locator("#level-history > div")).to_have_count(2, timeout=5000)
    expect(page.locator("#level-stats")).to_contain_text("probe ·")
    expect(page.locator("#log .tx.control", has_text="G29")).to_have_count(1)
    expect(page.locator("#log .sys", has_text="bed reading saved")).to_have_count(2)
    record_id = page.evaluate("() => window.apothecaryMachine.level.shown().id")
    r = page.request.get(f"{fresh_url}/firmware/printers/leveling/{record_id}")
    assert r.ok and len(r.json()["mesh"]) == 5 and r.json()["method"] == "probe"


@pytest.mark.e2e
def test_the_reading_shown_is_drawn_over_the_bed(page: Page, printer_url: str):
    """The reading a printer's Machine shows is the one the world draws over its bed:
    the newest at first, a 5x5 surface; picking another from the Machine's history
    swaps the heatmap and the surface."""
    _pin(printer_url, BOARD)
    _identify(printer_url)
    read_id = _read_the_bed(printer_url)
    probe_id = _read_the_bed(printer_url, probe=True)
    page.goto(f"{printer_url}/firmware/monitor?port=/dev/ttyFAKE1")
    machine = page.locator(MACHINE)
    expect(machine.locator("#c-state")).not_to_have_text("—", timeout=15000)
    assert page.evaluate("() => window.apothecaryPanels.state('machine').where") == {
        "tether": "printer_1"
    }
    marks = "window.fractalViewer.marks['printer_1']"
    shown = f"() => {marks} && {marks}.marks && {marks}.marks.mesh()"
    page.wait_for_function(f"(id) => ({shown})() && ({shown})().record_id === id", arg=probe_id)
    assert page.evaluate(f"() => {marks}.marks.mesh().rows") == 5
    machine.locator("#level-history .pick", has_text="read").first.click()
    expect(machine.locator("#level-stats")).to_contain_text("read ·")
    page.wait_for_function(f"(id) => ({shown})().record_id === id", arg=read_id)


@pytest.mark.e2e
def test_a_corner_button_is_four_lines_to_paper_height(page: Page, printer_url: str):
    """A corner button: four absolute lines, the last one at paper height, sent armed; the
    corners are the printer's own, from the build volume where it is pinned."""
    _pin(printer_url, BOARD)
    _identify(printer_url)
    page.goto(f"{printer_url}/firmware/monitor?port=/dev/ttyFAKE1")
    expect(page.locator("#c-state")).not_to_have_text("—", timeout=10000)
    lines = page.evaluate("() => window.apothecaryMachine.level.lines('BR')")
    assert lines == ["G90", "G1 Z5 F3000", "G1 X190 Y190 F3000", "G1 Z0.2 F600"]
    page.locator("#ctl").check()
    expect(page.locator("#control")).to_be_visible(timeout=5000)
    page.locator("#control button[data-cmd='M25']").click()  # the simulator is printing
    expect(page.locator("#c-state")).to_contain_text("idle", timeout=WITHIN_A_POLL)
    page.locator("#level-card button[data-corner='FL']").click()
    expect(page.locator("#log .tx.control", has_text="G1 X30 Y30 F3000")).to_be_visible(
        timeout=8000
    )
    expect(page.locator("#c-pos")).to_contain_text("X30.0", timeout=WITHIN_A_POLL)


# Seconds to stream, dwell or no dwell: each line is a round trip to the simulator, a
# millisecond at least, so a pause and a cancel land mid-file.
SLOW = "".join(f"G1 X{i % 200} Y{i % 200}\n" for i in range(6000))
# A minute at the least, whatever else the machine is doing: each move dwells 20 ms
# on the simulator's own clock, so a print still running when a slow page gets to
# it is not left to the page's speed.
A_MINUTE = "".join(f"G1 X{i % 200} Y{i % 200}\nG4 P20\n" for i in range(3000))


@pytest.mark.e2e
def test_a_file_is_kept_or_refused_and_nothing_leaves_disarmed(page: Page, printer_url: str):
    """Keep a file from the page; one the seam refuses is kept and said so; disarmed,
    Print sends nothing."""
    _identify(printer_url)
    page.goto(f"{printer_url}/firmware/monitor?port=/dev/ttyFAKE1")
    expect(page.locator("#c-state")).not_to_have_text("—", timeout=10000)
    expect(page.locator("#print-start")).to_be_disabled()
    page.locator("#print-file").set_input_files(
        {"name": "slow cube.gcode", "mimeType": "text/plain", "buffer": SLOW.encode()}
    )
    expect(page.locator("#print-pick")).to_contain_text(
        "slow cube.gcode · 6000 lines", timeout=8000
    )
    expect(page.locator("#log .sys", has_text="kept slow cube.gcode: 6000 lines")).to_be_visible()
    expect(page.locator("#print-start")).to_be_enabled()
    # A file the seam refuses is kept, said so, and never sent.
    page.locator("#print-file").set_input_files(
        {"name": "eeprom.gcode", "mimeType": "text/plain", "buffer": b"G28\nM500\n"}
    )
    expect(page.locator("#print-pick")).to_contain_text("refused: line 2: M500", timeout=8000)
    page.locator("#print-pick").select_option(
        label=page.locator("#print-pick option", has_text="slow cube").text_content()
    )

    # Disarmed: nothing leaves the page.
    page.locator("#print-start").click()
    expect(page.locator("#log .sys", has_text="arm control first")).to_be_visible(timeout=3000)
    assert not page.evaluate("() => window.apothecaryMachine.print.job().running")


def _armed_with_the_card_paused(page: Page, url: str, file_id: str):
    """The printer's Machine with a kept file picked, control armed and the card's own
    print paused, which a print from here needs."""
    _identify(url)
    page.goto(f"{url}/firmware/monitor?port=/dev/ttyFAKE1")
    expect(page.locator("#c-state")).not_to_have_text("—", timeout=10000)
    expect(page.locator(f"#print-pick option[value='{file_id}']")).to_be_attached()
    page.locator("#print-pick").select_option(file_id)
    page.locator("#ctl").check()
    expect(page.locator("#control")).to_be_visible(timeout=5000)
    page.locator("#control button[data-cmd='M25']").click()
    expect(page.locator("#c-state")).to_contain_text("idle", timeout=WITHIN_A_POLL)


@pytest.mark.e2e
def test_a_print_from_here_pauses_from_the_ring_and_cancels(page: Page, printer_url: str):
    """Print a kept file armed; the ring's Print cell pauses it, Resume resumes, Cancel
    cancels, and the record says so."""
    # A minute at the least, so the cancel lands mid-file however long the page takes to
    # get to it.
    _armed_with_the_card_paused(page, printer_url, _keep(printer_url, "slow cube.gcode", A_MINUTE))
    page.once("dialog", lambda d: d.accept())
    page.locator("#print-start").click()
    expect(page.locator("#print-progress")).to_contain_text(
        "slow cube.gcode · printing", timeout=5000
    )
    expect(page.locator("#c-state")).to_contain_text("printing", timeout=WITHIN_A_POLL)
    expect(page.locator("#c-state-s")).to_contain_text("print from here: printing")
    expect(
        page.locator("#log .sys", has_text="print started: slow cube.gcode (6000 lines)")
    ).to_be_visible()
    # The stream stays out of the log; the progress bar moves.
    page.wait_for_function("() => window.apothecaryMachine.print.job().sent >= 6", timeout=8000)
    assert page.locator("#log .tx", has_text="G1 X3 Y3").count() == 0

    # Pause from the ring: Control > Print > Pause goes to the print from here, not the card.
    # Nothing is selected and the Machine stands for a port pinned nowhere, so m opens its
    # device ring, as it did on the monitor page.
    m25_before = page.locator("#log .tx.control", has_text="M25").count()
    page.keyboard.press("m")
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    page.keyboard.press("7")
    page.keyboard.press("9")
    expect(page.locator("#ring-overlay .title")).to_have_text("Print")
    page.keyboard.press("6")
    expect(page.locator("#ring-overlay")).to_have_count(0)
    expect(page.locator("#print-progress")).to_contain_text("· paused ·", timeout=5000)
    assert page.locator("#log .tx.control", has_text="M25").count() == m25_before
    sent = page.evaluate("() => window.apothecaryMachine.print.job().sent")
    # The server's job is paused too; that a paused job feeds nothing is test_firmware_gcode's.
    job = page.request.get(f"{printer_url}/firmware/printers/print?port=/dev/ttyFAKE1").json()
    assert job["stage"] == "paused" and job["sent"] <= sent + 1
    expect(page.locator("#print-resume")).to_be_enabled()
    page.locator("#print-resume").click()
    expect(page.locator("#print-progress")).to_contain_text("· printing ·", timeout=5000)
    page.wait_for_function(
        "(n) => window.apothecaryMachine.print.job().sent > n + 2", arg=sent, timeout=8000
    )
    page.once("dialog", lambda d: d.accept())
    page.locator("#print-cancel").click()
    expect(page.locator("#print-progress")).to_contain_text("· cancelled ·", timeout=8000)
    expect(page.locator("#print-history")).to_contain_text(
        "print · slow cube.gcode · cancelled", timeout=5000
    )
    expect(page.locator("#log .tx.control", has_text="M104 S0").last).to_be_visible()
    expect(page.locator("#print-start")).to_be_enabled(timeout=5000)
    # Cancel ended the print's job, cancelled, and said why.
    job_id = page.evaluate("() => window.apothecaryMachine.print.job().job_id")
    job = page.request.get(f"{printer_url}/jobs/{job_id}").json()
    assert job["outcome"] == "cancelled" and "heaters" in job["reason"], job
    assert job["input"]["name"] == "slow cube.gcode" and job["finished_at"]


@pytest.mark.e2e
def test_a_short_file_prints_to_the_end(page: Page, printer_url: str):
    """A short file runs to the end: done, recorded, and the state card is the board's again."""
    dot = _keep(printer_url, "dot.gcode", "G28\nG1 X5 Y5 E0.1\nM84\n")
    _armed_with_the_card_paused(page, printer_url, dot)
    expect(page.locator("#print-pick")).to_contain_text("dot.gcode · 3 lines")
    page.once("dialog", lambda d: d.accept())
    page.locator("#print-start").click()
    expect(page.locator("#print-progress")).to_contain_text("dot.gcode · done · 3/3", timeout=10000)
    expect(page.locator("#print-history")).to_contain_text("dot.gcode · done · 3/3")
    expect(page.locator("#c-state")).to_contain_text("idle", timeout=WITHIN_A_POLL)
    r = page.request.get(f"{printer_url}/jobs?machine=/dev/ttyFAKE1&kind=print")
    newest = r.json()[0]
    assert (newest["input"]["name"], newest["outcome"]) == ("dot.gcode", "done")


@pytest.mark.e2e
def test_a_print_from_the_card_is_a_job_that_names_the_part_it_makes(page: Page, printer_url: str):
    """Pinned in the garage, the card offers the garage's parts and pieces, the printer's
    own left out; a print started naming one is a job of the garage with its file, its
    machine, the part and how it ended, and the card's history is the printer's jobs."""
    _pin(printer_url, BOARD)
    _identify(printer_url)
    dot = _keep(printer_url, "dot.gcode", "G28\nG1 X5 Y5 E0.1\nM84\n")
    _armed_with_the_card_paused(page, printer_url, dot)
    part = page.locator("#print-part")
    expect(part.locator("option[value='footpedal']")).to_be_attached(timeout=5000)
    expect(part.locator("option[value^='printer_1']")).to_have_count(0)
    expect(page.locator("#print-where")).to_have_text("in garage")
    part.select_option("footpedal")
    page.once("dialog", lambda d: d.accept())
    page.locator("#print-start").click()
    expect(page.locator("#print-progress")).to_contain_text("dot.gcode · done · 3/3", timeout=10000)
    expect(page.locator("#print-history")).to_contain_text(
        "print · dot.gcode → footpedal · done · 3/3 lines", timeout=5000
    )
    newest = page.request.get(f"{printer_url}/jobs?site=garage").json()[0]
    assert (newest["kind"], newest["input"]["name"], newest["outcome"]) == (
        "print",
        "dot.gcode",
        "done",
    )
    assert newest["part"] == {"path": "footpedal", "name": "footpedal"}
    assert (newest["machine"]["port"], newest["machine"]["path"]) == (PRINTER, BOARD)
    assert newest["started_at"] and newest["finished_at"]


@pytest.mark.e2e
def test_the_print_records_kept_before_jobs_show_in_the_cards_history(
    page: Page, start_server, tmp_path
):
    """A print record kept before a print was a job is in the printer's history,
    carried over as a print job, on a server that never saw it printed."""
    records = tmp_path / "state" / "prints" / "records"
    records.mkdir(parents=True)
    (records / "20260920T132512.468-dev_ttyFAKE1.json").write_text(
        json.dumps(
            {
                "id": "20260920T132512.468-dev_ttyFAKE1",
                "port": PRINTER,
                "file_id": "20260920T130000.000-old_cube",
                "name": "old cube.gcode",
                "at": "2026-09-20T13:25:12.468000+00:00",
                "finished": "2026-09-20T13:55:12.468000+00:00",
                "outcome": "done",
                "sent": 12,
                "total": 12,
                "error": None,
                "firmware": "Marlin",
                "lines": ["ok"],
            }
        )
    )
    url = start_server({"APOTHECARY_STATE_DIR": str(tmp_path / "state")})
    _identify(url)
    page.goto(f"{url}/firmware/monitor?port={PRINTER}")
    expect(page.locator("#print-history")).to_contain_text(
        "print · old cube.gcode · done · 12/12 lines", timeout=10000
    )
    log = page.locator("#print-history a").first
    expect(log).to_have_attribute("href", re.compile(r"/jobs/20260920T132512\.468-dev_ttyFAKE1$"))


def _printing(url: str, file_id: str, part: str | None = None) -> dict:
    """A print started over the API, as the card starts one: armed, the card's own print
    paused (the simulator is mid-way through one) and polled, then the file sent."""
    with httpx.Client(base_url=url, timeout=15.0) as http:
        http.post(
            "/firmware/printers/control", json={"port": PRINTER, "armed": True}
        ).raise_for_status()
        http.post(
            "/firmware/printers/command", json={"port": PRINTER, "command": "M25"}
        ).raise_for_status()
        http.get("/firmware/printers/status", params={"port": PRINTER}).raise_for_status()
        r = http.post(
            "/firmware/printers/print", json={"port": PRINTER, "file_id": file_id, "part": part}
        )
        r.raise_for_status()
        return r.json()


def _until_it_ends(url: str, cancel: bool = False) -> dict:
    with httpx.Client(base_url=url, timeout=15.0) as http:
        if cancel:
            http.post("/firmware/printers/print/cancel", json={"port": PRINTER})
        for _ in range(600):  # 30 s
            job = http.get("/firmware/printers/print", params={"port": PRINTER}).json()
            if not job["running"]:
                return job
            time.sleep(0.05)
    raise AssertionError(f"the print did not end: {job}")


@pytest.mark.e2e
def test_site_lists_the_sites_jobs_and_a_row_opens_its_machine(page: Page, printer_url: str):
    """Site's Jobs lists the jobs of the garage's machines: a print running on printer_1
    on top, then the one before it with the part it made and how it ended; the row of
    either selects printer_1 and opens its Machine, from whatever level is shown."""
    _pin(printer_url, BOARD)
    _identify(printer_url)
    dot = _keep(printer_url, "dot.gcode", "G28\nG1 X5 Y5 E0.1\nM84\n")
    slow = _keep(printer_url, "slow cube.gcode", A_MINUTE)
    before = _printing(printer_url, dot, part="footpedal")
    assert _until_it_ends(printer_url)["stage"] == "done"
    running = _printing(printer_url, slow)
    try:
        page.goto(f"{printer_url}/viewer/sites/garage")
        expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
        jobs = page.locator("#site-jobs")
        expect(jobs.locator("summary")).to_contain_text("running", timeout=10000)
        jobs.locator("summary").click()
        rows = page.locator("#site-jobs-list li[data-job]")
        expect(rows.first).to_have_attribute("data-job", running["job_id"])
        expect(rows.first).to_have_class(re.compile(r"\brunning\b"))
        expect(rows.first).to_contain_text("printer_1 · print · slow cube.gcode · running")
        expect(rows.nth(1)).to_have_attribute("data-job", before["job_id"])
        expect(rows.nth(1)).to_contain_text("printer_1 · print · dot.gcode → footpedal · done")
        # From a level below, the row steps out to printer_1, selects it and opens it.
        page.locator("#contents-list .contents-item[data-path='workbench']").dblclick()
        expect(page.locator("#contents-list .contents-item[data-path='printer_1']")).to_have_count(
            0, timeout=10000
        )
        rows.first.click()
        machine = page.locator(".panel[data-panel='machine']")
        expect(machine).to_be_visible(timeout=10000)
        expect(machine.locator(".panel-name")).to_contain_text("printer_1 · /dev/ttyFAKE1")
        expect(page.locator("#selected-body .prop-row", has_text="Name")).to_contain_text(
            "printer_1"
        )
        # It ends: the row says how, and running is no longer said.
        ended = _until_it_ends(printer_url, cancel=True)
        assert ended["stage"] == "cancelled"
        expect(rows.first).to_contain_text("slow cube.gcode · cancelled", timeout=10000)
        expect(jobs.locator("summary")).not_to_contain_text("running")
    finally:
        _until_it_ends(printer_url, cancel=True)


def _wearing_its_badge(page: Page, url: str):
    """The garage with the printer's board pinned and identified: the badge over printer_1."""
    _pin(url, BOARD)
    # Until the board is identified it wears a devkit's badge on its own node; once
    # it is known to be a printer the badge stands over the printer it drives.
    _identify(url)
    page.clock.install()
    page.goto(f"{url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
    badge = page.locator(".world-badge[data-path='printer_1']")
    expect(badge).to_be_visible(timeout=15000)
    return badge


@pytest.mark.e2e
def test_the_world_wears_its_machines(page: Page, printer_url: str):
    """A pinned printer stands under a badge in the 3D view that follows it as the camera
    moves and updates within a poll; its nozzle is drawn at its node."""
    badge = _wearing_its_badge(page, printer_url)
    expect(badge).to_contain_text("🖨")
    assert page.evaluate("() => window.fractalViewer.anchors.keys()") == ["printer_1"]

    # Fixed to the printer: drawn where the top of its envelope projects, to the pixel.
    def projected():
        return page.evaluate(
            """() => {
                const v = window.fractalViewer;
                const p = v.anchorPointFor('printer_1').project(v.camera);
                const w = v.canvas.clientWidth, h = v.canvas.clientHeight;
                const at = v.anchors.at('printer_1');
                return { x: (p.x + 1) / 2 * w, y: (1 - p.y) / 2 * h, at };
            }"""
        )

    got = projected()
    assert abs(got["at"]["x"] - got["x"]) < 1 and abs(got["at"]["y"] - got["y"]) < 1
    # The camera moves: the badge is where the printer now projects, within a frame.
    page.evaluate(  # a pan: camera and target move together, the world slides across
        "() => { const v = window.fractalViewer; v.camera.position.x += 1500;"
        " v.orbitControls.target.x += 1500; v.orbitControls.update(); }"
    )
    page.evaluate(FRAMES, 2)
    moved = projected()
    assert abs(moved["at"]["x"] - got["at"]["x"]) > 20
    assert abs(moved["at"]["x"] - moved["x"]) < 1 and abs(moved["at"]["y"] - moved["y"]) < 1

    # A poll lands in the badge within the poll interval, and moves the nozzle marker.
    page.evaluate("() => window.fractalViewer.pollNow('/dev/ttyFAKE1')")
    expect(badge).to_contain_text("printing", timeout=WITHIN_A_POLL)
    expect(badge).to_contain_text("°/")
    page.wait_for_function(
        "() => { const m = window.fractalViewer.marks['printer_1']; return m && m.marks; }",
        timeout=10000,
    )
    st = page.evaluate(
        "() => window.fractalViewer.bindings['printer_1.frame_system.mainboard'].printer_status"
    )
    target = page.evaluate("() => window.fractalViewer.marks['printer_1'].marks.target()")
    assert target["x"] == pytest.approx(st["position"]["x"], abs=0.01)


@pytest.mark.e2e
def test_a_reading_lies_on_the_bed_and_the_badge_selects_its_printer(page: Page, printer_url: str):
    """A bed reading saved on the port is drawn on the printer's bed; zoomed in, the badge
    stays over the printer, a click on it selects the printer, and unpinned it goes."""
    badge = _wearing_its_badge(page, printer_url)
    marks = "window.fractalViewer.marks['printer_1']"
    page.wait_for_function(f"() => {marks} && {marks}.marks", timeout=10000)
    record_id = _read_the_bed(printer_url)
    page.clock.fast_forward(5000)  # the world asks for the newest reading at most every 5 s
    page.evaluate("() => window.fractalViewer.rescanDevices()")
    page.wait_for_function(
        f"(id) => {marks}.marks.mesh() && {marks}.marks.mesh().record_id === id",
        arg=record_id,
        timeout=15000,
    )
    assert page.evaluate(f"() => {marks}.marks.mesh().rows") == 5

    # Zoomed into the printer the badge stays over it; a click on it selects the printer.
    contents = page.locator("#contents-list .contents-item")
    page.evaluate("() => window.fractalViewer.zoomIn('printer_1')")
    expect(contents.filter(has_text="gantry_system")).to_be_visible(timeout=10000)
    page.evaluate(FRAMES, 2)
    expect(badge).to_be_visible()
    page.evaluate("() => window.fractalViewer.jumpTo(0)")
    expect(contents.filter(has_text="workbench")).to_be_visible(timeout=10000)
    page.evaluate(FRAMES, 2)
    badge.click()
    expect(page.locator("#selected-body .prop-row", has_text="Name")).to_contain_text(
        "printer_1", timeout=5000
    )
    # Unpinned, the badge and the marks go.
    page.request.delete(f"{printer_url}/sites/garage/nodes/{BOARD}/device")
    page.evaluate("() => window.fractalViewer.rescanDevices()")
    expect(badge).to_have_count(0, timeout=10000)
    assert page.evaluate("() => Object.keys(window.fractalViewer.marks)") == []


@pytest.mark.e2e
def test_the_machine_stands_in_front_of_the_world(page: Page, printer_url: str):
    """A badge click opens the Machine in a popup tethered to the printer: the cards
    and latch the monitor page had, on the module it was made of; a jog from it moves
    the world's nozzle ahead of the poll; its comms log is in it, the board's one log;
    the ring's verbs go to it; closing it stops its polling."""
    _pin(printer_url, BOARD)
    _identify(printer_url)
    page.goto(f"{printer_url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
    badge = page.locator(".world-badge[data-path='printer_1']")
    expect(badge).to_be_visible(timeout=15000)
    badge.click()
    machine = page.locator(".panel[data-panel='machine']")
    expect(machine).to_be_visible(timeout=3000)
    assert page.evaluate("() => window.apothecaryPanels.state('machine').where") == {
        "tether": "printer_1"
    }
    expect(machine.locator("#c-state")).to_contain_text("printing", timeout=10000)
    expect(machine.locator("#ident")).to_contain_text("Marlin")
    # The module the monitor page was made of: the same ids, the same latch.
    expect(machine.locator("#control")).to_be_hidden()
    assert page.evaluate("() => window.apothecaryMachine.host") == "popup"
    # Its comms log is in it, the board's one log: no panel of its own.
    expect(page.locator(".panel[data-panel='log']")).to_have_count(0)
    log = machine
    expect(log.locator("#log")).to_contain_text("M115", timeout=8000)  # polls are hidden by default
    assert page.locator(".viewer-panel").bounding_box()["width"] >= 1280 / 3 - 2

    # Armed, a jog from the popup moves the world's nozzle marker ahead of the poll.
    machine.locator("#ctl").check()
    expect(machine.locator("#control")).to_be_visible(timeout=5000)
    machine.locator("#control button[data-cmd='M25']").click()
    expect(machine.locator("#c-state")).to_contain_text("idle", timeout=WITHIN_A_POLL)
    before = page.evaluate("() => window.fractalViewer.marks['printer_1'].marks.target()")
    machine.locator("#control button[data-step='10']").click()
    # Ahead of the poll, by mechanism rather than by the clock: where the marker
    # stands at the moment the jog's own event is dispatched, before any poll can
    # answer. (A wall-clock bound here measured the machine's load, not the page.)
    page.evaluate(
        """() => {
            window.__atJog = null;
            window.addEventListener('apothecary:position', (ev) => {
                if (ev.detail && ev.detail.source === 'jog' && window.__atJog === null)
                    window.__atJog = window.fractalViewer.marks['printer_1'].marks.target().x;
            });
        }"""
    )
    machine.locator("#control button[data-jog='X+']").click()
    page.wait_for_function("() => window.__atJog !== null", timeout=8000)
    assert page.evaluate("() => window.__atJog") == before["x"] + 10
    expect(log.locator("#log .tx.control", has_text="G1 X10 F3000").last).to_be_visible(
        timeout=8000
    )
    # The ring's control verbs go to the machine in front of the world: Control > Jog > Y+.
    page.locator("#viewer-canvas").click(button="right", position={"x": 30, "y": 30})
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    page.keyboard.press("Escape")
    page.locator("#contents-list .contents-item[data-path='printer_1']").click(button="right")
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    page.keyboard.press("2")  # Device
    page.keyboard.press("7")  # Control
    page.keyboard.press("2")  # Jog
    page.keyboard.press("8")  # Y+
    expect(page.locator("#ring-overlay")).to_have_count(0)
    expect(log.locator("#log .tx.control", has_text="G1 Y10 F3000").last).to_be_visible(
        timeout=8000
    )
    machine.locator("#control button[data-cmd='M24']").click()
    machine.locator("#ctl-disarm").click()
    expect(machine.locator("#control")).to_be_hidden(timeout=3000)

    # Dragging the popup lets go of the tether; closing it stops its polling, and
    # its log goes with it.
    tb = machine.locator(".panel-title").bounding_box()
    page.mouse.move(tb["x"] + 150, tb["y"] + tb["height"] / 2)
    page.mouse.down()
    page.mouse.move(tb["x"] + 150 - 120, tb["y"] + tb["height"] / 2 + 60, steps=6)
    page.mouse.up()
    assert page.evaluate("() => window.apothecaryPanels.state('machine').where") == "free"
    page.evaluate("() => window.fractalViewer.closeMachine()")
    expect(machine).to_have_count(0)
    expect(log).to_have_count(0)
    assert page.evaluate("() => window.apothecaryMachine") is None


@pytest.mark.e2e
def test_a_tethered_machine_floats_and_docks_into_the_rails_strip(page: Page, printer_url: str):
    """The machine opens as a popup tethered to its printer, in front of the world. Its
    dock button lets go of the printer and puts it in the rail's tab strip, shown; floated
    from its tab it is a free panel; opened from the badge again it is tethered again."""
    _pin(printer_url, BOARD)
    _identify(printer_url)
    page.goto(f"{printer_url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
    badge = page.locator(".world-badge[data-path='printer_1']")
    expect(badge).to_be_visible(timeout=15000)
    badge.click()
    popup = page.locator(".panel-free-layer .panel.tethered[data-panel='machine']")
    expect(popup).to_be_visible(timeout=3000)
    expect(page.locator(".panel-leader[visibility='visible']")).to_have_count(1, timeout=3000)
    expect(popup.locator(".panel-float")).to_have_attribute("title", re.compile("Dock"))

    popup.locator(".panel-float").click()
    rail = page.locator(".panel-rail")
    docked = rail.locator(".panel-tabbody .panel[data-panel='machine']")
    expect(docked).to_be_visible(timeout=2000)
    expect(rail.locator(".rail-tab[data-panel='machine']")).to_have_class(re.compile(r"\bactive\b"))
    assert page.evaluate("() => window.apothecaryPanels.state('machine').where") == "rail"
    expect(docked.locator("#c-state")).to_contain_text("printing", timeout=10000)
    expect(page.locator(".panel-leader")).to_have_count(0)
    # Site and Selected stay stacked above it.
    for pid in ("site", "selected"):
        expect(rail.locator(f".panel[data-panel='{pid}']")).to_be_visible()

    rail.locator(".rail-tab[data-panel='machine'] .rail-tab-float").click()
    free = page.locator(".panel-free-layer .panel[data-panel='machine']")
    expect(free).to_be_visible(timeout=2000)
    expect(free).not_to_have_class(re.compile(r"\btethered\b"))
    assert page.evaluate("() => window.apothecaryPanels.state('machine').where") == "free"
    expect(rail.locator(".rail-tab[data-panel='machine']")).to_have_count(0)

    # The badge again: tethered to its printer again.
    badge.click()
    expect(popup).to_be_visible(timeout=3000)
    assert page.evaluate("() => window.apothecaryPanels.state('machine').where") == {
        "tether": "printer_1"
    }
    page.evaluate("() => window.fractalViewer.closeMachine()")
    expect(page.locator(".panel[data-panel='machine']")).to_have_count(0)
