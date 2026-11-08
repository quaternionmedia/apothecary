"""The Stream Deck +'s knobs jogging the garage's machines, through the page: the layout
drawn on the deck, a turn while control is disarmed moving nothing, the router jogged once
its control is armed in the Machine's own way, the step key changing the size of a jog,
and the stop key stopping a spinning spindle with the latch disarmed.

This module is a walkthrough page too: `walkthrough/27-the-deck-jogging-the-machines.md`
is what its first test writes. The browser suite alone writes it.

Runs against a server of its own with one simulated deck whose layout is started
(APOTHECARY_DECK_CONTROL), the simulated printer idle on /dev/ttyFAKE1 and the simulated
router on /dev/ttyFAKE3, each pinned to its node: nothing here opens a HID device or a
serial port, and the machines' own switches, which are faster than the deck, are section
J of the bench checklist (docs/bench-checklist.md).
"""

from __future__ import annotations

import time

import httpx
import pytest
import rings
import windows
from boards import PRINTER
from garage import open_garage
from garage import select as _select
from playwright.sync_api import Page, expect
from windows import DECK

DECK_ID = "DEMODECK"
ROUTER = "/dev/ttyFAKE3"
CONTROLLER = "cnc_router.frame_system.controller"
MAINBOARD = "printer_1.frame_system.mainboard"


@pytest.fixture(scope="module")
def url(start_server):
    url = start_server(
        env_overrides={
            "APOTHECARY_SIMULATED_DECK": DECK_ID,
            "APOTHECARY_DECK_CONTROL": "1",
            "APOTHECARY_SIMULATED_PRINTER": "idle",
            "APOTHECARY_SIMULATED_ROUTER": ROUTER,
            "APOTHECARY_SIMULATED_SPEED": "0.05",
            "FAKE_ROUTER": "1",
        }
    )
    with httpx.Client(base_url=url, timeout=15.0) as http:
        for port, node in ((ROUTER, CONTROLLER), (PRINTER, MAINBOARD)):
            http.post("/firmware/devices/identify", json={"port": port}).raise_for_status()
            http.put(
                f"/sites/garage/nodes/{node}/device", json={"identity": port}
            ).raise_for_status()
    return url


def _control(url: str) -> dict:
    return httpx.get(f"{url}/firmware/decks/{DECK_ID}/control", timeout=15.0).json()


def _router(url: str) -> dict:
    status = httpx.get(f"{url}/firmware/printers/status", params={"port": ROUTER}, timeout=15.0)
    return status.json()


def _arm(url: str, armed: bool) -> None:
    httpx.post(
        f"{url}/firmware/printers/control", json={"port": ROUTER, "armed": armed}, timeout=15.0
    ).raise_for_status()


