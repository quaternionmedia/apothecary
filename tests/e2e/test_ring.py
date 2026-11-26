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
from boards import PRINTER
from garage import open_garage, select
from playwright.sync_api import Page, expect
from rings import cells as _wedges
from rings import cut_labels, greyed, on_world, open_at, past_the_chord

from apothecary.systems import by_id

MACHINE = windows.MACHINE
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
    "window.__intents = []; window.__refused = []; "
    "window.addEventListener('apothecary:intent', (e) => window.__intents.push(e.detail));"
    "window.addEventListener('apothecary:refused', (e) => window.__refused.push(e.detail));"
)


def _open_on(page: Page, url: str, node: str = "printer_1"):
    """The viewer on garage, the intents it carries captured, ``node`` selected."""
    page.add_init_script(CAPTURE)
    open_garage(page, url, settle=False)
    select(page, node)


def _title(page: Page) -> str:
    return page.locator("#ring-overlay .title").text_content() or ""


def _intents(page: Page) -> list:
    return page.evaluate("() => window.__intents")


def _refused(page: Page) -> list:
    return page.evaluate("() => window.__refused")


@pytest.mark.e2e
def test_key_m_opens_the_node_ring_in_its_cells(page: Page, ring_url: str):
    """m on a selected node: eight wedges, options cardinals first, the hub is 5."""
    _open_on(page, ring_url)
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
    _open_on(page, ring_url)
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
    # A machine drawn from a part carries Part, as printer_1 does.
    assert _wedges(page) == {
        "1": "Part",
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
def test_digits_walk_device_control_jog_and_what_leaves_the_ring_carries_the_address(
    page: Page, ring_url: str
):
    """7 7 2 8 reaches Jog > Y+ from printer_1's ring, Device seated last. Disarmed, Y+ is
    greyed with the server's reason, as the Machine's jog is: chosen anyway, no intent
    leaves the ring, and what does -- its refusal -- carries the address, and so does
    the page."""
    # Device's cells: Open (the board's Machine), Flash, ..., and Control, after Link,
    # in cell 7.
    _open_on(page, ring_url)
    expect(
        page.locator("#contents-list .contents-item[data-path='printer_1'] .dev-badge")
    ).to_be_visible(timeout=10000)
    page.wait_for_function(
        f"() => !!(window.fractalViewer.boards.board('{PRINTER}').status || {{}}).can",
        timeout=15000,
    )
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
    expect(page.locator("#ring-overlay .wedge.disabled")).to_have_count(6)
    page.keyboard.press("8")
    assert _title(page) == "Jog"  # chosen anyway: the ring stays, nothing is done
    assert _intents(page) == []
    refusals = _refused(page)
    assert len(refusals) == 1
    intent = refusals[0]
    assert intent["action"] == "control:jog:Y+"
    assert intent["option_id"] == "control:jog:Y+"
    assert intent["address"] == "7728"
    assert intent["context"] == {"pointing": "node", "targets": ["printer_1"]}
    assert "not armed" in intent["why"]
    page.keyboard.press("Escape")
    expect(page.locator("#ring-overlay")).to_have_count(0)
    # The same address, worked out from the ring itself two ways.
    by_path = page.evaluate(
        "() => window.apothecaryRing.addressOf(window.apothecaryRing.lastRing(), "
        "['device', 'control', 'control:jog', 'Y+'])"
    )
    by_action = page.evaluate(
        "() => window.apothecaryRing.addressOf(window.apothecaryRing.lastRing(), 'control:jog:Y+')"
    )
    assert by_path == by_action == intent["address"]
    # The status line says so as an error, with its address; no Machine is opened for
    # an act that was not done.
    expect(page.locator("#status")).to_contain_text("⌗7728", timeout=5000)
    expect(page.locator("#status")).to_contain_text("not armed")
    expect(page.locator("#status")).to_have_class(re.compile(r"\berror\b"))
    expect(page.locator(".panel[data-panel='machine']")).to_have_count(0)
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
    _open_on(page, ring_url)
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
        past_the_chord(page)

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
    past_the_chord(page)
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
    _open_on(page, ring_url)
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
    _open_on(page, ring_url)
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
    # full (its eighth cell is Device), so that is shown on the CNC router's, which
    # has no board pinned, and leaves cell 7 empty.
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
    windows.machine_ready(page, "printer")  # its Log, where what the jog sent is said
    expect(page.locator("#c-state")).not_to_have_text("—", timeout=10000)
    expect(page.locator("#ident")).to_contain_text("Marlin", timeout=8000)
    # Disarmed, the device ring's Control > Arm is the way in; the latch shows the address.
    expect(page.locator("#ctl")).to_have_attribute("data-address", "77", timeout=5000)
    page.locator(f"{windows.MACHINE_WINDOWS} #ident").click(button="right", modifiers=["Control"])
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    assert _title(page) == "printer_1"
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
    page.locator(f"{windows.MACHINE_WINDOWS} #ident").click(button="right", modifiers=["Control"])
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
    # Step out is there at the site's own level too, to the universe, at its one address.
    assert wedges["8"] == "Pieces" and wedges["1"] == "Step out" and wedges["7"] == "Systems"
    # The garage's pieces, cut by System, its loose parts under Parts by kind. The page
    # knows the address; the test asks rather than guesses.
    address = page.evaluate(
        "() => window.apothecaryRing.addressOf("
        "window.apothecaryRing.current().root, 'select:printer_1')"
    )
    assert address.startswith("8") and len(address) == 3 and "5" not in address
    page.keyboard.press("8")
    groups = _wedges(page)
    assert groups["8"] == "Building" and "Parts" in groups.values()  # the vocabulary's order
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
    up_crumb = page.locator("#view-banner .crumb").nth(-2)
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
    first in front; a piece chosen in Site's tree fills Selected and moves nothing in
    Site. Where a window opens, and what a tab does, are the window manager's
    (tests/e2e/test_window_manager.py)."""
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
        # The Models window, beside the world, closed until asked for.
        "models",
        # The Marks window, a tab beside it, closed until asked for.
        "marks",
        # The Part's sections, then the Airgap and its sections, each a window of its
        # own closed until asked for (apothecary/systems.py).
        *(f"part-{sid}" for sid in windows.PART_SECTIONS),
        "airgap",
        # The Airgap's sections, each a window of its own, closed until asked for.
        *(f"airgap-{sid}" for sid in windows.AIRGAP_SECTIONS),
        # The family's Members and Deliveries, closed until asked for.
        "family-members",
        "family-deliveries",
        # The Layers window, beside the world and a cell of Site's ring, closed until
        # asked for.
        "layers",
        # The Loops window, beside the world and a cell of the Machine's ring, closed
        # until asked for.
        "loops",
        # A printer's bed: Runs, Differences, Fixes and History, of the Machine's group,
        # closed until asked for.
        "bed-runs",
        "bed-differences",
        "bed-fixes",
        "bed-history",
        # The Workspace, a tab of Site's ring, closed until asked for.
        "working",
        # The Procedure, a tab of Site's ring, closed until asked for.
        "procedure",
        # The Deck, a stack of its own beside the world, closed until asked for.
        "deck",
        # The Motion window, a part's pieces moved through its motion, closed until
        # asked for.
        "motion",
        # The Badge window, the badge selected composed, closed until asked for.
        "badge",
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
    # Selecting a piece from Site's tree fills Selected and moves nothing in Site.
    before = site.bounding_box()
    row = page.locator("#contents-list .contents-item[data-path='printer_1']")
    at = row.bounding_box()
    row.click()
    expect(selected.locator("#pos-x")).to_be_visible(timeout=5000)
    assert site.bounding_box() == before and row.bounding_box() == at


@pytest.mark.e2e
def test_a_closed_window_stays_closed_and_the_ring_reopens_it(page: Page, ring_url: str):
    """A window closed by its tab's ✕ stays closed after a reload; the ring's Panels
    reaches it by address and opens it in front."""
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
        "Family",
        "Machine",
        "Part",
        "Pictures",
        "Site",
        "Tools",
        "Windows",
    ]
    page.keyboard.press(next(cell for cell, label in inner.items() if label == "Site"))
    # Panels › Site is a ring of Site and its own windows: Site first.
    site_ring = _wedges(page)
    assert sorted(site_ring.values()) == [
        "Jobs",
        "Layers",
        "Lighting",
        "Pinned",
        "Problems",
        "SCAD",
        "Site",
        "Workspace",
    ]
    page.keyboard.press(next(cell for cell, label in site_ring.items() if label == "Site"))
    expect(page.locator("#ring-overlay")).to_have_count(0)
    expect(windows.panel(page, "site")).to_be_visible()
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)

    # Panels › Tools › Bench › Bench brings the Bench in front of Pictures.
    inner = _panels_ring(page)
    page.keyboard.press(next(cell for cell, label in inner.items() if label == "Tools"))
    page.keyboard.press(next(cell for cell, label in _wedges(page).items() if label == "Bench"))
    page.keyboard.press(next(cell for cell, label in _wedges(page).items() if label == "Bench"))
    expect(windows.panel(page, "bench")).to_be_visible(timeout=5000)
    expect(windows.panel(page, "pictures")).to_be_hidden()


@pytest.mark.e2e
def test_the_rings_reset_layout_lays_the_pages_own_out_again(page: Page, ring_url: str):
    """Panels › Windows holds the views, World alone, Reset layout and the Tour; Reset
    layout lays the page's own layout out again and says so. What a person moved, and what a reset
    does with it, are the window manager's (tests/e2e/test_window_manager.py)."""
    world = _open_panels(page, ring_url)
    page.evaluate("() => window.apothecaryPanels.applyView('part')")
    assert windows.state(page, "pictures")["open"] is False

    inner = _panels_ring(page)
    page.keyboard.press(next(cell for cell, label in inner.items() if label == "Windows"))
    assert sorted(_wedges(page).values()) == [
        "Airgap view", "Family view", "Machine view", "Part view", "Reset layout", "Tour",
        "World alone",
    ]  # fmt: skip
    page.keyboard.press(
        next(cell for cell, label in _wedges(page).items() if label == "Reset layout")
    )
    expect(page.locator("#status")).to_contain_text("The page's own layout again")
    assert windows.state(page, "pictures")["stack"] == ["pictures", "bench", "settings"]
    assert world.bounding_box()["x"] <= 1


@pytest.mark.e2e
def test_a_stacks_plus_opens_any_window_there_and_windows_lists_them_by_group(
    page: Page, ring_url: str
):
    """Every stack but the world's wears a + among its buttons: pressed, every window by
    its group, ● open and ○ closed; a closed one chosen opens as a tab of that stack.
    The header's ⊞ Windows lists the same windows and no view, the first entry focused
    and the arrows moving along them; a window chosen there opens at its place."""
    _open_panels(page, ring_url)
    expect(page.locator(".lm_stack:has(.world-window) .lm_spawn")).to_have_count(0)
    plus = page.locator(".lm_stack:has(.lm_tab[data-panel='site']) .lm_spawn")
    plus.click()
    spawn = page.locator(".spawn-list")
    expect(spawn).to_be_visible()
    groups = spawn.locator(".spawn-group").all_inner_texts()
    assert [g.lower() for g in groups[:3]] == ["site", "part", "pictures"]
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

    # ⊞ Windows: the windows, and no view or journey; its first entry focused, the
    # arrows moving.
    page.locator("#windows-menu > summary").click()
    body = page.locator(".windows-menu-body")
    expect(body.locator(".view-item, [data-view]")).to_have_count(0)
    assert "views" not in [g.lower() for g in body.locator(".spawn-group").all_inner_texts()]
    expect(body.locator(".window-item[data-window='gather']")).to_have_text("● Gather")
    expect(body.locator(".journey-item, [data-journey]")).to_have_count(0)
    entries = body.locator(".window-item[data-window]")
    focused = "(el) => el === document.activeElement"
    assert entries.nth(0).evaluate(focused)
    page.keyboard.press("ArrowDown")
    assert entries.nth(1).evaluate(focused)
    # Gather, closed by its tab's ✕, chosen there: open again at its place, the menu away.
    page.keyboard.press("Escape")
    windows.close(page, "gather")
    windows.from_the_windows_menu(page, "gather")
    assert windows.state(page, "gather")["open"] is True


@pytest.mark.e2e
def test_on_a_short_page_the_view_menu_ends_at_the_page_and_scrolls_to_its_last_row(
    page: Page, ring_url: str
):
    """A page shorter than ⚙ View's list: the menu ends at the page's foot and scrolls
    by itself, so Select walls, its last row, is reached and pressed."""
    _open_panels(page, ring_url)
    page.set_viewport_size({"width": 1280, "height": 260})
    page.locator("#view-menu > summary").click()
    body = page.locator(windows.VIEW_MENU)
    expect(body.locator(".view-item").first).to_be_visible()
    box = body.evaluate(
        """(el) => ({ bottom: el.getBoundingClientRect().bottom, page: window.innerHeight,
            held: el.scrollHeight, shown: el.clientHeight })"""
    )
    assert box["bottom"] <= box["page"], box
    assert box["held"] > box["shown"], box
    walls = body.locator("label:has(#walls-toggle)")
    walls.scroll_into_view_if_needed()
    rect = walls.bounding_box()
    assert rect["y"] + rect["height"] <= box["page"], (rect, box)
    walls.click()
    expect(body.locator("#walls-toggle")).to_be_checked()


@pytest.mark.e2e
def test_the_view_menu_lists_the_views_and_a_view_pressed_there_lays_its_windows_out(
    page: Page, ring_url: str
):
    """The header's ⚙ View lists the views under their heading, above how the world is
    drawn: one that cannot be laid out now greyed with its reason, the first focused and
    the arrows moving along them. A view pressed there lays its windows out and folds the
    menu away. ⊞ Windows lists none of them."""
    world = _open_panels(page, ring_url)
    windows.open_window(page, "gather")
    page.locator("#view-menu > summary").click()
    expect(page.locator("#view-menu > summary")).to_have_text("⚙ View")
    body = page.locator(windows.VIEW_MENU)
    expect(body.locator(".view-menu-views .spawn-group")).to_have_text(["Views"])
    # The systems' views, each named as its cell on Panels › Windows is: a journey's is
    # the tour's to lay out, and is not listed.
    expect(body.locator(".view-item")).to_have_text(
        ["Reset layout", "Part view", "Machine view", "Airgap view", "Family view"]
    )
    # The views first, then how the world is drawn; Settings is a window, not here.
    order = body.evaluate(
        """(el) => { const at = (s) => el.querySelector(s).getBoundingClientRect().top;
            return [at('.view-item[data-view=default]'), at('.view-item[data-view=family]'),
                at('#snap-toggle'), at('#walls-toggle')]; }"""
    )
    assert order == sorted(order) and len(set(order)) == 4, order
    expect(body.locator("#settings-open")).to_have_count(0)
    # No Machine open and nothing selected: the Machine view is greyed, as every control
    # the page greys is, and says why; the Part view is not.
    machine = windows.view_entry(page, "machine")
    expect(machine).to_have_attribute("aria-disabled", "true")
    expect(machine).to_have_attribute("title", re.compile(r"^Disabled: no Machine is open"))
    expect(machine).to_have_css("opacity", "0.45")
    expect(windows.view_entry(page, "part")).not_to_have_attribute("aria-disabled", "true")
    expect(windows.view_entry(page, "part")).to_have_css("opacity", "1")
    assert page.evaluate("() => document.activeElement.dataset.view") == "default"
    page.keyboard.press("ArrowDown")
    assert page.evaluate("() => document.activeElement.dataset.view") == "part"
    page.keyboard.press("End")
    assert page.evaluate("() => document.activeElement.dataset.view") == "family"
    page.keyboard.press("Home")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    expect(body).to_be_hidden()
    expect(page.locator("#view-menu")).not_to_have_attribute("open", "")
    # The Part view: Selected in front beside the world, Site's below it, the rest closed.
    assert windows.state(page, "selected")["stack"][0] == "selected"
    assert windows.state(page, "site")["stack"] == ["site", "problems", "scad"]
    assert windows.state(page, "gather")["open"] is False
    expect(page.locator(windows.WORLD_HEADER)).to_be_hidden()
    share = by_id("part").view["row"][0]["size"] / 100  # the world's, in the registry
    assert world.bounding_box()["width"] == pytest.approx(
        page.viewport_size["width"] * share, abs=12
    )
    # ⊞ Windows lists every window, and no view.
    page.locator("#windows-menu > summary").click()
    listed = page.locator(".windows-menu-body")
    expect(listed.locator(".window-item[data-window='site']")).to_be_visible()
    expect(listed.locator(".view-item, [data-view]")).to_have_count(0)
    page.keyboard.press("Escape")
    # Default again, from the menu, drawn afresh as it opens.
    windows.from_the_view_menu(page, "default")
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
def test_a_ring_opened_at_the_screens_edge_keeps_every_label_whole(page: Page, ring_url: str):
    """Opened against either edge of the screen, the ring stands far enough in that no label
    is cut -- the canvas ring's, and the Panels ring's entered from it, whose Machine and
    Selected run out past the wedges on the level spokes -- however long the labels of the
    ring it is on."""
    open_garage(page, ring_url, settle=False)
    width, height = page.evaluate("() => [window.innerWidth, window.innerHeight]")
    for x in (0, width):
        open_at(page, x, height // 2)
        assert cut_labels(page) == [], x
        page.keyboard.press("4")  # Panels
        expect(page.locator("#ring-overlay .title")).to_have_text("Panels")
        assert cut_labels(page) == [], x
        page.keyboard.press("Escape")
        expect(page.locator("#ring-overlay")).to_have_count(0)


NO_MACHINE = "no printer's Machine is open: Loops works on the printer whose Machine is open"


@pytest.mark.e2e
def test_panels_machine_greys_the_loops_and_the_knobs_as_their_windows_do(
    page: Page, ring_url: str
):
    """With no printer's Machine open and no Stream Deck + found, Panels › Machine › Loops'
    Read, Start, Cancel and Set gains, and Panels › Tools › Deck's knobs On / off and Here,
    are greyed with the words their windows say, rather than live and refused once chosen;
    the windows themselves are not."""
    open_garage(page, ring_url, settle=False)
    on_world(page, "Panels", "Machine", "Loops")
    assert greyed(page) == {cell: f"Disabled: {NO_MACHINE}" for cell in ("6", "2", "4", "9")}
    page.keyboard.press("Escape")
    expect(page.locator("#ring-overlay")).to_have_count(0)
    on_world(page, "Panels", "Tools", "Deck")
    expect(page.locator("#ring-overlay .title")).to_have_text("Deck")
    knobs = greyed(page)
    assert set(knobs) == {"6", "9"}, knobs  # On / off, Here; the Deck window is live
    assert all("no Stream Deck + found" in why for why in knobs.values()), knobs


@pytest.mark.e2e
def test_an_open_ring_is_greyed_again_as_the_latch_goes_down_and_up(page: Page, ring_url: str):
    """A ring left open at Control › Jog is greyed again from each answer the page applies:
    the latch let go while it is open greys every jog with the server's reason, and armed
    again they are live, the ring where it was throughout."""

    def latch(armed: bool) -> None:
        httpx.post(
            f"{ring_url}/firmware/printers/control",
            json={"port": PRINTER, "armed": armed},
            timeout=15.0,
        ).raise_for_status()

    latch(True)
    page.goto(f"{ring_url}/firmware/monitor?port={PRINTER}")
    windows.machine_ready(page, "printer")
    expect(page.locator("#control")).to_be_visible(timeout=10000)  # armed: its pad
    page.locator(f"{windows.MACHINE_WINDOWS} #ident").click(button="right", modifiers=["Control"])
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    page.keyboard.press("7")
    page.keyboard.press("2")
    expect(page.locator("#ring-overlay .title")).to_have_text("Jog")
    assert greyed(page) == {}
    try:
        latch(False)
        jogs = page.locator("#ring-overlay .wedge.disabled")
        expect(jogs).to_have_count(6, timeout=10000)
        assert all("not armed" in why for why in greyed(page).values()), greyed(page)
        expect(page.locator("#ring-overlay .title")).to_have_text("Jog")
        latch(True)
        expect(jogs).to_have_count(0, timeout=10000)
    finally:
        latch(False)


@pytest.mark.e2e
def test_a_ring_answer_overtaken_on_its_way_is_not_drawn(page: Page, ring_url: str):
    """The ring's cells are asked for again as the latch is taken, and the latch is let go
    before that answer comes: the answer is of a moment already past when it lands, so the
    jogs stay greyed with the let-go latch's reason, never offered live."""

    def latch(armed: bool) -> None:
        httpx.post(
            f"{ring_url}/firmware/printers/control",
            json={"port": PRINTER, "armed": armed},
            timeout=15.0,
        ).raise_for_status()

    def frames(n: int = 2) -> None:
        page.evaluate(
            "(n) => new Promise((done) => {"
            " const step = (k) => (k ? requestAnimationFrame(() => step(k - 1)) : done());"
            " step(n); })",
            n,
        )

    def armed_in(route) -> bool:
        return '"armed":true' in (route.request.post_data or "").replace(" ", "")

    # A bed corner is greyed from the page's own answer of what the server would refuse, the
    # answer the ring is resolved with: it says when the page knows the latch has changed.
    corner = page.locator("#level-card button[data-corner='FL']")
    latch(True)
    page.goto(f"{ring_url}/firmware/monitor?port={PRINTER}")
    windows.machine_ready(page, "printer")
    expect(corner).to_be_enabled(timeout=10000)
    page.locator(f"{windows.MACHINE_WINDOWS} #ident").click(button="right", modifiers=["Control"])
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    page.keyboard.press("7")
    page.keyboard.press("2")
    expect(page.locator("#ring-overlay .title")).to_have_text("Jog")
    jogs = page.locator("#ring-overlay .wedge.disabled")
    held: list = []
    holding = [True]

    def hold(route) -> None:
        if holding[0]:
            held.append(route)
        else:
            route.continue_()

    try:
        latch(False)
        expect(jogs).to_have_count(6, timeout=10000)
        expect(corner).to_be_disabled(timeout=10000)
        page.route("**/menu/resolve", hold)
        latch(True)
        expect(corner).to_be_enabled(timeout=10000)
        for _ in range(100):  # the ring asks for its cells for the latch taken; held
            if any(armed_in(route) for route in held):
                break
            page.wait_for_timeout(50)
        assert any(armed_in(route) for route in held), "the ring did not ask again when armed"
        expect(jogs).to_have_count(6)
        latch(False)
        expect(corner).to_be_disabled(timeout=10000)
        frames(3)  # the page's look at the latch let go again has reached the open ring
        holding[0] = False
        late = held[:]
        held.clear()
        for route in late:
            route.continue_()
        for route in late:
            answer = route.request.response()
            assert answer is not None and answer.ok
            assert answer.finished() is None  # the whole answer is in the page
        frames()
        expect(page.locator("#ring-overlay .title")).to_have_text("Jog")
        assert len(greyed(page)) == 6, greyed(page)
        assert all("not armed" in why for why in greyed(page).values()), greyed(page)
    finally:
        holding[0] = False
        for route in held:
            route.continue_()
        page.unroute("**/menu/resolve")
        latch(False)


@pytest.mark.e2e
def test_the_headers_menus_the_tour_and_the_procedure_wear_their_cells_addresses(
    page: Page, ring_url: str
):
    """Each control a cell of the ring also is wears that cell's address, once: the
    header's ⚙ View, ⊞ Windows and Tour, the universe's crumb out of a site, the
    site's crumb and its ▾ at the site's own level (the ring's Site), the tour box's
    buttons, the Procedure's GO and Start over, and the Stream Deck +'s Open Deck (its
    ring's Deck)."""
    open_garage(page, ring_url, settle=False)
    canvas = page.evaluate(
        """async () => {
            const ring = await window.apothecaryRing.resolve({ context: { pointing: 'canvas', targets: [] }, site: 'garage' });
            const at = window.apothecaryRing.addresses(ring);
            const of = (path) => window.apothecaryRing.addressOf(ring, path);
            return { ...at, view: of(['view']), windows: of(['panels', 'panel:windows']), site: of(['Site']) };
        }"""
    )
    windows.open_window(page, "procedure")
    for selector, address in (
        ("#view-menu > summary", canvas["view"]),
        ("#windows-menu > summary", canvas["windows"]),
        ("#tour-pop-open", canvas["tour:toggle"]),
        (".tour-pop-next", canvas["tour:next"]),
        ("#universe-crumb", canvas["site:apothecary"]),
        ("#site-level", canvas["site"]),
        ("#site-menu > summary", canvas["site"]),
        (".panel[data-panel='procedure'] .procedure-again", canvas["procedure:again"]),
    ):
        assert address, selector
        control = page.locator(selector).first
        expect(control).to_have_attribute("data-address", address, timeout=10000)
        title = control.get_attribute("title") or ""
        assert title.endswith(f"⌗{address}") and title.count("⌗") == 1, (selector, title)
    select(page, "stream_deck")
    deck = page.evaluate(
        """async () => {
            const ring = await window.apothecaryRing.resolve({ context: { pointing: 'node', targets: ['stream_deck'] }, site: 'garage' });
            return window.apothecaryRing.addresses(ring)['panel:toggle:deck'] || null;
        }"""
    )
    assert deck
    expect(page.locator(".deck-open")).to_have_attribute("data-address", deck, timeout=10000)
