"""The ring in a browser: nine cells, addresses, and the buttons that carry them.

Runs against its own server (port 8769), like ``test_printer_ui.py``: the
scripted ``arduino-cli`` fake, the in-process simulated printer mid-way
through an SD print, and firmware state in a temp dir. Nothing here opens a
real port.

What is held to is rad's *the menu addresses nine cells*: options sit in
cells numbered as a numeric keypad, cardinals first (``8 6 2 4 9 3 1 7``);
a digit chooses its cell from anywhere; an arrow moves to the nearest
occupied cell in that direction, by the same rule the Python resolver runs;
5 backs out; and the digits pressed to reach an option are its address,
which the intent carries and the page's own buttons wear.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from firmware_helpers import write_fake_arduino_cli
from playwright.sync_api import Page, expect

RING_PORT = "8769"  # 8766 docs, 8768 printer UI
PRINTER = "/dev/ttyFAKE1"
VECTORS = Path(__file__).resolve().parents[1] / "conformance" / "nine_cells.json"

# The arrow rule, as vectors: (occupied cells, from, direction) -> cell. Used
# when the resolver's generated file is not there yet; the file wins when it is.
# Scored as menu.py's nearest(): least offset across the arrow's line, then
# least far along it, then the lower number; nothing ahead means stay put.
EMBEDDED_NEAREST = [
    # a four-item ring: corners empty, every cardinal reachable
    ([8, 6, 2, 4], 8, "left", 4),
    ([8, 6, 2, 4], 8, "right", 6),
    ([8, 6, 2, 4], 8, "down", 2),
    ([8, 6, 2, 4], 4, "up", 8),
    ([8, 6, 2, 4], 4, "right", 6),
    ([8, 6, 2, 4], 2, "up", 8),
    ([8, 6, 2, 4], 6, "left", 4),
    ([8, 6, 2, 4], None, "up", 8),
    ([8, 6, 2, 4], None, "left", 4),
    # a full ring
    ([1, 2, 3, 4, 6, 7, 8, 9], 8, "down", 2),
    ([1, 2, 3, 4, 6, 7, 8, 9], 8, "left", 7),
    ([1, 2, 3, 4, 6, 7, 8, 9], 7, "right", 8),
    ([1, 2, 3, 4, 6, 7, 8, 9], 7, "down", 4),
    ([1, 2, 3, 4, 6, 7, 8, 9], 9, "left", 8),
    ([1, 2, 3, 4, 6, 7, 8, 9], 1, "up", 4),
    ([1, 2, 3, 4, 6, 7, 8, 9], 3, "up", 6),
    ([1, 2, 3, 4, 6, 7, 8, 9], 4, "up", 7),
    ([1, 2, 3, 4, 6, 7, 8, 9], 2, "right", 3),
    ([1, 2, 3, 4, 6, 7, 8, 9], None, "right", 6),
    # nothing that way: stay
    ([8, 6, 2], 8, "left", 8),
    ([8, 6, 2], 2, "left", 2),
    ([8, 6, 2], None, "left", None),
    ([8], None, "down", None),
    ([8], 8, "up", 8),
    # five items: the corner beats the cardinal when it sits squarely ahead
    ([8, 6, 2, 4, 9], 8, "right", 9),
    ([8, 6, 2, 4, 9], 6, "up", 9),
]


def _nearest_vectors():
    """The resolver's vectors when written, else the embedded ones."""
    if not VECTORS.exists():
        return EMBEDDED_NEAREST
    data = json.loads(VECTORS.read_text(encoding="utf-8"))
    rows = data.get("nearest", data) if isinstance(data, dict) else data
    out = []
    for row in rows:
        occupied = row.get("occupied") or row.get("cells")
        start = row.get("from", row.get("from_cell", row.get("start")))
        direction = row.get("direction") or row.get("dir")
        want = row.get("expect", row.get("to", row.get("cell", row.get("result"))))
        out.append((occupied, start, direction, want))
    return out