def _until(check, what: str, seconds: float = 20.0) -> None:
    """``check`` true within ``seconds``: a jog takes the simulated router a moment, and
    the deck's keys follow its polls."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.3)
    raise AssertionError(what)


def _at_rest(url: str) -> bool:
    return _router(url)["machine_state"] == "Idle"


def _drawn(url: str) -> dict:
    return httpx.get(f"{url}/firmware/decks/{DECK_ID}", timeout=15.0).json()


@pytest.mark.e2e  # the browser suite's alone: not walkthrough, so `test run` stays quick
def test_the_knobs_jog_the_router_through_the_latch_and_the_stop_key_stops_it(
    page: Page, url: str, walkthrough
):
    """The layout is drawn on the deck by the server; from the Deck window the router is
    chosen and its knobs turned: disarmed, nothing moves and the strip says so; armed in
    the Machine's way, three clicks of knob one move X 3 mm and the X key shows where the
    tool is; the step key makes a click 10 mm; the stop key stops a spinning spindle with
    the latch disarmed. Walkthrough 27 is what it writes."""
    story = walkthrough(
        ordinal="27",
        slug="the-deck-jogging-the-machines",
        title="The deck jogging the machines",
        browser_suite_only=True,
        intro=(
            "The Stream Deck +'s knobs jog the garage's machines, through the control path "
            "the page's own pad uses: control armed in the Machine window, the dialect's "
            "bounds, and the machine's own stop. The deck in this page is simulated and "
            "so are the router and the printer, so every step can be shown; a turn is "
            "the report a real deck sends."
        ),
        runtime=(
            "It drives a real browser against a real server of its own, with one "
            "simulated deck whose layout is started, the simulated printer idle and the "
            "simulated router, each pinned to its node. No HID device or serial port is "
            "opened and nothing reaches the network."
        ),
        does_not_show=[
            "**A real deck or machine.** What only they show -- the knobs' feel, a gantry "
            "that stops, which stop is faster -- is section J of the bench checklist "
            "(docs/bench-checklist.md). The machine's own red button is faster than the "
            "deck's stop key, and the docs say so.",
            "**The printer.** The same turns jog it as `G91`, `G1 .. F3000`, `G90`, and its "
            "fourth knob extrudes within the bound the firmware guide names; "
            "tests/test_firmware_deck_control.py holds both.",
        ],
        page=page,
    )
    open_garage(page, url, settle=False)
    windows.open_window(page, "deck")
    deck = page.locator(DECK)
    expect(deck.locator(".deck-key img:visible")).to_have_count(8, timeout=15000)
    expect(deck.locator(".deck-strip-tap img:visible")).to_have_count(1, timeout=15000)
    assert _control(url)["running"] is True and _drawn(url)["strip_drawn"]["text"] == (
        "printer_1 · disarmed"
    )
    # 1. The layout the server drew, the router chosen.
    deck.locator(".deck-key[data-key='1']").click()
    expect(deck.locator(".deck-events")).to_contain_text("key 1 released", timeout=10000)
    assert _drawn(url)["strip_drawn"]["text"] == "cnc_router · disarmed"
    story.shows(
        "The deck's layout, drawn by the server, with the router chosen",
        "The top row's keys choose the machine and cycle the step; the bottom row holds the "
        "stops, one per machine and a bright red STOP ALL last, nearest the knobs. The strip "
        "says which machine, its position and that its control is disarmed.",
    )

    # 2. Disarmed: a turn moves nothing and the strip says why.
    before = _router(url)["position"]
    for _ in range(3):
        deck.locator(".deck-knob[data-knob='0'] .deck-turn[data-dir='1']").click()
    expect(deck.locator(".deck-events")).to_contain_text("knob 0 turned +1", timeout=10000)
    state = _control(url)
    assert state["sent"] == [] and "disarmed" in state["said"], state
    assert _router(url)["position"] == before
    story.shows(
        "Disarmed, three turns of knob one move nothing",
        "Control is armed in the Machine window, or by two long presses of the machine's "
        "key, and until then the strip says *disarmed* and nothing is sent. The router "
        "has not moved.",
    )

    # 3. Armed the Machine's way: three clicks are three millimetres of X.
    _arm(url, True)
    for _ in range(3):
        deck.locator(".deck-knob[data-knob='0'] .deck-turn[data-dir='1']").click()
    expect(deck.locator(".deck-events")).to_contain_text("knob 0 turned +1", timeout=10000)
    state = _control(url)
    assert state["sent"] == ["$J=G91 G21 X1 F1000"] * 3, state
    _until(lambda: _at_rest(url), "the router came to rest")
    after = _router(url)["position"]
    assert after["x"] == pytest.approx(before["x"] + 3), (before, after)
    _until(
        lambda: f"X {_router(url)['work_position']['x']:.1f}"
        in _drawn(url)["strip_drawn"]["small"],
        "the strip shows where the tool is",
    )
    story.shows(
        "Armed, three turns jog X by 3 mm and the X key shows where the tool is",
        "Each click is one `$J=G91 G21 X1 F1000`, GRBL's own jog line, sent through the "
        "same function as the page's pad; the X key reads the tool's new position from the "
        "next poll.",
    )

    # 4. The step key: a click is now 10 mm.
    deck.locator(".deck-key[data-key='2']").click()
    deck.locator(".deck-knob[data-knob='1'] .deck-turn[data-dir='-1']").click()
    expect(deck.locator(".deck-events").locator("li").first).to_contain_text(
        "knob 1 turned", timeout=10000
    )
    assert _control(url)["sent"][-1] == "$J=G91 G21 Y-10 F1000"
    _until(lambda: _at_rest(url), "the router came to rest")
    assert _router(url)["position"]["y"] == pytest.approx(after["y"] - 10)

    # 5. The stop key, with the latch disarmed.
    httpx.post(
        f"{url}/firmware/printers/command", json={"port": ROUTER, "command": "M3 S8000"}, timeout=15
    ).raise_for_status()
    assert _router(url)["spindle"]["on"] is True
    _arm(url, False)
    deck.locator(".deck-key[data-key='5']").click()  # cnc_router's own stop
    expect(deck.locator(".deck-events")).to_contain_text("key 5 released", timeout=10000)
    assert _control(url)["sent"][-1] == "stop cnc_router"
    assert _router(url)["spindle"]["on"] is False
    assert "STOP sent to cnc_router" in _drawn(url)["strip_drawn"]["small"]
    story.shows(
        "The router's stop key stops it whatever the latch says",
        "The step key made the last click 10 mm. The router's own stop key, the bottom "
        "row's second, then sent its soft reset with the latch disarmed: the spindle that was turning is "
        "off. The machine's own red button is faster, and stays the stop to reach for.",
    )


@pytest.mark.e2e
def test_the_deck_window_and_a_control_pad_show_and_steer_the_same_knobs(page: Page, url: str):
    """The knobs are one state, the server's. The Deck window shows the machine they move
    and their step, and chooses each; a key pressed on the deck shows there; the router's
    Control pad says where the knobs are and points them at the router; the ring's Knobs
    chooses the step, which both show; the window stops them, and the pad's row goes."""
    httpx.put(
        f"{url}/firmware/decks/{DECK_ID}/control",
        json={"machine": "printer_1", "step_mm": 1},
        timeout=15.0,
    ).raise_for_status()
    _arm(url, False)
    open_garage(page, url, settle=False)
    windows.open_window(page, "deck")
    knobs = page.locator(DECK).locator(".deck-control")
    machine = knobs.locator(".deck-machine[aria-pressed='true']")
    step = knobs.locator(".deck-step[aria-pressed='true']")
    expect(machine).to_have_text("printer_1", timeout=10000)
    expect(step).to_have_text("1")

    # 1. Chosen in the window: the deck's keys and strip follow.
    knobs.locator(".deck-machine[data-machine='cnc_router']").click()
    expect(machine).to_have_text("cnc_router", timeout=10000)
    assert _drawn(url)["strip_drawn"]["text"].startswith("cnc_router · ")
    knobs.locator(".deck-step[data-mm='10']").click()
    expect(step).to_have_text("10", timeout=10000)
    assert _drawn(url)["keys_drawn"]["2"]["small"] == "10 mm"

    # 2. Pressed on the deck: the window follows.
    page.locator(DECK).locator(".deck-key[data-key='0']").click()
    expect(machine).to_have_text("printer_1", timeout=10000)

    # 3. The router's Control pad: where the knobs are, and Knobs here.
    _select(page, "cnc_router")
    page.locator("#selected-body .device-section .dev-open").click()
    windows.machine_ready(page, "router")
    windows.machine(page).locator("#ctl").check()
    expect(page.locator("#control")).to_be_visible(timeout=5000)
    said = page.locator("#deck-knobs-on")
    expect(said).to_have_text("knobs on printer_1 · step 10 mm", timeout=10000)
    page.locator("#deck-here").click()
    expect(said).to_have_text("knobs on this machine · step 10 mm", timeout=10000)
    expect(page.locator("#deck-here")).to_be_hidden()
    assert _control(url)["machine"] == "cnc_router"

    # 4. The ring's Knobs: the step, which the pad and the window both show.
    rings.on_world(page, "Panels", "Machine", "Knobs", "Step", "0.1 mm")
    expect(said).to_have_text("knobs on this machine · step 0.1 mm", timeout=10000)
    windows.open_window(page, "deck")  # the Machine view laid its own windows out
    expect(step).to_have_text("0.1", timeout=10000)

    # 5. Stopped from the window: off on the server, and the pad's row goes.
    knobs.locator(".deck-run").click()
    expect(knobs).to_contain_text("knobs off", timeout=10000)
    assert _control(url) == {"running": False}
    expect(page.locator("#control .deck-knobs-grp")).to_have_attribute("hidden", "", timeout=10000)
    knobs.locator(".deck-run").click()
    _until(lambda: _control(url)["running"], "the knobs started again")
    _arm(url, False)
