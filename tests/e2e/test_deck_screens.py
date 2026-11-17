"""The deck's strip while a print streams, through the page: a print begun on the printer
brings the Progress screen forward on the deck's strip, a swipe along the Deck window's
strip walks the screens and stops at their ends, a tap changes nothing, the knobs' screen
says the jogs are refused while the print holds the port, and a print that ends stays on
Progress, how it ended, until a touch.

This module is a walkthrough page too: `walkthrough/41-the-deck-while-a-print-streams.md`
is what its first test writes. The browser suite alone writes it.

Runs against a server of its own with one simulated deck whose layout is started
(APOTHECARY_DECK_CONTROL) and the simulated printer idle on /dev/ttyFAKE1 pinned to its
node: nothing here opens a HID device or a serial port. What only a real deck shows -- the
shape of a swipe the device reports -- is section J of the bench checklist
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
# A print long enough to be paused in: a two-second dwell first, which a pause catches
# every time, so the print is held at its second line and the tool where it began, and
# two thousand short moves after it.
GCODE = "G90\nG4 P2000\n" + "".join(
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
        stamp = "|".join([drawn["text"], drawn["small"] or "", drawn["colour"]])
        img = deck.locator(".deck-strip-tap img")
        return (img.get_attribute("src") or "").endswith(
            "v=" + quote(stamp, safe="-_.!~*'()")
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


def _post(url: str, path: str, **body) -> httpx.Response:
    return httpx.post(f"{url}/firmware/printers/{path}", json={"port": PRINTER, **body}, timeout=30)


@pytest.mark.e2e  # the browser suite's alone: not walkthrough, so `test run` stays quick
def test_the_deck_shows_a_print_and_a_swipe_walks_its_screens(page: Page, url: str, walkthrough):
    """A print is begun on the simulated printer: the strip brings Progress forward on
    its own, with the file's name, a bar and the stage; swiped back to the knobs, it
    says the jogs are refused in the server's words and is not pulled forward again; a
    swipe to Status shows the printer's state; a tap moves nothing; the print is
    cancelled, and Progress says so until a touch. Walkthrough 41 is what it writes."""
    story = walkthrough(
        ordinal="41",
        slug="the-deck-while-a-print-streams",
        title="The deck while a print streams",
        browser_suite_only=True,
        intro=(
            "While a print streams, the Stream Deck +'s touch strip shows how far it is "
            "and what the printer is doing, and a swipe along the strip switches screens: "
            "the knobs', Progress and Status. The deck in this page is simulated and so is "
            "the printer; the drag a swipe makes is the event a real deck reports."
        ),
        runtime=(
            "It drives a real browser against a real server of its own, with one simulated "
            "deck whose layout is started and the simulated printer pinned to its node. No "
            "HID device or serial port is opened and nothing reaches the network."
        ),
        does_not_show=[
            "**Progress's clock.** The strip says how long a print has run, which differs on "
            "every run; the server draws it into the strip's picture, so where Progress shows "
            "the strip is greyed in the picture and its words are written under it, the time "
            "as ‒:‒‒.",
            "**A real deck.** What only it shows -- how the device reports a finger drawn "
            "along its strip, and the strip's brightness under a hand -- is section J of "
            "the bench checklist (docs/bench-checklist.md).",
            "**A cut.** A router's job is the same record; tests/test_firmware_deck_control.py "
            "holds its screens.",
        ],
        page=page,
    )
    open_garage(page, url, settle=False)
    windows.open_window(page, "deck")
    deck = page.locator(DECK)
    expect(deck.locator(".deck-strip-tap img:visible")).to_have_count(1, timeout=15000)
    assert _screen(url) == "knobs"
    expect(deck.locator(".deck-screen")).to_contain_text("strip screen: knobs (1/3)", timeout=10000)

    # 1. A print is begun: Progress is brought forward, once.
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
    _until(lambda: _screen(url) == "progress", "Progress brought forward")
    _until(lambda: _strip(url)["text"].startswith(FILE_NAME[:20]), "the file named on the strip")
    # The layout draws the strip at its tick (deck_control.TICK_S): the pause is said at
    # the next one.
    _until(lambda: "paused" in (_strip(url)["small"] or ""), "the pause said on the strip")
    strip = _strip(url)
    assert strip["bar"] is not None and "paused" in strip["small"], strip
    assert "remaining" not in strip["small"]
    expect(deck.locator(".deck-screen")).to_contain_text(
        "strip screen: progress (2/3)", timeout=10000
    )
    _window_shows_the_strip(url, deck)
    story.shows(
        "A print begun brings Progress forward on the strip",
        "The simulated printer is streaming a kept file. The strip names the file, how far "
        "it is as a number and a bar, the stage and how long it has run; no time remaining "
        "is shown, since the job's record carries none. The print is paused where it is "
        "so the picture can be read.",
        shown=_strip_words(url),
        blank=STRIP_WITH_A_CLOCK,
    )

    # 2. Swiped back to the knobs: the jogs are refused, in the server's words, and
    #    Progress is not brought forward again.
    _swipe(page, deck, -1)
    _until(lambda: _screen(url) == "knobs", "swiped back to the knobs")
    _until(lambda: "holds the port" in (_strip(url)["small"] or ""), "the hold said")
    assert _strip(url)["text"] == "printer_1 · held" and "jogs refused" in _strip(url)["small"]
    time.sleep(5)  # two ticks of the layout: nothing pulls the strip forward again
    assert _screen(url) == "knobs"
    _window_shows_the_strip(url, deck)
    story.shows(
        "Swiped back to the knobs, which say a print holds the port",
        "A drag along the strip, most of its length, is a swipe. The knobs' screen no longer "
        "looks live: the print holds the port, the server refuses a jog, and the strip says "
        "so in the server's own words. Progress was brought forward once for this print and "
        "is not brought forward again.",
        blank=TIME_LEFT_SHOWN,
    )

    # 3. A tap moves nothing; a swipe forward twice stops at Status.
    heard = _touches(url)
    deck.locator(".deck-strip-tap").click(position={"x": 200, "y": 20})
    _until(lambda: _touches(url) > heard, "the tap heard")
    assert _screen(url) == "knobs"
    for screen in ("progress", "status"):
        _swipe(page, deck, +1)
        _until(lambda wanted=screen: _screen(url) == wanted, f"swiped on to {screen}")
    heard = _touches(url)
    _swipe(page, deck, +1)  # the third has nowhere to go
    _until(lambda: _touches(url) > heard, "the third swipe heard")
    time.sleep(1)  # taken in the layout's turn, where it moves nothing
    assert _screen(url) == "status"
    assert _strip(url)["text"].startswith("printer_1 · ")
    _window_shows_the_strip(url, deck)
    story.shows(
        "On to Status, the last screen",
        "Another swipe forward shows the printer's state, its temperatures and the first "
        "thing it asks of a person, read from the newest status anyone's poll made. A swipe "
        "past the last screen moves nothing, and a tap on the strip changed nothing.",
        blank=TIME_LEFT_SHOWN,
    )

    # 4. The print ends, cancelled: Progress says so until a touch of it.
    _swipe(page, deck, -1)
    _until(lambda: _screen(url) == "progress", "back on Progress")
    _post(url, "print/cancel").raise_for_status()
    _until(lambda: "cancelled" in (_strip(url)["small"] or ""), "the end said on the strip")
    time.sleep(5)
    assert "cancelled" in _strip(url)["small"] and _screen(url) == "progress"
    _window_shows_the_strip(url, deck)
    story.shows(
        "A print that ended stays on Progress until a touch",
        "The print was cancelled. The strip says how it ended and after how long, and keeps "
        "saying it: nothing about the print clears it but a touch of this screen.",
        shown=_strip_words(url),
        blank=STRIP_WITH_A_CLOCK,
    )
    deck.locator(".deck-strip-tap").click(position={"x": 200, "y": 20})
    _until(lambda: _strip(url)["text"] == "printer_1 · no job", "the result cleared by a touch")
    assert _screen(url) == "progress"
    _post(url, "control", armed=False)
