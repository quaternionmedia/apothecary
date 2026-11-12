"""The Marks window, as a person goes through it on a drawn whiteboard.

⊞ Windows › Marks opens it beside Models: the picture pinned at the bench, each of
its marks with its kind, and its note. A person's word on a mark -- its drop-down,
or the ring's cell on the mark chosen -- is read back by the picture's shapes in
the world, and a note typed offers the size it states for its line. A whiteboard
photographed from one side has its corners nudged and is squared again. Walkthrough
pages 37 and 38 are what the first two tests write.

Its server is the module's own: a whiteboard drawn here, with a plate, a ring
alone, a line and its size, pinned at the workbench and read by the outline finder.
"""

from __future__ import annotations

import io
import re

import httpx
import pytest
import windows
from doc_capture import moments
from garage import look_down, open_garage, said, status
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import expect

BLUE, BLACK = (20, 30, 120), (10, 10, 10)
MARKS = ".panel[data-panel='marks']"
# What changes on every run whatever the page does: the moments.
CHANGING = moments(MARKS, "#status")


def _whiteboard() -> bytes:
    image = Image.new("RGB", (1600, 1200), (238, 238, 236))
    pen = ImageDraw.Draw(image)
    pen.rectangle((250, 250, 700, 520), outline=BLUE, width=9)
    pen.ellipse((1290, 1000, 1370, 1080), outline=BLACK, width=6)
    pen.line((250, 590, 700, 590), fill=BLACK, width=5)
    pen.text((400, 605), "120 mm", fill=BLACK, font=ImageFont.load_default(size=44))
    held = io.BytesIO()
    image.save(held, format="PNG")
    return held.getvalue()


@pytest.fixture(scope="module")
def url(base_url, start_server, tmp_path_factory):
    """This module's own server, the drawn whiteboard pinned at the workbench and its
    shapes found by the outline finder. ``base_url`` is asked for only so that with no
    server to run against this is skipped, as every browser test is."""
    folder = tmp_path_factory.mktemp("marks_pictures")
    (folder / "whiteboard.png").write_bytes(_whiteboard())
    url = start_server({"APOTHECARY_PICTURE_ROOT": str(folder)})
    with httpx.Client(base_url=url, timeout=30.0) as http:
        view = http.post(
            "/sites/garage/views",
            json={"host": "workbench", "picture": "whiteboard.png", "mm_across": 1600},
        )
        view.raise_for_status()
        http.post(
            f"/sites/garage/views/{view.json()['id']}/find", json={"finder": "outline"}
        ).raise_for_status()
    return url


def _shapes(page) -> int:
    return page.evaluate("() => window.apothecaryPictures.drawnAt('workbench').shapes.length")


