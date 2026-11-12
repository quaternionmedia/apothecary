"""The Tour, as a person takes it: ⊞ Windows › Tour opens the walkthrough beside the live
page, on the first step not yet answered; a page chosen shows its first step as its test
recorded it; ✓ As shown and ✗ Off keep a person's word on the step, Off only with what is
off; Back shows the word kept; the ring's Panels › Windows › Tour cells do what its
buttons do; a reload opens it where it was; and `apothecary tour` reads back what was
said. Walkthrough page 34 is what it writes.

Runs against a server of its own, its state folder this module's, so the verdicts it
keeps are its and `apothecary tour` reads them from there.
"""

from __future__ import annotations

import re

import httpx
import pytest
import windows
from click.testing import CliRunner
from doc_capture import MOMENT
from garage import open_garage
from playwright.sync_api import expect
from rings import on_world
from viewer_ready import settled

from apothecary.cli.main import cli

ROUTER = "31-what-the-router-needs.md"
TOUR = ".panel[data-panel='tour']"
NOTE = "Z's line ends past the pad's edge"
# What changes on every run whatever the page does: the moments, and the commit the
# server runs (and whether its tree has changes beside it).
COMMIT = r"against (?:[0-9a-f]{8}|an unknown commit)(?: with changes)?"
CHANGING = ((TOUR, MOMENT), (TOUR, COMMIT), ("#status", MOMENT))


def _words(text: str) -> str:
    """What the window says, its moments and the commit left out, as its pictures blank them."""
    return re.sub(COMMIT, "against …", re.sub(MOMENT, "…", text))


@pytest.fixture(scope="module")
def state(tmp_path_factory):
    return tmp_path_factory.mktemp("tour-state")


@pytest.fixture(scope="module")
def url(start_server, state):
    return start_server({"APOTHECARY_STATE_DIR": str(state)})


def _answers(url: str) -> dict:
    stops = httpx.get(f"{url}/tour", timeout=15.0).json()["stops"]
    return next(s for s in stops if s["page"] == ROUTER)["answers"]


