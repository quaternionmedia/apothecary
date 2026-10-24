"""The ring in a browser: nine cells, addresses, and the buttons that carry them.

Runs against a server of its own from the conftest's ``start_server``, like
``test_printer_ui.py``: the scripted ``arduino-cli``, the in-process simulated
printer mid-way through an SD print, and firmware state in a temp dir. Nothing
here opens a real port.

What is held to is rad's *the menu addresses nine cells*: options sit in
cells numbered as a numeric keypad, cardinals first (``8 6 2 4 9 3 1 7``);
a digit chooses its cell from anywhere; an arrow moves to the nearest
occupied cell in that direction, by the same rule the Python resolver runs;
5 backs out; and the digits pressed to reach an option are its address,
which the intent carries and the page's own buttons wear.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import Page, expect

PRINTER = "/dev/ttyFAKE1"
# The arrow rule as vectors, generated from menu.py's resolver; tests/test_menu.py
# fails when the file is missing or stale.
VECTORS = Path(__file__).resolve().parents[1] / "conformance" / "nine_cells.json"


@pytest.fixture(scope="module")
def ring_url(start_server):
    url = start_server()
    # The printer is identified (M115) and pinned to printer_1 up front, so the
    # node ring carries Device > Control from the first test on.
    httpx.post(f"{url}/firmware/devices/identify", json={"port": PRINTER}, timeout=15.0)
    r = httpx.put(
        f"{url}/sites/garage/nodes/printer_1/device", json={"identity": PRINTER}, timeout=15.0
    )
    assert r.status_code == 200, r.text
    return url


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
    # And they survive the panel being redrawn by a poll: the section is replaced,
    # so the one without the mark set here is the redrawn one.
    page.evaluate(
        "() => { document.querySelector('#selected-body .device-section').dataset.old = 1 }"
    )
    page.locator("#selected-body .dev-poll").click()
    redrawn = page.locator("#selected-body .device-section:not([data-old]) .dev-watch")
    expect(redrawn).to_have_attribute("data-address", "28", timeout=5000)


@pytest.mark.e2e
def test_arrows_reach_the_nearest_occupied_cell(page: Page, ring_url: str):
    """The browser's rule, vector by vector, against the resolver's table."""
    _open_viewer(page, ring_url)
    vectors = json.loads(VECTORS.read_text(encoding="utf-8"))["nearest"]
    assert len(vectors) >= 20
    wrong = []
    for v in vectors:
        got = page.evaluate(
            "([occ, from, dir]) => window.apothecaryRing.nearest(from, dir, occ)",
            [v["occupied"], v["from"], v["direction"]],
        )
        if got != v["expect"]:
            wrong.append({**v, "got": got})
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
    # The menu names its highlighted item by that item's id.
    expect(page.locator("#ring-overlay")).to_have_attribute("aria-activedescendant", "ring-cell-6")
    expect(page.locator("#ring-cell-6")).to_have_attribute("data-cell", "6")
    page.mouse.move(cx - 51, cy - 51)  # up-left: cell 7, empty on this ring, so nothing
    expect(page.locator("#ring-overlay .wedge.hot")).to_have_count(0)
    assert page.locator("#ring-overlay").get_attribute("aria-activedescendant") is None
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
    # Sixteen pieces: grouped in small lettered groups, each named for its
    # first piece in name order. The page knows the address; the test asks
    # rather than guesses.
    address = page.evaluate(
        "() => window.apothecaryRing.addressOf("
        "window.apothecaryRing.current().root, 'select:printer_1')"
    )
    assert address.startswith("8") and len(address) == 3 and "5" not in address
    page.keyboard.press("8")
    groups = _wedges(page)
    assert len(groups) >= 2 and groups["8"].startswith("arduino")  # sorted, named for the first
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


def _open_panels(page: Page, url: str):
    """The garage viewer with the rail as it starts (each test has fresh storage)."""
    page.goto(f"{url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
    return page.locator(".panel-rail-right"), page.locator(".viewer-panel")


def _world_is(page: Page, width: float):
    page.wait_for_function(
        "(w) => Math.abs(document.querySelector('.viewer-panel').offsetWidth - w) <= 2", arg=width
    )


@pytest.mark.e2e
def test_a_panel_closes_to_a_tab_and_collapses(page: Page, ring_url: str):
    """The side column is a rail of panels, and the world keeps at least half the window.
    A closed panel leaves a tab that brings it back; a collapsed one keeps its title."""
    rail, world = _open_panels(page, ring_url)
    ids = page.evaluate("() => window.apothecaryPanels.list().map((p) => p.id)")
    assert ids == ["contents", "selected", "jobs", "validation", "scad", "camera"]
    assert page.evaluate("() => window.apothecaryPanels.state('camera').open") is False
    expect(rail.locator(".panel[data-panel='contents']")).to_be_visible()
    assert world.bounding_box()["width"] >= page.viewport_size["width"] / 2

    # Close: gone from the rail, a tab remains; the tab brings it back.
    page.locator(".panel[data-panel='validation'] .panel-close").click()
    expect(page.locator(".panel-tab[data-panel='validation']")).to_be_visible(timeout=1000)
    expect(rail.locator(".panel[data-panel='validation']")).to_have_count(0)
    page.locator(".panel-tab[data-panel='validation']").click()
    expect(rail.locator(".panel[data-panel='validation']")).to_be_visible(timeout=1000)
    expect(page.locator(".panel-tab")).to_have_count(1)  # the camera's, closed by default

    # Collapse: the body folds, the title stays.
    page.locator(".panel[data-panel='contents'] .panel-collapse").click()
    expect(page.locator("#contents-list")).to_be_hidden(timeout=1000)
    page.locator(".panel[data-panel='contents'] .panel-collapse").click()
    expect(page.locator("#contents-list")).to_be_visible(timeout=1000)


@pytest.mark.e2e
def test_a_panel_floats_drags_and_docks(page: Page, ring_url: str):
    """Floated, a panel leaves the rail, follows the pointer, stays on the page, docks back."""
    rail, world = _open_panels(page, ring_url)
    page.locator(".panel[data-panel='selected'] .panel-float").click()
    free = page.locator(".panel-free-layer .panel[data-panel='selected']")
    expect(free).to_be_visible(timeout=1000)
    before = free.bounding_box()
    title = free.locator(".panel-title")
    tb = title.bounding_box()
    page.mouse.move(tb["x"] + 120, tb["y"] + tb["height"] / 2)
    page.mouse.down()
    page.mouse.move(tb["x"] + 120 - 200, tb["y"] + tb["height"] / 2 + 150, steps=8)
    page.mouse.up()
    after = free.bounding_box()
    assert after["x"] == pytest.approx(before["x"] - 200, abs=3)
    assert after["y"] == pytest.approx(before["y"] + 150, abs=3)
    # Dragged past the edge, it is clamped to the page.
    tb = title.bounding_box()
    page.mouse.move(tb["x"] + 120, tb["y"] + tb["height"] / 2)
    page.mouse.down()
    page.mouse.move(-500, tb["y"] + tb["height"] / 2, steps=6)
    page.mouse.up()
    wb = world.bounding_box()
    assert free.bounding_box()["x"] >= wb["x"] - 1
    # Dock it back.
    free.locator(".panel-float").click()
    expect(rail.locator(".panel[data-panel='selected']")).to_be_visible(timeout=1000)


@pytest.mark.e2e
def test_a_closed_panel_stays_closed_and_the_ring_reopens_it(page: Page, ring_url: str):
    """What was done survives a reload; the ring's Panels cell reaches a panel by address;
    with every panel closed the world has the whole width."""
    rail, world = _open_panels(page, ring_url)
    page.locator(".panel[data-panel='scad'] .panel-close").click()
    page.reload()
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
    expect(page.locator(".panel-tab[data-panel='scad']")).to_be_visible(timeout=2000)
    assert page.evaluate("() => window.apothecaryPanels.state('scad').open") is False

    # From the ring: Panels › OpenSCAD reopens it by address.
    page.locator("#viewer-canvas").click(button="right", position={"x": 30, "y": 30})
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    wedges = _wedges(page)
    panels_cell = next(cell for cell, label in wedges.items() if label == "Panels")
    page.keyboard.press(panels_cell)
    assert _title(page) == "Panels"
    inner = _wedges(page)
    scad_cell = next(cell for cell, label in inner.items() if label == "OpenSCAD")
    page.keyboard.press(scad_cell)
    expect(page.locator("#ring-overlay")).to_have_count(0)
    expect(rail.locator(".panel[data-panel='scad']")).to_be_visible(timeout=2000)
    expect(page.locator(".panel-tab")).to_have_count(1)  # the camera's, closed by default

    # Every panel closed: the world has the whole width, and six tabs wait.
    for pid in ["contents", "selected", "jobs", "validation", "scad"]:
        page.evaluate("(id) => window.apothecaryPanels.close(id)", pid)
    expect(page.locator(".panel-tab")).to_have_count(6, timeout=2000)
    _world_is(page, page.viewport_size["width"])


@pytest.mark.e2e
def test_the_rail_hides_resizes_and_changes_sides(page: Page, ring_url: str):
    """The tilde hides and shows the rail (a tab stands in meanwhile), its edge drags to
    a width of at most half the page, and its grip drags it to the other side -- all of
    it remembered; the ring's Panels > Rail hides it too."""
    rail, world = _open_panels(page, ring_url)
    full = page.viewport_size["width"]
    page.locator("#job-name").focus()
    page.keyboard.press("`")  # typing a tilde into a box is typing, not a toggle
    expect(page.locator("#job-name")).to_have_value("`")
    expect(rail).to_be_visible()
    page.locator("#viewer-canvas").click(position={"x": 200, "y": 200})
    page.keyboard.press("`")
    expect(rail).to_be_hidden(timeout=1000)
    expect(page.locator(".panel-tab-rail[data-rail='right']")).to_be_visible()
    _world_is(page, full)
    page.keyboard.press("`")
    expect(rail).to_be_visible(timeout=1000)

    before = page.evaluate("() => window.apothecaryPanels.railWidth('right')")
    edge = rail.locator(".panel-rail-resizer").bounding_box()
    page.mouse.move(edge["x"] + 3, edge["y"] + 200)
    page.mouse.down()
    page.mouse.move(edge["x"] + 3 - 150, edge["y"] + 200, steps=6)
    page.mouse.up()
    wider = page.evaluate("() => window.apothecaryPanels.railWidth('right')")
    assert wider == pytest.approx(before + 150, abs=3)
    page.mouse.move(edge["x"] + 3 - 150, edge["y"] + 200)
    page.mouse.down()
    page.mouse.move(-2000, edge["y"] + 200, steps=6)  # far past the limit
    page.mouse.up()
    assert page.evaluate("() => window.apothecaryPanels.railWidth('right')") <= full / 2 + 1
    assert world.bounding_box()["width"] >= full / 2 - 2

    grip = rail.locator(".panel-rail-grip").bounding_box()
    page.mouse.move(grip["x"] + 5, grip["y"] + 5)
    page.mouse.down()
    page.mouse.move(100, grip["y"] + 5, steps=8)
    page.mouse.up()
    left = page.locator(".panel-rail-left")
    expect(left.locator(".panel[data-panel='contents']")).to_be_visible(timeout=1000)
    expect(rail).to_be_hidden()
    page.reload()
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
    expect(left.locator(".panel[data-panel='contents']")).to_be_visible(timeout=2000)
    left.locator(".panel-rail-swap").click()
    expect(rail.locator(".panel[data-panel='contents']")).to_be_visible(timeout=1000)

    # From the ring: Panels > Rail hides it too.
    page.locator("#viewer-canvas").click(button="right", position={"x": 30, "y": 30})
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    page.keyboard.press(next(cell for cell, label in _wedges(page).items() if label == "Panels"))
    page.keyboard.press(next(cell for cell, label in _wedges(page).items() if label == "Rail"))
    expect(rail).to_be_hidden(timeout=2000)
    page.keyboard.press("`")
    expect(rail).to_be_visible(timeout=1000)
