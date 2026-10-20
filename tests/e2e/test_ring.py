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
import re
from pathlib import Path

import httpx
import pytest
import windows
from playwright.sync_api import Page, expect

PRINTER = "/dev/ttyFAKE1"
MACHINE = ".panel[data-panel='machine']"  # a board's Machine, in front of the world
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
        # Every piece's own, in the same cells everywhere.
        "8": "Step in",
        "6": "Move",
        "2": "Why this",
        # What this piece is: what is inside it, a host's camera and pictures, a part's
        # editor.
        "4": "Inside",
        "9": "Camera",
        "3": "Picture",
        "1": "Part",
        # A board pinned to it comes and goes, so it is seated last: the eighth.
        "7": "Device",
    }
    assert page.locator("#ring-overlay .wedge.empty").count() == 0
    assert page.locator("#ring-overlay .hub-digit").text_content() == "5"
    assert _title(page) == "printer_1"
    # Every wedge shows its digit, occupied or not; a parented option shows a chevron.
    digits = page.locator("#ring-overlay .digit").all_text_contents()
    assert sorted(digits) == ["1", "2", "3", "4", "6", "7", "8", "9"]
    assert page.locator("#ring-overlay .label", has_text="Device ›").count() == 1
    page.keyboard.press("Escape")
    expect(ring).to_have_count(0)


@pytest.mark.e2e
def test_the_toolbar_button_and_ctrl_right_click_open_it_too(page: Page, ring_url: str):
    _open_viewer(page, ring_url)
    page.locator("#ring-open").click()
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    assert _title(page) == "printer_1"
    page.keyboard.press("Escape")
    expect(page.locator("#ring-overlay")).to_have_count(0)
    # Ctrl+right-click on another row opens that row's ring, and selects the row.
    page.locator("#contents-list .contents-item[data-path='cnc_router']").click(
        button="right", modifiers=["Control"]
    )
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    assert _title(page) == "cnc_router"
    # Nothing pinned: no Device option at all, not a greyed one, and no cell moved.
    assert _wedges(page) == {
        "8": "Step in",
        "6": "Move",
        "2": "Why this",
        "4": "Inside",
        "9": "Camera",
        "3": "Picture",
    }
    expect(page.locator("#contents-list .contents-item[data-path='cnc_router']")).to_have_class(
        "contents-item selected"
    )
    page.keyboard.press("Escape")


