"""The tour, as a person takes it: Tour in the header opens a box over the page, on the
roadmap's first stop nobody has said anything of, a page shown only; the line of Print a
part chosen puts the page on its first stage -- the machine opened, the piece chosen,
the stage entered; ✓ As shown keeps a person's word and puts the next stage on, with
the steps its tests recorded to try there; the See stage slices the piece where no file
is kept, and its path is drawn; ✗ Off keeps what is off, and only with it; a view laid
out moves the windows and not the box; the ring's Panels › Windows › Tour cells do what
its buttons do; a reload opens it where it was; and `apothecary tour` reads back what
was said. Walkthrough page 34 is what it writes.

Runs against a server of its own that says it is the demo (the tour puts a stage on
nowhere else), with the simulated printer pinned to printer_1's mainboard and the
scripted OrcaSlicer its slicer; its state folder is this module's, so the answers it
keeps are its and `apothecary tour` reads them from there.
"""

from __future__ import annotations

import re

import httpx
import pytest
import windows
from boards import BOARD, DWELL, LAYERS, PRINTER
from click.testing import CliRunner
from doc_capture import MOMENT
from garage import open_garage
from playwright.sync_api import expect
from rings import open_from_key, press
from slicer_helpers import write_fake_orcaslicer
from viewer_ready import settled

from apothecary.cli.main import cli

BOX = "#tour-pop"
MAKE = "A part is chosen, shaped, sliced, seen and printed on a machine."
NOTE = "the job's row is cut off at the window's foot"
# What changes on every run whatever the page does: the moments, and the commit the
# server runs; and what changes with any line added to the roadmap, how many stops the
# tour holds.
COMMIT = r"against (?:[0-9a-f]{8}|an unknown commit)(?: with changes)?"
STOPS = r"(?<=of )\d+(?= said)"
CHANGING = ((BOX, MOMENT), (BOX, COMMIT), (BOX, STOPS), ("#status", MOMENT))
STEP_ON = "() => document.querySelector('#journey-rail [aria-current=step]')?.dataset.step"


def _words(text: str) -> str:
    """What the box says, its moments, the commit and the count of stops left out, as its
    pictures blank them."""
    return re.sub(STOPS, "…", re.sub(COMMIT, "against …", re.sub(MOMENT, "…", text)))


@pytest.fixture(scope="module")
def state(tmp_path_factory):
    return tmp_path_factory.mktemp("tour-state")


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
        http.put(
            f"/sites/garage/nodes/{BOARD}/device", json={"identity": PRINTER}
        ).raise_for_status()
    return url


def _answers(url: str) -> dict:
    lines = httpx.get(f"{url}/tour", timeout=15.0).json()["lines"]
    return {s["id"]: s["answer"] for line in lines for s in line["stops"]}


def _put_on(page, step: str) -> None:
    """The box done putting the page on ``step``, and the rail there."""
    expect(page.locator(f"{BOX} .tour-pop-put")).to_have_text("Put the page here", timeout=60000)
    page.wait_for_function(f"(s) => ({STEP_ON})() === s", arg=step, timeout=15000)


def _off_the_buttons(page) -> None:
    """The mouse on the status line, so no button pressed last is drawn hovered in a
    picture: whether it is depends on when the picture is taken."""
    page.mouse.move(640, 700)


