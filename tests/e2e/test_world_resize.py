"""The world keeps its proportions when the space it is given changes.

The rail beside the world can be dragged wider, hidden and shown again, all
without the window changing size. The camera's aspect and the canvas's
drawing buffer must follow the canvas each time, or the world is drawn
stretched; and since the world is drawn only when something in it changes, a
frame must be drawn at the new size each time, or what shows is stale.

A walkthrough's picture blanks words that differ from run to run, each blank one
width, which can give the world another size too: the picture is of the world
drawn at that size.
"""

from __future__ import annotations

import pytest
from doc_capture import WRAP_WORDS, _blanked, picture, same_picture
from playwright.sync_api import Page
from viewer_ready import settled

SIZES = """() => {
    const v = window.fractalViewer, c = v.canvas, r = v.renderer;
    return {
        width: c.clientWidth, height: c.clientHeight,
        aspect: v.camera.aspect,
        bufferWidth: c.width / r.getPixelRatio(), bufferHeight: c.height / r.getPixelRatio(),
    };
}"""


# The world is drawn only when something in it changes (render on demand): a new size
# must be drawn, a frame at the canvas's new drawing-buffer size.
DRAWN = """(before) => {
    const v = window.fractalViewer, c = v.canvas;
    return v.framesDrawn > before && v.drawnAt && v.drawnAt[0] === c.width && v.drawnAt[1] === c.height;
}"""


def _frames(page: Page) -> int:
    return page.evaluate("() => window.fractalViewer.framesDrawn")


def _in_step(page: Page, frames_before: int | None = None) -> dict:
    """Wait until the camera and the drawing buffer agree with the canvas, and, given the
    frames drawn before the change, until a frame is drawn at the new size; return its
    sizes."""
    if frames_before is not None:
        page.wait_for_function(DRAWN, arg=frames_before, timeout=5000)
    page.wait_for_function(
        f"""() => {{
            const s = ({SIZES})();
            return s.width > 0 && s.height > 0
                && Math.abs(s.aspect - s.width / s.height) < 1e-3
                && Math.abs(s.bufferWidth - s.width) <= 1 && Math.abs(s.bufferHeight - s.height) <= 1;
        }}""",
        timeout=5000,
    )
    return page.evaluate(SIZES)


@pytest.mark.e2e
def test_the_world_keeps_its_aspect_as_the_rail_changes(page: Page, base_url: str):
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(f"{base_url}/viewer/sites/garage")
    settled(page)
    first = _in_step(page)

    # Dragging the rail's edge toward the world makes the world narrower.
    edge = page.locator(".panel-rail-resizer").bounding_box()
    assert edge, "the rail has an edge to drag"
    x, y = edge["x"] + edge["width"] / 2, edge["y"] + edge["height"] / 2
    before = _frames(page)
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x - 160, y, steps=8)
    page.mouse.up()
    narrower = _in_step(page, before)
    assert narrower["width"] < first["width"] - 100, (first, narrower)

    # Hiding the rail gives the world the page's width; showing it gives it back.
    before = _frames(page)
    page.locator(".panel-rail-hide").click()
    wider = _in_step(page, before)
    assert wider["width"] > narrower["width"] + 100, (narrower, wider)
    before = _frames(page)
    page.keyboard.press("Backquote")  # the tilde key shows the rail again
    again = _in_step(page, before)
    assert abs(again["width"] - narrower["width"]) <= 2, (narrower, again)


# A status line naming a folder by a path long enough to take rows of its own, as Part ›
# Save names the server's clone, and the blank a walkthrough's picture puts on it.
FOLDER = "/" + "/".join(["a-folder-named-at-length"] * 16) + "/server1/variants.git"
FOLDER_BLANKED = (("#status", r"/\S+/variants\.git"),)


@pytest.mark.e2e
def test_a_picture_with_words_blanked_is_of_the_world_drawn_at_the_size_they_leave_it(
    page: Page, base_url: str
):
    """The path blanked, the status line takes fewer rows in the picture than on the
    screen, so the world above it is taller there, and a canvas given a new size is
    cleared until a frame is drawn at it. The picture is that frame: the page as it
    shows once it has drawn under the same blank."""
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(f"{base_url}/viewer/sites/garage")
    settled(page)
    page.evaluate(
        "(said) => window.fractalViewer.setStatus(said, 'success')",
        f"Saved: the ref is in {FOLDER}, not this checkout",
    )
    settled(page)
    on_screen = _in_step(page)
    shot = picture(page, FOLDER_BLANKED)

    # The page back as it shows, then the same blank put in it, and a frame drawn at the
    # size it leaves waited for.
    settled(page)
    assert _in_step(page)["height"] == on_screen["height"]
    page.evaluate(WRAP_WORDS, [list(b) for b in FOLDER_BLANKED])
    before = _frames(page)
    style = page.add_style_tag(content=_blanked(FOLDER_BLANKED))
    try:
        blanked = _in_step(page, before)
        settled(page)
        drawn = page.screenshot()
    finally:
        style.evaluate("(tag) => tag.remove()")
        page.evaluate("() => window.__unblank()")
    assert blanked["height"] > on_screen["height"], (on_screen, blanked)
    assert same_picture(shot, drawn), "the picture is not of the world drawn at its size"
