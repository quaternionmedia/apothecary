"""A whiteboard to a model, round twice through the page: walkthrough page 30, written
by the test here.

Monday's photograph of the garage's whiteboard is pinned at it from the ring, squared
and laid in front of it; its shapes found, its writing typed in Marks, its shapes made.
Tuesday's, with the drawing changed, is pinned beside it: the whiteboard's history
shows both, what changed since Monday is a row each, and one row is taken. Scrubbed
back to Monday, the moment is placed on the bench.

Its server is the module's own, with the two photographs in its picture folder,
drawn here (tests/test_whiteboard_history.py's whiteboard on a wall).
"""

from __future__ import annotations

import pytest
import rings
import windows
from doc_capture import moments
from garage import open_garage, said, select, status
from playwright.sync_api import Page, expect
from whiteboards_helpers import drawing as _drawing

MARKS = ".panel[data-panel='marks']"
WITHIN = 20_000
CHANGING = moments("#status", ".marks-when-said")

# Above the floor in front of the whiteboard, looking down and towards the wall.
LOOK_AT_THE_FLOOR_IN_FRONT = """() => {
    const v = window.fractalViewer;
    const g = window.apothecaryPictures.state().find((e) => e.host === 'whiteboard');
    const [x, y] = g.mat.centre;
    v.orbitControls.target.copy(v.sceneAt(x, y + 200, 0));
    v.camera.position.copy(v.sceneAt(x, y - 1300, 2200));
    v.orbitControls.update();
}"""


@pytest.fixture(scope="module")
def url(start_server, tmp_path_factory):
    folder = tmp_path_factory.mktemp("whiteboard_round_twice")
    _drawing(folder / "monday.png")
    _drawing(
        folder / "tuesday.png", plate=(250, 250, 800, 520), disc=(960, 250, 1260, 550), wedge=False
    )
    return start_server({"APOTHECARY_PICTURE_ROOT": str(folder)})


def _drawn(page: Page):
    return page.evaluate("() => window.apothecaryPictures.drawnAt('whiteboard')")


def _settled(page: Page) -> None:
    page.evaluate(LOOK_AT_THE_FLOOR_IN_FRONT)
    page.wait_for_timeout(400)


