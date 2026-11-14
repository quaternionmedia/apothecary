"""Every stage of every journey, put on by the tour: the chain the page manages, taken a
stage at a time on the demo as a person starts it. A part designed; made on the printer;
cut on the router; the board a machine runs on built for and heard; a deck's knobs on the
machines; the site brought up through the family's hub; the site watched; and a drawing
photographed into shapes. At each stage the tour's box says what the page did to stand
there, and the page stands there: its window in front, its subject chosen, what the
stage needs made. Walkthrough page 39 is what it writes.

Runs against `python -m apothecary serve --demo` as a subprocess (demo_process.py), the
one place the tour puts a stage on, with the scripted OrcaSlicer its slicer. Nothing is
armed, started or made into a piece by the tour, and the test says so at its end, with
the serial guard's record empty.
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest
import windows
from demo_process import guarded_env, start_demo, stop
from doc_capture import MOMENT
from garage import open_garage
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import expect
from slicer_helpers import write_fake_orcaslicer
from viewer_ready import settled

from apothecary import journeys, tour
from apothecary.demo import DECK, DEVKIT, PRINTER, ROUTER

BOX = "#tour-pop"
COMMIT = r"against (?:[0-9a-f]{8}|an unknown commit)(?: with changes)?"
STOPS = r"(?<=\d/)\d+"
# What changes on every run whatever the page does: the moments, in the box, on the
# status line and in each window that says when it last heard its subject.
CHANGING = (
    (BOX, MOMENT),
    (BOX, COMMIT),
    (BOX, STOPS),
    ("#status", MOMENT),
    *(
        (f".panel[data-panel='{pid}']", MOMENT)
        for pid in ("machine", "machine-status", "machine-sketch", "machine-log", "machine-print", "deck", "working", "procedure", "marks", "jobs")
    ),
)  # fmt: skip
STEP_ON = "() => document.querySelector('#journey-rail [aria-current=step]')?.dataset.step"
VIEWER = "window.fractalViewer"

# The stage of each journey its picture is taken on, and the page's words for the
# journey: what it is given by the one before, and what it hands on.
PICTURED = {
    "design": (
        "numbers",
        "Design a part: its numbers, its text, what is kept of it, whether it is ready",
        "The chain starts at a part. The footpedal is chosen among the garage's pieces; "
        "its editor is opened as Part › Edit opens it, its numbers controls in Parameters; "
        "its SCAD is opened in the editor beside the world; Variants and History hold "
        "what was saved and applied; Readiness and Problems say whether it can be made. "
        "The picture is Numbers. What this journey hands on is a part a machine can make.",
    ),
    "make": (
        "print",
        "Print a part: the part sliced for the printer, its path drawn, the job ready",
        "The part goes to a machine. printer_1's Machine is opened and the footpedal "
        "chosen; Slice's stage is the Machine's Print window with the part under makes; "
        "See needs a file, so the page slices the footpedal for printer_1 where none is "
        "kept, and its path is drawn on the bed; Start's stage is the Machine and Jobs. "
        "The picture is Start: the tour arms nothing and starts nothing.",
    ),
    "cut": (
        "see",
        "Cut a part: its toolpath written for the router, drawn on the table",
        "The same path through another machine. cnc_router's Machine is opened in "
        "printer_1's place and the router_coupon chosen, a part that says how it is "
        "cut; Toolpath's stage is the router's Cut window; See writes the coupon's "
        "toolpath where none is kept and draws it on the table; Needs is the router's "
        "Status, where it says what it needs before it moves; Cut is the Machine and "
        "Jobs. The picture is See.",
    ),
    "board": (
        "hear",
        "Flash a board: its sketch on the Bench, its Flashing, what it says",
        "A machine runs on a board, and a board on firmware. The demo's devkit stands "
        "on its port unpinned, so the page pins it to esp32_blink, as Pin in the piece's "
        "Device section does, and opens its Machine: Pin's stage is Selected, where the "
        "site says which device is which. The Bench is opened on esp32_blink's sketch, "
        "as its ring's Device › Flash sketch does: each build of it with its toolchain. Flash's stage is the "
        "board's Flashing window, Hear's its Sketch and its Log. The picture is Hear. "
        "Compile, upload and Listen are left to the person.",
    ),
    "hands": (
        "knobs",
        "Drive a machine: the Stream Deck, and the printer beside it",
        "Hands on what was made to move. The stream_deck piece is chosen and the Deck "
        "window brought forward: its keys and strip as the server draws them. Knobs "
        "opens printer_1's Machine beside it, the machine the deck has chosen, where its "
        "control is armed before a knob moves anything. The picture is Knobs, the "
        "printer disarmed.",
    ),
    "bring-up": (
        "steps",
        "Start a site: the procedure, the family's members, the hub's audit",
        "The machines one at a time become a site brought up in order. No machine is "
        "in this journey, so the one open is closed. Steps is the Procedure, each step "
        "a member's of the family and fired through the hub on GO; Members is each "
        "member and its door; Audit is the hub's deliveries. The picture is Steps: GO "
        "is a person's.",
    ),
    "watch": (
        "space",
        "Watch a site: the Working space, then one machine's hour",
        "A site that is up is watched. Space is the Working space on the garage; Hour "
        "chooses printer_1 and opens its hour there: its state poll by poll, and where "
        "a camera over it would keep its frames. The picture is Space.",
    ),
    "drawing": (
        "marks",
        "Read a drawing: the whiteboard photographed, squared, read",
        "Last, what is seen becomes parts, and the chain closes. The whiteboard is "
        "chosen on the garage's wall; Picture pins the demo's photograph of it there, "
        "as its ring's Picture › Folder does, squared and laid in front; Shapes finds "
        "its closed strokes; Marks sorts each mark; Models is where an image model is "
        "asked and never trusted; Pieces is where Picture › Make stands each shape up, "
        "which is left to the person: a piece made is a part, to design. The picture "
        "is Marks.",
    ),
}


def _words(text: str) -> str:
    return re.sub(STOPS, "…", re.sub(COMMIT, "against …", re.sub(MOMENT, "…", text)))


@pytest.fixture(scope="module")
def demo(base_url, tmp_path_factory):
    """The demo as a person starts it, its folders temp ones, the serial guard on."""
    folder = tmp_path_factory.mktemp("chain-demo")
    env = guarded_env(folder)
    env["APOTHECARY_ORCASLICER"] = str(write_fake_orcaslicer(folder / "their-orcaslicer"))
    env["FAKE_ORCA_LAYERS"], env["FAKE_ORCA_DWELL"] = "6", "20"
    url, proc = start_demo(folder, env)
    yield {"url": url, "touched": Path(env["APOTHECARY_TEST_SERIAL_GUARD"])}
    stop(proc)


def _put_on(page, step: str) -> None:
    """The box done putting the page on ``step``, and the rail there."""
    expect(page.locator(BOX)).not_to_have_class(re.compile(r"\bbusy\b"), timeout=90000)
    try:
        page.wait_for_function(f"(s) => ({STEP_ON})() === s", arg=step, timeout=15000)
    except PlaywrightTimeout:
        said = page.locator(f"{BOX} .tour-pop-did li").all_text_contents()
        pytest.fail(f"the page was not put on {step}: the box says {said}")


def _shown(page, pid: str) -> None:
    page.wait_for_function(
        "(id) => window.apothecaryPanels.state(id)?.shown", arg=pid, timeout=15000
    )


def _says(page, pid: str, words) -> None:
    expect(windows.panel(page, pid)).to_contain_text(words, timeout=20000)


def _machine_port(page) -> str | None:
    return page.evaluate(f"() => {VIEWER}.machine ? {VIEWER}.machine.port : null")


def _drawn(page) -> dict:
    return page.evaluate("() => window.apothecaryPictures.drawnAt('whiteboard')") or {}


# What stands at each stage once it is put on, beyond its first window in front and the
# rail on it: (journey, stage) -> a check of the page.
def _selected(name):
    return lambda page: page.wait_for_function(
        f"(n) => {VIEWER}.selectedName === n", arg=name, timeout=10000
    )


def _on(port):
    return lambda page: page.wait_for_function(
        f"(p) => {VIEWER}.machine && {VIEWER}.machine.port === p", arg=port, timeout=15000
    )


def _path_drawn_on(machine):
    return lambda page: expect(page.locator("#status")).to_contain_text(
        f"path is drawn on {machine} and framed", timeout=30000
    )


STANDS = {
    ("design", "choose"): _selected("footpedal"),
    ("design", "numbers"): lambda page: expect(
        windows.panel(page, "part-parameters").locator("input").first
    ).to_be_visible(),
    ("design", "text"): lambda page: _says(page, "part-scad", re.compile(r"\S")),
    ("design", "kept"): lambda page: _shown(page, "part-variants"),
    ("design", "ready"): lambda page: _shown(page, "part-readiness"),
    ("make", "choose"): _on(PRINTER),
    ("make", "shape"): lambda page: _shown(page, "part-parameters"),
    ("make", "slice"): lambda page: _says(page, "machine-print", "footpedal"),
    ("make", "see"): _path_drawn_on("printer_1"),
    ("make", "print"): lambda page: _shown(page, "machine"),
    ("cut", "choose"): _on(ROUTER),
    ("cut", "toolpath"): lambda page: _says(page, "machine-print", "Toolpath"),
    ("cut", "see"): _path_drawn_on("cnc_router"),
    ("cut", "needs"): lambda page: _says(page, "machine-status", "Pins on"),
    ("cut", "cut"): lambda page: _shown(page, "machine"),
    ("board", "pin"): lambda page: (
        _on(DEVKIT)(page),
        _selected("esp32_blink")(page),
        _says(page, "selected", DEVKIT),
    ),
    ("board", "bench"): lambda page: _says(page, "bench", "esp32_blink"),
    ("board", "flash"): lambda page: _shown(page, "machine-flashing"),
    ("board", "hear"): lambda page: _says(page, "machine-sketch", "should run"),
    ("hands", "deck"): lambda page: (_selected("stream_deck")(page), _says(page, "deck", DECK)),
    ("hands", "knobs"): lambda page: (_on(PRINTER)(page), _says(page, "machine", "Control")),
    ("bring-up", "steps"): lambda page: (
        page.wait_for_function(f"() => {VIEWER}.machine === null"),
        _says(page, "procedure", "bring-up"),
    ),
    ("bring-up", "members"): lambda page: _says(page, "family-members", "board"),
    ("bring-up", "audit"): lambda page: _shown(page, "family-deliveries"),
    ("watch", "space"): lambda page: _says(page, "working", "Choose a machine"),
    ("watch", "hour"): lambda page: (
        _selected("printer_1")(page),
        _says(page, "working", "printer_1"),
    ),
    ("drawing", "board"): _selected("whiteboard"),
    ("drawing", "picture"): lambda page: page.wait_for_function(
        "() => (window.apothecaryPictures.drawnAt('whiteboard') || {}).squared", timeout=30000
    ),
    ("drawing", "shapes"): lambda page: page.wait_for_function(
        "() => (window.apothecaryPictures.drawnAt('whiteboard') || {}).shapes?.length === 3",
        timeout=30000,
    ),
    ("drawing", "marks"): lambda page: _says(page, "marks", "whiteboard.png · whiteboard"),
    ("drawing", "models"): lambda page: _says(page, "models", "qmcp"),
    ("drawing", "pieces"): _selected("whiteboard"),
}
# What the box says the page did, somewhere among a journey's stages, the first time round.
DID = {
    "design": [
        "footpedal chosen",
        "footpedal framed in the world, as f does",
        "footpedal's editor opened, as Part › Edit does",
        "footpedal's SCAD opened in its window, as Part › SCAD does",
    ],
    "make": ["printer_1's Machine opened", "footpedal sliced for printer_1, as Slice does"],
    "cut": [
        "cnc_router's Machine opened",
        "router_coupon chosen",
        "router_coupon's toolpath written for cnc_router, as Toolpath does",
    ],
    "board": [
        f"{DEVKIT} pinned to esp32_blink, as Pin in its Device section does",
        "esp32_blink's Machine opened",
        "the Bench opened on esp32_blink@arduino",
    ],
    "hands": ["stream_deck chosen", "printer_1's Machine opened"],
    "bring-up": ["printer_1's Machine closed: Start a site has no machine in it"],
    "watch": [
        "the Working space opened: the Working space of garage",
        "printer_1 framed in the world, as f does",
        "the Working space opened: printer_1's hour in the Working space",
    ],
    "drawing": [
        "whiteboard chosen",
        "whiteboard.png pinned at whiteboard, as its Picture › Folder does",
        "3 shapes found at whiteboard, as its Picture › Find shapes › outline does",
    ],
}


@pytest.mark.e2e
def test_every_stage_has_what_stands_there_written_down():
    """This module's own tables name every stage of every journey, and a pictured one each."""
    stages = {(j.id, s.id) for j in journeys.JOURNEYS for s in j.steps}
    assert set(STANDS) == stages
    assert set(PICTURED) == set(DID) == {j.id for j in journeys.JOURNEYS}
    for journey in journeys.JOURNEYS:
        assert PICTURED[journey.id][0] in {s.id for s in journey.steps}


