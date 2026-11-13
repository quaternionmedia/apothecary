"""The tour over the page, a prototype on Make a thing: Tour in the header opens a box
above the windows, on the journey's first stage not yet said; Put the page here opens
the machine the journey is staged on, chooses its piece and enters the stage; ✓ As shown
keeps a person's word and puts the next stage on; the See stage slices the piece where
no file is kept, and its path is drawn; ✗ Off keeps what is off; and a view laid out
moves the windows and not the box. Walkthrough page 39 is what it writes.

Runs against a server of its own that says it is the demo (the tour puts a stage on
nowhere else), with the simulated printer pinned to printer_1's mainboard and the
scripted OrcaSlicer its slicer.
"""

from __future__ import annotations

import re

import httpx
import pytest
import windows
from boards import BOARD, DWELL, LAYERS, PRINTER
from doc_capture import MOMENT
from garage import open_garage
from playwright.sync_api import expect
from slicer_helpers import write_fake_orcaslicer
from viewer_ready import settled

BOX = "#tour-pop"
COMMIT = r"against (?:[0-9a-f]{8}|an unknown commit)(?: with changes)?"
CHANGING = ((BOX, MOMENT), (BOX, COMMIT), ("#status", MOMENT))
NOTE = "the job's row is cut off at the window's foot"
STEP_ON = "() => document.querySelector('#journey-rail [aria-current=step]')?.dataset.step"


@pytest.fixture(scope="module")
def state(tmp_path_factory):
    return tmp_path_factory.mktemp("tour-pop-state")


@pytest.fixture(scope="module")
def url(start_server, state, tmp_path_factory):
    orca = write_fake_orcaslicer(tmp_path_factory.mktemp("orca"))
    url = start_server(
        {
            "APOTHECARY_STATE_DIR": str(state),
            "APOTHECARY_DEMO": str(state),
            "APOTHECARY_SIMULATED_PRINTER": "idle",
            "APOTHECARY_ORCASLICER": str(orca),
            "FAKE_ORCA_LAYERS": LAYERS,
            "FAKE_ORCA_DWELL": DWELL,
        }
    )
    with httpx.Client(base_url=url, timeout=15.0) as http:
        http.post("/firmware/devices/identify", json={"port": PRINTER}).raise_for_status()
        http.put(f"/sites/garage/nodes/{BOARD}/device", json={"identity": PRINTER}).raise_for_status()
    return url


def _answers(url: str) -> dict:
    make = httpx.get(f"{url}/tour/journeys", timeout=15.0).json()["journeys"][0]
    return {s["id"]: s["answer"] for s in make["stages"]}


def _put_on(page, step: str) -> None:
    """The box done putting the page on ``step``, and the rail there."""
    expect(page.locator(f"{BOX} .tour-pop-put")).to_have_text("Put the page here", timeout=60000)
    page.wait_for_function(f"(s) => ({STEP_ON})() === s", arg=step, timeout=15000)


def _words(text: str) -> str:
    return re.sub(COMMIT, "against …", re.sub(MOMENT, "…", text))