@pytest.mark.e2e
def test_a_persons_word_on_a_mark_is_read_back_in_the_world_and_a_note_is_typed(
    page, url, walkthrough
):
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    story = walkthrough(
        ordinal="37",
        slug="marks-worn-in-the-world",
        title="Marks worn in the world",
        intro=(
            "A whiteboard's marks as the Marks window sorts them, worn over its picture in "
            "the world: each mark's box in its kind's colour and each note a ✎ where it is "
            "written. A person's word on a mark is read back by the picture's shapes, and "
            "a note typed offers the size it states for its line. "
            "[docs/pictures.md](../docs/pictures.md#the-marks-window) is the reference; "
            "[page 30](30-a-whiteboard-round-twice-through-the-page.md) is a whiteboard "
            "round twice."
        ),
        runtime=(
            "It drives a real browser against a real server of its own, a whiteboard drawn "
            "here -- a plate, a ring alone, a line and its size -- pinned at the workbench "
            "and read by the outline finder."
        ),
        does_not_show=[
            "**A photograph.** The whiteboard is drawn by the test, square to the camera; "
            "a photograph from one side is [page 38](38-a-whiteboard-s-corners.md).",
            "**What changes on every run.** Moments are blanked in the pictures.",
        ],
        browser_suite_only=True,
    )
    open_garage(page, url)
    page.wait_for_function(
        "() => window.apothecaryPictures.state().some((e) => e.host === 'workbench' && e.mat)"
    )
    assert _shapes(page) == 1

    # Opened from ⊞ Windows: the picture, its four marks and its one note.
    windows.from_the_windows_menu(page, "marks")
    marks = windows.panel(page, "marks")
    expect(marks.locator(".marks-view")).to_contain_text("whiteboard.png · workbench")
    expect(marks.locator(".marks-row")).to_have_count(4)
    expect(marks.locator(".marks-said")).to_contain_text("read back by this picture's shapes")
    kinds = marks.locator(".marks-kind")
    assert sorted(kinds.evaluate_all("(all) => all.map((s) => s.value)")) == [
        "diagram",
        "diagram",
        "unsure",
        "writing",
    ]
    # Worn over the picture in the world: each mark's box in its kind's colour, and
    # the note's ✎ where it is written.
    page.wait_for_function(
        "() => (window.apothecaryPictures.state().find((e) => e.host === 'workbench') || {}).marks?.length === 4"
    )
    worn = page.evaluate(
        "() => window.apothecaryPictures.state().find((e) => e.host === 'workbench').marks"
    )
    assert sorted(m["kind"] for m in worn) == ["diagram", "diagram", "unsure", "writing"]
    assert {m["colour"] for m in worn if m["kind"] == "writing"} == {0xC3A2EC}
    expect(page.locator(".world-badge.note-mark")).to_have_count(1)
    ring = marks.locator(".marks-row").filter(has_text="a letter, or a hole")
    expect(ring).to_have_count(1)
    ring_id = ring.get_attribute("data-mark")
    ring = marks.locator(f".marks-row[data-mark='{ring_id}']")
    look_down(page, "workbench")
    story.shows(
        "⊞ Windows › Marks: four marks sorted, worn over the picture",
        "The header's ⊞ Windows, Marks under Pictures: the whiteboard pinned at the "
        "workbench, its four marks each with the kind the sorter gave it -- two "
        "diagrams, writing, and the ring alone unsure -- and its one note. The camera "
        "turned to look straight down on the workbench: each mark's box is worn over the "
        "picture in its kind's colour, and the note is a ✎ where it is written.",
        shown=marks.locator(".marks-said").inner_text(),
        blank=CHANGING,
    )

    # Its drop-down is a person's word: the ring a diagram's, and a second shape there.
    ring.locator(".marks-kind").select_option("diagram")
    expect(ring).to_contain_text("you said so; the sorter said unsure")
    said(page, f"{ring_id} is diagram, as you said: 2 shapes in the picture now")
    page.wait_for_function(
        "() => window.apothecaryPictures.drawnAt('workbench').shapes.length === 2"
    )
    story.shows(
        "A person's word: the ring is a diagram's, and a second shape there",
        "The ring's drop-down, diagram: the row says a person said so and the sorter said "
        "unsure, and the picture's shapes read it back, a second shape there now.",
        shown=status(page).inner_text(),
        blank=CHANGING,
    )

    # Chosen, the ring's Marks cells say what it is: nothing, and the shape is gone.
    ring.locator(".marks-choose").click()
    expect(ring.locator(".marks-choose")).to_have_attribute("aria-pressed", "true")
    assert page.evaluate("() => window.apothecaryMarks.act('say:nothing')") is True
    said(page, f"{ring_id} is nothing, as you said: 1 shape in the picture now")
    page.wait_for_function(
        "() => window.apothecaryPictures.drawnAt('workbench').shapes.length === 1"
    )
    # With no mark chosen the cell says so and changes nothing.
    marks.locator(".marks-row.chosen .marks-choose").click()
    assert page.evaluate("() => window.apothecaryMarks.act('say:diagram')") is False
    expect(status(page)).to_contain_text("choose a mark in Marks first")
    story.says(
        "Chosen, the ring's Nothing takes the shape away",
        "The ring's row chosen, and Nothing -- the cell of Panels › Pictures › Marks, its "
        "verb handed to the window as the ring hands it: the ring is nothing, as a person "
        "said, and its shape is gone. With no mark chosen the cell says to choose one, and "
        "changes nothing.",
        shown=status(page).inner_text(),
    )

    # The note's ✎ in the world brings its box in front; typed, with Enter: what it
    # says, and the size it states for its line.
    note = marks.locator(".marks-note-row")
    expect(note).to_have_count(1)
    page.locator(".world-badge.note-mark").dispatch_event("click")
    expect(note.locator(".marks-words")).to_be_focused()
    expect(note).to_contain_text("beside")
    note.locator(".marks-words").fill("120 mm")
    note.locator(".marks-words").press("Enter")
    said(page, 'says "120 mm", as you typed')
    expect(marks.locator(".marks-offer")).to_contain_text("is 120 mm long, this picture is")
    expect(marks.locator(".marks-words")).to_have_value("120 mm")
    expect(page.locator(".world-badge.note-mark")).to_have_attribute(
        "aria-label", re.compile(r"says 120 mm$")
    )
    story.shows(
        "The note's ✎ opens its box; typed, it offers the size it states",
        "The ✎ in the world pressed: the note's box in front in Marks. 120 mm typed and "
        "Enter: the note says it, its ✎ says it, and Marks offers the size it states for "
        "its line, this picture's width from it.",
        shown=marks.locator(".marks-offer").inner_text(),
        blank=CHANGING,
    )
    assert errors == []