@pytest.mark.e2e
def test_the_tour_puts_the_page_on_every_stage_of_the_chain(page, demo, walkthrough):
    url = demo["url"]
    story = walkthrough(
        ordinal="39",
        slug="the-chain-a-stage-at-a-time",
        title="The chain, a stage at a time",
        intro=(
            "Every journey the page has, in the order of the chain it manages, each put "
            "on a stage at a time by the [tour](34-the-tour.md): a part designed, made "
            "on the printer, cut on the router; the board a machine runs on; a deck's "
            "knobs on the machines; the site brought up and watched; and a drawing "
            "photographed into shapes, which stand up as parts to design. Each journey "
            "hands the next what it made. Under each is what the tour's box said the "
            "page did to stand on each stage, then what the page said of it. "
            "[docs/tour.md](../docs/tour.md) is the reference, and "
            "[docs/ROADMAP.md](../docs/ROADMAP.md) the order."
        ),
        runtime=(
            "It drives a real browser against `apothecary serve --demo`, started as a "
            "person starts it: a simulated printer, router, devkit and Stream Deck, the "
            "scripted firmware tools, and a script that answers as OrcaSlicer's command "
            "line does. Every Python process of the demo refuses a real serial port."
        ),
        does_not_show=[
            "**Anything armed, started, sent or made.** A stage is where a person does "
            "those: ▶ Print, ▶ Cut, Upload, GO, a knob turned, Picture › Make. Each is "
            "its own page's, named at its stage in the tour's box.",
            "**A server that is not the demo**, where the tour puts nothing on.",
            "**A camera's picture.** A browser's camera cannot be put on a stage; pages "
            "01 to 03 are read.",
            "**What changes on every run.** Moments and the commit the server runs are "
            "blanked in the pictures and left out of the words.",
        ],
        browser_suite_only=True,
    )
    box = page.locator(BOX)
    did = box.locator(".tour-pop-did li")
    title = box.locator(".tour-pop-title")
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    open_garage(page, url)
    page.locator("#tour-pop-open").click()
    expect(box).to_be_visible()
    lines = httpx.get(f"{url}/tour", timeout=15.0).json()["lines"]

    for journey in journeys.JOURNEYS:
        at = next(
            i
            for i, line in enumerate(lines)
            if line["stops"]
            and line["stops"][0]["id"] == tour.stage_id(journey.id, journey.steps[0].id)
        )
        said_of = []
        done = []
        for n, step in enumerate(journey.steps):
            # The journey's line chosen puts its first stage on; Next › each one after.
            if n == 0:
                box.locator(".tour-pop-lines").select_option(value=str(at))
            else:
                box.get_by_role("button", name="Next", exact=True).click()
            expect(title).to_have_text(f"{journey.name} · {n + 1}. {step.label}")
            _put_on(page, step.id)
            expect(box.locator(".tour-pop-did.refused")).to_have_count(0)
            _shown(page, step.forward[0])
            STANDS[journey.id, step.id](page)
            said = [_words(t) for t in did.all_text_contents()]
            done += said[:-1]
            said_of.append(
                f"{n + 1} {step.label}: "
                + ("; ".join(said[:-1]) or "nothing more to do")
                + f"\n    {said[-1]}"
            )
        for expected in DID[journey.id]:
            assert any(expected in d for d in done), (journey.id, expected, done)

        # Back on the stage its picture is of: chosen among the line's stops, and put on
        # again with nothing left to do but what its windows need.
        stage, heading, words = PICTURED[journey.id]
        label = next(s.label for s in journey.steps if s.id == stage)
        box.locator(".tour-pop-stops button", has_text=label).click()
        _put_on(page, stage)
        STANDS[journey.id, stage](page)
        page.mouse.move(640, 700)
        settled(page)
        story.shows(heading, words, shown="\n".join(said_of), blank=CHANGING)

    # Nothing armed, nothing started, no piece made, no answer given, no real port touched.
    with httpx.Client(base_url=url, timeout=15.0) as http:
        assert http.get("/firmware/printers/armed").json() == {"armed": {}}
        assert (
            http.get("/firmware/printers/print", params={"port": PRINTER}).json()["running"]
            is False
        )
        answered = [
            s for line in http.get("/tour").json()["lines"] for s in line["stops"] if s["answer"]
        ]
        assert answered == []
    assert _drawn(page).get("made") == {}
    assert errors == []
    assert not demo["touched"].exists() or demo["touched"].read_text() == ""