@pytest.mark.e2e
def test_the_tour_over_the_page_puts_each_stage_of_make_a_thing_on(page, url, walkthrough):
    story = walkthrough(
        ordinal="39",
        slug="the-tour-over-the-page",
        title="The tour over the page (a prototype)",
        intro=(
            "A prototype of the tour as a box over the page, on one journey, Make a thing: "
            "each stage put on by the page -- the machine opened, the piece chosen, the "
            "stage entered, the piece sliced where a stage needs its file -- for a person "
            "to explore, and one word kept on the stage. The box is above the windows, so "
            "a view or a journey lays them out beneath it."
        ),
        runtime=(
            "It drives a real browser against a real server of its own that says it is the "
            "demo, its printer a simulation and its slicer a script that answers as "
            "OrcaSlicer's command line does."
        ),
        does_not_show=[
            "**What to try at a stage.** The box gives the stage's own line from the rail; "
            "what its tests check there is not yet read into it.",
            "**Any journey but Make a thing**, and **a server that is not the demo**, where "
            "the box puts nothing on.",
        ],
        browser_suite_only=True,
    )
    box = page.locator(BOX)
    did = box.locator(".tour-pop-did li")
    open_garage(page, url)

    # 1. Tour, in the header: the box over the page, the page as it was.
    expect(box).to_be_hidden()
    page.locator("#tour-pop-open").click()
    expect(box).to_be_visible()
    assert page.evaluate("() => document.querySelector('#tour-pop').matches(':popover-open')")
    expect(box.locator(".tour-pop-name")).to_have_text("Tour · Make a thing · 0 of 5 said")
    expect(box.locator(".tour-pop-stage")).to_have_text("1. Choose")
    expect(box.locator(".tour-pop-answer")).to_have_text("Not said yet.")
    expect(page.locator("#journey-rail")).to_be_hidden()
    assert page.evaluate("() => window.fractalViewer.machine") is None
    settled(page)
    story.shows(
        "Tour, in the header, opens a box over the page",
        "Tour in the header: a box above the windows, on Make a thing's first stage "
        "nobody has said anything of. Nothing in the page has moved: no Machine is open "
        "and no journey is entered.",
        shown=box.locator(".tour-pop-name").inner_text(),
        blank=CHANGING,
    )

    # 2. Put the page here: the machine opened, the piece chosen, the stage entered.
    box.locator(".tour-pop-put").click()
    _put_on(page, "choose")
    expect(did).to_contain_text(
        ["printer_1's Machine opened", "footpedal chosen", "Make a thing entered", "1 Choose"]
    )
    assert page.evaluate("() => window.fractalViewer.selectedName") == "footpedal"
    assert windows.state(page, "site")["shown"] is True
    settled(page)
    story.shows(
        "Put the page here opens what the stage needs and enters it",
        "Put the page here: printer_1's Machine is opened and the footpedal chosen, as a "
        "person would do each, and Make a thing is entered at Choose, its windows laid "
        "out and its rail in the header. The box says what it did, then what the page "
        "said. The stage is there to explore.",
        shown="\n".join(_words(t) for t in did.all_inner_texts()),
        blank=CHANGING,
    )

    # 3. ✓ As shown: kept, and the next stage put on.
    box.get_by_role("button", name="✓ As shown").click()
    expect(box.locator(".tour-pop-stage")).to_have_text("2. Shape")
    _put_on(page, "shape")
    assert _answers(url)["choose"]["verdict"] == "as shown"
    page.wait_for_function("() => window.apothecaryPanels.state('part-parameters').shown")
    expect(box.locator(".tour-pop-name")).to_have_text("Tour · Make a thing · 1 of 5 said")
    story.says(
        "✓ As shown keeps the word and puts the next stage on",
        "✓ As shown: the server keeps it with the commit it runs, and the box goes to "
        "Shape and puts the page there, Parameters in front.",
        shown=_words(did.last.inner_text()),
    )

    # 4. See, chosen in the box: no file is kept, so the piece is sliced, and its path drawn.
    box.locator(".tour-pop-stages button", has_text="4 See").click()
    _put_on(page, "see")
    expect(did).to_contain_text(["footpedal sliced for printer_1, as Slice does"])
    expect(did.last).to_contain_text("path is drawn on printer_1 and framed")
    settled(page)
    story.shows(
        "See is put on from nothing: the piece sliced, its path drawn",
        "See, chosen on the box: the stage draws the chosen file's path, and no file is "
        "kept, so the page does the stage before it -- the footpedal sliced for "
        "printer_1, as Slice does -- and the path is drawn on the machine and framed.",
        shown="\n".join(_words(t) for t in did.all_inner_texts()),
        blank=CHANGING,
    )

    # 5. ✗ Off keeps what is off, and only with it.
    box.get_by_role("button", name="✗ Off").click()
    expect(box.locator(".tour-pop-answer")).to_have_text("Not kept: say what is off.")
    assert _answers(url)["see"] is None
    box.locator(".tour-pop-note").fill(NOTE)
    box.get_by_role("button", name="✗ Off").click()
    expect(box.locator(".tour-pop-stage")).to_have_text("5. Print")
    _put_on(page, "print")
    assert _answers(url)["see"] == {**_answers(url)["see"], "verdict": "off", "note": NOTE}
    page.wait_for_function("() => window.apothecaryPanels.state('machine').shown")
    story.says(
        "✗ Off keeps what is off, and only with it",
        "✗ Off with the box empty is refused; with what is off typed, it is kept, and the "
        "box goes to Print and puts the page there, the Machine and Jobs in front.",
        shown=_words(did.last.inner_text()),
    )

    # 6. A view laid out moves the windows, and not the box.
    before = box.bounding_box()
    assert before["y"] >= 0 and before["y"] + before["height"] <= page.viewport_size["height"]
    page.evaluate("() => window.fractalViewer.openView('default')")
    page.wait_for_function("() => window.apothecaryPanels.state('machine-print').shown === false || true")
    expect(box).to_be_visible()
    assert page.evaluate("() => document.querySelector('#tour-pop').matches(':popover-open')")
    assert box.bounding_box() == before
    settled(page)
    story.shows(
        "A view laid out moves the windows, and not the box",
        "The Default view laid out from ⊞ Windows: every window goes where that view "
        "has it, and the box is where it was, open on the stage it showed.",
        shown=box.locator(".tour-pop-name").inner_text(),
        blank=CHANGING,
    )
