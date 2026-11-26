"""The deck's screens while a print streams, through the page: a print begun on the
printer brings the Print screen forward; a tap on a screen's name along the Deck window's
strip shows it; a knob pressed shows the next; a knob turned anywhere but Jog moves
nothing and says so; Temps draws the printer's hotend and bed as a graph of the polls
made while the print runs; the Bench draws both machines; and a print that ends stays on
Print, how it ended, until a touch.

This module is a walkthrough page too: `walkthrough/41-the-deck-while-a-print-streams.md`
is what its first test writes. The browser suite alone writes it.

Runs against a server of its own with one simulated deck whose layout is started
(APOTHECARY_DECK_CONTROL) and the simulated printer idle on /dev/ttyFAKE1 pinned to its
node: nothing here opens a HID device or a serial port. What only a real deck shows -- a
finger's tap on a name, a knob's press -- is section J of the bench checklist
(docs/bench-checklist.md).
"""

from __future__ import annotations

import re
import time
from urllib.parse import quote

import httpx
import pytest
import windows
from boards import PRINTER
from doc_capture import TIME_LEFT
from garage import open_garage
from playwright.sync_api import Page, expect
from windows import DECK

DECK_ID = "SIMDECK"
MAINBOARD = "printer_1.frame_system.mainboard"
FILE_NAME = "bench_coupon.gcode"
# The time an armed latch has left, in the Deck window and on printer_1's row in Site.
TIME_LEFT_SHOWN = ((DECK, TIME_LEFT), ("#contents-list", TIME_LEFT), (".world-badge", TIME_LEFT))
# The strip itself, where it carries Progress's clock: the server draws the time into its
# picture, where no word can be blanked, so it is left out of the picture whole and its
# words are written under it with the time blanked (_strip_words).
STRIP_WITH_A_CLOCK = (*TIME_LEFT_SHOWN, f"{DECK} .deck-strip-tap")
# A print long enough to be paused in: its heaters asked for, without waiting on them, so
# Temps has a rise to draw; a two-second dwell, which a pause catches every time, so the
# print is held there and the tool where it began; and two thousand short moves after it.
GCODE = "G90\nM104 S200\nM140 S60\nG4 P2000\n" + "".join(
    f"G1 X{10 + n % 40} Y{10 + n % 30} F6000\n" for n in range(2000)
)


@pytest.fixture(scope="module")
def url(start_server):
    url = start_server(
        env_overrides={
            "APOTHECARY_SIMULATED_DECK": DECK_ID,
            "APOTHECARY_DECK_CONTROL": "1",
            "APOTHECARY_SIMULATED_PRINTER": "idle",
            "APOTHECARY_SIMULATED_SPEED": "1",  # the dwell lasts the two seconds it says
        }
    )
    with httpx.Client(base_url=url, timeout=15.0) as http:
        http.post("/firmware/devices/identify", json={"port": PRINTER}).raise_for_status()
        http.put(
            f"/sites/garage/nodes/{MAINBOARD}/device", json={"identity": PRINTER}
        ).raise_for_status()
    return url


def _drawn(url: str) -> dict:
    return httpx.get(f"{url}/firmware/decks/{DECK_ID}", timeout=15.0).json()


def _screen(url: str) -> str:
    return httpx.get(f"{url}/firmware/decks/{DECK_ID}/control", timeout=15.0).json()["screen"]


def _strip(url: str) -> dict:
    return _drawn(url)["strip_drawn"]


def _touches(url: str) -> int:
    """How many touches of the strip the deck has reported."""
    events = httpx.get(f"{url}/firmware/decks/{DECK_ID}/events", timeout=15.0).json()["events"]
    return sum(1 for e in events if e["kind"] == "touch")


def _until(check, what: str, seconds: float = 20.0) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.3)
    raise AssertionError(what)


def _strip_words(url: str) -> str:
    """The strip's two lines as the server drew them, its clock blanked as a picture's is."""
    strip = _strip(url)
    return f"{strip['text']}\n{re.sub(TIME_LEFT, '‒:‒‒', strip['small'] or '')}"