@pytest.mark.e2e
def test_the_tour_puts_the_page_on_each_stage_and_keeps_a_person_s_word(
    page, url, state, walkthrough, monkeypatch
):
    story = walkthrough(
        ordinal="34",
        slug="the-tour",
        title="The tour",
        intro=(
            "What the roadmap claims, a stop at a time, in a box over the page: "
            "[docs/ROADMAP.md](../docs/ROADMAP.md) orders it, each of its lines naming a "
            "journey, whose stages are stops the page is put on, or walkthrough pages, "
            "each a stop that is read. A person explores a stage where it stands, and "
            "one word is kept on the stop with the commit the server ran. The box says "
            "nothing of its own: a stop's words are the journey's or the page's. "
            "[docs/tour.md](../docs/tour.md) is the reference."
        ),
        runtime=(
            "It drives a real browser against a real server of its own that says it is "
            "the demo, its printer a simulation and its slicer a script that answers as "
            "OrcaSlicer's command line does. Its state folder is this test's, so the "
            "answers it keeps are its own. The roadmap and the pages are as committed."
        ),
        does_not_show=[
            "**A server that is not the demo**, where the box shows a stage and puts "
            "nothing on.",
            "**A stage armed or started.** Start's stage brings the Machine and Jobs "
            "forward; arming control and starting a print are a person's.",
            "**What changes on every run.** Moments and the commit the server runs are "
            "blanked in the pictures and left out of the words, and so is how many stops "
            "the tour holds, which any line added to the roadmap changes.",
        ],
        browser_suite_only=True,
    )
    box = page.locator(BOX)
    did = box.locator(".tour-pop-did li")
    title = box.locator(".tour-pop-title")
    open_garage(page, url)

    # 1. Tour, in the header: the box over the page, on the first stop nobody has said
    # anything of, the page as it was.
    expect(box).to_be_hidden()
    page.locator("#tour-pop-open").click()
    expect(box).to_be_visible()
    assert page.evaluate("() => document.querySelector('#tour-pop').matches(':popover-open')")
    expect(box.locator(".tour-pop-name")).to_have_text(re.compile(r"^Tour · 0 of \d+ said, 0 off$"))
    expect(title).to_have_text("00 — Getting started")
    expect(box.locator(".tour-pop-explore")).to_contain_text("Shown only: a page is read")
    expect(box.locator(".tour-pop-page")).to_have_attribute(
        "href", re.compile(r"/walkthrough/00-getting-started\.md$")
    )
    expect(box.locator(".tour-pop-put")).to_be_hidden()
    expect(box.locator(".tour-pop-answer")).to_have_text("Not said yet.")
    expect(page.locator("#journey-rail")).to_be_hidden()
    assert page.evaluate("() => window.fractalViewer.machine") is None
    settled(page)
    story.shows(
        "Tour, in the header, opens a box over the page on the roadmap's first stop",
        "Tour in the header: a box above the windows, on the first stop of the roadmap "
        "nobody has said anything of. That is page 00, and a page is shown only: its "
        "first words, its link, and a word asked on the whole of it. Nothing in the "
        "page beneath has moved.",
        shown=_words(box.locator(".tour-pop-explore").inner_text()),
        blank=CHANGING,
    )

    # 2. The line of Print a part chosen: its first stage, put on.
    lines = httpx.get(f"{url}/tour", timeout=15.0).json()["lines"]
    at = next(i for i, line in enumerate(lines) if line["text"] == MAKE)
    assert lines[at]["group"] == "Making a thing"
    box.locator(".tour-pop-lines").select_option(value=str(at))
    expect(title).to_have_text("Print a part · 1. Choose")
    _put_on(page, "choose")
    expect(did).to_contain_text(
        ["printer_1's Machine opened", "footpedal chosen", "Print a part entered", "1 Choose"]
    )
    assert page.evaluate("() => window.fractalViewer.selectedName") == "footpedal"
    assert windows.state(page, "site")["shown"] is True
    settled(page)
    story.shows(
        "A journey's line chosen puts the page on its first stage",
        "The box's drop-down holds the roadmap's lines under its headings, in its order; "
        "the line of Making a thing that names the journey Print a part, chosen. Its "
        "stages are the stops, and the page is put on the first: printer_1's Machine "
        "opened and the footpedal chosen, as a person would do each, and the journey "
        "entered at Choose, its windows laid out and its rail in the header. The box "
        "says what it did, then what the page said. The stage is there to explore.",
        shown="\n".join(_words(t) for t in did.all_inner_texts()),
        blank=CHANGING,
    )

    # 3. ✓ As shown: kept, and the next stage put on, with what its tests recorded there.
    box.get_by_role("button", name="✓ As shown").click()
    expect(title).to_have_text("Print a part · 2. Shape")
    _put_on(page, "shape")
    assert _answers(url)["journey:make/choose"]["verdict"] == "as shown"
    page.wait_for_function("() => window.apothecaryPanels.state('part-parameters').shown")
    expect(box.locator(".tour-pop-name")).to_have_text(re.compile(r"^Tour · 1 of \d+ said, 0 off$"))
    tries = box.locator(".tour-pop-tries li")
    expect(tries).to_have_text(
        [
            "A size dragged is checked once the slider rests",
            "Apply draws the variant, marked as not saved",
        ]
    )
    expect(tries.first.locator("a")).to_have_attribute(
        "href", re.compile(r"/walkthrough/screenshots/04-02-[a-z0-9-]+\.png$")
    )
    _off_the_buttons(page)
    settled(page)
    story.shows(
        "✓ As shown keeps the word and puts the next stage on, with what to try there",
        "✓ As shown: the server keeps it with the commit it runs, and the box goes to "
        "Shape and puts the page there, Parameters in front. Under what it did are the "
        "steps this stage's tests recorded, each a link to its picture: what to try.",
        shown="\n".join(tries.all_inner_texts()),
        blank=CHANGING,
    )

    # 4. See, chosen in the box: no file is kept, so the piece is sliced, and its path drawn.
    box.locator(".tour-pop-stops button", has_text="4 See").click()
    _put_on(page, "see")
    expect(did).to_contain_text(["footpedal sliced for printer_1, as Slice does"])
    expect(did.last).to_contain_text("path is drawn on printer_1 and framed")
    settled(page)
    story.shows(
        "See is put on from nothing: the piece sliced, its path drawn",
        "See, chosen among the line's stops: the stage draws the chosen file's path, and "
        "no file is kept, so the page does the stage before it -- the footpedal sliced "
        "for printer_1, as Slice does -- and the path is drawn on the machine and framed.",
        shown="\n".join(_words(t) for t in did.all_inner_texts()),
        blank=CHANGING,
    )

    # 5. ✗ Off keeps what is off, and only with it.
    box.get_by_role("button", name="✗ Off").click()
    expect(box.locator(".tour-pop-answer")).to_have_text("Not kept: say what is off.")
    assert _answers(url)["journey:make/see"] is None
    box.locator(".tour-pop-note").fill(NOTE)
    box.get_by_role("button", name="✗ Off").click()
    expect(title).to_have_text("Print a part · 5. Start")
    _put_on(page, "print")
    see = _answers(url)["journey:make/see"]
    assert (see["verdict"], see["note"]) == ("off", NOTE)
    page.wait_for_function("() => window.apothecaryPanels.state('machine').shown")
    story.says(
        "✗ Off keeps what is off, and only with it",
        "✗ Off with the field empty is refused, the box saying what it needs and staying "
        "on the stop; with what is off typed, it is kept, and the box goes to Start and "
        "puts the page there, the Machine and Jobs in front. Nothing is armed.",
        shown=_words(did.last.inner_text()),
    )

    # 6. A view laid out moves the windows, and not the box.
    before = box.bounding_box()
    assert before["y"] >= 0 and before["y"] + before["height"] <= page.viewport_size["height"]
    page.evaluate("() => window.fractalViewer.openView('default')")
    expect(page.locator("#status")).to_contain_text("The page's own layout again")
    expect(box).to_be_visible()
    assert page.evaluate("() => document.querySelector('#tour-pop').matches(':popover-open')")
    assert box.bounding_box() == before
    _off_the_buttons(page)
    settled(page)
    story.shows(
        "A view laid out moves the windows, and not the box",
        "The Default view laid out: every window goes where that view has it, and the "
        "box is where it was, open on the stop it showed. The line's stops wear what "
        "was said of each.",
        shown=_words(box.locator(".tour-pop-name").inner_text()),
        blank=CHANGING,
    )

    # 7. The ring: Panels › Windows › Tour's cells do what its buttons do.
    # (Opened by its key: See framed the machine, so a click on the world lands on a piece.)
    open_from_key(page)
    press(page, "Panels", "Windows", "Tour", "Back")
    expect(title).to_have_text("Print a part · 4. See")
    _put_on(page, "see")
    expect(box.locator(".tour-pop-answer")).to_contain_text(f"✗ Off: {NOTE} -- said ")
    open_from_key(page)
    press(page, "Panels", "Windows", "Tour", "As shown")
    expect(title).to_have_text("Print a part · 5. Start")
    assert _answers(url)["journey:make/see"]["verdict"] == "as shown"  # the latest is its answer
    _put_on(page, "print")
    story.says(
        "Panels › Windows › Tour: its cells are its buttons",
        "The canvas ring's Panels › Windows › Tour: Back goes to See, put on again, where "
        "the box shows what was said of it; As shown says otherwise now, and the latest "
        "word is the stop's. Off, Next, Put here and Its page are cells there too, and "
        "Tour opens and closes the box.",
        shown=_words(box.locator(".tour-pop-title").inner_text()),
    )

    # 8. Reloaded: open again, where it was.
    page.reload()
    expect(box).to_be_visible(timeout=30000)
    expect(title).to_have_text("Print a part · 5. Start")
    story.says(
        "Reloaded, it is open where it was",
        "The page reloaded: the box is open again on the stop it showed, where it was "
        "left; this browser keeps where it was, the server what was said.",
        shown=_words(title.inner_text()),
    )

    # 9. `apothecary tour` reads back what was said.
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(state))
    said = CliRunner().invoke(cli, ["tour"])
    assert said.exit_code == 0, said.output
    out = said.output.splitlines()
    here = out.index(f"  {MAKE} 2 as shown, 0 off, 3 not yet")
    assert out[here - 1] == "Making a thing"
    assert out[here + 1].startswith("    ✓ Choose (") and out[here + 2].startswith("    ✓ See (")
    story.says(
        "`apothecary tour` reads back what was said",
        "At the command line, `apothecary tour`: the roadmap's lines under its headings, "
        "each with how many of its stops are as shown, off and not yet, and each stop "
        "answered with the commit and moment it was said against; `--off` lists only "
        "what is off.",
        shown="\n".join(
            re.sub(r" \([^()]*\)$", " (…)", line) for line in out[here - 1 : here + 3]
        ),
    )