@pytest.fixture(scope="module")
def leaning(base_url, start_server, tmp_path_factory):
    """This module's second server: a whiteboard photographed from one side, pinned
    at the garage's whiteboard and searched by the outline finder."""
    from whiteboards_helpers import photograph as _photograph

    folder = tmp_path_factory.mktemp("leaning_pictures")
    _photograph(folder / "leaning.png")
    url = start_server({"APOTHECARY_PICTURE_ROOT": str(folder)})
    with httpx.Client(base_url=url, timeout=30.0) as http:
        view = http.post(
            "/sites/garage/views", json={"host": "whiteboard", "picture": "leaning.png"}
        )
        view.raise_for_status()
        http.post(
            f"/sites/garage/views/{view.json()['id']}/find", json={"finder": "outline"}
        ).raise_for_status()
    return url


@pytest.mark.e2e
def test_a_whiteboards_corner_nudged_squares_its_photograph_again(page, leaning, walkthrough):
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    story = walkthrough(
        ordinal="38",
        slug="a-whiteboard-s-corners",
        title="A whiteboard's corners",
        intro=(
            "A photograph pinned at a whiteboard is squared to it from the whiteboard's "
            "four corners, found on the photograph; the Marks window shows them as handles, "
            "and a corner dragged or nudged squares it again. "
            "[docs/pictures.md](../docs/pictures.md#pinned-at-a-whiteboard) is the reference."
        ),
        runtime=(
            "It drives a real browser against a real server of its own: a whiteboard "
            "photographed from one side, drawn by the test, pinned at the garage's "
            "whiteboard and searched by the outline finder."
        ),
        does_not_show=[
            "**A corner dragged.** The corner here is nudged with the arrow keys; a drag "
            "sets it the same way, on release.",
            "**What changes on every run.** Moments are blanked in the pictures.",
        ],
        browser_suite_only=True,
    )
    open_garage(page, leaning)
    page.wait_for_function(
        "() => window.apothecaryPictures.state().some((e) => e.host === 'whiteboard' && e.mat)"
    )
    windows.from_the_windows_menu(page, "marks")
    marks = windows.panel(page, "marks")
    expect(marks.locator(".marks-view")).to_contain_text("· whiteboard")
    # The photograph it was squared from, its four corners on it, found.
    expect(marks.locator(".marks-corner")).to_have_count(4)
    expect(marks.locator(".marks-corners-said")).to_contain_text("found; drag a corner")
    before = page.evaluate("() => window.apothecaryPictures.drawnAt('whiteboard').picture")
    story.shows(
        "⊞ Windows › Marks: the photograph it was squared from, its corners found",
        "The header's ⊞ Windows, Marks: the photograph pinned at the whiteboard, as taken "
        "from one side, with the whiteboard's four corners found on it as handles.",
        shown=marks.locator(".marks-corners-said").inner_text(),
        blank=CHANGING,
    )

    # The top-right corner nudged left with the arrow keys, and set with Enter.
    corner = marks.locator(".marks-corner[data-handle='1']")
    left_before = corner.evaluate("(e) => parseFloat(e.style.left)")
    corner.focus()
    for _ in range(5):
        page.keyboard.press("ArrowLeft")
    assert corner.evaluate("(e) => parseFloat(e.style.left)") == pytest.approx(
        left_before - 1.0, abs=0.01
    )
    page.keyboard.press("Enter")
    said(page, "the whiteboard squared again with your corners: 3 shapes found in it")
    page.wait_for_function(
        "(was) => window.apothecaryPictures.drawnAt('whiteboard').picture !== was", arg=before
    )
    expect(marks.locator(".marks-corners-said")).to_contain_text("placed by you")
    story.shows(
        "A corner nudged and set: squared again with it",
        "The top-right corner focused, the left arrow pressed five times and Enter: the "
        "whiteboard is squared again with the corners as placed, its shapes found again, "
        "and Marks says the corners were placed by you.",
        shown=status(page).inner_text(),
        blank=CHANGING,
    )
    assert errors == []