def _window_shows_the_strip(url: str, deck) -> None:
    """The Deck window shows the strip the server drew last, loaded, and no touch is
    lit on it: what a picture of it is taken of. The window fetches the strip again when
    what is drawn on it changes (widgets/deck.js), within its beat."""

    def shown() -> bool:
        drawn = _strip(url)
        img = deck.locator(".deck-strip-tap img")
        return (img.get_attribute("src") or "").endswith(
            "v=" + quote(drawn["v"], safe="-_.!~*'()")
        ) and img.evaluate("(i) => i.complete && i.naturalWidth > 0")

    _until(shown, "the Deck window showing the strip as drawn")
    expect(deck.locator(".deck-touch")).to_be_hidden(timeout=5000)
    expect(deck.locator(".deck-heard")).to_have_count(0, timeout=5000)


def _swipe(page: Page, deck, direction: int) -> None:
    """A finger drawn along the Deck window's strip, as a person does it with the mouse:
    left (forward) or right (back), most of the strip's length."""
    box = deck.locator(".deck-strip-tap").bounding_box()
    y = box["y"] + box["height"] / 2
    a, b = (0.85, 0.15) if direction > 0 else (0.15, 0.85)
    page.mouse.move(box["x"] + box["width"] * a, y)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] * (a + b) / 2, y, steps=4)
    page.mouse.move(box["x"] + box["width"] * b, y, steps=4)
    page.mouse.up()


SCREENS = ("bench", "knobs", "home", "progress", "status", "bed")


def _tap(deck, screen: str) -> None:
    """A tap on ``screen``'s name along the top of the Deck window's strip: its sixth."""
    box = deck.locator(".deck-strip-tap").bounding_box()
    i = SCREENS.index(screen)
    deck.locator(".deck-strip-tap").click(
        position={"x": box["width"] * (i + 0.5) / len(SCREENS), "y": box["height"] * 0.12}
    )


def _post(url: str, path: str, **body) -> httpx.Response:
    return httpx.post(f"{url}/firmware/printers/{path}", json={"port": PRINTER, **body}, timeout=30)