@pytest.mark.e2e
def test_digits_walk_device_control_jog_and_the_intent_carries_the_address(
    page: Page, ring_url: str
):
    """7 7 2 8 reaches Jog > Y+ from printer_1's ring, Device seated last; the intent says so,
    and so does the page."""
    # Device's cells: Open (the board's Machine), Flash, ..., and Control, after Link,
    # in cell 7.
    _open_viewer(page, ring_url)
    expect(
        page.locator("#contents-list .contents-item[data-path='printer_1'] .dev-badge")
    ).to_be_visible(timeout=10000)
    page.keyboard.press("m")
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    page.keyboard.press("7")
    assert _title(page) == "Device"
    assert _wedges(page) == {
        "8": "Open",
        "6": "Poll",
        "2": "Flash",
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
    assert page.locator("#ring-overlay .address").text_content() == "⌗772"
    page.keyboard.press("8")
    expect(page.locator("#ring-overlay")).to_have_count(0)
    intents = _intents(page)
    assert len(intents) == 1
    intent = intents[0]
    assert intent["action"] == "control:jog:Y+"
    assert intent["option_id"] == "control:jog:Y+"
    assert intent["address"] == "7728"
    assert intent["context"] == {"pointing": "node", "targets": ["printer_1"]}
    # The same address, worked out from the ring itself two ways.
    by_path = page.evaluate(
        "() => window.apothecaryRing.addressOf(window.apothecaryRing.lastRing(), "
        "['device', 'control', 'control:jog', 'Y+'])"
    )
    by_action = page.evaluate(
        "() => window.apothecaryRing.addressOf(window.apothecaryRing.lastRing(), 'control:jog:Y+')"
    )
    assert by_path == by_action == intent["address"]
    # A board's verb goes to its Machine, opened for it: disarmed, the jog is refused,
    # and the status line says so as an error, with its address.
    expect(page.locator("#status")).to_contain_text("⌗7728", timeout=5000)
    expect(page.locator("#status")).to_contain_text("not armed")
    expect(page.locator("#status")).to_have_class(re.compile(r"\berror\b"))
    expect(page.locator(".panel[data-panel='machine']")).to_be_visible()
    page.evaluate("() => window.fractalViewer.closeMachine()")
    # "Appear as generated": the Device section's buttons wear their addresses.
    opener = page.locator("#selected-body .dev-open")
    expect(opener).to_have_attribute("data-address", "78", timeout=5000)
    assert (opener.get_attribute("title") or "").endswith(" · ⌗78")
    expect(page.locator("#selected-body .dev-unpin")).to_have_attribute("data-address", "79")
    # And they survive the panel being redrawn by a poll: the section is replaced,
    # so the one without the mark set here is the redrawn one.
    page.evaluate(
        "() => { document.querySelector('#selected-body .device-section').dataset.old = 1 }"
    )
    page.evaluate("() => window.fractalViewer.pollNow('/dev/ttyFAKE1')")
    redrawn = page.locator("#selected-body .device-section:not([data-old]) .dev-open")
    expect(redrawn).to_have_attribute("data-address", "78", timeout=5000)


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

    # On the page: arrows highlight, walking from cell to cell, and a chord is the corner.
    page.keyboard.press("m")
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    page.keyboard.press("7")
    page.keyboard.press("7")  # the control ring: eight options, every cell held
    assert len(_wedges(page)) == 8
    hot = page.locator("#ring-overlay .wedge.hot")

    def walk(key: str, cell: str) -> None:
        page.keyboard.press(key)
        expect(hot).to_have_attribute("data-cell", cell)
        page.wait_for_timeout(300)  # past the chord window, so the next arrow is a walk

    for key, cell in (("ArrowUp", "8"), ("ArrowLeft", "7"), ("ArrowDown", "4"), ("ArrowDown", "1")):
        walk(key, cell)
    # From 1, Up then Right inside the chord window: the corner between them, 9. Walked,
    # the same two arrows go up to 4 and on to 6, the next held cell right of it. The
    # chord's two keys are sent in one turn of the page, so a busy machine cannot hold
    # them apart past the window.
    page.evaluate(
        "() => ['ArrowUp', 'ArrowRight'].forEach((key) => "
        "window.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true })))"
    )
    expect(hot).to_have_attribute("data-cell", "9")
    page.wait_for_timeout(300)
    for key, cell in (
        ("ArrowDown", "6"),
        ("ArrowDown", "3"),
        ("ArrowLeft", "2"),
        ("ArrowLeft", "1"),
    ):
        walk(key, cell)
    walk("ArrowUp", "4")
    walk("ArrowRight", "6")
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
    page.keyboard.press("7")
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
    page.keyboard.press("7")
    page.keyboard.press("Escape")
    expect(page.locator("#ring-overlay")).to_have_count(0)
    assert _intents(page) == []


@pytest.mark.e2e
def test_the_pointer_uses_the_same_cells(page: Page, ring_url: str):
    """Hover in the band highlights the compass wedge; a click commits; the hub backs out."""
    _open_viewer(page, ring_url)
    page.locator("#contents-list .contents-item[data-path='printer_1']").click(
        button="right", modifiers=["Control"]
    )
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
    # Over an empty cell the pointer highlights nothing. printer_1's ring is
    # full (its eighth cell is Part), so that is shown on the CNC router's, which
    # has no board pinned and no part, and leaves cell 7 empty.
    page.keyboard.press("Escape")
    expect(page.locator("#ring-overlay")).to_have_count(0)
    page.locator("#contents-list .contents-item[data-path='cnc_router']").click(
        button="right", modifiers=["Control"]
    )
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    assert _title(page) == "cnc_router"
    box = page.locator("#ring-svg").bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(cx - 51, cy - 51)  # up-left: cell 7, empty on this ring, so nothing
    expect(page.locator("#ring-overlay .wedge.hot")).to_have_count(0)
    assert page.locator("#ring-overlay").get_attribute("aria-activedescendant") is None
    page.keyboard.press("Escape")
    expect(page.locator("#ring-overlay")).to_have_count(0)
    page.locator("#contents-list .contents-item[data-path='printer_1']").click(
        button="right", modifiers=["Control"]
    )
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    box = page.locator("#ring-svg").bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(cx - 51, cy - 51)
    page.mouse.click(cx - 51, cy - 51)  # up-left: Device, seated last, a submenu
    assert _title(page) == "Device"
    page.mouse.click(cx, cy)  # the hub: back out
    assert _title(page) == "printer_1"
    page.mouse.click(cx, cy - 72)  # up: Step in
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
def test_jog_by_address_on_a_machine_s_device_ring(page: Page, ring_url: str):
    """The printer monitor's address opens the printer's Machine in front of the world;
    inside it the ring is its device ring. Armed, 7 2 8 jogs Y+: G91/G1/G90 in the log,
    and the button wears ⌗728."""
    page.add_init_script(CAPTURE)
    page.goto(f"{ring_url}/firmware/monitor?port={PRINTER}")
    expect(page.locator(MACHINE)).to_be_visible(timeout=15000)
    expect(page.locator("#c-state")).not_to_have_text("—", timeout=10000)
    expect(page.locator("#ident")).to_contain_text("Marlin", timeout=8000)
    # Disarmed, the device ring's Control > Arm is the way in; the latch shows the address.
    expect(page.locator("#ctl")).to_have_attribute("data-address", "77", timeout=5000)
    page.locator(f"{MACHINE} #ident").click(button="right", modifiers=["Control"])
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
    page.locator("#control").click(
        button="right", modifiers=["Control"], position={"x": 10, "y": 10}
    )
    try:
        expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    except AssertionError:
        raise AssertionError(
            "the ring did not open on a Ctrl+right-click; the page's last lines:\n"
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
    page.locator(f"{MACHINE} #ident").click(button="right", modifiers=["Control"])
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    page.keyboard.press("7")
    page.keyboard.press("7")
    expect(page.locator("#control")).to_be_hidden(timeout=5000)


@pytest.mark.e2e
def test_pieces_are_chosen_and_the_tree_walked_by_digits(page: Page, ring_url: str):
    """The Contents list, from the ring: Pieces lists the level, a digit selects,
    Inside goes down a piece, Parent goes back, and a stepped-in level's Step out steps
    out."""
    page.add_init_script(CAPTURE)
    page.goto(f"{ring_url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
    # Nothing selected: m opens the canvas ring, standing on the root.
    page.keyboard.press("Escape")
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    page.keyboard.press("m")
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    wedges = _wedges(page)
    assert wedges["8"] == "Pieces" and "Step out" not in wedges.values()
    # The garage's pieces, grouped in small lettered groups, each named for its
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

    # Inside: the node ring lists what is inside; a digit selects it and opens the branch.
    page.keyboard.press("m")
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    wedges = _wedges(page)
    into_cell = next(c for c, label in wedges.items() if label == "Inside")
    assert "Parent" not in wedges.values()  # a top-level piece has nothing above it
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
    up_cell = next(c for c, label in wedges.items() if label == "Parent")
    page.keyboard.press(up_cell)
    assert _intents(page)[-1]["action"] == "select:printer_1"
    expect(page.locator("#selected-body .prop-row", has_text="Name")).to_contain_text("printer_1")

    # Stepped in, the canvas ring's Pieces are the level's two pieces and Step out, seated
    # after every cell the canvas ring always has, steps out.
    page.locator("#contents-list .contents-item[data-path='printer_1']").dblclick()
    expect(page.locator("#contents-list .contents-item", has_text="gantry_system")).to_be_visible(
        timeout=10000
    )
    # Empty canvas, Ctrl+right-clicked, is the canvas ring whatever is selected.
    page.locator("#viewer-canvas").click(
        button="right", modifiers=["Control"], position={"x": 8, "y": 8}
    )
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    wedges = _wedges(page)
    assert wedges["8"] == "Pieces" and wedges["6"] == "Site" and wedges["1"] == "Step out"
    # The trail's crumb one level up is Step out, and wears its address.
    up_crumb = page.locator("#breadcrumb .crumb").nth(-2)
    expect(up_crumb).to_have_attribute("data-address", "1", timeout=5000)
    page.keyboard.press("1")
    assert _intents(page)[-1]["action"] == "zoom-out"
    expect(page.locator("#contents-list .contents-item", has_text="workbench")).to_be_visible(
        timeout=10000
    )


def _open_panels(page: Page, url: str):
    """The garage viewer with its windows as they start (each test has fresh storage)."""
    page.goto(f"{url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
    return page.locator(windows.WORLD)


def _second_tab(page: Page):
    """A second tab among Pictures', as a Machine is: registered the way the page
    registers one, with a body of its own."""
    page.evaluate(
        """() => {
            const el = document.createElement('div');
            el.id = 'second-body';
            el.textContent = 'a second tab';
            window.apothecaryPanels.register('second', { title: 'Second', body: el });
        }"""
    )


def _panels_ring(page: Page) -> dict:
    """The canvas ring opened on Panels: its cells."""
    page.locator("#viewer-canvas").click(
        button="right", modifiers=["Control"], position={"x": 30, "y": 30}
    )
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    page.keyboard.press(next(cell for cell, label in _wedges(page).items() if label == "Panels"))
    expect(page.locator("#ring-overlay .title")).to_have_text("Panels")
    return _wedges(page)


@pytest.mark.e2e
def test_the_world_and_the_panels_are_windows_of_one_layout(page: Page, ring_url: str):
    """The world and every panel are windows of one layout: Site above Selected in the
    column on the world's right, Pictures, the Bench and Settings tabs below them, the
    first in front. A panel the page registers later joins those tabs behind the one in
    front; a tab pressed brings its panel in front."""
    world = _open_panels(page, ring_url)
    ids = page.evaluate("() => window.apothecaryPanels.list().map((p) => p.id)")
    assert ids == [
        "world",
        "site",
        "problems",
        "pinned",
        "jobs",
        "scad",
        "selected",
        "pictures",
        "bench",
        "settings",
        "gather",
        "airgap",
        # The Airgap's sections, each a window of its own, closed until asked for.
        *(f"airgap-{sid}" for sid in windows.AIRGAP_SECTIONS),
    ]
    assert not any(windows.state(page, f"airgap-{s}")["open"] for s in windows.AIRGAP_SECTIONS)
    expect(page.locator(".lm_goldenlayout")).to_have_count(1)
    expect(windows.tab(page, "world")).to_have_count(0)  # the world's window has no tab
    site, selected = windows.panel(page, "site"), windows.panel(page, "selected")
    expect(site).to_be_visible()
    expect(selected).to_be_visible()
    assert site.bounding_box()["y"] < selected.bounding_box()["y"]  # Site on top
    wb = world.bounding_box()
    assert site.bounding_box()["x"] >= wb["x"] + wb["width"] - 1  # on the world's right
    assert wb["x"] <= 1 and wb["width"] >= page.viewport_size["width"] / 2
    assert windows.state(page, "pictures")["stack"] == ["pictures", "bench", "settings"]
    assert windows.state(page, "pictures")["shown"] is True
    expect(windows.panel(page, "bench")).to_be_hidden()
    pictures_y = windows.panel(page, "pictures").bounding_box()["y"]
    assert pictures_y > selected.bounding_box()["y"]  # below Selected
    # Registered later: a tab of the same stack, behind the one in front.
    _second_tab(page)
    expect(windows.tab(page, "second")).to_have_count(1)
    assert windows.state(page, "second")["stack"] == ["pictures", "bench", "settings", "second"]
    expect(windows.panel(page, "second")).to_be_hidden()
    expect(windows.panel(page, "pictures")).to_be_visible()
    # Selecting a piece from Site's tree fills Selected and moves nothing in Site.
    before = site.bounding_box()
    row = page.locator("#contents-list .contents-item[data-path='printer_1']")
    at = row.bounding_box()
    row.click()
    expect(selected.locator("#pos-x")).to_be_visible(timeout=5000)
    assert site.bounding_box() == before and row.bounding_box() == at

    # A tab pressed: its panel in front, the other behind it.
    windows.show(page, "second")
    expect(page.locator("#second-body")).to_be_visible()
    expect(windows.panel(page, "pictures")).to_be_hidden()
    windows.show(page, "pictures")
    expect(page.locator("#pictures-list")).to_be_visible(timeout=5000)
    expect(windows.tab(page, "pictures")).to_have_class(re.compile(r"\blm_active\b"))


@pytest.mark.e2e
def test_a_closed_window_stays_closed_and_the_ring_reopens_it(page: Page, ring_url: str):
    """A window closed by its tab's ✕ stays closed after a reload; the ring's Panels
    reaches it by address and opens it in front; with every panel closed the world has
    the whole width."""
    world = _open_panels(page, ring_url)
    windows.close(page, "site")
    expect(windows.panel(page, "site")).to_have_count(0)
    page.reload()
    expect(world).to_be_visible(timeout=15000)
    page.wait_for_function("() => window.apothecaryPanels && window.apothecaryPanels.state('site')")
    assert windows.state(page, "site")["open"] is False

    # From the ring: Panels › Site opens it by address.
    inner = _panels_ring(page)
    assert sorted(inner.values()) == [
        "Airgap",
        "Bench",
        "Docs",
        "Machine",
        "Pictures",
        "Selected",
        "Site",
        "Windows",
    ]
    page.keyboard.press(next(cell for cell, label in inner.items() if label == "Site"))
    # Panels › Site is a ring of Site and its own windows: Site first.
    site_ring = _wedges(page)
    assert sorted(site_ring.values()) == ["Jobs", "Pinned", "Problems", "SCAD", "Site"]
    page.keyboard.press(next(cell for cell, label in site_ring.items() if label == "Site"))
    expect(page.locator("#ring-overlay")).to_have_count(0)
    expect(windows.panel(page, "site")).to_be_visible()
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)

    # Panels › Bench › Bench brings the Bench in front of Pictures.
    inner = _panels_ring(page)
    page.keyboard.press(next(cell for cell, label in inner.items() if label == "Bench"))
    page.keyboard.press(next(cell for cell, label in _wedges(page).items() if label == "Bench"))
    expect(windows.panel(page, "bench")).to_be_visible(timeout=5000)
    expect(windows.panel(page, "pictures")).to_be_hidden()

    # Every panel closed: the world has the whole width.
    for state in page.evaluate("() => window.apothecaryPanels.list()")[1:]:
        page.evaluate("(id) => window.apothecaryPanels.close(id)", state["id"])
    expect(page.locator(".panel")).to_have_count(0)
    windows.world_is(page, page.viewport_size["width"])
    # The world alone in the layout, a panel opens beside it again, after a reload too.
    page.wait_for_timeout(400)  # the layout is remembered a moment after it changes
    page.reload()
    expect(world).to_be_visible(timeout=15000)
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    inner = _panels_ring(page)
    page.keyboard.press(next(cell for cell, label in inner.items() if label == "Site"))
    page.keyboard.press(next(cell for cell, label in _wedges(page).items() if label == "Site"))
    expect(windows.panel(page, "site")).to_be_visible(timeout=5000)
    expect(page.locator(windows.WORLD_HEADER)).to_be_hidden()
    assert world.bounding_box()["width"] < page.viewport_size["width"] - 100
    assert errors == [], errors


@pytest.mark.e2e
def test_a_window_dragged_beside_the_world_is_remembered_until_the_layout_is_reset(
    page: Page, ring_url: str
):
    """Pictures' tab dragged onto the world's left edge: a window of its own on the
    world's left, the world narrower; a reload finds it there. Panels › Windows ›
    Reset layout puts every window where the page puts it."""
    world = _open_panels(page, ring_url)
    wb = world.bounding_box()
    windows.drag(page, windows.tab(page, "pictures"), (wb["x"] + 30, wb["y"] + wb["height"] / 2))
    pictures = windows.panel(page, "pictures")
    expect(pictures).to_be_visible()
    page.wait_for_function(
        "() => document.querySelector(\".panel[data-panel='pictures']\").getBoundingClientRect().x < 2"
    )
    # The world on its right.
    assert world.bounding_box()["x"] >= pictures.bounding_box()["width"] - 1
    assert windows.state(page, "pictures")["stack"] == ["pictures"]
    assert windows.state(page, "bench")["stack"] == ["bench", "settings"]
    page.wait_for_timeout(400)  # the layout is remembered a moment after it changes
    page.reload()
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
    assert pictures.bounding_box()["x"] < 2
    assert windows.state(page, "pictures")["stack"] == ["pictures"]
    expect(page.locator(windows.WORLD_HEADER)).to_be_hidden()  # still no tab of its own

    inner = _panels_ring(page)
    page.keyboard.press(next(cell for cell, label in inner.items() if label == "Windows"))
    assert sorted(_wedges(page).values()) == [
        "Airgap view", "Machine view", "Part view", "Reset layout", "World alone",
    ]  # fmt: skip
    page.keyboard.press(
        next(cell for cell, label in _wedges(page).items() if label == "Reset layout")
    )
    expect(page.locator("#status")).to_contain_text("The page's own layout again")
    assert windows.state(page, "pictures")["stack"] == ["pictures", "bench", "settings"]
    assert world.bounding_box()["x"] <= 1

    # A tab dropped on the world's own right quarter: a window of its own there, with
    # its tab to drag, close and find it by; the world's window still has none.
    wb = world.bounding_box()
    to = (wb["x"] + wb["width"] * 0.85, wb["y"] + wb["height"] / 2)
    windows.drag(page, windows.tab(page, "bench"), to)
    page.wait_for_function("() => window.apothecaryPanels.state('bench').stack.length === 1")
    expect(windows.tab(page, "bench")).to_be_visible()
    expect(page.locator(windows.WORLD_HEADER)).to_be_hidden()


@pytest.mark.e2e
def test_a_stacks_plus_opens_any_window_there_and_windows_lists_them_by_group(
    page: Page, ring_url: str
):
    """Every stack but the world's wears a + among its buttons: pressed, every window by
    its group, ● open and ○ closed; a closed one chosen opens as a tab of that stack.
    The header's ⊞ Windows lists the views and the same windows, the first focused and
    the arrows moving along them; a window chosen there opens at its place, a view lays
    its windows out."""
    world = _open_panels(page, ring_url)
    expect(page.locator(".lm_stack:has(.world-window) .lm_spawn")).to_have_count(0)
    plus = page.locator(".lm_stack:has(.lm_tab[data-panel='site']) .lm_spawn")
    plus.click()
    spawn = page.locator(".spawn-list")
    expect(spawn).to_be_visible()
    groups = spawn.locator(".spawn-group").all_inner_texts()
    assert [g.lower() for g in groups[:3]] == ["site", "selected", "pictures"]
    assert "airgap" in [g.lower() for g in groups]
    expect(spawn.locator(".window-item[data-window='gather']")).to_have_text("○ Gather")
    expect(spawn.locator(".window-item[data-window='site']")).to_have_text("● Site")
    page.keyboard.press("Escape")
    expect(spawn).to_have_count(0)
    # Gather, closed, chosen from Site's +: a tab among Site's, in front.
    plus.click()
    spawn.locator(".window-item[data-window='gather']").click()
    expect(spawn).to_have_count(0)
    expect(windows.panel(page, "gather")).to_be_visible()
    assert windows.state(page, "gather")["stack"][-1] == "gather"
    assert windows.state(page, "gather")["stack"][0] == "site"

    # ⊞ Windows: the views, then the windows; the first focused, the arrows moving.
    page.locator("#windows-menu > summary").click()
    body = page.locator(".windows-menu-body")
    expect(body.locator(".view-item")).to_have_text(["Default", "Part", "Machine", "Airgap"])
    expect(body.locator(".window-item[data-window='gather']")).to_have_text("● Gather")
    assert page.evaluate("() => document.activeElement.dataset.view") == "default"
    page.keyboard.press("ArrowDown")
    assert page.evaluate("() => document.activeElement.dataset.view") == "part"
    page.keyboard.press("Enter")
    expect(body).to_be_hidden()
    # The Part view: Selected in front beside the world, Site's below it, the rest closed.
    assert windows.state(page, "selected")["stack"][0] == "selected"
    assert windows.state(page, "site")["stack"] == ["site", "problems", "scad"]
    assert windows.state(page, "gather")["open"] is False
    expect(page.locator(windows.WORLD_HEADER)).to_be_hidden()
    assert world.bounding_box()["width"] > 600
    # Default again, from the menu.
    page.locator("#windows-menu > summary").click()
    body.locator(".view-item[data-view='default']").click()
    assert windows.state(page, "pictures")["stack"] == ["pictures", "bench", "settings"]


@pytest.mark.e2e
def test_the_tilde_shows_the_world_alone_and_the_ring_does_too(page: Page, ring_url: str):
    """The tilde shows the world alone, the whole width, and again every window back;
    typed into a box it is typing; Panels › Windows › World alone does it too."""
    _open_panels(page, ring_url)
    full = page.viewport_size["width"]
    before = windows.world_width(page)
    page.evaluate("() => window.apothecaryPanels.open('gather')")
    page.locator("#gather-answers").focus()
    page.keyboard.press("`")  # typing a tilde into a box is typing, not a toggle
    expect(page.locator("#gather-answers")).to_have_value("`")
    expect(windows.panel(page, "site")).to_be_visible()
    page.locator("#viewer-canvas").click(position={"x": 200, "y": 200})
    page.keyboard.press("`")
    windows.world_is(page, full)
    expect(windows.panel(page, "site")).to_be_hidden()
    assert page.evaluate("() => window.apothecaryPanels.isWorldAlone()") is True
    page.keyboard.press("`")
    expect(windows.panel(page, "site")).to_be_visible()
    windows.world_is(page, before)
    page.keyboard.press("~")
    windows.world_is(page, full)
    page.keyboard.press("~")
    windows.world_is(page, before)

    # From the ring: Panels › Windows › World alone.
    inner = _panels_ring(page)
    page.keyboard.press(next(cell for cell, label in inner.items() if label == "Windows"))
    page.keyboard.press(
        next(cell for cell, label in _wedges(page).items() if label == "World alone")
    )
    windows.world_is(page, full)
    expect(page.locator("#status")).to_contain_text("The world alone")
    # A panel opened from anywhere ends it: the panels are back.
    page.evaluate("() => window.apothecaryPanels.open('selected')")
    expect(windows.panel(page, "selected")).to_be_visible()
    windows.world_is(page, before)


@pytest.mark.e2e
def test_the_splitter_beside_the_world_is_dragged_and_remembered(page: Page, ring_url: str):
    """The splitter between the world and the column drags the column wider; the
    width it was dragged to is what it has after a reload."""
    world = _open_panels(page, ring_url)
    before = windows.world_width(page)
    splitter = page.locator(".lm_root > .lm_row > .lm_splitter").first
    sb = splitter.bounding_box()
    windows.drag(page, splitter, (sb["x"] - 120, sb["y"] + sb["height"] / 2))
    page.wait_for_function(
        "(w) => document.querySelector('.viewer-panel').offsetWidth < w - 80", arg=before
    )
    narrower = windows.world_width(page)
    page.wait_for_timeout(400)  # the layout is remembered a moment after it changes
    page.reload()
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
    windows.world_is(page, narrower)
    assert world.bounding_box()["width"] < before - 80
    expect(page.locator(windows.WORLD_HEADER)).to_be_hidden()  # still no tab of its own
