"""The Marks window, as a person goes through it on a drawn whiteboard.

⊞ Windows › Marks opens it beside Models: the picture pinned at the bench, each of
its marks with its kind, and its note. A person's word on a mark -- its drop-down,
or the ring's cell on the mark chosen -- is read back by the picture's shapes in
the world, and a note typed offers the size it states for its line.

Its server is the module's own: a whiteboard drawn here, with a plate, a ring
alone, a line and its size, pinned at the workbench and read by the outline finder.
"""

from __future__ import annotations

import io

import httpx
import pytest
import windows
from garage import open_garage, said, status
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import expect

BLUE, BLACK = (20, 30, 120), (10, 10, 10)


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
def test_a_persons_word_on_a_mark_is_read_back_in_the_world_and_a_note_is_typed(page, url):
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
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
    ring = marks.locator(".marks-row").filter(has_text="a letter, or a hole")
    expect(ring).to_have_count(1)
    ring_id = ring.get_attribute("data-mark")
    ring = marks.locator(f".marks-row[data-mark='{ring_id}']")

    # Its drop-down is a person's word: the ring a diagram's, and a second shape there.
    ring.locator(".marks-kind").select_option("diagram")
    expect(ring).to_contain_text("you said so; the sorter said unsure")
    said(page, f"{ring_id} is diagram, as you said: 2 shapes in the picture now")
    page.wait_for_function(
        "() => window.apothecaryPictures.drawnAt('workbench').shapes.length === 2"
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

    # The note typed, with Enter: what it says, and the size it states for its line.
    note = marks.locator(".marks-note-row")
    expect(note).to_have_count(1)
    expect(note).to_contain_text("beside")
    note.locator(".marks-words").fill("120 mm")
    note.locator(".marks-words").press("Enter")
    said(page, 'says "120 mm", as you typed')
    expect(marks.locator(".marks-offer")).to_contain_text("is 120 mm long, this picture is")
    expect(marks.locator(".marks-words")).to_have_value("120 mm")
    assert errors == []
