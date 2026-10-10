"""A picture to a print, round twice through the page: the fourth loop of the loops
plan (docs/plans/ui-flows-2026-10-08.md), held end to end.

A camera added above the bench and told which of this browser's cameras it is; a
picture taken that lies on the bench; its shapes found; one made a piece; the piece
adjusted in Selected; sliced for printer_1 by Slice in its Machine's Print from here,
the G-code chosen there; a print job for it started on printer_1; the job watched in
printer_1's Machine to its end. Then round again: the camera turned by its turn
ring, a second picture taken with P, a second piece made and adjusted, sliced by
Slice on its own ring this time, and a second print, started from the ring's Send
file, while the Machine stays open in the rail. Every step
is taken through the page's own controls and ring cells, and what is asserted is
what a person sees: the status line, Contents, the camera's section, the Machine's
Print from here card and Site's Jobs. Each step's words name the next step.

This module is a walkthrough page too: `walkthrough/13-a-picture-to-a-print.md` is
what it writes, its pictures taken as it goes, so the page shows the loop as it is.
It is the browser suite's alone, unmarked `walkthrough`, so `apothecary test run`
stays quick; CI's browser shards write it and check it against what is committed.

The browser is Chromium with its fake camera playing tests/e2e/test_the_loop.py's
drawing (a dark rectangle, disc and triangle on a light ground), so the plain finder
has shapes to find in every frame and no real camera is ever opened. The server is
this module's own: the simulated printer, idle, answers on ``/dev/ttyFAKE1``,
identified and pinned to printer_1's mainboard as the bench's real board is, and
its picture folder holds only what this run puts there. No real serial port is
opened. The slicer is the scripted OrcaSlicer of the unit tests
(tests/slicer_helpers.py), named by the server's APOTHECARY_ORCASLICER: it answers
as OrcaSlicer's command line does and writes a short file of layers, each move
followed by a dwell the simulated printer takes in real time, so a print is seen
running before it ends.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import expect
from slicer_helpers import write_fake_orcaslicer
from test_camera import _drag
from test_the_loop import _labels, _open_garage, _press, _ring_on, _said, _status, _y4m
from viewer_ready import settled

PRINTER = "/dev/ttyFAKE1"
BOARD = "printer_1.frame_system.mainboard"
MACHINE = ".panel[data-panel='machine']"


# The scripted slicer's layers, each move followed by a dwell of this many ms: a few
# seconds of printing on the simulated printer, seen running before it ends.
LAYERS, DWELL = "15", "60"


def _kept(page, url: str, piece: str) -> dict:
    """The newest slice of ``piece`` (GET /slicer/slices) and the file it kept, as the
    Print card lists it: its id, its name and the lines a print of it streams."""
    record = next(
        r for r in page.request.get(f"{url}/slicer/slices").json() if r["made"]["name"] == piece
    )
    (kept,) = [
        f
        for f in page.request.get(f"{url}/firmware/printers/prints").json()
        if f["id"] == record["file_id"]
    ]
    return {"record": record, **kept}


# The widths the page is laid out for: the rail beside the world, and the narrower.
WIDTHS = ((1280, 800), (1024, 768))

# Print from here, read as a person reads it: its blocks one under the other, the
# controls of each row side by side, and nothing poking out of the card -- what scrolls
# (the slice's values, the task log, the history) keeps its own overflow. What overlaps
# or pokes out, named.
CROWDED = """(sel) => {
    const card = document.querySelector(sel);
    const shown = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
    const over = (a, b) => a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1;
    const name = (el) => el.id || el.className || el.tagName;
    const bad = [];
    const blocks = [...card.children].filter(shown);
    for (let i = 0; i < blocks.length; i++) for (let j = i + 1; j < blocks.length; j++)
        if (over(blocks[i].getBoundingClientRect(), blocks[j].getBoundingClientRect())) bad.push(`${name(blocks[i])} over ${name(blocks[j])}`);
    for (const row of card.querySelectorAll('.row')) {
        const kids = [...row.children].filter(shown);
        for (let i = 0; i < kids.length; i++) for (let j = i + 1; j < kids.length; j++)
            if (over(kids[i].getBoundingClientRect(), kids[j].getBoundingClientRect())) bad.push(`${name(kids[i])} over ${name(kids[j])}`);
    }
    const edge = card.getBoundingClientRect().right;
    const scrolled = (el) => el.closest('.slice-settings, .task-log, #print-history');
    for (const el of card.querySelectorAll('*'))
        if (shown(el) && !scrolled(el) && el.getBoundingClientRect().right > edge + 1) bad.push(`${name(el)} past the card's edge`);
    return bad;
}"""


@pytest.fixture(scope="module")
def shots(tmp_path_factory):
    """Where the Print card is pictured at each width, under pytest's temp folder."""
    folder = tmp_path_factory.getbasetemp() / "slice-shots"
    folder.mkdir(exist_ok=True)
    return folder


