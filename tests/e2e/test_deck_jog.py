"""The Stream Deck +'s knobs jogging the garage's machines, through the page: the layout
drawn on the deck, a turn while control is disarmed moving nothing, the router jogged once
its control is armed in the Machine's own way, the step key changing the size of a jog,
the stop key stopping a spinning spindle and disarming the router, two long presses of
the router's key arming it, DISARM letting go of every machine, and UNLOCK taking the
router out of the alarm a stop mid-move leaves it in.

This module is a walkthrough page too: `walkthrough/27-the-deck-jogging-the-machines.md`
is what its first test writes. The browser suite alone writes it.

Runs against a server of its own with one simulated deck whose layout is started
(APOTHECARY_DECK_CONTROL), the simulated printer idle on /dev/ttyFAKE1 and the simulated
router on /dev/ttyFAKE3, each pinned to its node: nothing here opens a HID device or a
serial port, and the machines' own switches, which are faster than the deck, are section
J of the bench checklist (docs/bench-checklist.md).
"""

from __future__ import annotations

import re
import time

import httpx
import pytest
import rings
import windows
from boards import PRINTER
from doc_capture import TIME_LEFT
from garage import open_garage
from garage import select as _select
from playwright.sync_api import Page, expect
from windows import DECK

DECK_ID = "SIMDECK"
# The time an armed latch has left, which the Deck window writes beside the machine it
# moves and under the strip; the strip's own picture carries it too, drawn by the server
# where no word can be blanked, so the picture is left out whole: its words are under it.
TIME_LEFT_SHOWN = ((DECK, TIME_LEFT), f"{DECK} .deck-strip-tap")
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


def _arm(url: str, armed: bool, port: str = ROUTER) -> None:
    httpx.post(
        f"{url}/firmware/printers/control", json={"port": port, "armed": armed}, timeout=15.0
    ).raise_for_status()


def _held(url: str, key: int, seconds: float) -> None:
    """A key held down for ``seconds`` and let go, as a real deck reports it."""
    events = f"{url}/firmware/decks/{DECK_ID}/events"
    for value in (True, False):
        given = httpx.post(events, json={"kind": "key", "index": key, "value": value}, timeout=15)
        assert given.status_code == 201, given.text
        if value:
            time.sleep(seconds)


def _key(deck, index: int) -> str:
    return deck.locator(f".deck-key[data-key='{index}'] img").get_attribute("src")


