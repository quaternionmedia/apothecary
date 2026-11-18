"""Windows a person opened are open again after a reload, where they were: Models, Marks,
the Working space and the Deck, each registered closed and opened from ⊞ Windows, laid
out again in the stack it was in, and the world as wide as it was. No window of the page
is one panels.js says a reload closes. Walkthrough page 33 is what it writes.

Runs against a server of its own, so the site it draws is the code's whatever ran before.
"""

from __future__ import annotations

import pytest
import windows
from doc_capture import TEMPERATURE, moments
from garage import open_garage
from playwright.sync_api import expect
from viewer_ready import settled

# Windows the page's own layout leaves closed, each opened from ⊞ Windows by a person:
# Models, Marks and the Deck in the one stack beside the world, Working space among the
# tabs.
OPENED = ("models", "marks", "working", "deck")

# What changes on every run whatever the page does: the moments, and in the Working
# space how many observations the hour holds and a temperature.
CHANGING = (
    *moments(".panel", "#status"),
    ".working-space .ws-said",
    (".working-space", r"\d+(?:\.\d)? °C"),
    (".working-space pre", TEMPERATURE),
)


@pytest.fixture(scope="module")
def url(start_server):
    return start_server()


@pytest.mark.e2e
def test_windows_a_person_opened_are_open_after_a_reload_where_they_were(page, url, walkthrough):
    """Models, Marks, Working space and the Deck, opened from ⊞ Windows, are open again
    after a reload, each in the stack it was in, and the world keeps the width it had:
    none is dropped from the remembered layout, its room kept from the world. And no
    window of the page is one panels.js says a reload closes."""
    story = walkthrough(
        ordinal="33",
        slug="windows-kept-over-a-reload",
        title="Windows kept over a reload",
        intro=(
            "The windows a person opens are the page's layout from then: a reload lays "
            "them out again where they were, and the world keeps the room it had. Four "
            "windows the page's own layout leaves closed -- Models, Marks, the Working "
            "space and the Deck -- are opened from ⊞ Windows and the page is reloaded. "
            "[docs/viewer.md](../docs/viewer.md#the-windows) is the reference."
        ),
        runtime=(
            "It drives a real browser against a real server of its own, on the garage as "
            "the code has it. The layout is remembered in the browser, as a person's is; "
            "nothing is kept on the server."
        ),
        does_not_show=[
            "**Another browser.** The layout is this browser's own: another browser, or "
            "this one with its site data cleared, opens the page's own layout.",
            "**What changes on every run.** Moments, how many observations the Working "
            "space's hour holds and a temperature are blanked in the pictures.",
        ],
        browser_suite_only=True,
    )
    lost = []
    page.on("console", lambda m: lost.append(m.text) if "a reload closes it" in m.text else None)
    open_garage(page, url)

    # 1. Four windows opened from ⊞ Windows, each where the page puts it.
    for pid in OPENED:
        windows.from_the_windows_menu(page, pid)
        assert windows.state(page, pid)["open"] is True, pid
    windows.remembered(page)
    stacks = {pid: windows.state(page, pid)["stack"] for pid in OPENED}
    assert stacks["deck"] == ["models", "marks", "deck"], stacks
    width = windows.world_width(page)
    settled(page)
    story.shows(
        "Models, Marks, the Working space and the Deck, opened from ⊞ Windows",
        "The header's ⊞ Windows, four times: Models, Marks and the Deck tabs of the one "
        "stack beside the world, Models taking its room from the world's and each after it "
        "in front as it opens, and the Working space a tab of the "
        "stack under Selected, beside Pictures, Bench and Settings, each in front as it "
        "opens. The browser remembers the layout a moment after each change.",
        blank=CHANGING,
    )

    # 2. Reloaded: each open again in the stack it was in, the world as wide.
    page.reload()
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=20000)
    for pid in OPENED:
        state = windows.state(page, pid)
        assert state is not None and state["open"] is True, pid
        assert state["stack"] == stacks[pid], pid
    assert abs(windows.world_width(page) - width) < 2, (windows.world_width(page), width)
    assert lost == []
    settled(page)
    story.shows(
        "Reloaded, each is open where it was, and the world as wide",
        "The page reloaded: the four are open again, each in the stack it was in, and "
        "the world has the room it had. No window of the page is one a reload closes. "
        "The Working space's tab comes back last in its stack, where the remembered "
        "layout holds it; before the reload the tab row drew it ahead of Settings.",
        blank=CHANGING,
    )
