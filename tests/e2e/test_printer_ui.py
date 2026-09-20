"""Printer UI end to end, with timing bounds: the viewer must stay snappy while it polls.

Runs against its own server (port 8766) so nothing here depends on the
host's toolchain or on a board being plugged in: ``ARDUINO_CLI`` is the
scripted fake from the unit tests (two ports, ``/dev/ttyFAKE0`` an Uno and
``/dev/ttyFAKE1`` unmatched), the serial engine is the in-process
``SimulatedPrinter`` started mid-way through an SD print, and firmware state
lives in a temp dir so pins never touch ``~/.apothecary``.

The bounds are deliberately loose enough for CI and tight enough to catch
the failure modes they name: a blocked event loop, stacked polls, a panel
rebuilt under the user's cursor.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from firmware_helpers import write_fake_arduino_cli
from playwright.sync_api import Page, expect

PRINTER_PORT = "8768"  # 8766 is the docs-generation server
POLL_S = 2.0  # the overlay's cadence (POLL_MS in fractal_viewer.html.j2)


@pytest.fixture(scope="module")
def printer_url(tmp_path_factory):
    root = Path(__file__).resolve().parents[2]
    tmp = tmp_path_factory.mktemp("printer-server")
    env = os.environ.copy()
    env.update(
        {
            "APOTHECARY_VIEWER_PATH": "",
            "ARDUINO_CLI": str(write_fake_arduino_cli(tmp / "arduino-cli")),
            "APOTHECARY_TOOLS_DIR": str(tmp / "tools"),
            "APOTHECARY_STATE_DIR": str(tmp / "state"),
            "APOTHECARY_SERIAL_ENGINE": "simulated",
            "APOTHECARY_SIMULATED_PRINTER": "printing",
        }
    )
    from ports import refuse_a_held_port

    refuse_a_held_port(PRINTER_PORT)
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "apothecary.api:app",
            "--host",
            "127.0.0.1",
            "--port",
            PRINTER_PORT,
            # Let go of idle keep-alive connections quickly on SIGTERM: the browser
            # that held them outlives this fixture, and a server that lingers on
            # the port is the one the next run's health check would find.
            "--timeout-graceful-shutdown",
            "1",
        ],
        cwd=root,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{PRINTER_PORT}"
    healthy = False
    for _ in range(40):
        try:
            if httpx.get(f"{url}/health", timeout=1.0).status_code == 200:
                healthy = True
                break
        except (httpx.ConnectError, httpx.TimeoutException):
            time.sleep(0.5)
        if proc.poll() is not None:
            break
    if proc.poll() is not None:
        # Our server exited -- usually because something else holds the port (a
        # previous run still shutting down). Whatever answers there now is not
        # the server these tests describe, so stop rather than test a stranger.
        pytest.exit(
            f"printer test server exited at start; is {url} held by another process?", returncode=1
        )
    if not healthy:
        proc.terminate()
        pytest.exit("printer test server failed to start", returncode=1)
    yield url
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


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


def _ensure_pinned(page: Page, name: str, port: str):
    """Select ``name`` and make sure ``port`` is pinned to it (tests run in any order)."""
    _select(page, name)
    section = page.locator("#selected-body .device-section")
    expect(section).not_to_contain_text("scanning devices", timeout=8000)
    if "pinned" in section.inner_text() and port in section.inner_text():
        return section
    if section.locator(".dev-unpin").count():
        section.locator(".dev-unpin").click()
    expect(section.locator(".dev-manual")).to_be_visible(timeout=5000)
    section.locator(".dev-manual").fill(port)
    section.locator(".dev-manual").press("Enter")
    expect(section).to_contain_text("pinned", timeout=5000)
    return section


@pytest.mark.e2e
def test_panel_opens_before_devices_finish_loading(page: Page, printer_url: str):
    """Selecting a node never waits for the device scan: the panel is up within 1 s."""
    page.goto(f"{printer_url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
    # dispatch_event, not click(): the bound must cover the viewer's own work,
    # not Playwright's actionability wait on a page still streaming STLs
    # through headless software GL.
    t0 = time.monotonic()
    page.locator("#contents-list .contents-item", has_text="printer_1").first.dispatch_event(
        "click"
    )
    expect(page.locator("#selected-body .prop-row", has_text="Name")).to_be_visible(timeout=1000)
    assert time.monotonic() - t0 < 1.0
    # The Device section is part of the panel from the first render, and
    # settles (scan done) within a bounded time rather than blocking it.
    expect(page.locator("#selected-body .device-section")).to_be_visible(timeout=1000)
    expect(page.locator("#selected-body .device-section .dev-pick")).to_be_visible(timeout=8000)
    options = page.locator("#selected-body .dev-pick option").all_text_contents()
    assert any("/dev/ttyFAKE1" in o for o in options)


@pytest.mark.e2e
def test_pin_identify_watch_poll_and_sync(page: Page, printer_url: str):
    """Pin → identify → Watch: polls at the stated cadence, never stacked, and the node follows."""
    page.goto(f"{printer_url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
    _select(page, "printer_1")
    pick = page.locator("#selected-body .dev-pick")
    expect(pick).to_be_visible(timeout=8000)
    pick.select_option("/dev/ttyFAKE1")

    t0 = time.monotonic()
    page.locator("#selected-body .dev-pin").click()
    expect(page.locator("#selected-body .device-section")).to_contain_text("pinned", timeout=5000)
    assert time.monotonic() - t0 < 5.0
    expect(
        page.locator("#contents-list .contents-item[data-path='printer_1'] .dev-badge")
    ).to_be_visible()

    # Watch opens the overlay on that port; identify tells it this is a printer.
    page.locator("#selected-body .dev-watch").click()
    expect(page.locator("#serial-overlay")).to_be_visible()
    expect(page.locator("#serial-port")).to_have_value("/dev/ttyFAKE1", timeout=5000)
    page.locator("#serial-identify").click()
    expect(page.locator("#serial-meta")).to_contain_text(
        "Marlin Apothecary Simulator", timeout=8000
    )

    # Cadence bound: after the first poll line, count polls over ~3 periods.
    temps = page.locator("#serial-body .temp")
    expect(temps.first).to_be_visible(timeout=5000)
    n0 = temps.count()
    window = 3.25 * POLL_S
    time.sleep(window)
    delta = temps.count() - n0
    assert 2 <= delta <= 4, f"{delta} polls in {window}s at a {POLL_S}s cadence"

    # What the polls said reached the panel, the badge and the node's status.
    section = page.locator("#selected-body .device-section")
    expect(section).to_contain_text("printing")
    expect(section.locator(".temps")).to_contain_text("/210°")
    badge = page.locator("#contents-list .contents-item[data-path='printer_1'] .dev-badge")
    expect(badge).to_contain_text("🖨 210°/60°")
    assert "printing" in badge.get_attribute("class")
    expect(page.locator("#status-select")).to_have_value("printing", timeout=POLL_S * 1000 + 3000)

    # The other printer is untouched, and the pinned port is no longer offered to it.
    _select(page, "printer_2")
    expect(page.locator("#status-select")).to_have_value("idle")
    expect(page.locator("#selected-body .device-section")).not_to_contain_text("/dev/ttyFAKE1")


@pytest.mark.e2e
def test_editing_survives_polling(page: Page, printer_url: str):
    """A position edit in progress is not wiped by the 2 s poll re-render."""
    page.goto(f"{printer_url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
    _select(page, "printer_1")
    expect(page.locator("#selected-body .device-section")).to_contain_text("pinned", timeout=8000)
    page.locator("#selected-body .dev-watch").click()
    expect(page.locator("#serial-body .temp").first).to_be_visible(timeout=8000)

    x = page.locator("#pos-x")
    x.click()
    x.fill("")
    x.type("123")
    time.sleep(2.25 * POLL_S)  # at least two polls land while the field is being edited
    assert page.evaluate("document.activeElement && document.activeElement.id") == "pos-x"
    expect(x).to_have_value("123")
    # And the panel's device section did keep updating underneath.
    expect(page.locator("#selected-body .device-section .temps")).to_contain_text("/210°")

    # Unpin from the panel: immediate (no second scan), badge gone, node keeps its last status.
    t0 = time.monotonic()
    page.locator("#selected-body .dev-unpin").click()
    expect(page.locator("#selected-body .dev-pick")).to_be_visible(timeout=3000)
    assert time.monotonic() - t0 < 3.0
    expect(
        page.locator("#contents-list .contents-item[data-path='printer_1'] .dev-badge")
    ).to_have_count(0)


@pytest.mark.e2e
def test_firmware_page_printer_poll(page: Page, printer_url: str):
    """The firmware page's card polls the (already identified) printer within a bound."""
    page.goto(f"{printer_url}/firmware")
    card = page.locator(".device[data-port='/dev/ttyFAKE1']")
    expect(card).to_be_visible(timeout=10000)
    btn = card.locator(".dev-printer")
    expect(btn).to_have_text("Poll")  # identified by the viewer test above and cached
    t0 = time.monotonic()
    btn.click()
    status = page.locator(".device[data-port='/dev/ttyFAKE1'] .printer-status")
    expect(status).to_contain_text("printing", timeout=5000)
    assert time.monotonic() - t0 < 5.0
    expect(status).to_contain_text("/210°")  # the simulator wobbles ±0.3° around its target