def _redrawn(deck, index: int, before: str) -> None:
    """The Deck window shows the key's picture as the server now draws it, loaded."""
    img = deck.locator(f".deck-key[data-key='{index}'] img")
    expect(img).not_to_have_attribute("src", before, timeout=10000)
    img.evaluate("(img) => img.decode()")


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
    tool is; the step key makes a click 10 mm; the stop key stops a spinning spindle and
    disarms the router; two long presses of its key arm it and DISARM lets go of every
    machine; after a stop mid-move UNLOCK takes it out of its alarm. Walkthrough 27 is what
    it writes."""
    story = walkthrough(
        ordinal="27",
        slug="the-deck-jogging-the-machines",
        title="The deck jogging the machines",
        browser_suite_only=True,
        intro=(
            "The Stream Deck +'s knobs jog the garage's machines, through the control path "
            "the page's own pad uses: control armed in the Machine window or by two long "
            "presses of a machine's key and let go by DISARM, the dialect's bounds, the "
            "machine's own stop, and UNLOCK after an alarm. The deck in this page is "
            "simulated and "
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
            "**The strip's picture.** The server draws the time an armed control has left "
            "into it, which differs on every run, so it is greyed in the pictures; the "
            "window writes its words under it, the time blanked there as everywhere.",
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
    expect(deck.locator(".deck-heard")).to_have_count(0, timeout=5000)  # lit a moment
    # No key drawn hovered or ringed with focus: whether it is depends on the moment.
    page.mouse.move(640, 700)
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    story.shows(
        "The deck's layout, drawn by the server, with the router chosen",
        "The top row's keys choose the machine and cycle the step; the bottom row holds the "
        "stops, one per machine and a bright red STOP ALL last, nearest the knobs. The strip "
        "says which machine, its position and that its control is disarmed.",
        blank=TIME_LEFT_SHOWN,
    )

    # 2. Disarmed: a turn moves nothing and the strip says why.
    before = _router(url)["position"]
    for _ in range(3):
        deck.locator(".deck-knob[data-knob='0'] .deck-turn[data-dir='1']").click()
    expect(deck.locator(".deck-events")).to_contain_text("knob 0 turned +1", timeout=10000)
    state = _control(url)
    assert state["sent"] == [] and "disarmed" in state["said"], state
    assert _router(url)["position"] == before
    expect(deck.locator(".deck-heard")).to_have_count(0, timeout=5000)  # lit a moment
    # No key drawn hovered or ringed with focus: whether it is depends on the moment.
    page.mouse.move(640, 700)
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    story.shows(
        "Disarmed, three turns of knob one move nothing",
        "Control is armed in the Machine window, or by two long presses of the machine's "
        "key, and until then the strip says *disarmed* and nothing is sent. The router "
        "has not moved.",
        blank=TIME_LEFT_SHOWN,
    )

    # 3. Armed the Machine's way: three clicks are three millimetres of X. The words of a
    #    turn are on the list since step 2: what is waited for is the third jog sent.
    _arm(url, True)
    for turned in range(1, 4):
        deck.locator(".deck-knob[data-knob='0'] .deck-turn[data-dir='1']").click()
        # A turn made while the machine is moving is summed with the ones after it and sent
        # when it is free, so each click waits for its own jog to end: one
        # `$J` a click is what a person turning a knob at a knob's pace sends.
        _until(
            lambda turned=turned: len(_control(url)["sent"]) == turned and _at_rest(url),
            f"turn {turned} was sent as a jog of its own and the router came to rest",
        )
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
    expect(deck.locator(".deck-heard")).to_have_count(0, timeout=5000)  # lit a moment
    # No key drawn hovered or ringed with focus: whether it is depends on the moment.
    page.mouse.move(640, 700)
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    story.shows(
        "Armed, three turns jog X by 3 mm and the X key shows where the tool is",
        "Each click is one `$J=G91 G21 X1 F1000`, GRBL's own jog line, sent through the "
        "same function as the page's pad; the X key reads the tool's new position from the "
        "next poll.",
        blank=TIME_LEFT_SHOWN,
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

    # 5. The stop key, armed: the router stopped, and disarmed.
    httpx.post(
        f"{url}/firmware/printers/command", json={"port": ROUTER, "command": "M3 S8000"}, timeout=15
    ).raise_for_status()
    assert _router(url)["spindle"]["on"] is True
    deck.locator(".deck-key[data-key='5']").click()  # cnc_router's own stop
    expect(deck.locator(".deck-events")).to_contain_text("key 5 released", timeout=10000)
    assert _control(url)["sent"][-1] == "stop cnc_router"
    assert _router(url)["spindle"]["on"] is False
    assert _control(url)["armed_s"] == 0
    assert _drawn(url)["strip_drawn"]["text"] == "cnc_router · disarmed"
    assert "STOP sent to cnc_router" in _drawn(url)["strip_drawn"]["small"]
    expect(deck.locator(".deck-heard")).to_have_count(0, timeout=5000)  # lit a moment
    # No key drawn hovered or ringed with focus: whether it is depends on the moment.
    page.mouse.move(640, 700)
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    story.shows(
        "The router's stop key stops it and disarms it",
        "The step key made the last click 10 mm. The router's own stop key, the bottom "
        "row's second, sends its soft reset whatever the latch says, and disarms the router: "
        "the spindle that was turning is off, and the next turn moves nothing until its control "
        "is armed again. The machine's own red button is faster, and stays the stop to reach for.",
        blank=TIME_LEFT_SHOWN,
    )

    # 6. Two long presses of the router's key arm it, as ⚙ Control in its Machine does,
    #    and DISARM is lit.
    disarm = _key(deck, 3)
    _held(url, 1, 1.0)
    assert "again within 5 s to arm" in _control(url)["said"]
    time.sleep(0.5)
    _held(url, 1, 1.0)
    _until(lambda: _control(url)["armed_s"] > 0, "two long presses armed the router")
    assert _drawn(url)["strip_drawn"]["text"].startswith("cnc_router · armed ")
    drawn = _drawn(url)["keys_drawn"]["3"]
    assert (drawn["text"], drawn["colour"], drawn["small"]) == ("DISARM", "red", "every machine")
    _redrawn(deck, 3, disarm)
    expect(deck.locator(".deck-heard")).to_have_count(0, timeout=5000)  # lit a moment
    # No key drawn hovered or ringed with focus: whether it is depends on the moment.
    page.mouse.move(640, 700)
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    # The page asks which machines are armed every two seconds: the badge says so then.
    expect(page.locator(".world-badge[data-path='cnc_router']")).to_have_class(
        re.compile(r"\barmed\b"), timeout=10000
    )
    story.shows(
        "Two long presses of the router's key arm it, and DISARM is lit",
        "The router's key, the top row's second, held a second, let go, and held a second "
        "again: the first says to press again within 5 s, the second arms the router's "
        "control for the latch's five minutes, as ⚙ Control in its Machine does. DISARM, "
        "the top row's last, is lit while any machine is armed.",
        blank=TIME_LEFT_SHOWN,
    )

    # 7. DISARM lets go of every machine's control at once.
    _arm(url, True, PRINTER)  # the printer armed in its Machine meanwhile
    disarm = _key(deck, 3)
    deck.locator(".deck-key[data-key='3']").click()
    expect(deck.locator(".deck-events")).to_contain_text("key 3 released", timeout=10000)
    _until(lambda: _control(url)["armed_s"] == 0, "DISARM let go of the router")
    assert "printer_1, cnc_router disarmed" in _drawn(url)["strip_drawn"]["small"]
    drawn = _drawn(url)["keys_drawn"]["3"]
    assert (drawn["colour"], drawn["small"]) == ("grey", "nothing armed")
    _redrawn(deck, 3, disarm)
    expect(deck.locator(".deck-heard")).to_have_count(0, timeout=5000)  # lit a moment
    # No key drawn hovered or ringed with focus: whether it is depends on the moment.
    page.mouse.move(640, 700)
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    story.shows(
        "DISARM lets go of every machine's control",
        "The printer armed in its own Machine meanwhile, and DISARM pressed once: both "
        "machines' control is let go, the strip names them, and DISARM is grey with "
        "nothing armed. A turn moves nothing again.",
        blank=TIME_LEFT_SHOWN,
    )

    # 8. A stop while the router moves leaves it in alarm, as a real controller is after a
    #    reset mid-move, and UNLOCK is lit.
    _arm(url, True)
    unlock = _key(deck, 6)
    x = _router(url)["position"]["x"]
    for line in ("G91", f"G1 X{-100 if x > -290 else 100} F100"):
        httpx.post(
            f"{url}/firmware/printers/command", json={"port": ROUTER, "command": line}, timeout=15
        ).raise_for_status()
    _until(lambda: _router(url)["machine_state"] == "Run", "the router moving", 10.0)
    deck.locator(".deck-key[data-key='5']").click()
    _until(lambda: _router(url)["machine_state"] == "Alarm", "the router in alarm", 10.0)
    _until(lambda: _drawn(url)["keys_drawn"]["6"]["text"] == "UNLOCK", "UNLOCK drawn")
    assert _drawn(url)["keys_drawn"]["6"]["colour"] == "amber"
    _redrawn(deck, 6, unlock)

    # 9. Armed again, a turn in alarm moves nothing and the strip says to press UNLOCK.
    _arm(url, True)
    before = _router(url)["position"]
    sent = len(_control(url)["sent"])
    deck.locator(".deck-knob[data-knob='0'] .deck-turn[data-dir='1']").click()
    expect(deck.locator(".deck-events").locator("li").first).to_contain_text(
        "knob 0 turned", timeout=10000
    )
    _until(lambda: "in alarm: UNLOCK it" in _control(url)["said"], "the strip says UNLOCK it")
    assert len(_control(url)["sent"]) == sent and _router(url)["position"] == before
    expect(deck.locator(".deck-heard")).to_have_count(0, timeout=5000)  # lit a moment
    # No key drawn hovered or ringed with focus: whether it is depends on the moment.
    page.mouse.move(640, 700)
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    story.shows(
        "After a stop mid-move the router is in alarm, and UNLOCK is lit",
        "The router sent 100 mm along X slowly and the router's stop key pressed while it "
        "moved: the controller is in alarm, as a real one is after a reset mid-move, and "
        "UNLOCK lights in the middle of the bottom row. Armed again, a turn moves nothing, "
        "and the strip says to press UNLOCK.",
        blank=TIME_LEFT_SHOWN,
    )

    # 10. UNLOCK takes the router out of its alarm, and the next turn moves it.
    unlock = _key(deck, 6)
    deck.locator(".deck-key[data-key='6']").click()
    _until(lambda: _control(url)["sent"][-1:] == ["$X"], "UNLOCK sent $X")
    _until(lambda: _at_rest(url), "the router idle")
    _until(lambda: _drawn(url)["keys_drawn"]["6"]["text"] == "STOP JOG", "STOP JOG again")
    deck.locator(".deck-knob[data-knob='0'] .deck-turn[data-dir='1']").click()
    _until(lambda: _router(url)["position"] != before, "the next turn moved the router")
    _until(lambda: _at_rest(url), "the router came to rest")
    _redrawn(deck, 6, unlock)
    expect(deck.locator(".deck-heard")).to_have_count(0, timeout=5000)  # lit a moment
    # No key drawn hovered or ringed with focus: whether it is depends on the moment.
    page.mouse.move(640, 700)
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    story.shows(
        "UNLOCK sends $X, and the next turn moves the router",
        "UNLOCK pressed: it sends the router's `$X` through the latch, the alarm is "
        "cleared and the key is STOP JOG again, and the next turn of knob one jogs X.",
        blank=TIME_LEFT_SHOWN,
    )
    _arm(url, False)


@pytest.mark.e2e
def test_the_deck_window_and_a_control_pad_show_and_steer_the_same_knobs(page: Page, url: str):
    """The knobs are one state, the server's. The Deck window shows the machine they move
    and their step, and chooses each; a key pressed on the deck shows there; the router's
    Control pad says where the knobs are and points them at the router, its Knobs here
    answered by the deck; the ring's Knobs chooses the step, which both show, and the
    strip's screen, which the window shows and changes back, sending nothing to a machine;
    the window stops them, and the pad's row goes."""
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
    # The deck's answer for this port says the knobs can be pointed here (can.here).
    expect(page.locator("#deck-here")).to_be_enabled()
    expect(page.locator("#deck-here")).not_to_have_attribute("aria-disabled", "true")
    page.locator("#deck-here").click()
    expect(said).to_have_text("knobs on this machine · step 10 mm", timeout=10000)
    expect(page.locator("#deck-here")).to_be_hidden()
    assert _control(url)["machine"] == "cnc_router"

    # 4. The ring's Knobs: the step, which the pad and the window both show.
    rings.on_world(page, "Panels", "Machine", "Knobs", "Step", "0.1 mm")
    expect(said).to_have_text("knobs on this machine · step 0.1 mm", timeout=10000)
    windows.open_window(page, "deck")  # the Machine view laid its own windows out
    expect(step).to_have_text("0.1", timeout=10000)

    # 5. The strip's screen, from the ring's Knobs › Screen and from the window: a real
    #    deck's is changed from here too, and nothing goes to a machine.
    sent = (_control(url)["sent"], _router(url)["position"])
    rings.on_world(page, "Panels", "Machine", "Knobs", "Screen", "Status")
    shown = knobs.locator(".deck-screen-to[aria-pressed='true']")
    expect(shown).to_have_text("Status", timeout=10000)
    expect(knobs.locator(".deck-screen")).to_contain_text("strip screen: Status (3/3)")
    _until(lambda: (_drawn(url)["strip_drawn"]["small"] or "").endswith("· 3/3"), "Status drawn")
    knobs.locator(".deck-screen-to[data-screen='knobs']").click()
    expect(shown).to_have_text("Knobs", timeout=10000)
    assert _control(url)["screen"] == "knobs"
    assert (_control(url)["sent"], _router(url)["position"]) == sent

    # 6. Stopped from the window: off on the server, and the pad's row goes.
    knobs.locator(".deck-run").click()
    expect(knobs).to_contain_text("knobs off", timeout=10000)
    off = _control(url)
    assert off["running"] is False and set(off) == {"running", "can"}
    expect(page.locator("#control .deck-knobs-grp")).to_have_attribute("hidden", "", timeout=10000)
    knobs.locator(".deck-run").click()
    _until(lambda: _control(url)["running"], "the knobs started again")
    _arm(url, False)