@pytest.fixture(scope="module")
def url(base_url, start_server, tmp_path_factory):
    """This module's own server: the simulated printer idle on ``/dev/ttyFAKE1``,
    identified (M115) and pinned to printer_1's mainboard, and the scripted OrcaSlicer
    its slicer. ``base_url`` is asked for only so that with no server to run against
    this is skipped, as every browser test is."""
    orca = write_fake_orcaslicer(tmp_path_factory.mktemp("orca"))
    url = start_server(
        {
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


# Chromium names a fake camera by the file it plays, and the page shows that name
# (the status line, the camera's card): a path that is the same on every run keeps
# the walkthrough the same when nothing else changed.
DRAWING = Path(tempfile.gettempdir()) / "apothecary-e2e" / "three-shapes.y4m"


@pytest.fixture(scope="module")
def _drawing_camera_browser(browser_type):
    """Chromium with its fake camera playing test_the_loop.py's drawing, from ``DRAWING``.
    Written whole and moved into place, so a run beside this one never reads half."""
    DRAWING.parent.mkdir(parents=True, exist_ok=True)
    fd, part = tempfile.mkstemp(dir=DRAWING.parent, suffix=".y4m")
    os.close(fd)
    _y4m(part)
    os.replace(part, DRAWING)
    browser = browser_type.launch(
        args=[
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-stream",
            f"--use-file-for-fake-video-capture={DRAWING}",
        ]
    )
    yield browser
    browser.close()


@pytest.fixture
def page(_drawing_camera_browser, url):
    """A page on this module's server whose camera sees the drawing, allowed."""
    context = _drawing_camera_browser.new_context(
        viewport={"width": 1280, "height": 800}, base_url=url
    )
    context.grant_permissions(["camera"], origin=url)
    yield context.new_page()
    context.close()


# The view brought closer to the bench, from where it looked: the turn of a person's
# wheel, so the pictures show the bench and what stands on it.
CLOSER = """([x, y, z, distance]) => {
    const v = window.fractalViewer;
    const from = v.camera.position.clone().sub(v.orbitControls.target).normalize();
    v.orbitControls.target.set(x, z, y);
    v.camera.position.copy(v.orbitControls.target).addScaledVector(from, distance);
    v.orbitControls.update();
}"""


def _closer_to_the_bench(page) -> None:
    """The bench's top is x 0..1800, y 0..600 at z 780 in the garage's frame."""
    page.evaluate(CLOSER, [900, 300, 780, 2600])
    settled(page)


def _attached(page, url: str) -> dict:
    return page.request.get(f"{url}/sites/garage/attached").json()


def _row(page, path: str):
    return page.locator(f"#contents-list .contents-item[data-path='{path}']")


def _make(page, url: str, word: str) -> str:
    """Picture › Make on the bench's ring, the found shape whose label starts with
    ``word``; the piece it made, as Contents lists it."""
    before = set(_attached(page, url)["made"])
    _ring_on(page, "workbench")
    _press(page, "Picture", "Make")
    labels = _labels(page)
    assert labels[0] == "Make all", labels
    label = next((got for got in labels[1:] if got.startswith(word)), labels[1])
    _press(page, label)
    page.wait_for_function(
        "(n) => Object.keys(window.apothecaryPictures.attached().made || {}).length === n",
        arg=len(before) + 1,
        timeout=10000,
    )
    (piece,) = set(_attached(page, url)["made"]) - before
    expect(_row(page, piece)).to_be_visible(timeout=10000)
    return piece


def _adjust(page, piece: str, field: str, value: float) -> float:
    """Part › Edit on the piece's ring, one slider moved, Apply; the value applied."""
    _ring_on(page, piece)
    _press(page, "Part", "Edit")
    _said(page, f"Editing {piece}: its parameters are in Selected")
    slider = page.locator(f"#part-params .param[data-field='{field}'] input[type=range]")
    expect(slider).to_be_visible(timeout=10000)
    got = slider.evaluate(
        "(el, v) => { el.value = v; el.dispatchEvent(new Event('input')); return Number(el.value); }",
        value,
    )
    expect(page.locator("#stage-summary")).to_contain_text("1 change staged, valid", timeout=10000)
    page.locator("#apply-btn").click()
    _said(page, f"{piece} rebuilt")
    return got


# What differs on every run whatever the page does, blanked in the pictures: a kept
# picture's name (the time it was taken, to the millisecond) where the place's card, a
# made piece's facts, the editor's found sizes and a host's views say it; when a print
# started and ended, and how long it took; and the temperature chart's count of polls.
CHANGING = (
    ".world-badge.place-mark .badge-words",
    "#selected-body .picture-facts[data-facts='made']",
    "#selected-body .view-row",
    "#part-params .cand .src",
    f"{MACHINE} #print-progress",
    f"{MACHINE} #print-history",
    f"{MACHINE} #chart-span",
    f"{MACHINE} #chart",
    "#site-jobs-list",
)


def _undated(row: str) -> str:
    """A row of Site's Jobs without the time it started, or a print's progress without
    how long it took: each is every run's own."""
    return row.rsplit(" · ", 1)[0]


def _mm(value: float) -> str:
    """A number as the page's status and facts write it: to a tenth, no trailing zero."""
    return f"{round(value, 1):g}"


def _found(page, host: str = "workbench") -> None:
    """Picture › Find shapes on the bench's ring; its outlines drawn."""
    _ring_on(page, host)
    _press(page, "Picture")
    assert _labels(page)[-1] == "Find shapes", _labels(page)
    _press(page, "Find shapes")
    _said(page, f"found at {host}")


@pytest.mark.e2e
def test_a_picture_to_a_print_twice(page, url, walkthrough, shots):
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    story = walkthrough(
        ordinal="13",
        slug="a-picture-to-a-print",
        title="A picture to a print",
        intro=(
            "A camera over the bench, a picture taken, its shapes found, one made a "
            "piece, the piece adjusted, sliced for printer_1, and a print job for it on "
            "printer_1, watched to its end in printer_1's Machine; then round again with "
            "the camera turned, for a second piece, sliced from its own ring, and a "
            "second print. Every step is the page's own: a cell of a ring, a button, a "
            "key or a box, and every step's words name the next one."
        ),
        runtime=(
            "It drives a real browser against a real server of its own. The browser's "
            "camera is Chromium's fake one, playing a drawing of three shapes, the "
            "slicer a scripted stand-in for OrcaSlicer's command line, and the printer "
            "the simulated one, pinned to printer_1's board as the bench's real board "
            "is. It needs no network, opens no serial port, and refuses both."
        ),
        does_not_show=[
            "**A real camera, a real slicer or a real printer.** The camera plays a "
            "drawing; the slicer is a script that answers as OrcaSlicer's command line "
            "does and writes a few layers of moves and dwells, whatever the piece; the "
            "printer is a simulation that answers as Marlin does. OrcaSlicer's real "
            "slices are docs/slicer.md's, and the camera's and the printer's real runs "
            "are steps of the bench checklist.",
            "**A print that heats.** The start the slice writes sets the hotend and the "
            "bed, and the simulated printer is at what it is told at once; nothing "
            "warms, and the file turns both off at its end.",
            "**What changes on every run.** When a print started and ended, how long it "
            "took, and the names pictures are kept under (the time each was taken) are "
            "blanked in the pictures and left out of the words, so this page "
            "changes when the loop does, not when the clock does. A running print is "
            "described rather than pictured, for the same reason.",
        ],
        page=page,
        browser_suite_only=True,
    )
    _open_garage(page, url)
    _closer_to_the_bench(page)

    # ---------------------------------------------------------------- round one
    # 1. A camera, added at the bench from its ring.
    _ring_on(page, "workbench")
    _press(page, "Camera", "Add here")
    _said(page, "above workbench, looking straight down: its Device says which")
    page.wait_for_function("() => /^camera_/.test(window.fractalViewer.selectedName || '')")
    camera = page.evaluate("() => window.fractalViewer.selectedName")
    expect(_row(page, camera)).to_be_visible()
    section = page.locator("#selected-body .camera-section")
    expect(section.locator("[data-facts='lands']")).to_have_text("lands on workbench")
    settled(page)
    story.shows(
        "Camera › Add here stands a camera over the bench",
        f"The bench's ring, Camera › Add here: {camera} stands above the bench's middle, "
        "looking straight down, selected, a row of Contents. The status line names the "
        "next step: its Device.",
        shown=_status(page).inner_text(),
        blank=CHANGING,
    )

    # 2. Its device: this browser's camera, from its own ring.
    _ring_on(page, camera)
    _press(page, "Device")
    (label,) = _labels(page)
    _press(page, label)
    _said(page, f"{camera} is {DRAWING}")
    expect(_status(page)).to_contain_text("Take picture (P) keeps a frame where it looks")
    expect(section.locator("[data-facts='device']")).to_have_text(str(DRAWING))
    story.says(
        "Device says which of this browser's cameras it is",
        "The camera's own ring, Device, and the one camera this browser has. The status "
        "line names the next step: Take picture, or P.",
        shown=_status(page).inner_text(),
    )

    # 3. Take picture, from its ring: a frame that lies on the bench.
    _ring_on(page, camera)
    _press(page, "Take picture")
    _said(page, f"{camera}'s picture lies on workbench: Picture › Find shapes finds what is in it")
    page.wait_for_function(
        "() => window.apothecaryPictures.state().some((e) => e.host === 'workbench' && e.mat)",
        timeout=10000,
    )
    expect(section.locator(".camera-thumbs .cam-thumb")).to_have_count(1)
    (first,) = _attached(page, url)["views"]
    assert first["camera"] == camera and first["picture"].startswith("captures/")
    settled(page)
    story.shows(
        "Take picture lays the frame on the bench",
        "The camera's ring, Take picture: the frame is kept, lies on the bench where the "
        "camera looks, and is the first thumbnail in the camera's section. Nothing is "
        "found in it yet; the status line names Picture › Find shapes.",
        shown=_status(page).inner_text(),
        blank=CHANGING,
    )

    # 4. Find shapes, from the bench's ring.
    _found(page)
    expect(_status(page)).to_contain_text("Picture › Make makes them pieces")
    page.wait_for_function(
        "() => window.apothecaryPictures.state().some((e) => e.host === 'workbench' && e.outlines.length)",
        timeout=10000,
    )
    (first,) = _attached(page, url)["views"]
    assert first["finder"] == "plain" and len(first["shapes"]) >= 3
    expect(page.locator(".world-badge.place-mark[data-host='workbench']")).to_contain_text(
        f"{len(first['shapes'])} shape"
    )
    settled(page)
    story.shows(
        "Find shapes outlines what the picture holds",
        "The bench's ring, Picture › Find shapes: the plain finder outlines each shape on "
        "the picture where it lies. A camera's picture is sized as it is taken, so the "
        "status line names Make at once.",
        shown=_status(page).inner_text(),
        blank=CHANGING,
    )

    # 5. Make: the disc stands up as a piece, and the words name the next steps.
    disc = _make(page, url, "disc")
    _said(page, f"made {disc}: Part › Edit adjusts it, and a printer's Machine prints it")
    settled(page)
    story.shows(
        "Make stands a shape up as a piece",
        f"The bench's ring, Picture › Make and the disc: {disc} stands on its outline, a "
        "row of Contents. The status line names the two steps after it: Part › Edit "
        "adjusts it, and a printer's Machine prints it.",
        shown=_status(page).inner_text(),
        blank=CHANGING,
    )

    # 6. Adjusted in Selected: its thickness, which the picture could only guess.
    thick = _mm(_adjust(page, disc, "height", 5))
    expect(_status(page)).to_contain_text(f"× {thick} mm; found ")
    expect(_status(page)).to_contain_text("thickness a person's: a printer's Machine prints it")
    facts = page.locator("#selected-body .picture-facts[data-facts='made']")
    expect(facts).to_contain_text(f"× {thick} mm, a person's")
    settled(page)
    story.shows(
        "Part › Edit adjusts it in Selected",
        f"The piece's ring, Part › Edit: its parameters in Selected, under where it came "
        f"from. Its thickness, which a picture cannot see, set to {thick} mm and "
        "applied: it is rebuilt where it stands, and the status line names the printer's "
        "Machine.",
        shown=_status(page).inner_text(),
        blank=CHANGING,
    )

    # 7. printer_1's Machine, from its ring: Print from here offers the piece.
    _ring_on(page, "printer_1")
    _press(page, "Device", "Open")
    _said(page, "Opened printer_1")
    machine = page.locator(MACHINE)
    expect(machine).to_be_visible(timeout=5000)
    expect(machine.locator(".panel-name")).to_contain_text(f"printer_1 · {PRINTER}")
    expect(machine.locator("#c-state")).to_contain_text("idle", timeout=10000)
    makes = machine.locator("#print-part")
    expect(makes.locator(f"option[value='{disc}']")).to_be_attached(timeout=10000)
    expect(machine.locator("#print-where")).to_have_text("in garage")

    # The piece chosen as what it makes, and Slice: the slicer's log in the card while
    # it runs, then the G-code it kept chosen in the card's files, saying what it was
    # sliced from and for which printer, and what the slice used.
    makes.select_option(disc)
    slicing = machine.locator("#print-slice")
    expect(slicing).to_be_enabled()
    slicing.click()
    _said(
        page,
        f"slicing {disc} for printer_1: its log is in Print from here, and its G-code is "
        "chosen there when it ends",
    )
    said = machine.locator("#print-slice-said")
    expect(said).to_contain_text(f"{disc} sliced for printer_1 by OrcaSlicer 2.4.2", timeout=30000)
    kept = _kept(page, url, disc)
    pick = machine.locator("#print-pick")
    expect(pick).to_have_value(kept["id"])
    expect(pick.locator("option:checked")).to_have_text(
        f"{disc}.gcode · {kept['lines']} lines · sliced from {disc} for printer_1"
    )
    expect(machine.locator("#print-slice-task")).to_be_hidden()
    _said(
        page,
        f"{disc}.gcode kept and chosen: sliced from {disc} for printer_1, 1h 2m 3s, "
        f"0.79 g of filament, {LAYERS} layers; ▶ Print prints it",
    )
    sliced_said = _status(page).inner_text()
    # What the slice used, each value with where it came from: a made piece declares
    # none, so every one is the printer's, and the words say why.
    settings = {s["name"]: s for s in kept["record"]["settings"]}
    assert settings["print settings"]["note"].startswith("a word's print settings are a stub")
    assert {s["origin"] for s in settings.values()} == {"printer"}
    expect(said.locator(".slice-settings")).to_contain_text("layer_height")
    expect(said.locator(".slice-settings")).to_contain_text("start")
    machine.locator("#ctl").check()
    expect(page.locator("#control")).to_be_visible(timeout=5000)
    expect(machine.locator("#print-start")).to_be_enabled()
    machine.locator("#print-card").scroll_into_view_if_needed()
    story.shows(
        "Slice, in printer_1's Machine, slices the piece and chooses its G-code",
        "printer_1's ring, Device › Open: its Machine in the rail, beside Selected. Print "
        f"from here lists the pieces of the garage under makes; {disc} chosen, its Slice "
        "slices it for printer_1, the slicer's log in the card while it runs. The G-code "
        "it kept is chosen in the card's files, saying what it was sliced from and for "
        "which printer, and the card lists what the slice used -- each value from the "
        "printer's profile, a piece declaring none -- with the slicer's estimate; "
        "control is armed.",
        shown=sliced_said,
        blank=CHANGING,
    )

    # 8. ▶ Print: asked first, naming the piece; a job begins.
    asked = []
    page.once("dialog", lambda d: (asked.append(d.message), d.accept()))
    machine.locator("#print-start").click()
    expect(machine.locator("#print-progress")).to_contain_text(
        f"{disc}.gcode · printing", timeout=5000
    )
    assert asked and f"making {disc}" in asked[0], asked
    # What was asserted is what the page shows: a short print can end, and say so in
    # the status line, before the line is read again.
    started = (
        f"started {disc}.gcode on {PRINTER}, making {disc}: Print from here follows it to "
        "its end, and Site's Jobs lists it"
    )
    _said(page, started)
    expect(machine.locator("#print-history")).to_contain_text(
        f"print · {disc}.gcode → {disc} · running", timeout=5000
    )
    story.says(
        "Print starts a job that names the piece",
        f"Print from here's ▶ Print asks first, naming the file, the port and {disc}; "
        "then the file streams, one line per ok, and the job is the newest of printer_1's "
        "history, running. The status line names where it is followed.",
        shown=f"{asked[0]}\n\n{started}",
    )

    # 9. Watched to its end, in the Machine and in Site's Jobs.
    progress = machine.locator("#print-progress")
    expect(progress).to_contain_text(f"{disc}.gcode · done", timeout=30000)
    lines = kept["lines"]
    expect(progress).to_contain_text(f"{disc}.gcode · done · {lines}/{lines} lines (100.0%)")
    expect(machine.locator("#print-history")).to_contain_text(
        f"print · {disc}.gcode → {disc} · done · {lines}/{lines} lines"
    )
    _said(page, f"{disc}.gcode on {PRINTER}, making {disc}, ended: done, {lines}/{lines} lines")
    ended_said = _status(page).inner_text()
    expect(machine.locator("#c-state")).to_contain_text("idle", timeout=10000)
    jobs = page.locator("#site-jobs")
    jobs.locator("summary").click()
    rows = page.locator("#site-jobs-list li[data-job]")
    expect(rows.first).to_contain_text(f"printer_1 · print · {disc}.gcode → {disc} · done")
    # The job keeps the picture and the camera its piece came from; its row does not say them.
    (job,) = page.request.get(f"{url}/jobs?site=garage").json()
    assert job["part"] == {
        "path": disc,
        "name": "disc",
        "picture": first["picture"],
        "camera": camera,
    }, job
    assert job["machine"]["port"] == PRINTER and job["outcome"] == "done"
    expect(rows.first).not_to_contain_text(first["picture"])
    story.says(
        "The job ends, and says so where it is watched",
        "The status line says the print ended and how; the Machine's progress reads done, "
        "every line sent; its history keeps the job with the piece it made, and Site's "
        "Jobs lists it under printer_1. The job's record keeps the picture and the camera "
        "the piece came from, and its row does not show them.",
        shown=(
            f"{ended_said}\n{_undated(progress.inner_text())}\n{_undated(rows.first.inner_text())}"
        ),
    )

    # ---------------------------------------------------------------- round two
    # 10. The camera turned by its turn ring: half a turn, so its next picture lies
    # the other way round on the bench.
    _row(page, camera).click()
    page.wait_for_function(
        "(n) => window.fractalViewer.cameraHandles?.userData.camera === n", arg=camera
    )
    settled(page)
    with page.expect_response(lambda r: r.url.endswith(f"/cameras/{camera}/pose")) as posed:
        _drag(page, "turn", [0, -45, -90, -135, -180])
    assert posed.value.ok
    _said(page, f"{camera} turned to")
    expect(_status(page)).to_contain_text("its next picture lands on workbench")
    turn_said = _status(page).inner_text()
    turned = page.request.get(f"{url}/sites/garage/cameras/{camera}").json()
    assert turned["turn"] == pytest.approx(180, abs=8), turned

    # 11. P, with the camera selected: the second picture.
    page.locator("#viewer-canvas").focus()
    page.keyboard.press("p")
    _said(page, f"{camera}'s picture lies on workbench: Picture › Find shapes")
    expect(section.locator(".camera-thumbs .cam-thumb")).to_have_count(2, timeout=10000)
    second = _attached(page, url)["views"][-1]
    assert second["id"] != first["id"] and second["taken"]["turn"] == pytest.approx(turned["turn"])
    settled(page)
    story.shows(
        "Turned by its ring, the camera takes a second picture with P",
        f"{camera} selected wears its turn ring; dragged half a turn, its next picture "
        "lands on the bench the other way round. P takes it: the second thumbnail, and "
        "the status line names Find shapes again.",
        shown=f"{turn_said}\n{_status(page).inner_text()}",
        blank=CHANGING,
    )

    # 12. Its shapes found, and its plate made the second piece.
    _found(page)
    page.wait_for_function(
        "(id) => window.apothecaryPictures.state().some((e) => e.host === 'workbench'"
        " && e.view === id && e.outlines.length)",
        arg=second["id"],
        timeout=10000,
    )
    plate = _make(page, url, "plate")
    assert plate != disc
    _said(page, f"made {plate}: Part › Edit adjusts it, and a printer's Machine prints it")

    # 13. Adjusted: narrower.
    width = _mm(_adjust(page, plate, "width", 40))
    expect(_status(page)).to_contain_text(f"{plate} rebuilt {width} × ")
    expect(_status(page)).to_contain_text("a printer's Machine prints it")
    settled(page)
    story.shows(
        "A second piece, made and adjusted",
        f"Find shapes and Make on the second picture: {plate} stands beside {disc}. "
        f"Part › Edit narrows it to {width} mm and applies it.",
        shown=_status(page).inner_text(),
        blank=CHANGING,
    )

    # 14. The Machine stayed open in the rail, and makes lists the new piece without its
    # being opened again; the piece's own ring's Print chooses it there.
    expect(machine).to_be_visible()
    expect(makes.locator(f"option[value='{plate}']")).to_be_attached(timeout=10000)
    expect(makes).to_have_value(disc)
    _ring_on(page, plate)
    assert _labels(page)[-4:] == ["Picture", "Part", "Print", "Slice"]
    _press(page, "Slice")
    _said(
        page,
        f"Slice: slicing {plate} for printer_1: its log is in Print from here, and its "
        "G-code is chosen there when it ends",
    )
    expect(makes).to_have_value(plate)
    assert page.evaluate("() => window.fractalViewer.selectedName") == plate
    expect(said).to_contain_text(f"{plate} sliced for printer_1 by OrcaSlicer 2.4.2", timeout=30000)
    plate_kept = _kept(page, url, plate)
    expect(pick).to_have_value(plate_kept["id"])
    expect(pick.locator("option:checked")).to_have_text(
        f"{plate}.gcode · {plate_kept['lines']} lines · sliced from {plate} for printer_1"
    )
    _said(page, f"{plate}.gcode kept and chosen: sliced from {plate} for printer_1")
    # The first piece's file is still kept, and still says what it was sliced from.
    expect(pick.locator(f"option[value='{kept['id']}']")).to_have_text(
        f"{disc}.gcode · {kept['lines']} lines · sliced from {disc} for printer_1"
    )
    settled(page)
    story.shows(
        "Slice, on the piece's ring, slices it in printer_1's Machine",
        f"{plate}'s ring ends with Print and Slice, a printer being pinned in the garage. "
        f"Slice brings printer_1's Machine forward with {plate} chosen under makes -- "
        "listed there already, though the Machine stayed open while it was made -- and "
        "slices it there; its G-code is chosen beside the first piece's, each saying what "
        "it was sliced from. The status line names ▶ Print.",
        shown=_status(page).inner_text(),
        blank=CHANGING,
    )

    # 15. Send file, from printer_1's ring: what the card has chosen, printed.
    _ring_on(page, "printer_1")
    _press(page, "Device", "Control")
    if "Arm" in _labels(page):  # the latch lapses after minutes without a control
        _press(page, "Arm")
        expect(page.locator("#control")).to_be_visible(timeout=5000)
        _ring_on(page, "printer_1")
        _press(page, "Device", "Control")
    asked.clear()
    page.once("dialog", lambda d: (asked.append(d.message), d.accept()))
    _press(page, "Print", "Send file")
    expect(machine.locator("#print-progress")).to_contain_text(
        f"{plate}.gcode · printing", timeout=5000
    )
    assert asked and f"making {plate}" in asked[0], asked
    _said(page, f"Send file: started {plate}.gcode on {PRINTER}, making {plate}: Print from here")
    expect(machine.locator("#print-progress")).to_contain_text(
        f"{plate}.gcode · done", timeout=30000
    )
    plate_lines = plate_kept["lines"]
    _said(
        page,
        f"{plate}.gcode on {PRINTER}, making {plate}, ended: done, {plate_lines}/{plate_lines} lines",
    )

    # 16. Two jobs, each naming its piece: the Machine's history and Site's Jobs.
    history = machine.locator("#print-history > div")
    expect(history.first).to_contain_text(f"print · {plate}.gcode → {plate} · done")
    expect(history.nth(1)).to_contain_text(f"print · {disc}.gcode → {disc} · done")
    expect(rows).to_have_count(2, timeout=10000)
    expect(rows.first).to_contain_text(f"printer_1 · print · {plate}.gcode → {plate} · done")
    expect(rows.nth(1)).to_contain_text(f"printer_1 · print · {disc}.gcode → {disc} · done")
    newest, older = page.request.get(f"{url}/jobs?site=garage").json()
    assert (newest["part"]["path"], older["part"]["path"]) == (plate, disc)
    assert (newest["part"]["picture"], newest["part"]["camera"]) == (second["picture"], camera)
    machine.locator("#print-card").scroll_into_view_if_needed()
    jobs.scroll_into_view_if_needed()
    expect(jobs.locator("summary")).to_contain_text("Jobs · 2")
    story.shows(
        "Send file prints the second, and both jobs name their pieces",
        f"printer_1's ring, Device › Control › Print › Send file, prints what the card has "
        f"chosen: {plate}, and the status line says when it ends. The Machine's history "
        "and Site's Jobs keep both jobs, newest first, each with the piece it made.",
        shown="\n".join(
            [_status(page).inner_text(), *(_undated(row) for row in rows.all_inner_texts())]
        ),
        blank=CHANGING,
    )

    # Print from here at each width the page is laid out for, with the second piece's
    # slice said under makes: nothing in it overlaps, and nothing pokes out of it.
    card = machine.locator("#print-card")
    for width, height in WIDTHS:
        page.set_viewport_size({"width": width, "height": height})
        card.scroll_into_view_if_needed()
        expect(said).to_contain_text(f"{plate} sliced for printer_1", timeout=5000)
        settled(page)
        assert page.evaluate(CROWDED, f"{MACHINE} #print-card") == [], width
        card.screenshot(path=str(shots / f"print-card-{width}.png"))
        page.screenshot(path=str(shots / f"page-{width}.png"))

    assert "/viewer/sites/garage" in page.url  # nothing switched the site
    assert errors == []