@pytest.fixture(scope="module")
def twice(base_url, start_server, tmp_path_factory):
    """This module's third server: two photographs of the garage's whiteboard, the
    second with the drawing changed, the first's shapes made and its note typed."""
    from whiteboards_helpers import drawing as _drawing

    folder = tmp_path_factory.mktemp("twice_pictures")
    _drawing(folder / "monday.png")
    _drawing(
        folder / "tuesday.png", plate=(250, 250, 800, 520), disc=(960, 250, 1260, 550), wedge=False
    )
    url = start_server({"APOTHECARY_PICTURE_ROOT": str(folder)})
    with httpx.Client(base_url=url, timeout=30.0) as http:
        ids = []
        for name in ("monday.png", "tuesday.png"):
            view = http.post("/sites/garage/views", json={"host": "whiteboard", "picture": name})
            view.raise_for_status()
            ids.append(view.json()["id"])
            http.post(
                f"/sites/garage/views/{ids[-1]}/find", json={"finder": "outline"}
            ).raise_for_status()
            if name == "monday.png":
                (note,) = http.get(f"/sites/garage/views/{ids[0]}/marks").json()["notes"]
                http.put(
                    f"/sites/garage/views/{ids[0]}/notes/{note['id']}", json={"text": "lid, 3 off"}
                ).raise_for_status()
                http.post(
                    f"/sites/garage/views/{ids[0]}/make", json={"all": True}
                ).raise_for_status()
    return url


@pytest.mark.e2e
def test_a_whiteboards_history_is_scrubbed_a_change_taken_and_a_moment_placed(page, twice):
    from garage import select

    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    open_garage(page, twice)
    page.wait_for_function(
        "() => window.apothecaryPictures.state().some((e) => e.host === 'whiteboard' && e.mat)"
    )
    windows.from_the_windows_menu(page, "marks")
    marks = windows.panel(page, "marks")

    # Now: the second photograph, and what changed since the first, a row each.
    expect(marks.locator(".marks-when-said")).to_contain_text("Now: photograph 2 of 2")
    expect(marks.locator(".marks-strip .tick.photograph")).to_have_count(2)
    expect(marks.locator(".marks-strip .tick.made")).to_have_count(3)
    moved = marks.locator(".marks-change").filter(has_text="moved")
    expect(moved.locator(".marks-take")).to_have_count(1)
    second = page.evaluate("() => window.apothecaryPictures.drawnAt('whiteboard').id")

    # Its Take rebuilds the disc's piece from the second photograph, and nothing else.
    moved.locator(".marks-take").click()
    said(page, "taken: ")
    expect(status(page)).to_contain_text("made")
    expect(status(page)).to_contain_text("dropped")
    made = page.request.get(f"{twice}/sites/garage/attached").json()["made"]
    assert sorted(r["view"] for r in made.values()).count(second) == 1

    # Earlier, from the ring's cell: the first photograph drawn, its words as then.
    for _ in range(8):
        if "photograph 1 of 2" in marks.locator(".marks-when-said").inner_text():
            break
        was = marks.locator(".marks-when-said").inner_text()
        assert page.evaluate("() => window.apothecaryMarks.act('earlier')") is True
        expect(marks.locator(".marks-when-said")).not_to_have_text(was)
        expect(status(page)).to_contain_text("the whiteboard as of")
    expect(marks.locator(".marks-when-said")).to_contain_text("photograph 1 of 2")
    page.wait_for_function(
        "(was) => window.apothecaryPictures.drawnAt('whiteboard').id !== was", arg=second
    )
    expect(marks.locator(".marks-change")).to_have_count(0)

    # The slider scrubbed back to now draws the second again.
    marks.locator(".marks-when").fill("1000")
    expect(marks.locator(".marks-when-said")).to_contain_text("Now: photograph 2 of 2")
    page.wait_for_function(
        "(id) => window.apothecaryPictures.drawnAt('whiteboard').id === id", arg=second
    )

    # Placed at the bench, selected in the world: the moment's picture lies there.
    select(page, "workbench")
    marks.locator(".marks-place").click()
    said(page, "the whiteboard now placed at workbench: 2 shape(s) there to make")
    page.wait_for_function(
        "() => window.apothecaryPictures.state().some((e) => e.host === 'workbench' && e.mat)"
    )
    assert errors == []