@pytest.mark.e2e
def test_a_whiteboard_to_a_model_round_twice(page: Page, url: str, walkthrough):
    """Walkthrough page 30: the whiteboard loop through the page, twice round."""
    story = walkthrough(
        ordinal="30",
        slug="a-whiteboard-round-twice-through-the-page",
        title="A whiteboard, round twice through the page",
        intro=(
            "A drawing on the garage's whiteboard to pieces on its floor, and round again "
            "when the drawing changes, as a person goes through it in the page: a "
            "photograph pinned at the whiteboard from its ring, squared to it and laid in "
            "front of it; its shapes found, its writing typed in Marks and its shapes made; "
            "then a second photograph of the changed drawing, the whiteboard's history, a "
            "change taken, and a moment of it placed on the bench. "
            "[docs/pictures.md](../docs/pictures.md#a-whiteboards-history) is the reference, "
            "and [page 29](29-a-whiteboard-round-twice.md) goes round by the commands."
        ),
        runtime=(
            "It drives a real browser against a real server of its own. The two "
            "photographs are drawn to order, a whiteboard on a wall square on, and lie in "
            "the server's picture folder. It needs no network."
        ),
        does_not_show=[
            "**A real photograph.** Both are drawn to order; a whiteboard seen from one "
            "side is squared in tests/test_whiteboard.py, and its corners moved in "
            "tests/e2e/test_marks_window.py.",
            "**Anything kept across a restart.** The photographs' views, their words and "
            "the pieces made are kept in the server's memory.",
            "**A note sent out.** Neither looksatwords nor qmcp is reached here.",
            "**What changes on every run.** The moments on the status line and under When "
            "are blanked in the pictures.",
        ],
        browser_suite_only=True,
    )
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    open_garage(page, url)

    # 1. The whiteboard, on the garage's south wall.
    select(page, "whiteboard")
    expect(page.locator("#selected-body")).to_contain_text("whiteboard")
    story.shows(
        "The whiteboard, on the garage's south wall",
        "The garage's whiteboard hangs on its south wall beside the door, facing the room: "
        "a part, its width and height its writing surface's. Selected, its ring holds "
        "Picture, as any place a picture can lie does.",
        blank=CHANGING,
    )

    # 2. Monday's photograph pinned from the ring: squared, sized, laid in front.
    rings.on_row(page, "whiteboard", "Picture", "Folder", "monday")
    page.wait_for_function(
        "() => (window.apothecaryPictures.drawnAt('whiteboard') || {}).squared", timeout=WITHIN
    )
    monday = _drawn(page)
    assert monday["in_front"] and monday["mm_across"] == 1200
    _settled(page)
    story.shows(
        "Picture › Folder pins a photograph: squared, sized and laid in front",
        "The whiteboard's ring, Picture › Folder › monday: the photograph's corners are "
        "found and it is redrawn square on, as wide as the whiteboard's surface with no "
        "width typed, and laid flat on the floor in front of it, its top towards the wall.",
        blank=CHANGING,
    )

    # 3. Its shapes found by the outline finder.
    rings.on_row(page, "whiteboard", "Picture", "Find shapes", "outline")
    page.wait_for_function(
        "() => (window.apothecaryPictures.drawnAt('whiteboard') || {}).shapes?.length === 3",
        timeout=WITHIN,
    )
    _settled(page)
    story.shows(
        "Find shapes › outline outlines each closed stroke",
        "Picture › Find shapes › outline: the plate, the disc and the wedge, outlined where "
        "they lie in front of the whiteboard. The writing is not a shape.",
        blank=CHANGING,
    )

    # 4. Its writing typed in Marks, worn over the picture.
    windows.from_the_windows_menu(page, "marks")
    marks = page.locator(MARKS)
    expect(marks.locator(".marks-view")).to_contain_text("monday.png · whiteboard")
    note = marks.locator(".marks-note-row")
    expect(note).to_have_count(1)
    note.locator(".marks-words").fill("lid, 3 off")
    note.locator(".marks-words").press("Enter")
    said(page, 'says "lid, 3 off", as you typed')
    expect(page.locator(".world-badge.note-mark")).to_have_attribute(
        "aria-label", "m4 says lid, 3 off"
    )
    _settled(page)
    story.shows(
        "Marks: each mark sorted, and the writing typed",
        "⊞ Windows › Marks lists the photograph's marks, each a diagram's or writing, and "
        "its one note; what it says is typed and said with Enter. Over the picture in the "
        "world, each mark's box in its kind's colour, and the note's ✎ where it is written.",
        blank=CHANGING,
    )

    # 5. Its shapes made, on the floor in front at full size.
    rings.on_row(page, "whiteboard", "Picture", "Make", "Make all")
    page.wait_for_function(
        "() => Object.keys(window.apothecaryPictures.attached().made || {}).length === 3",
        timeout=WITHIN,
    )
    _settled(page)
    story.shows(
        "Make all stands each shape up as a piece, at full size",
        "Picture › Make › Make all: the plate, the disc and the wedge stand on the floor in "
        "front of the whiteboard where they were drawn, as big as they are drawn on it.",
        blank=CHANGING,
    )

    # 6. Tuesday's photograph, the drawing changed: the history shows both.
    rings.on_row(page, "whiteboard", "Picture", "Folder", "tuesday")
    page.wait_for_function(
        "(was) => (window.apothecaryPictures.drawnAt('whiteboard') || {}).id !== was",
        arg=monday["id"],
        timeout=WITHIN,
    )
    rings.on_row(page, "whiteboard", "Picture", "Find shapes", "outline")
    page.wait_for_function(
        "() => (window.apothecaryPictures.drawnAt('whiteboard') || {}).shapes?.length === 2",
        timeout=WITHIN,
    )
    page.evaluate("() => window.apothecaryMarks.load()")
    expect(marks.locator(".marks-when-said")).to_contain_text(
        "Now: photograph 2 of 2", timeout=WITHIN
    )
    rows = marks.locator(".marks-change")
    expect(rows.filter(has_text="moved")).to_have_count(1)
    # The photograph listed, and its corners, are Tuesday's.
    expect(marks.locator(".marks-view")).to_have_value(_drawn(page)["id"])
    expect(marks.locator(".marks-corners-said")).to_contain_text("found; drag a corner")
    _settled(page)
    story.shows(
        "Tuesday's photograph, and what changed since Monday",
        "The drawing changed: the plate wider, the disc moved, the wedge rubbed out. "
        "Pinned and searched as the first was, it is the whiteboard now, and Marks shows "
        "its history under When -- a tick for each photograph, word and piece -- and what "
        "changed since Monday, a row each. Nothing has changed yet: Monday's pieces stand.",
        shown="\n".join(
            r.inner_text().replace("\n", " ").replace("Take", "").strip() for r in rows.all()
        ),
        blank=CHANGING,
    )

    # 7. One row taken: the disc's piece rebuilt from Tuesday's, and nothing else.
    rows.filter(has_text="moved").locator(".marks-take").click()
    expect(status(page)).to_contain_text("taken: ", timeout=WITHIN)
    made = page.request.get(f"{url}/sites/garage/attached").json()["made"]
    assert sorted(r["word"] for r in made.values()) == ["disc", "plate", "wedge"]
    assert sum(1 for r in made.values() if r["view"] != monday["id"]) == 1
    story.says(
        "Take on one row changes that piece and no other",
        "The disc's row taken: its piece is dropped and made again from Tuesday's "
        "photograph, where the disc is now. The plate and the wedge, their rows left, "
        "stand as Monday made them.",
        shown=status(page).inner_text(),
    )

    # 8. Earlier on the ring, until Monday: its photograph drawn, its words as then.
    for _ in range(4):
        if "photograph 1 of 2" in marks.locator(".marks-when-said").inner_text():
            break
        was = marks.locator(".marks-when-said").inner_text()
        rings.on_world(page, "Panels", "Pictures", "Marks", "Earlier")
        expect(marks.locator(".marks-when-said")).not_to_have_text(was, timeout=WITHIN)
        expect(status(page)).to_contain_text("the whiteboard as of")
    expect(marks.locator(".marks-when-said")).to_contain_text("photograph 1 of 2", timeout=WITHIN)
    expect(marks.locator(".marks-when-said")).to_contain_text("1 word(s) given · 3 piece(s) made")
    page.wait_for_function(
        "(id) => (window.apothecaryPictures.drawnAt('whiteboard') || {}).id === id",
        arg=monday["id"],
        timeout=WITHIN,
    )
    _settled(page)
    story.shows(
        "Earlier, the whiteboard as it stood on Monday",
        "The canvas ring's Panels › Pictures › Marks › Earlier steps the slider to the event "
        "before, twice: to Tuesday's photograph, then to Monday's pieces being made. "
        "Monday's photograph is drawn in front of the whiteboard again, its note's words "
        "as they were then.",
        blank=CHANGING,
    )

    # 9. That moment placed on the bench.
    select(page, "workbench")
    marks.locator(".marks-place").click()
    expect(status(page)).to_contain_text("placed at workbench", timeout=WITHIN)
    expect(page.locator("#selected-body")).to_contain_text("monday.png")
    page.wait_for_function(
        "() => window.apothecaryPictures.state().some((e) => e.host === 'workbench' && e.mat)",
        timeout=WITHIN,
    )
    story.shows(
        "A moment placed on the bench",
        "The bench selected in the world, Place: Monday's drawing is pinned on the bench, as "
        "wide as it was on the whiteboard and searched by the same finder, with its words, "
        "its shapes there to make beside the pieces.",
        blank=CHANGING,
    )
    assert errors == []