@pytest.mark.e2e  # the browser suite's alone: not walkthrough, so `test run` stays quick
def test_the_deck_shows_a_print_and_a_tap_walks_its_screens(page: Page, url: str, walkthrough):
    """A print is begun on the simulated printer: the deck brings Print forward on its
    own, with the file's name, a bar and the stage, and key 2 its number; a tap on Jog
    shows the knobs, which say the jogs are refused in the server's words, and Print is
    not pulled forward again; a knob pressed shows Home, where a turn moves nothing and
    says so; Temps draws the heaters as they rise; the Bench draws both machines; the
    print is cancelled, and Print says so until a touch. Walkthrough 41 is what it
    writes."""
    story = walkthrough(
        ordinal="41",
        slug="the-deck-while-a-print-streams",
        title="The deck while a print streams",
        browser_suite_only=True,
        intro=(
            "The Stream Deck + has six screens, named along the top of its touch strip: the "
            "Bench, with both machines, then the chosen machine's Jog, Home, Print, Temps and "
            "Bed. A tap on a name shows that screen and a knob pressed shows the next. While "
            "a print streams the deck shows how far it is, the printer's heaters as a graph "
            "and what each machine is doing on its key. The deck in this page is simulated "
            "and so is the printer; each tap and press is the event a real deck reports."
        ),
        runtime=(
            "It drives a real browser against a real server of its own, with one simulated "
            "deck whose layout is started and the simulated printer pinned to its node. No "
            "HID device or serial port is opened and nothing reaches the network."
        ),
        does_not_show=[
            "**The clocks.** Print says how long a print has run, which differs on every run; "
            "the server draws it into the strip's picture, so where it shows the strip is "
            "greyed in the picture and its words are written under it, the time as ‒:‒‒. The graph on Temps and "
            "the spark line on the printer's key are drawn from the polls of this run, so "
            "their shape differs from run to run.",
            "**A real deck.** What only it shows -- a finger's tap on a name, a knob's press, "
            "the strip's brightness under a hand -- is section J of the bench checklist "
            "(docs/bench-checklist.md).",
            "**A cut, Home's and Bed's keys.** A router's job is the same record, and its "
            "screens are Cut, Status and Table; HOME and PROBE held send the page's own home "
            "and probe. tests/test_firmware_deck_control.py holds them.",
        ],
        page=page,
    )
    open_garage(page, url, settle=False)
    windows.open_window(page, "deck")
    deck = page.locator(DECK)
    expect(deck.locator(".deck-strip-tap img:visible")).to_have_count(1, timeout=15000)
    assert _screen(url) == "knobs"
    expect(deck.locator(".deck-screen")).to_contain_text("screen: Jog (2/6)", timeout=10000)

    # 1. A print is begun: Print is brought forward, once.
    kept = httpx.post(
        f"{url}/firmware/printers/prints",
        params={"name": FILE_NAME, "machine": "printer"},
        content=GCODE.encode(),
        timeout=30,
    )
    assert kept.status_code == 201, kept.text
    _post(url, "control", armed=True).raise_for_status()
    started = httpx.post(
        f"{url}/firmware/printers/print",
        json={"port": PRINTER, "file_id": kept.json()["id"]},
        timeout=30,
    )
    assert started.status_code == 202, started.text
    now = lambda: httpx.get(f"{url}/firmware/printers/print", params={"port": PRINTER}).json()  # noqa: E731
    _until(lambda: now().get("stage") == "printing", "the print streaming")
    _post(url, "print/pause").raise_for_status()  # held where it is, to be read
    _until(lambda: now().get("stage") == "paused", "the print paused")
    _until(lambda: _screen(url) == "progress", "Print brought forward")
    _until(lambda: _strip(url)["text"].startswith(FILE_NAME[:20]), "the file named on the strip")
    # The layout draws the strip at its tick (deck_control.TICK_S): the pause is said at
    # the next one.
    _until(lambda: "paused" in (_strip(url)["small"] or ""), "the pause said on the strip")
    strip = _strip(url)
    assert strip["bar"] is not None and "paused" in strip["small"], strip
    assert "remaining" not in strip["small"]
    assert strip["art"]["tabs"][strip["art"]["tab"]] == "Print"
    assert _drawn(url)["keys_drawn"]["2"]["text"] == "PRINT"
    expect(deck.locator(".deck-screen")).to_contain_text("screen: Print (4/6)", timeout=10000)
    _window_shows_the_strip(url, deck)
    story.shows(
        "A print begun brings Print forward",
        "The simulated printer is streaming a kept file. The strip names the file, how far "
        "it is as a number and a bar, the stage and how long it has run, with Print lit "
        "among the six screens' names along its top; no time remaining is shown, since the "
        "job's record carries none. The third key is the screen's own, the print's number, "
        "and the printer's key carries the print's bar. The print is paused where it is so "
        "the picture can be read.",
        shown=_strip_words(url),
        blank=STRIP_WITH_A_CLOCK,
    )

    # 2. A tap on Jog: the jogs are refused, in the server's words, and Print is not
    #    brought forward again.
    _tap(deck, "knobs")
    _until(lambda: _screen(url) == "knobs", "the knobs shown by a tap on Jog")
    _until(lambda: "holds the port" in (_strip(url)["small"] or ""), "the hold said")
    assert _strip(url)["text"] == "printer_1 · held" and "jogs refused" in _strip(url)["small"]
    time.sleep(5)  # two ticks of the layout: nothing pulls the strip forward again
    assert _screen(url) == "knobs"
    _window_shows_the_strip(url, deck)
    # The window's line for the knobs says what the strip says, not the last thing they did.
    expect(deck.locator(".deck-knobs-said")).to_contain_text(
        f"held · {_strip(url)['small']}", timeout=10000
    )
    story.shows(
        "A tap on Jog shows the knobs, which say a print holds the port",
        "A tap on a name along the top of the strip shows that screen. The knobs' screen "
        "no longer looks live: what each knob moves is greyed, the print holds the port, "
        "the server refuses a jog, and the strip says so in the server's own words, as the "
        "window's line for the knobs does. Print was brought forward once for this print "
        "and is not brought forward again.",
        blank=TIME_LEFT_SHOWN,
    )

    # 3. A knob pressed shows the next screen, Home; a turn there moves nothing.
    sent = httpx.get(f"{url}/firmware/decks/{DECK_ID}/control", timeout=15.0).json()["sent"]
    deck.locator(".deck-knob[data-knob='0'] .deck-press").click()
    _until(lambda: _screen(url) == "home", "Home shown by a knob pressed")
    deck.locator(".deck-knob[data-knob='0'] .deck-turn[data-dir='1']").click()
    _until(
        lambda: "the knobs move nothing on Home" in (_strip(url)["art"]["footer"] or ""),
        "the turn said to move nothing",
    )
    assert httpx.get(f"{url}/firmware/decks/{DECK_ID}/control", timeout=15.0).json()["sent"] == sent
    assert _drawn(url)["keys_drawn"]["2"]["text"] == "HOME"
    _window_shows_the_strip(url, deck)
    # The line under the strip's screen, written under its picture with its two lines.
    expect(deck.locator(".deck-strip-said .deck-strip-foot")).to_contain_text(
        "the knobs move nothing on Home", timeout=10000
    )
    story.shows(
        "A knob pressed shows Home, where a turn moves nothing",
        "Pressing a knob shows the next screen, and from the last the first. Home says "
        "where each axis stands and its switch as the last poll read it, and the third key "
        "is HOME, held a second to home every axis through the page's own path. The knobs "
        "move a machine on Jog alone: turned here, they send nothing and the strip says so.",
        blank=TIME_LEFT_SHOWN,
    )

    # 4. Temps: the printer's heaters as a graph of the polls made while the print runs.
    _tap(deck, "status")
    _until(lambda: _screen(url) == "status", "Temps shown")

    def risen() -> bool:
        series = (_strip(url)["art"]["body"] or {}).get("series") or []
        return len(series) == 2 and all(len(s["points"]) >= 4 for s in series)

    _until(risen, "the heaters drawn over a few polls", seconds=40)
    body = _strip(url)["art"]["body"]
    assert body["kind"] == "graph" and [s["target"] for s in body["series"]] == [200.0, 60.0]
    assert _drawn(url)["keys_drawn"]["2"]["art"]["title"] == "HOTEND"
    _window_shows_the_strip(url, deck)
    story.shows(
        "Temps draws the heaters as they rise",
        "The printer's hotend and bed over the last ten minutes, each as it was read and "
        "what it was asked to reach dashed, the newest written at the right. The graph is "
        "drawn from the polls anyone made -- here the deck's own, while the printer's "
        "control is armed -- and the deck asks for nothing to draw it. The third key is "
        "the hotend's number.",
        blank=TIME_LEFT_SHOWN,
    )

    # 5. The Bench: both machines at once. The printer's control let go first, so no clock
    #    is drawn into the strip (a cancel needs no latch).
    _post(url, "control", armed=False).raise_for_status()
    _tap(deck, "bench")
    _until(lambda: _screen(url) == "bench", "the Bench shown")
    _until(
        lambda: _strip(url)["text"].startswith("Bench · printer_1 paused · cnc_router"),
        "the Bench drawn",
    )
    assert "armed" not in _strip(url)["text"]
    machines = _strip(url)["art"]["body"]["machines"]
    assert [m["name"] for m in machines] == ["printer_1", "cnc_router"]
    assert machines[0]["bar_label"].startswith(FILE_NAME[:12])
    _window_shows_the_strip(url, deck)
    story.shows(
        "The Bench shows both machines",
        "The first screen is both machines, half the strip each: its state, its numbers and "
        "its job's bar. The printer's control was let go first, as the Site's row says; a "
        "machine armed says so here with the time it has left. The knobs move nothing here.",
        shown=_strip_words(url),
        blank=TIME_LEFT_SHOWN,
    )

    # 6. The print ends, cancelled: Print says so until a touch of it.
    _tap(deck, "progress")
    _until(lambda: _screen(url) == "progress", "back on Print")
    _post(url, "print/cancel").raise_for_status()
    _until(lambda: "cancelled" in (_strip(url)["small"] or ""), "the end said on the strip")
    time.sleep(5)
    assert "cancelled" in _strip(url)["small"] and _screen(url) == "progress"
    _window_shows_the_strip(url, deck)
    story.shows(
        "A print that ended stays on Print until a touch",
        "The print was cancelled. The strip says how it ended and after how long, and keeps "
        "saying it: nothing about the print clears it but a touch of this screen.",
        shown=_strip_words(url),
        blank=STRIP_WITH_A_CLOCK,
    )
    _tap(deck, "progress")
    _until(lambda: _strip(url)["text"] == "printer_1 · no job", "the result cleared by a touch")
    assert _screen(url) == "progress"
    heard = _touches(url)
    _swipe(page, deck, -1)  # a swipe still walks them: back to Home
    _until(lambda: _touches(url) > heard, "the swipe heard")
    _until(lambda: _screen(url) == "home", "swiped back to Home")
    _post(url, "control", armed=False)