@pytest.fixture(scope="module")
def ring_url(tmp_path_factory):
    root = Path(__file__).resolve().parents[2]
    tmp = tmp_path_factory.mktemp("ring-server")
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

    refuse_a_held_port(RING_PORT)
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "apothecary.api:app",
            "--host",
            "127.0.0.1",
            "--port",
            RING_PORT,
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
    url = f"http://127.0.0.1:{RING_PORT}"
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
            f"ring test server exited at start; is {url} held by another process?", returncode=1
        )
    if not healthy:
        proc.terminate()
        pytest.exit("ring test server failed to start", returncode=1)
    # The printer is identified (M115) and pinned to printer_1 up front, so the
    # node ring carries Device > Control from the first test on.
    httpx.post(f"{url}/firmware/devices/identify", json={"port": PRINTER}, timeout=15.0)
    r = httpx.put(
        f"{url}/sites/garage/nodes/printer_1/device", json={"identity": PRINTER}, timeout=15.0
    )
    assert r.status_code == 200, r.text
    yield url
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


CAPTURE = (
    "window.__intents = []; "
    "window.addEventListener('apothecary:intent', (e) => window.__intents.push(e.detail));"
)


def _open_viewer(page: Page, url: str, node: str = "printer_1"):
    page.add_init_script(CAPTURE)
    page.goto(f"{url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
    page.locator("#contents-list .contents-item", has_text=node).first.click()
    expect(page.locator("#selected-body .prop-row", has_text="Name")).to_be_visible(timeout=5000)


def _wedges(page: Page) -> dict:
    """cell -> label of every wedge that holds something."""
    return page.evaluate(
        """() => Object.fromEntries([...document.querySelectorAll('#ring-overlay .wedge')]
            .filter((w) => !w.classList.contains('empty'))
            .map((w) => [w.dataset.cell, w.getAttribute('aria-label')]))"""
    )


def _title(page: Page) -> str:
    return page.locator("#ring-overlay .title").text_content() or ""


def _intents(page: Page) -> list:
    return page.evaluate("() => window.__intents")


@pytest.mark.e2e
def test_key_m_opens_the_node_ring_in_its_cells(page: Page, ring_url: str):
    """m on a selected node: eight wedges, options cardinals first, the hub is 5."""
    _open_viewer(page, ring_url)
    expect(
        page.locator("#contents-list .contents-item[data-path='printer_1'] .dev-badge")
    ).to_be_visible(timeout=10000)
    page.keyboard.press("m")
    ring = page.locator("#ring-overlay")
    expect(ring).to_be_visible(timeout=5000)
    assert page.locator("#ring-overlay .wedge").count() == 8
    assert _wedges(page) == {
        "8": "Zoom in",
        "6": "Move",
        "2": "Device",
        "4": "Why this",
        "9": "Into",
    }
    assert page.locator("#ring-overlay .wedge.empty").count() == 3
    assert page.locator("#ring-overlay .hub-digit").text_content() == "5"
    assert _title(page) == "printer_1"
    # Every wedge shows its digit, occupied or not; a parented option shows a chevron.
    digits = page.locator("#ring-overlay .digit").all_text_contents()
    assert sorted(digits) == ["1", "2", "3", "4", "6", "7", "8", "9"]
    assert page.locator("#ring-overlay .label", has_text="Device ›").count() == 1
    page.keyboard.press("Escape")
    expect(ring).to_have_count(0)


@pytest.mark.e2e
def test_the_toolbar_button_and_right_click_open_it_too(page: Page, ring_url: str):
    _open_viewer(page, ring_url)
    page.locator("#ring-open").click()
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    assert _title(page) == "printer_1"
    page.keyboard.press("Escape")
    expect(page.locator("#ring-overlay")).to_have_count(0)
    # Right-click on another row opens that row's ring, and selects the row.
    page.locator("#contents-list .contents-item[data-path='printer_2']").click(button="right")
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    assert _title(page) == "printer_2"
    # Nothing pinned: no Device option at all, not a greyed one, so Why this moves up a cell.
    assert _wedges(page) == {"8": "Zoom in", "6": "Move", "2": "Why this", "4": "Into"}
    expect(page.locator("#contents-list .contents-item[data-path='printer_2']")).to_have_class(
        "contents-item selected"
    )
    page.keyboard.press("Escape")


@pytest.mark.e2e
def test_digits_walk_device_control_jog_and_the_intent_carries_the_address(
    page: Page, ring_url: str
):
    """2 1 2 8 reaches Jog > Y+ from the node ring; the intent says so, and so does the page."""
    _open_viewer(page, ring_url)
    expect(
        page.locator("#contents-list .contents-item[data-path='printer_1'] .dev-badge")
    ).to_be_visible(timeout=10000)
    page.keyboard.press("m")
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    page.keyboard.press("2")
    assert _title(page) == "Device"
    assert _wedges(page) == {
        "8": "Watch",
        "6": "Poll",
        "2": "Monitor",
        "4": "Query",
        "9": "Unpin",
        "3": "Rescan",
        "1": "Link",
        "7": "Control",
    }
    page.keyboard.press("7")
    assert _title(page) == "Control"
    assert _wedges(page)["2"] == "Jog"
    assert _wedges(page)["1"] == "Stop"
    page.keyboard.press("2")
    assert _title(page) == "Jog"
    # The numpad as a jog pad: up, right, down, left, up-right, down-right.
    assert _wedges(page) == {"8": "Y+", "6": "X+", "2": "Y-", "4": "X-", "9": "Z+", "3": "Z-"}
    assert page.locator("#ring-overlay .address").text_content() == "⌗272"
    page.keyboard.press("8")
    expect(page.locator("#ring-overlay")).to_have_count(0)
    intents = _intents(page)
    assert len(intents) == 1
    intent = intents[0]
    assert intent["action"] == "control:jog:Y+"
    assert intent["option_id"] == "control:jog:Y+"
    assert intent["address"] == "2728"
    assert intent["context"] == {
        "pointing": "node",
        "targets": ["printer_1"],
        "where": {"x": 0, "y": 0},
    }
    # The same address, worked out from the ring itself two ways.
    by_path = page.evaluate(
        "() => window.apothecaryRing.addressOf(window.apothecaryRing.lastRing(), "
        "['device', 'control', 'control:jog', 'Y+'])"
    )
    by_action = page.evaluate(
        "() => window.apothecaryRing.addressOf(window.apothecaryRing.lastRing(), 'control:jog:Y+')"
    )
    assert by_path == by_action == intent["address"]
    # A viewer-carried control verb is posted as the intent and answered in the status line.
    expect(page.locator("#status")).to_contain_text("⌗2728", timeout=5000)
    # "Appear as generated": the Device section's buttons wear their addresses.
    watch = page.locator("#selected-body .dev-watch")
    expect(watch).to_have_attribute("data-address", "28", timeout=5000)
    assert (watch.get_attribute("title") or "").endswith(" · ⌗28")
    expect(page.locator("#selected-body .dev-poll")).to_have_attribute("data-address", "26")
    expect(page.locator("#selected-body .dev-monitor")).to_have_attribute("data-address", "22")
    # And they survive the panel being redrawn by a poll.
    page.locator("#selected-body .dev-poll").click()
    page.wait_for_timeout(500)
    expect(page.locator("#selected-body .dev-watch")).to_have_attribute(
        "data-address", "28", timeout=5000
    )


@pytest.mark.e2e
def test_arrows_reach_the_nearest_occupied_cell(page: Page, ring_url: str):
    """The browser's rule, vector by vector, against the resolver's (or the embedded) table."""
    _open_viewer(page, ring_url)
    vectors = _nearest_vectors()
    assert len(vectors) >= 20
    wrong = []
    for occupied, start, direction, want in vectors:
        got = page.evaluate(
            "([occ, from, dir]) => window.apothecaryRing.nearest(from, dir, occ)",
            [occupied, start, direction],
        )
        if got != want:
            wrong.append((occupied, start, direction, want, got))
    assert not wrong, f"nearest disagrees on {len(wrong)} vector(s): {wrong}"

    # On the page: arrows highlight, a chord is the corner, walking gets there too.
    page.keyboard.press("m")
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    page.keyboard.press("2")
    page.keyboard.press("7")  # the control ring: eight options, every cell held
    assert len(_wedges(page)) == 8
    page.keyboard.press("ArrowUp")
    expect(page.locator("#ring-overlay .wedge.hot")).to_have_attribute("data-cell", "8")
    page.keyboard.press("ArrowLeft")  # inside the chord window: the corner
    expect(page.locator("#ring-overlay .wedge.hot")).to_have_attribute("data-cell", "7")
    page.wait_for_timeout(300)  # past the window, so the next arrow is a walk, not a chord
    page.keyboard.press("ArrowDown")
    page.wait_for_timeout(300)
    expect(page.locator("#ring-overlay .wedge.hot")).to_have_attribute("data-cell", "4")
    page.keyboard.press("ArrowDown")
    page.wait_for_timeout(300)
    expect(page.locator("#ring-overlay .wedge.hot")).to_have_attribute("data-cell", "1")
    page.keyboard.press("ArrowRight")
    page.wait_for_timeout(300)
    expect(page.locator("#ring-overlay .wedge.hot")).to_have_attribute("data-cell", "2")
    page.keyboard.press("ArrowUp")
    page.wait_for_timeout(300)
    page.keyboard.press("ArrowRight")
    page.wait_for_timeout(300)  # 8 then 9: the same corner, reached by walking
    expect(page.locator("#ring-overlay .wedge.hot")).to_have_attribute("data-cell", "9")
    page.keyboard.press("Escape")
    assert _intents(page) == []


@pytest.mark.e2e
def test_five_backs_out_and_escape_closes(page: Page, ring_url: str):
    _open_viewer(page, ring_url)
    expect(
        page.locator("#contents-list .contents-item[data-path='printer_1'] .dev-badge")
    ).to_be_visible(timeout=10000)
    page.keyboard.press("m")
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    page.keyboard.press("2")
    page.keyboard.press("7")
    assert _title(page) == "Control"
    page.keyboard.press("5")
    assert _title(page) == "Device"
    page.keyboard.press("Backspace")
    assert _title(page) == "printer_1"
    # Backspace on the ring is the hub, not the viewer's step-out.
    assert page.evaluate("() => window.fractalViewer.focusPath") == []
    page.keyboard.press("5")  # at the top: closes
    expect(page.locator("#ring-overlay")).to_have_count(0)
    page.keyboard.press("m")
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    page.keyboard.press("2")
    page.keyboard.press("Escape")
    expect(page.locator("#ring-overlay")).to_have_count(0)
    assert _intents(page) == []


@pytest.mark.e2e
def test_the_pointer_uses_the_same_cells(page: Page, ring_url: str):
    """Hover in the band highlights the compass wedge; a click commits; the hub backs out."""
    _open_viewer(page, ring_url)
    page.locator("#contents-list .contents-item[data-path='printer_1']").click(button="right")
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    box = page.locator("#ring-svg").bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(cx, cy - 72)  # straight up, mid-band: cell 8
    expect(page.locator("#ring-overlay .wedge.hot")).to_have_attribute("data-cell", "8")
    page.mouse.move(cx + 72, cy)  # right: cell 6
    expect(page.locator("#ring-overlay .wedge.hot")).to_have_attribute("data-cell", "6")
    page.mouse.move(cx - 51, cy - 51)  # up-left: cell 7, empty on this ring, so nothing
    expect(page.locator("#ring-overlay .wedge.hot")).to_have_count(0)
    page.mouse.move(cx, cy + 72)
    page.mouse.click(cx, cy + 72)  # down: Device, a submenu
    assert _title(page) == "Device"
    page.mouse.click(cx, cy)  # the hub: back out
    assert _title(page) == "printer_1"
    page.mouse.click(cx, cy - 72)  # up: Zoom in
    expect(page.locator("#ring-overlay")).to_have_count(0)
    intents = _intents(page)
    assert [i["action"] for i in intents] == ["zoom-in"]
    assert intents[0]["address"] == "8"
    assert page.evaluate("() => window.fractalViewer.focusPath") == ["printer_1"]
    # Beyond the ring there is nothing to choose: a click there cancels.
    page.keyboard.press("m")
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    box = page.locator("#ring-svg").bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.click(cx + 108 * 1.35 + 20, cy)
    expect(page.locator("#ring-overlay")).to_have_count(0)
    assert len(_intents(page)) == 1


@pytest.mark.e2e
def test_jog_by_address_on_the_monitor_page(page: Page, ring_url: str):
    """Armed, 7 2 8 on the device ring jogs Y+: G91/G1/G90 in the log, and the button wears ⌗728."""
    page.add_init_script(CAPTURE)
    page.goto(f"{ring_url}/firmware/monitor?port={PRINTER}")
    expect(page.locator("#c-state")).not_to_have_text("—", timeout=10000)
    expect(page.locator("#ident")).to_contain_text("Marlin", timeout=8000)
    # Disarmed, the device ring's Control > Arm is the way in; the latch shows the address.
    expect(page.locator("#ctl")).to_have_attribute("data-address", "77", timeout=5000)
    page.keyboard.press("m")
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    assert _title(page) == "ttyFAKE1"
    assert _wedges(page)["1"] == "Link"
    assert _wedges(page)["7"] == "Control"
    page.keyboard.press("7")
    assert _wedges(page)["7"] == "Arm"
    page.keyboard.press("7")
    expect(page.locator("#control")).to_be_visible(timeout=5000)
    assert _intents(page)[-1]["address"] == "77"
    # Armed now: the same cell reads Disarm, and the overlay's buttons are numbered.
    expect(page.locator("#ctl")).to_have_attribute("data-address", "77", timeout=5000)
    expect(page.locator("#control button[data-jog='Y+']")).to_have_attribute(
        "data-address", "728", timeout=5000
    )
    expect(page.locator("#control button[data-cmd='M25']")).to_have_attribute("data-address", "796")
    # The link verbs have cells too: Link > Reconnect is 18 from this ring.
    expect(page.locator("#reconnect")).to_have_attribute("data-address", "18")
    expect(page.locator("#control button[data-cmd='M410']")).to_have_attribute(
        "data-address", "736"
    )
    expect(page.locator("#estop")).to_have_attribute("data-address", "71")
    assert (page.locator("#control button[data-jog='Y+']").get_attribute("title") or "").endswith(
        " · ⌗728"
    )

    page.locator(
        "#control button[data-cmd='M25']"
    ).click()  # pause the SD print, as the jog test does
    expect(page.locator("#c-state")).to_contain_text("idle", timeout=8000)
    page.locator("#control button[data-step='10']").click()
    page.locator("#control").click(button="right", position={"x": 10, "y": 10})
    try:
        expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    except AssertionError:
        raise AssertionError(
            "the ring did not open on a right-click; the page's last lines:\n"
            + "\n".join(page.locator("#log .sys").all_inner_texts()[-6:])
            + f"\nisOpen={page.evaluate('window.apothecaryRing.isOpen()')}"
        ) from None
    assert _wedges(page)["7"] == "Control"
    page.keyboard.press("7")
    assert _wedges(page)["7"] == "Disarm"
    page.keyboard.press("2")
    assert _title(page) == "Jog"
    page.keyboard.press("8")
    expect(page.locator("#ring-overlay")).to_have_count(0)
    intent = _intents(page)[-1]
    assert intent["action"] == "control:jog:Y+"
    assert intent["address"] == "728"
    assert intent["address"] == page.locator("#control button[data-jog='Y+']").get_attribute(
        "data-address"
    )
    expect(page.locator("#log .tx.control", has_text="G91").last).to_be_visible(timeout=8000)
    expect(page.locator("#log .tx.control", has_text="G1 Y10 F3000").last).to_be_visible()
    expect(page.locator("#log .tx.control", has_text="G90").last).to_be_visible()
    try:
        expect(page.locator("#c-pos")).to_contain_text("Y10.0", timeout=8000)
    except AssertionError:
        # Say what the board was told, not just where it ended up.
        raise AssertionError(
            "position after one jog: "
            + page.locator("#c-pos").inner_text()
            + "\n"
            + "\n".join(page.locator("#log .tx.control").all_inner_texts())
            + "\n"
            + f"intents: {_intents(page)}"
        ) from None
    # Disarm by address, and the overlay goes.
    page.keyboard.press("m")
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    page.keyboard.press("7")
    page.keyboard.press("7")
    expect(page.locator("#control")).to_be_hidden(timeout=5000)


@pytest.mark.e2e
def test_pieces_are_chosen_and_the_tree_walked_by_digits(page: Page, ring_url: str):
    """The Contents list, from the ring: Pieces lists the level, a digit selects,
    Into goes down a piece, Up goes back, and a zoomed level's Up steps out."""
    page.add_init_script(CAPTURE)
    page.goto(f"{ring_url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
    # Nothing selected: m opens the canvas ring, standing on the root.
    page.keyboard.press("Escape")
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    page.keyboard.press("m")
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    wedges = _wedges(page)
    assert wedges["8"] == "Pieces" and "Up" not in wedges.values()
    # Thirteen pieces: grouped in small lettered groups, each named for its
    # first piece. The page knows the address; the test asks rather than guesses.
    address = page.evaluate(
        "() => window.apothecaryRing.addressOf("
        "window.apothecaryRing.current().root, 'select:printer_1')"
    )
    assert address.startswith("8") and len(address) == 3 and "5" not in address
    page.keyboard.press("8")
    groups = _wedges(page)
    assert len(groups) >= 2 and groups["8"].startswith("cnc")  # sorted, named for the first
    for digit in address[1:]:
        page.keyboard.press(digit)
    expect(page.locator("#ring-overlay")).to_have_count(0)
    intent = _intents(page)[-1]
    assert intent["action"] == "select:printer_1" and intent["address"] == address
    expect(page.locator("#selected-body .prop-row", has_text="Name")).to_contain_text("printer_1")
    # The row it chose wears that address, from the canvas ring.
    expect(page.locator("#contents-list .contents-item[data-path='printer_1']")).to_have_attribute(
        "data-address", address, timeout=5000
    )

    # Into: the node ring lists what is inside; a digit selects it and opens the branch.
    page.keyboard.press("m")
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    wedges = _wedges(page)
    into_cell = next(c for c, label in wedges.items() if label == "Into")
    assert "Up" not in wedges.values()  # a top-level piece has nothing above it
    page.keyboard.press(into_cell)
    assert _wedges(page)["8"] == "frame_system"
    page.keyboard.press("8")
    expect(page.locator("#selected-body .prop-row", has_text="Name")).to_contain_text(
        "frame_system"
    )
    expect(
        page.locator("#contents-list .contents-item[data-path='printer_1.frame_system']")
    ).to_be_visible()
    page.keyboard.press("m")
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    wedges = _wedges(page)
    up_cell = next(c for c, label in wedges.items() if label == "Up")
    page.keyboard.press(up_cell)
    assert _intents(page)[-1]["action"] == "select:printer_1"
    expect(page.locator("#selected-body .prop-row", has_text="Name")).to_contain_text("printer_1")

    # Zoomed in, the canvas ring's Pieces are the level's two pieces and Up steps out.
    page.locator("#contents-list .contents-item[data-path='printer_1']").dblclick()
    expect(page.locator("#contents-list .contents-item", has_text="gantry_system")).to_be_visible(
        timeout=10000
    )
    # Empty canvas, right-clicked, is the canvas ring whatever is selected.
    page.locator("#viewer-canvas").click(button="right", position={"x": 8, "y": 8})
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    wedges = _wedges(page)
    assert wedges["8"] == "Pieces" and wedges["6"] == "Up"
    expect(page.locator("#zoom-out-btn")).to_have_attribute("data-address", "6", timeout=5000)
    page.keyboard.press("6")
    assert _intents(page)[-1]["action"] == "zoom-out"
    expect(page.locator("#contents-list .contents-item", has_text="workbench")).to_be_visible(
        timeout=10000
    )
