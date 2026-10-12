"""The world keeps its proportions when the space it is given changes.

The rail beside the world can be dragged wider, hidden and shown again, all
without the window changing size. The camera's aspect and the canvas's
drawing buffer must follow the canvas each time, or the world is drawn
stretched; and since the world is drawn only when something in it changes, a
frame must be drawn at the new size each time, or what shows is stale.
"""

from __future__ import annotations

import pytest
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
