"""The tour, as a person takes it: Tour in the header opens a box over the page, on the
first stage with no word on this build, a word said of an earlier one shown as that; the
journey Print a part chosen takes the page to its first stage -- the machine opened, the
piece chosen, the stage entered; ✓ Works keeps a person's word, under the name asked of
them once, and takes the page to the next stage, with what there is to try there; the See stage slices the piece where no file is kept, and its path is drawn;
✗ Off keeps what is off, and only with it; a view laid out moves the windows and not the
box; the ring's Panels › Windows › Tour cells do what its buttons do; a reload opens it
where it was; a machine with no board connected is taken as the site plans it; a stage
that needs what only a person brings is entered, the box saying what it needs; and the
server gives back every word kept. Walkthrough page 34 is what it writes.

Runs against a server of its own, with the simulated printer pinned to printer_1's
mainboard, the router's controller not pinned, and the scripted OrcaSlicer its slicer;
its state folder is this module's, so the feedback it keeps is its own, beside one word
left there as said of an earlier build.
"""

from __future__ import annotations

import json
import re

import httpx
import pytest
import windows
from boards import BOARD, DWELL, LAYERS, PRINTER
from doc_capture import MOMENT
from firmware_helpers import write_fake_arduino_cli
from garage import open_garage
from playwright.sync_api import expect
from rings import open_from_key, press
from simulated_process import still_folder
from slicer_helpers import write_fake_orcaslicer
from viewer_ready import settled

BOX = "#tour-pop"
NOTE = "the job's row is cut off at the window's foot"
BY = "Ada"
# A word kept before the server ran this commit.
EARLIER = {
    "stage": "design/choose",
    "verdict": "works",
    "note": "",
    "by": "Grace",
    "at": "2026-11-01T10:00:00+00:00",
    "commit": "0000000",
    "changed": False,
}
PLANNED = "cnc_router's Machine opened with no board connected: what it makes is planned there"
NO_BOARD = (
    "esp32_blink's board is pinned to a board, but not connected: connect it, or ⟳ Rescan in "
    "its Device section"
)
# What changes on every run whatever the page does: the moments; and what changes with
# any stage added to a journey, how many the tour holds.
STAGES = r"(?<=\d/)\d+"
CHANGING = ((BOX, MOMENT), (BOX, STAGES), ("#status", MOMENT))
STEP_ON = "() => document.querySelector('#journey-rail [aria-current=step]')?.dataset.step"


def _words(text: str) -> str:
    """What the box says, its moments and the count of stages left out, as its pictures
    blank them."""
    return re.sub(STAGES, "…", re.sub(MOMENT, "…", text))


@pytest.fixture(scope="module")
def state():
    return still_folder("tour-state")