@pytest.mark.e2e
def test_the_tour_beside_the_page_keeps_a_person_s_word_on_each_step(
    page, url, state, walkthrough, monkeypatch
):
    story = walkthrough(
        ordinal="34",
        slug="the-tour",
        title="The tour",
        intro=(
            "The walkthrough a step at a time, beside the live page: each step as the test "
            "that writes its page recorded it -- its heading, its words, the picture taken "
            "after its assertions, what it showed -- and a person's word on it, kept with "
            "the commit the server ran. The words say what to do in the page; the picture "
            "is what the page did when the test did it. A page no test writes is read whole "
            "at its link. [docs/tour.md](../docs/tour.md) is the reference."
        ),
        runtime=(
            "It drives a real browser against a real server of its own, whose state folder "
            "is this test's, so the words it keeps are its own and `apothecary tour` reads "
            "them from there. The steps it shows are the walkthrough's pages as committed."
        ),
        does_not_show=[
            "**Doing a step.** The tour shows a step's words and picture beside the page; "
            "doing what the words say is the person's, in the page beside it, and is "
            "each page's own test.",
            "**What changes on every run.** Moments and the commit the server runs are "
            "blanked in the pictures and left out of the words.",
        ],
        browser_suite_only=True,
    )
    window = page.locator(TOUR)
    lead = window.locator(".tour-next")
    open_garage(page, url)

    # 1. ⊞ Windows › Tour: beside the world, on the first step not yet answered.
    windows.from_the_windows_menu(page, "tour")
    expect(lead).to_contain_text("Page 00 is read whole")
    expect(window.locator(".tour-heading")).to_have_text("Getting started")
    expect(window.locator(".tour-said")).to_contain_text(
        re.compile(r"^0 of \d+ steps answered, 0 off")
    )
    expect(window.locator(".tour-page")).to_have_attribute(
        "href", re.compile(r"/walkthrough/00-getting-started\.md$")
    )
    settled(page)
    story.shows(
        "⊞ Windows › Tour opens beside the world, on the first step not answered",
        "The header's ⊞ Windows, Tour under Tools: the walkthrough beside the world, "
        "nothing answered yet, so on its first page. Page 00 is written by hand and its "
        "checks run with the tests, so it is read whole: the window gives its first "
        "words and its page's link, and asks whether it says what the app does.",
        shown=_words(lead.inner_text()),
        blank=CHANGING,
    )

    # 2. A page chosen: its first step, as its test recorded it.
    stops = httpx.get(f"{url}/tour", timeout=15.0).json()["stops"]
    at = next(i for i, s in enumerate(stops) if s["page"] == ROUTER)
    window.locator(".tour-stops").select_option(value=str(at))  # "31 — What the router needs"
    expect(lead).to_contain_text("Step 1 of 7 of page 31")
    expect(window.locator(".tour-heading")).to_have_text(
        "1. In alarm, Needs you says what clears it"
    )
    picture = window.locator(".tour-picture img")
    expect(picture).to_have_attribute(
        "src",
        re.compile(r"/walkthrough/screenshots/31-01-in-alarm-needs-you-says-what-clears-it\.png$"),
    )
    page.wait_for_function(
        "() => document.querySelector(\".panel[data-panel='tour'] .tour-picture img\").naturalWidth > 0"
    )
    expect(window.locator(".tour-answer")).to_have_text("Not answered yet.")
    story.shows(
        "Page 31 chosen: its first step, as its test recorded it",
        "The window's drop-down, page 31: its first step's heading and words, which say "
        "what a person does in the page beside it, and the picture its test took after "
        "the step's assertions passed. A click on the picture opens it whole in a tab of "
        "its own; its page is the link at the foot.",
        shown=_words(lead.inner_text()),
        blank=CHANGING,
    )

    # 3. ✓ As shown: kept on the server, and the next step shown.
    window.get_by_role("button", name="✓ As shown").click()
    expect(lead).to_contain_text("Step 2 of 7 of page 31")
    assert _answers(url)["1"]["verdict"] == "as shown"
    expect(window.locator(".tour-stops option:checked")).to_contain_text("· 1/7")
    expect(window.locator(".tour-said")).to_contain_text(
        re.compile(r"^1 of \d+ steps answered, 0 off")
    )
    story.shows(
        "✓ As shown keeps the word and goes to the next step",
        "✓ As shown: the server keeps it, with the moment and the commit it runs, and the "
        "window goes to step 2. The drop-down counts the page's steps answered, and the "
        "line under it the whole tour's.",
        shown=_words(page.locator("#status").inner_text()),
        blank=CHANGING,
    )

    # 4. ✗ Off with nothing said is refused; with what is off, kept.
    window.get_by_role("button", name="✗ Off").click()
    expect(window.locator(".tour-answer")).to_have_text("Not kept: say what is off.")
    expect(lead).to_contain_text("Step 2 of 7 of page 31")
    assert set(_answers(url)) == {"1"}
    window.locator(".tour-note").fill(NOTE)
    window.get_by_role("button", name="✗ Off").click()
    expect(lead).to_contain_text("Step 3 of 7 of page 31")
    assert _answers(url)["2"] == {**_answers(url)["2"], "verdict": "off", "note": NOTE}
    expect(window.locator(".tour-note")).to_have_value("")
    story.says(
        "✗ Off keeps what is off, and only with it",
        "✗ Off with the box empty is refused, the window saying what it needs and staying "
        "on the step; with what is off typed in the box, it is kept, and the window goes "
        "on.",
        shown=_words(page.locator("#status").inner_text()),
    )

    # 5. ‹ Back: the word kept on the step, beside it.
    window.get_by_role("button", name="‹ Back").click()
    expect(lead).to_contain_text("Step 2 of 7 of page 31")
    expect(window.locator(".tour-answer")).to_contain_text(f"✗ Off: {NOTE} -- said ")
    expect(window.locator(".tour-stops option:checked")).to_contain_text("· 2/7 · 1 off")
    story.shows(
        "‹ Back shows the word kept on the step",
        "‹ Back to step 2: under its picture, what was said of it, when, and against which "
        "commit; the drop-down says the page has one step off.",
        shown=_words(window.locator(".tour-answer").inner_text()),
        blank=CHANGING,
    )

    # 6. The ring: Panels › Windows › Tour's cells do what its buttons do.
    on_world(page, "Panels", "Windows", "Tour", "Next")
    expect(lead).to_contain_text("Step 3 of 7 of page 31")
    on_world(page, "Panels", "Windows", "Tour", "As shown")
    expect(lead).to_contain_text("Step 4 of 7 of page 31")
    assert _answers(url)["3"]["verdict"] == "as shown"
    story.says(
        "Panels › Windows › Tour: its cells are its buttons",
        "The canvas ring's Panels › Windows › Tour: Next goes to step 3, and As shown keeps "
        "a word on it and goes to step 4. Back, Off, Its page and Its picture are cells "
        "there too.",
        shown=_words(lead.inner_text()),
    )

    # 7. Reloaded: open again, where it was.
    windows.remembered(page)
    page.reload()
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=20000)
    expect(lead).to_contain_text("Step 4 of 7 of page 31")
    story.says(
        "Reloaded, it is open where it was",
        "The page reloaded: the Tour is open again beside the world, as any window is, on "
        "the step it showed; this browser keeps where it was, the server what was said.",
        shown=_words(lead.inner_text()),
    )

    # 8. `apothecary tour` reads back what was said.
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(state))
    said = CliRunner().invoke(cli, ["tour", "--page", "31"])
    assert said.exit_code == 0, said.output
    lines = said.output.splitlines()
    assert lines[0] == "31 What the router needs: 2 as shown, 1 off, 4 not yet"
    assert lines[2].startswith(
        f"  ✗ 2. A jog in alarm did not go, and the card keeps why: {NOTE} ("
    )
    story.says(
        "`apothecary tour` reads back what was said",
        "At the command line, `apothecary tour --page 31`: each step answered, with what is "
        "off, and the commit and moment each was said against; `--off` lists only what is "
        "off, across every page.",
        shown="\n".join(re.sub(r" \([^()]*\)$", " (…)", line) for line in lines[:-1]),
    )