@pytest.mark.e2e
def test_query_from_panel_and_overlay(page: Page, printer_url: str):
    """Query asks M115 without pinning; the overlay's query box runs allowlisted codes only."""
    page.goto(f"{printer_url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
    _select(page, "printer_3")
    section = page.locator("#selected-body .device-section")
    # printer_1 holds /dev/ttyFAKE1 from the earlier test; FAKE0 (the Uno) is free.
    expect(section.locator(".dev-pick")).to_be_visible(timeout=8000)
    section.locator(".dev-pick").select_option("/dev/ttyFAKE0")
    t0 = time.monotonic()
    section.locator(".dev-query").click()
    expect(section.locator(".device-query")).to_contain_text("/dev/ttyFAKE0", timeout=8000)
    assert time.monotonic() - t0 < 8.0
    # The simulated engine answers M115 on any port, so FAKE0 identifies as a printer too --
    # and querying did not pin it.
    expect(section.locator(".device-query")).to_contain_text("Marlin Apothecary Simulator")
    expect(section).not_to_contain_text("pinned")

    # Overlay query box: visible only in printer mode; refuses non-report codes via the API.
    _ensure_pinned(page, "printer_1", "/dev/ttyFAKE1")
    page.locator("#selected-body .dev-watch").click()
    expect(page.locator("#serial-query-row")).to_be_visible(timeout=8000)
    page.locator("#serial-query").fill("M119")
    page.locator("#serial-query-row button").click()
    expect(page.locator("#serial-body")).to_contain_text("y_min: TRIGGERED", timeout=5000)
    page.locator("#serial-query").fill("M104 S200")
    page.locator("#serial-query-row button").click()
    expect(page.locator("#serial-body")).to_contain_text("query refused", timeout=5000)
    assert page.locator("#serial-query-codes option").count() >= 10


@pytest.mark.e2e
def test_manual_pin_poll_now_and_auto_refresh(page: Page, printer_url: str):
    """Pin by typed identity, poll from the panel, and the auto-refresh keeps to its interval."""
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

    # Poll now on the bound printer updates the badge without opening the overlay.
    _ensure_pinned(page, "printer_1", "/dev/ttyFAKE1")
    expect(page.locator("#selected-body .dev-poll")).to_be_visible(timeout=8000)
    expect(page.locator("#serial-overlay")).to_be_hidden()
    page.locator("#selected-body .dev-poll").click()
    badge = page.locator("#contents-list .contents-item[data-path='printer_1'] .dev-badge")
    expect(badge).to_contain_text("/", timeout=5000)  # temps, not the bare 🖨
    expect(page.locator("#serial-overlay")).to_be_hidden()

    # Auto-refresh at 5 s: count fresh scans over ~2.5 intervals -- 2 or 3, never a pile-up.
    scans = []
    page.on(
        "request", lambda r: scans.append(time.monotonic()) if "/devices?fresh=1" in r.url else None
    )
    page.locator("#devices-interval").select_option("5000")
    if not page.locator("#devices-auto").is_checked():
        page.locator("#devices-auto").check()
    t0 = time.monotonic()
    # Not time.sleep: sync-API event callbacks only fire during Playwright calls.
    page.wait_for_timeout(12500)
    n = sum(1 for t in scans if t >= t0)
    assert 2 <= n <= 3, f"{n} auto-refresh scans in 12.5 s at a 5 s interval"
    page.locator("#devices-auto").uncheck()
    before = len(scans)
    page.wait_for_timeout(6000)
    assert len(scans) == before, "auto-refresh kept running after being switched off"


@pytest.mark.e2e
def test_focused_monitor_page(page: Page, printer_url: str):
    """The focused monitor: status within a bound, cadence, log, query, reconnect, reset."""
    page.goto(f"{printer_url}/firmware/monitor?port=/dev/ttyFAKE1")
    t0 = time.monotonic()
    expect(page.locator("#c-state")).to_contain_text("printing", timeout=8000)
    assert time.monotonic() - t0 < 8.0
    expect(page.locator("#ident")).to_contain_text("Marlin Apothecary Simulator")
    expect(page.locator("#port")).to_have_value("/dev/ttyFAKE1")
    expect(page.locator("#c-board")).to_contain_text("held", timeout=5000)
    expect(page.locator("#c-hot")).to_contain_text("/ 210°")

    # Cadence: with poll traffic shown, count M105 sends over ~3 periods.
    page.locator("#show-polls").check()
    sends = page.locator("#log .tx", has_text="M105")
    expect(sends.first).to_be_visible(timeout=5000)
    n0 = sends.count()
    page.wait_for_timeout(int(3.25 * POLL_S * 1000))
    delta = sends.count() - n0
    assert 2 <= delta <= 4, f"{delta} polls in {3.25 * POLL_S}s at a {POLL_S}s cadence"
    expect(page.locator("#chart path")).to_have_count(4)  # two series + two targets
    expect(page.locator("#chart-span")).to_contain_text("polls")

    # Hidden poll traffic leaves only the story: open, M115, queries, sys lines.
    page.locator("#show-polls").uncheck()
    assert page.locator("#log .tx", has_text="M105").count() == 0
    page.locator("#q").fill("M119")
    page.locator("#qform button").click()
    expect(page.locator("#log")).to_contain_text("y_min: TRIGGERED", timeout=5000)
    page.locator("#q").fill("G28")
    page.locator("#qform button").click()
    expect(page.locator("#log")).to_contain_text("query refused", timeout=5000)

    # Reconnect keeps the log and comes back polling; reset shows the boot banner.
    t0 = time.monotonic()
    page.locator("#reconnect").click()
    expect(page.locator("#log .sys", has_text="closed /dev/ttyFAKE1")).to_be_visible(timeout=6000)
    expect(page.locator("#log .sys", has_text="opened /dev/ttyFAKE1").last).to_be_visible()
    assert time.monotonic() - t0 < 6.0
    expect(page.locator("#log")).to_contain_text("y_min: TRIGGERED")  # earlier entries survived
    page.once("dialog", lambda d: d.accept())
    page.locator("#reset").click()
    expect(page.locator("#log .boot", has_text="start")).to_be_visible(timeout=8000)

    # Release drops the link and stops auto-poll.
    page.locator("#release").click()
    expect(page.locator("#c-board")).to_contain_text("not held", timeout=5000)
    assert not page.locator("#auto").is_checked()
    n1 = page.locator("#log .sys").count()
    page.wait_for_timeout(int(2.5 * POLL_S * 1000))
    assert page.locator("#c-board").inner_text().count("held") >= 1  # still "not held": no reopen
    assert page.locator("#log .sys").count() == n1


BOARD = "printer_1.frame_system.mainboard"


@pytest.mark.e2e
def test_board_inside_the_printer_drives_it(page: Page, printer_url: str):
    """Pin the port to the mainboard: the printer row and panel speak for it; its status follows."""
    page.goto(f"{printer_url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
    # Start clean: nothing pinned on the printer itself.
    _select(page, "printer_1")
    section = page.locator("#selected-body .device-section")
    expect(section).not_to_contain_text("scanning devices", timeout=8000)
    if section.locator(".dev-unpin").count():
        section.locator(".dev-unpin").click()
        expect(section.locator(".dev-manual")).to_be_visible(timeout=5000)

    _expand_to(page, BOARD)
    expect(page.locator("#selected-body .prop-row", has_text="Name")).to_contain_text("mainboard")
    expect(section.locator(".dev-pick")).to_be_visible(timeout=8000)
    section.locator(".dev-pick").select_option("/dev/ttyFAKE1")
    section.locator(".dev-query").click()  # identifies the port (M115) without pinning
    expect(section.locator(".device-query")).to_contain_text("Marlin", timeout=8000)
    section.locator(".dev-pin").click()
    expect(section).to_contain_text("pinned", timeout=5000)

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
    t0 = time.monotonic()
    section.locator(".dev-poll").click()
    expect(page.locator("#status-select")).to_have_value("printing", timeout=8000)
    assert time.monotonic() - t0 < 8.0

    # The via link jumps to the board's own row and panel.
    section.locator(".dev-via").click()
    expect(page.locator("#selected-body .prop-row", has_text="Name")).to_contain_text("mainboard")
    expect(section.locator(".dev-unpin")).to_be_visible()
    section.locator(".dev-unpin").click()
    expect(section.locator(".dev-manual")).to_be_visible(timeout=5000)
    expect(
        page.locator("#contents-list .contents-item[data-path='printer_1'] .dev-badge")
    ).to_have_count(0)


@pytest.mark.e2e
def test_control_overlay_is_latched(page: Page, printer_url: str):
    """Nothing heats or moves until Control is armed; armed, the effect shows within a poll."""
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
    t0 = time.monotonic()
    page.locator("#control button[data-cmd='M140 S{h-bed}']").click()
    expect(page.locator("#c-bed")).to_contain_text("/ 45°", timeout=POLL_S * 1000 + 3000)
    assert time.monotonic() - t0 < POLL_S + 3
    expect(page.locator("#log .tx.control", has_text="M140 S45")).to_be_visible()

    # An out-of-bounds value never reaches the board.
    page.locator("#h-hot").fill("900")
    page.locator("#control button[data-cmd='M104 S{h-hot}']").click()
    expect(page.locator("#ctl-sent")).to_contain_text("above 300", timeout=5000)
    assert page.locator("#log .tx.control", has_text="M104 S900").count() == 0

    # Pause the SD print, then a jog: three lines, relative mode restored, the
    # position card follows; resume afterwards.
    page.locator("#control button[data-cmd='M25']").click()
    expect(page.locator("#c-state")).to_contain_text("idle", timeout=POLL_S * 1000 + 3000)
    page.locator("#control button[data-step='10']").click()
    page.locator("#control button[data-jog='Y+']").click()
    expect(page.locator("#log .tx.control", has_text="G90").last).to_be_visible(timeout=8000)
    expect(page.locator("#c-pos")).to_contain_text("Y10.0", timeout=POLL_S * 1000 + 3000)
    page.locator("#control button[data-cmd='M24']").click()
    expect(page.locator("#c-state")).to_contain_text("printing", timeout=POLL_S * 1000 + 3000)

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
def test_the_board_is_drawn_in_its_printer_and_the_nozzle_follows_a_jog(
    page: Page, printer_url: str
):
    """The monitor shows the pinned board inside its printer; a jog moves the nozzle marker
    ahead of the poll that confirms it; the firmware page draws the same board on its card."""
    page.goto(f"{printer_url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
    _expand_to(page, BOARD)
    section = page.locator("#selected-body .device-section")
    expect(section).not_to_contain_text("scanning devices", timeout=8000)
    if section.locator(".dev-unpin").count() == 0:
        expect(section.locator(".dev-manual")).to_be_visible(timeout=5000)
        section.locator(".dev-manual").fill("/dev/ttyFAKE1")
        section.locator(".dev-manual").press("Enter")
        expect(section).to_contain_text("pinned", timeout=5000)
    # Make sure printer_1 itself is not also pinned from an earlier test.
    page.request.delete(f"{printer_url}/sites/garage/nodes/printer_1/device")

    page.goto(f"{printer_url}/firmware/monitor?port=/dev/ttyFAKE1")
    expect(page.locator("#c-state")).not_to_have_text("—", timeout=10000)
    t0 = time.monotonic()
    expect(page.locator("#view-card")).to_be_visible(timeout=10000)
    expect(page.locator("#board-view canvas")).to_have_count(1, timeout=10000)
    assert time.monotonic() - t0 < 10.0
    expect(page.locator("#view-note")).to_contain_text("printer_1")
    page.wait_for_function(
        "() => window.apothecaryBoardView && window.apothecaryBoardView.target()", timeout=5000
    )
    # The bodies land where the site puts them: the printer's shape encloses
    # its board and its build volume. (A node's STL arrives in its parent's
    # frame; drawn untranslated, the printer sat a bench-width away.)
    page.wait_for_function(
        "() => Object.keys(window.apothecaryBoardView.bodies()).length === 2", timeout=15000
    )
    drawn = page.evaluate(
        "() => ({ bodies: window.apothecaryBoardView.bodies(), "
        "volume: window.apothecaryBoardView.volume() })"
    )
    printer_box = drawn["bodies"]["printer_1"]
    board_box = drawn["bodies"][BOARD]
    for inner in (board_box, drawn["volume"]):
        for axis in "xyz":
            assert printer_box["min"][axis] - 1 <= inner["min"][axis], (axis, drawn)
            assert inner["max"][axis] <= printer_box["max"][axis] + 1, (axis, drawn)
    assert printer_box["max"]["x"] - printer_box["min"]["x"] == pytest.approx(300, abs=1)
    assert board_box["min"]["z"] == pytest.approx(5, abs=1)  # on the enclosure floor
    page.locator("#ctl").check()
    expect(page.locator("#control")).to_be_visible(timeout=5000)
    page.locator("#control button[data-cmd='M25']").click()  # pause the SD print so a jog is honest
    expect(page.locator("#c-state")).to_contain_text("idle", timeout=POLL_S * 1000 + 3000)
    page.wait_for_timeout(int(POLL_S * 1000) + 500)  # a poll after the pause: the real place
    before = page.evaluate("() => window.apothecaryBoardView.target()")
    page.locator("#control button[data-step='10']").click()
    page.locator("#control button[data-jog='X+']").click()
    # Ahead of the poll: the target moved the moment the jog was sent.
    page.wait_for_function(
        "(bx) => window.apothecaryBoardView.target().x === bx + 10", arg=before["x"], timeout=1500
    )
    # And it settles there: the drawn position catches up within a second.
    page.wait_for_function(
        "(bx) => Math.abs(window.apothecaryBoardView.position().x - (bx + 10)) < 0.5",
        arg=before["x"],
        timeout=2000,
    )
    page.locator("#control button[data-cmd='M24']").click()
    page.locator("#ctl-disarm").click()

    page.goto(f"{printer_url}/firmware")
    card = page.locator(".device[data-port='/dev/ttyFAKE1']")
    expect(card).to_be_visible(timeout=10000)
    expect(card.locator(".board-view canvas")).to_have_count(1, timeout=10000)
    expect(card.locator(".board-view-note")).to_contain_text("garage › printer_1")
    # A port pinned nowhere draws nothing.
    expect(page.locator(".device[data-port='/dev/ttyFAKE0'] .board-view")).to_be_hidden()


@pytest.mark.e2e
def test_bed_level_probe_reads_and_records(page: Page, printer_url: str):
    """Read mesh needs no latch and fills the heatmap; Probe bed needs it, shows its stage
    while the port is held, saves a record the history lists; a corner button is four lines;
    the reading is drawn over the bed in the board view, on this page and the firmware page."""
    page.request.put(
        f"{printer_url}/sites/garage/nodes/{BOARD}/device", data={"identity": "/dev/ttyFAKE1"}
    )
    page.request.delete(f"{printer_url}/sites/garage/nodes/printer_1/device")
    page.goto(f"{printer_url}/firmware/monitor?port=/dev/ttyFAKE1")
    expect(page.locator("#c-state")).not_to_have_text("—", timeout=10000)
    expect(page.locator("#level-stats")).to_contain_text("no reading yet")
    before = page.locator("#level-history > div").count()

    # A read: no latch, no movement, a 5x5 mesh from the simulator within a few seconds.
    t0 = time.monotonic()
    page.locator("#level-read").click()
    expect(page.locator("#mesh .cell")).to_have_count(25, timeout=15000)
    assert time.monotonic() - t0 < 15.0
    expect(page.locator("#level-stats")).to_contain_text("read ·")
    expect(page.locator("#level-stats")).to_contain_text("probe offset X-44 Y-10 Z-3.15")
    expect(page.locator("#level-history > div")).to_have_count(before + 1)
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
    expect(page.locator("#level-history > div")).to_have_count(before + 2, timeout=5000)
    expect(page.locator("#level-stats")).to_contain_text("probe ·")
    expect(page.locator("#log .tx.control", has_text="G29")).to_have_count(1)
    expect(page.locator("#log .sys", has_text="bed reading saved")).to_have_count(2)
    record_id = page.evaluate("() => window.apothecaryMonitor.level.shown().id")
    r = page.request.get(f"{printer_url}/firmware/printers/leveling/{record_id}")
    assert r.ok and len(r.json()["mesh"]) == 5 and r.json()["method"] == "probe"
    # The reading is drawn in the world too: a 5x5 surface over the probed area of
    # the bed, stretched so its shape reads, following whichever reading is shown.
    expect(page.locator("#board-view canvas")).to_have_count(1, timeout=10000)
    page.wait_for_function(
        "(id) => window.apothecaryBoardView && window.apothecaryBoardView.mesh()"
        " && window.apothecaryBoardView.mesh().record_id === id",
        arg=record_id,
        timeout=5000,
    )
    drawn = page.evaluate("() => window.apothecaryBoardView.mesh()")
    volume = page.evaluate("() => window.apothecaryBoardView.volume()")
    assert drawn["rows"] == 5 and drawn["cols"] == 5 and drawn["exaggeration"] >= 10
    assert drawn["bounds"]["min"]["x"] >= 0 and drawn["bounds"]["max"]["x"] <= 220
    assert drawn["bounds"]["max"]["x"] == 166  # the probe's -44 offset keeps it off the right edge
    assert drawn["z"]["min"] == pytest.approx(
        volume["min"]["z"] + 0.4
    )  # a relief resting on the bed
    assert drawn["z"]["max"] <= volume["max"]["z"]
    assert drawn["z"]["max"] - drawn["z"]["min"] == pytest.approx(
        drawn["range"] * drawn["exaggeration"], abs=0.01
    )
    expect(page.locator("#view-note")).to_contain_text("drawn ×")
    # The history still holds the read; picking it swaps the heatmap back, and the surface.
    page.locator("#level-history .pick", has_text="read").first.click()
    expect(page.locator("#level-stats")).to_contain_text("read ·")
    page.wait_for_function(
        "(id) => window.apothecaryBoardView.mesh().record_id !== id", arg=record_id, timeout=5000
    )

    # A corner button: four absolute lines, the last one at paper height.
    lines = page.evaluate("() => window.apothecaryMonitor.level.lines('BR')")
    assert lines == ["G90", "G1 Z5 F3000", "G1 X190 Y190 F3000", "G1 Z0.2 F600"]
    page.locator("#control button[data-cmd='M25']").click()  # the simulator is printing
    expect(page.locator("#c-state")).to_contain_text("idle", timeout=POLL_S * 1000 + 3000)
    page.locator("#level-card button[data-corner='FL']").click()
    expect(page.locator("#log .tx.control", has_text="G1 X30 Y30 F3000")).to_be_visible(
        timeout=8000
    )
    expect(page.locator("#c-pos")).to_contain_text("X30.0", timeout=POLL_S * 1000 + 3000)
    page.locator("#control button[data-cmd='M24']").click()
    page.locator("#ctl-disarm").click()
    expect(page.locator("#control")).to_be_hidden(timeout=3000)

    # The firmware page's card draws the newest reading over the bed as well.
    page.goto(f"{printer_url}/firmware")
    card = page.locator(".device[data-port='/dev/ttyFAKE1']")
    expect(card.locator(".board-view canvas")).to_have_count(1, timeout=10000)
    page.wait_for_function(
        "() => { const v = window.apothecaryBoardViews.get('/dev/ttyFAKE1');"
        " return v && v.mesh(); }",
        timeout=10000,
    )
    expect(card.locator(".board-view-note")).to_contain_text("drawn ×")


@pytest.mark.e2e
def test_a_file_prints_from_here_without_a_card(page: Page, printer_url: str):
    """Keep a file from the page, print it armed, pause and resume from the ring's Print
    cell, cancel, and see the record; a second file runs to the end and the state comes back."""
    page.goto(f"{printer_url}/firmware/monitor?port=/dev/ttyFAKE1")
    expect(page.locator("#c-state")).not_to_have_text("—", timeout=10000)
    expect(page.locator("#print-start")).to_be_disabled()
    slow = "\n".join(f"G1 X{i} Y{i} E{i / 10:.1f}\nG4 P150" for i in range(1, 41)) + "\n"
    page.locator("#print-file").set_input_files(
        {"name": "slow cube.gcode", "mimeType": "text/plain", "buffer": slow.encode()}
    )
    expect(page.locator("#print-pick")).to_contain_text("slow cube.gcode · 80 lines", timeout=8000)
    expect(page.locator("#log .sys", has_text="kept slow cube.gcode: 80 lines")).to_be_visible()
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
    assert not page.evaluate("() => window.apothecaryMonitor.print.job().running")
    page.locator("#ctl").check()
    expect(page.locator("#control")).to_be_visible(timeout=5000)
    page.locator("#control button[data-cmd='M25']").click()  # the card's print is in the way
    expect(page.locator("#c-state")).to_contain_text("idle", timeout=POLL_S * 1000 + 3000)
    page.wait_for_timeout(int(POLL_S * 1000) + 300)  # a poll that sees the card idle

    page.once("dialog", lambda d: d.accept())
    t0 = time.monotonic()
    page.locator("#print-start").click()
    expect(page.locator("#print-progress")).to_contain_text(
        "slow cube.gcode · printing", timeout=5000
    )
    assert time.monotonic() - t0 < 5
    expect(page.locator("#c-state")).to_contain_text("printing", timeout=POLL_S * 1000 + 3000)
    expect(page.locator("#c-state-s")).to_contain_text("print from here: printing")
    expect(
        page.locator("#log .sys", has_text="print started: slow cube.gcode (80 lines)")
    ).to_be_visible()
    # The stream stays out of the log; the progress bar moves.
    page.wait_for_function("() => window.apothecaryMonitor.print.job().sent >= 6", timeout=8000)
    assert page.locator("#log .tx", has_text="G4 P150").count() == 0

    # Pause from the ring: Control > Print > Pause goes to the print from here, not the card.
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
    sent = page.evaluate("() => window.apothecaryMonitor.print.job().sent")
    page.wait_for_timeout(1200)
    assert page.evaluate("() => window.apothecaryMonitor.print.job().sent") <= sent + 1
    expect(page.locator("#print-resume")).to_be_enabled()
    page.locator("#print-resume").click()
    expect(page.locator("#print-progress")).to_contain_text("· printing ·", timeout=5000)
    page.wait_for_function(
        "(n) => window.apothecaryMonitor.print.job().sent > n + 2", arg=sent, timeout=8000
    )
    page.once("dialog", lambda d: d.accept())
    page.locator("#print-cancel").click()
    expect(page.locator("#print-progress")).to_contain_text("· cancelled ·", timeout=8000)
    expect(page.locator("#print-history")).to_contain_text(
        "slow cube.gcode · cancelled", timeout=5000
    )
    expect(page.locator("#log .tx.control", has_text="M104 S0").last).to_be_visible()
    expect(page.locator("#print-start")).to_be_enabled(timeout=5000)

    # A short file runs to the end: done, recorded, and the state card is the board's again.
    page.locator("#print-file").set_input_files(
        {"name": "dot.gcode", "mimeType": "text/plain", "buffer": b"G28\nG1 X5 Y5 E0.1\nM84\n"}
    )
    expect(page.locator("#print-pick")).to_contain_text("dot.gcode · 3 lines", timeout=8000)
    page.once("dialog", lambda d: d.accept())
    page.locator("#print-start").click()
    expect(page.locator("#print-progress")).to_contain_text("dot.gcode · done · 3/3", timeout=10000)
    expect(page.locator("#print-history")).to_contain_text("dot.gcode · done · 3/3")
    expect(page.locator("#c-state")).to_contain_text("idle", timeout=POLL_S * 1000 + 3000)
    r = page.request.get(f"{printer_url}/firmware/printers/print/records?port=/dev/ttyFAKE1")
    assert [x["outcome"] for x in r.json()] == ["done", "cancelled"]
    page.locator("#control button[data-cmd='M24']").click()  # leave the card printing for the rest
    page.locator("#ctl-disarm").click()
    expect(page.locator("#control")).to_be_hidden(timeout=3000)