@pytest.fixture(scope="module")
def url(start_server, state):
    # Every folder the Bench's card names is at a name of its own: nothing of a pytest temp's
    # run number is in a picture.
    kit = still_folder("tour-kit")
    orca = write_fake_orcaslicer(kit / "orca")
    (state / "tour").mkdir()
    (state / "tour" / "feedback.jsonl").write_text(json.dumps(EARLIER) + "\n", encoding="utf-8")
    url = start_server(
        {
            "APOTHECARY_STATE_DIR": str(state),
            "APOTHECARY_TOOLS_DIR": str(kit / "tools"),
            "APOTHECARY_CACHE_DIR": str(kit / "cache"),
            "ARDUINO_CLI": str(write_fake_arduino_cli(kit / "arduino-cli")),
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


def _feedback(url: str) -> dict:
    journeys = httpx.get(f"{url}/tour", timeout=15.0).json()["journeys"]
    return {s["id"]: s["feedback"] for j in journeys for s in j["stages"]}


def _taken_to(page, step: str) -> None:
    """The box done taking the page to ``step``, and the rail there."""
    expect(page.locator(BOX)).not_to_have_class(re.compile(r"\bbusy\b"), timeout=60000)
    page.wait_for_function(f"(s) => ({STEP_ON})() === s", arg=step, timeout=15000)


def _off_the_buttons(page) -> None:
    """The mouse on the status line, so no button pressed last is drawn hovered in a
    picture: whether it is depends on when the picture is taken."""
    page.mouse.move(640, 700)


@pytest.mark.e2e
def test_the_tour_takes_the_page_to_each_stage_and_keeps_a_person_s_word(
    page, url, state, walkthrough
):
    story = walkthrough(
        ordinal="34",
        slug="the-tour",
        title="The tour",
        intro=(
            "The page's journeys a stage at a time, in a box over the page: going to a "
            "stage takes the page there, a person explores it where it stands, and one "
            "word is kept on the stage -- it works, or it is off, with what is off. The "
            "box says nothing of its own: a stage's words are the ones its journey's "
            "rail shows. [docs/tour.md](../docs/tour.md) is the reference."
        ),
        runtime=(
            "It drives a real browser against a real server of its own, its printer a "
            "simulation pinned to printer_1's mainboard, its router's controller not "
            "pinned, and its slicer a script that answers as OrcaSlicer's command line "
            "does. Its state folder is this test's, so the feedback it keeps is its own."
        ),
        does_not_show=[
            "**A stage armed or started.** Start's stage brings the Print window and Jobs "
            "forward; arming control and starting a print are a person's.",
            "**What changes on every run.** Moments are blanked in the pictures and "
            "left out of the words, and so is how many stages the tour holds, which any "
            "stage added to a journey changes.",
        ],
        browser_suite_only=True,
    )
    box = page.locator(BOX)
    did = box.locator(".tour-pop-did li")
    title = box.locator(".tour-pop-title")
    open_garage(page, url)

    # 1. Tour, in the header: the box over the page, on the first stage with no word on
    # this build, the page as it was. What was said of an earlier build is shown as that.
    expect(box).to_be_hidden()
    page.locator("#tour-pop-open").click()
    expect(box).to_be_visible()
    assert page.evaluate("() => document.querySelector('#tour-pop').matches(':popover-open')")
    expect(box.locator(".tour-pop-name")).to_have_text(re.compile(r"^0/\d+$"))
    expect(title).to_have_text("Design a part · 1. Choose")
    expect(box.locator(".tour-pop-put")).to_be_enabled()
    expect(box.locator(".tour-pop-feedback")).to_contain_text("✓ Works -- said by Grace ")
    expect(box.locator(".tour-pop-feedback")).to_contain_text(
        "of an earlier build (0000000): this stage waits for a word again"
    )
    expect(box.locator(".tour-pop-stages button").first).to_have_class(re.compile(r"\bearlier\b"))
    expect(page.locator("#journey-rail")).to_be_hidden()
    assert page.evaluate("() => window.fractalViewer.machine") is None
    settled(page)
    story.shows(
        "Tour, in the header, opens a box over the page on the first stage",
        "Tour in the header: a box above the windows, on the first stage with no word "
        "on this build, which is where the journeys begin: Design a part, at Choose. "
        "Its head names the stage and how many have a word on them, its drop-down holds "
        "the journeys in their order, and under it are this journey's stages. A word "
        "was said of this stage while the server ran an earlier commit: it is shown, as "
        "that, and the stage waits for a word again. Nothing in the page beneath has "
        "moved: ↻ beside the stage's words takes the page there.",
        shown=_words(box.locator(".tour-pop-feedback").inner_text()),
        blank=CHANGING,
    )

    # 2. Print a part chosen: the page taken to its first stage.
    journeys = httpx.get(f"{url}/tour", timeout=15.0).json()["journeys"]
    at = next(i for i, j in enumerate(journeys) if j["name"] == "Print a part")
    box.locator(".tour-pop-journeys").select_option(value=str(at))
    expect(title).to_have_text("Print a part · 1. Choose")
    _taken_to(page, "choose")
    # What the page did is folded under one line, and stays open once a person opens it.
    expect(did.first).to_be_hidden()
    box.locator(".tour-pop-more summary").click()
    expect(did.first).to_be_visible()
    expect(did).to_contain_text(
        ["printer_1's Machine opened", "footpedal chosen", "Print a part entered", "1 Choose"]
    )
    assert page.evaluate("() => window.fractalViewer.selectedName") == "footpedal"
    assert windows.state(page, "site")["shown"] is True
    settled(page)
    story.shows(
        "A journey chosen takes the page to its first stage",
        "Print a part, chosen in the box's drop-down. The page is taken to its first "
        "stage: printer_1's Machine opened and the footpedal chosen, as a person would "
        "do each, and the journey entered at Choose, its windows laid out and its rail "
        "in the header. The box keeps what the page did, then what the page said, "
        "folded under one line, opened here. The stage is there to explore.",
        shown="\n".join(_words(t) for t in did.all_inner_texts()),
        blank=CHANGING,
    )

    # 3. ✓ Works: kept under a name, asked once, and the page taken to the next stage,
    # with what to try there.
    box.get_by_role("button", name="✓ Works").click()
    expect(box.locator(".tour-pop-feedback")).to_have_text(
        "Not kept: say who you are, once, in the field below."
    )
    expect(box.locator(".tour-pop-by")).to_be_focused()
    assert _feedback(url)["make/choose"] is None
    box.locator(".tour-pop-by").fill(BY)
    box.get_by_role("button", name="✓ Works").click()
    expect(title).to_have_text("Print a part · 2. Shape")
    _taken_to(page, "shape")
    said = _feedback(url)["make/choose"]
    assert (said["verdict"], said["by"], said["current"]) == ("works", BY, True)
    page.wait_for_function("() => window.apothecaryPanels.state('part-parameters').shown")
    expect(box.locator(".tour-pop-name")).to_have_text(re.compile(r"^1/\d+$"))
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
        "✓ Works keeps the word and takes the page to the next stage, with what to try",
        "✓ Works is kept under a name: with none given the box asks for it, once, and "
        "this browser keeps it. Named, the server keeps the word, and the box goes to "
        "Shape and takes the page there, Parameters in front. Folded under one line "
        "with what the page did is "
        "what there is to try on this stage, each a link to a picture of it in the "
        "walkthrough.",
        shown="\n".join(tries.all_inner_texts()),
        blank=CHANGING,
    )

    # 4. See, chosen in the box: no file is kept, so the piece is sliced, and its path drawn.
    box.locator(".tour-pop-stages button", has_text="4 See").click()
    _taken_to(page, "see")
    expect(did).to_contain_text(["footpedal sliced for printer_1, as Slice does"])
    expect(did.last).to_contain_text("path is drawn on printer_1 and framed")
    settled(page)
    story.shows(
        "See is reached from nothing: the piece sliced, its path drawn",
        "See, chosen among the journey's stages: the stage draws the chosen file's "
        "path, and no file is kept, so the page does the stage before it -- the "
        "footpedal sliced for printer_1, as Slice does -- and the path is drawn on the "
        "machine and framed.",
        shown="\n".join(_words(t) for t in did.all_inner_texts()),
        blank=CHANGING,
    )

    # 5. ✗ Off keeps what is off, and only with it.
    box.get_by_role("button", name="✗ Off").click()
    expect(box.locator(".tour-pop-feedback")).to_have_text("Not kept: say what is off.")
    assert _feedback(url)["make/see"] is None
    box.locator(".tour-pop-note").fill(NOTE)
    box.get_by_role("button", name="✗ Off").click()
    expect(title).to_have_text("Print a part · 5. Start")
    _taken_to(page, "print")
    see = _feedback(url)["make/see"]
    assert (see["verdict"], see["note"]) == ("off", NOTE)
    page.wait_for_function("() => window.apothecaryPanels.state('machine-print').shown")
    story.says(
        "✗ Off keeps what is off, and only with it",
        "✗ Off with the field empty is refused, the box saying what it needs and staying "
        "on the stage; with what is off typed, it is kept, and the box goes to Start and "
        "takes the page there, the Print window, where ▶ Print is, and Jobs in front. Nothing is armed.",
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
        "box is where it was, open on the stage it showed. The journey's stages wear "
        "what was said of each.",
        shown=_words(box.locator(".tour-pop-name").inner_text()),
        blank=CHANGING,
    )

    # 7. The ring: Panels › Windows › Tour's cells do what its buttons do.
    # (Opened by its key: See framed the machine, so a click on the world lands on a piece.)
    open_from_key(page)
    press(page, "Panels", "Windows", "Tour", "Back")
    expect(title).to_have_text("Print a part · 4. See")
    _taken_to(page, "see")
    expect(box.locator(".tour-pop-feedback")).to_contain_text(f"✗ Off: {NOTE} -- said by {BY} ")
    open_from_key(page)
    press(page, "Panels", "Windows", "Tour", "Works")
    expect(title).to_have_text("Print a part · 5. Start")
    assert _feedback(url)["make/see"]["verdict"] == "works"  # the latest is its feedback
    _taken_to(page, "print")
    story.says(
        "Panels › Windows › Tour: its cells are its buttons",
        "The canvas ring's Panels › Windows › Tour: Back goes to See, the page taken "
        "there again, where the box shows what was said of it; Works says otherwise "
        "now, and the latest word is the stage's. Off, Next, Take me here, Its page and "
        "Who, the name's field, are cells there too, and Tour opens and closes the box.",
        shown=_words(box.locator(".tour-pop-title").inner_text()),
    )

    # 8. Reloaded: open again, where it was.
    page.reload()
    expect(box).to_be_visible(timeout=30000)
    expect(title).to_have_text("Print a part · 5. Start")
    # And the page is taken to that stage again, not left bare under a box that says
    # where it was: its machine open, its part chosen.
    page.wait_for_function(
        "() => window.fractalViewer.machine?.handle?.kind() && window.fractalViewer.selectedName === 'footpedal'",
        timeout=60000,
    )
    expect(box).not_to_have_class(re.compile(r"\bbusy\b"), timeout=60000)
    story.says(
        "Reloaded, it is open where it was",
        "The page reloaded: the box is open again on the stage it showed, where it was "
        "left; this browser keeps where it was, the server what was said.",
        shown=_words(title.inner_text()),
    )

    # 9. A machine whose board is not connected: its Machine as the site plans it.
    at = next(i for i, j in enumerate(journeys) if j["name"] == "Cut a part")
    box.locator(".tour-pop-journeys").select_option(value=str(at))
    expect(title).to_have_text("Cut a part · 1. Choose")
    _taken_to(page, "choose")
    expect(did).to_contain_text([PLANNED, "router_coupon chosen", "Cut a part entered"])
    expect(box.locator(".tour-pop-needs")).to_be_empty()
    assert page.evaluate("() => window.fractalViewer.machine.plan") is True
    # The one file kept is the printer's slice: listed in the router's Cut, and not chosen.
    pick = page.locator(".panel[data-panel='machine-print'] #print-pick")
    expect(pick.locator("option").first).to_have_text("— none kept for a router —")
    expect(pick).to_have_value("")
    story.says(
        "A machine with no board connected is taken as the site plans it",
        "Cut a part, chosen: its stages are on the router's Machine, and this server's "
        "router has no board connected. Its Machine opens all the same, as its badge "
        "opens it: what it makes is planned there, its toolpath written and drawn, "
        "and ▶ Cut is its board's once it is connected.",
        shown="\n".join(_words(t) for t in did.all_inner_texts()),
    )

    # 10. A stage that needs what only a person brings: entered, and what it needs said.
    at = next(i for i, j in enumerate(journeys) if j["name"] == "Flash a board")
    box.locator(".tour-pop-journeys").select_option(value=str(at))
    expect(title).to_have_text("Flash a board · 1. Pin")
    _taken_to(page, "pin")
    expect(box.locator(".tour-pop-more summary")).to_have_text("This stage needs something first")
    expect(box.locator(".tour-pop-needs")).to_have_text(NO_BOARD)
    expect(did).to_contain_text(["Flash a board entered"])
    assert windows.state(page, "selected")["shown"] is True
    # Nothing was pinned for the person.
    assert page.evaluate(
        "() => window.fractalViewer.bindingFor('esp32_blink').row?.binding_source !== 'manual'"
    )
    _off_the_buttons(page)
    settled(page)
    story.shows(
        "A stage that needs what only a person brings says what it needs",
        "Flash a board, chosen: its first stage is the board on its port pinned to its "
        "piece, and no board of esp32_blink's is connected. Which device is which is a "
        "person's to say, so nothing is pinned for them: the page leaves the rest, "
        "enters the stage all the same, so Selected is in front, where a board is "
        "pinned, and the box opens on what the stage needs. ↻ takes the page the rest "
        "of the way once it is there.",
        shown=_words(box.locator(".tour-pop-needs").inner_text()),
        blank=CHANGING,
    )

    # 11. Every word kept is the server's to give back, oldest first.
    kept = httpx.get(f"{url}/tour/feedback", timeout=15.0).json()["feedback"]
    assert [(r["stage"], r["verdict"], r["note"], r["by"]) for r in kept] == [
        ("design/choose", "works", "", "Grace"),
        ("make/choose", "works", "", BY),
        ("make/see", "off", NOTE, BY),
        ("make/see", "works", "", BY),
    ]
    assert all(r["at"] and "commit" in r and "changed" in r for r in kept)
    assert (state / "tour" / "feedback.jsonl").read_text(encoding="utf-8").count("\n") == 4
    story.says(
        "Every word kept is given back, oldest first",
        "`GET /tour/feedback`: every word said, none rewritten, each with its stage, "
        "who said it, the moment, and the commit the server ran. The latest for a "
        "stage is its feedback; the rest is there for whoever reviews what was found.",
        shown="\n".join(
            f"{r['stage']}\t{r['verdict']}\t{r['by']}" + (f"\t{r['note']}" if r["note"] else "")
            for r in kept
        ),
    )
