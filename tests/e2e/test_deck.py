"""The Stream Deck +, through the page: its piece on the bench opens the Deck window, a
program draws its keys and its strip through the routes, and the window shows them as
they were sent; a simulated deck is pressed, turned and tapped from the window, and what
it heard is listed, as the server keeps it.

This module is a walkthrough page too: `walkthrough/26-the-stream-deck.md` is what its
first test writes, its pictures taken as it goes. The browser suite alone writes it.

Runs against a server of its own with one simulated deck (APOTHECARY_SIMULATED_DECK),
under the simulated serial engine: no HID device is listed or opened, and nothing
reaches the network. A real deck is section J of the bench checklist
(docs/bench-checklist.md).
"""

from __future__ import annotations

import httpx
import pytest
import windows
from garage import open_garage, select
from playwright.sync_api import Page, expect
from windows import DECK

DECK_ID = "DEMODECK"
LABELS = [
    ("X-", "blue"), ("Y+", "blue"), ("Y-", "blue"), ("X+", "blue"),
    ("Z-", "green"), ("Z+", "green"), ("1 mm", "amber"), ("STOP", "red"),
]  # fmt: skip


@pytest.fixture(scope="module")
def url(start_server):
    return start_server({"APOTHECARY_SIMULATED_DECK": DECK_ID})


def _heard(url: str) -> list:
    return httpx.get(f"{url}/firmware/decks/{DECK_ID}/events").json()["events"]


@pytest.mark.e2e  # the browser suite's alone: not walkthrough, so `test run` stays quick
def test_the_deck_is_drawn_from_here_and_what_it_hears_is_listed(page: Page, url: str, walkthrough):
    """The stream_deck piece's Open Deck opens the Deck window on the one deck found,
    its keys and strip empty; a program draws all eight keys and the strip and the window
    shows each as it was sent; a key pressed, a knob turned and pressed, and the strip
    tapped from the window are the events a real deck reports, listed there and kept by
    the server. Walkthrough 26 is what it writes."""
    story = walkthrough(
        ordinal="26",
        slug="the-stream-deck",
        title="The Stream Deck +",
        browser_suite_only=True,
        intro=(
            "An Elgato Stream Deck + at the garage's bench, found on USB, its keys and its "
            "touch strip drawn from here, and its keys, knobs and touches heard. The deck "
            "in this page is simulated, so every step can be shown; the device's own "
            "reports are the same events."
        ),
        runtime=(
            "It drives a real browser against a real server of its own, with one simulated "
            "deck under the simulated serial engine. No HID device is listed or opened and "
            "nothing reaches the network."
        ),
        does_not_show=[
            "**A real deck.** What only a deck shows -- its screen, its knobs' feel, the "
            "udev rule -- is section J of the bench checklist (docs/bench-checklist.md).",
            "**The knobs jogging a machine.** That is the controller (docs/stream-deck.md).",
        ],
        page=page,
    )
    open_garage(page, url)
    # 1. The piece on the bench, and its door to the Deck.
    select(page, "stream_deck")
    door = page.locator("#selected-body .deck-open")
    expect(door).to_be_visible(timeout=5000)
    door.click()
    deck = page.locator(DECK)
    expect(deck).to_be_visible(timeout=5000)
    expect(deck.locator(".deck-name")).to_contain_text(
        f"Stream Deck + · {DECK_ID} · 0x0fd9:0x0084 · simulated", timeout=10000
    )
    expect(deck.locator(".deck-key img:visible")).to_have_count(0)
    expect(deck.locator(".deck-events")).to_contain_text("nothing heard yet")
    story.shows(
        "The stream_deck piece's Open Deck opens the Deck window",
        "The Stream Deck + stands on the bench's right end; its piece's Open Deck opens "
        "the Deck window on the one deck found, a simulated one, named with Elgato's "
        "vendor id and the model's product id. Nothing has been drawn on it yet.",
    )

    # 2. A program draws it, through the routes.
    for index, (text, colour) in enumerate(LABELS):
        sent = httpx.put(
            f"{url}/firmware/decks/{DECK_ID}/keys/{index}", json={"text": text, "colour": colour}
        )
        assert sent.status_code == 200, sent.text
    strip = httpx.put(
        f"{url}/firmware/decks/{DECK_ID}/strip",
        json={"text": "cnc_router", "small": "disarmed", "colour": "grey"},
    )
    assert strip.status_code == 200, strip.text
    expect(deck.locator(".deck-key img:visible")).to_have_count(8, timeout=10000)
    expect(deck.locator(".deck-strip-tap img:visible")).to_have_count(1, timeout=10000)
    sizes = deck.locator(".deck-key img").evaluate_all(
        "(is) => is.map((i) => [i.naturalWidth, i.naturalHeight])"
    )
    assert sizes == [[120, 120]] * 8, sizes
    assert deck.locator(".deck-strip-tap img").evaluate(
        "(i) => [i.naturalWidth, i.naturalHeight]"
    ) == [
        800,
        100,
    ]
    story.shows(
        "A program draws its eight keys and its strip",
        "Each key and the strip were set by a PUT to the deck's routes: a label on a "
        "colour, drawn here and sent as the JPEG the device takes. The window shows what "
        "was sent, since a deck cannot be asked what it shows.",
    )

    # 3. The deck is pressed, turned and tapped, as a real one reports.
    deck.locator(".deck-key[data-key='3']").click()
    deck.locator(".deck-knob[data-knob='1'] .deck-turn[data-dir='1']").click()
    deck.locator(".deck-knob[data-knob='1'] .deck-turn[data-dir='1']").click()
    deck.locator(".deck-knob[data-knob='0'] .deck-turn[data-dir='-1']").click()
    deck.locator(".deck-knob[data-knob='2'] .deck-press").click()
    deck.locator(".deck-strip-tap").click()  # its middle
    events = deck.locator(".deck-events li")
    expect(events).to_have_count(8, timeout=10000)  # 2 + 2 + 1 + 2 + 1
    heard = _heard(url)
    assert [(e["kind"], e["index"], e["value"]) for e in heard[:2]] == [
        ("key", 3, True),
        ("key", 3, False),
    ]
    assert [(e["kind"], e["index"], e["value"]) for e in heard[2:5]] == [
        ("knob-turn", 1, 1),
        ("knob-turn", 1, 1),
        ("knob-turn", 0, -1),
    ]
    assert heard[-1]["kind"] == "touch" and heard[-1]["value"]["kind"] == "short"
    assert abs(heard[-1]["value"]["x"] - 400) <= 3 and abs(heard[-1]["value"]["y"] - 50) <= 3
    expect(events.first).to_contain_text("strip short at")
    expect(events.nth(1)).to_contain_text("knob 2 released")
    expect(deck.locator(".deck-events")).to_contain_text("key 3 pressed")
    expect(deck.locator(".deck-events")).to_contain_text("knob 1 turned +1")
    expect(deck.locator(".deck-events")).to_contain_text("knob 0 turned −1")
    story.shows(
        "A key pressed, knobs turned and pressed, the strip tapped",
        "Key 3 pressed, knob 1 turned two steps clockwise, knob 0 one step the other way, "
        "knob 2 pressed and the strip tapped: each is the event a real deck reports, "
        "listed here newest first and kept by the server, which a program reads with "
        "`GET /firmware/decks/{id}/events`. The strip's tap carries its position in the "
        "strip's own pixels, 800 across.",
    )
    assert windows.state(page, "deck")["open"]
