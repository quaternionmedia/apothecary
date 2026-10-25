"""The world is drawn only when something in it changes (docs/viewer.md, "How the world
is drawn"): a page left alone draws nothing, so a machine drawing in software -- the
headless shell these tests run in has no GPU -- idles, and answers typing at once. What
changes draws: a selection, the view turned, the window resized.

The page counts the frames it draws (``framesDrawn``); these tests read the count,
not a picture.
"""

from __future__ import annotations

import pytest
import rings
import windows
from playwright.sync_api import Page, expect
from viewer_ready import by_hand, settled

FRAMES = "() => window.fractalViewer.framesDrawn"


def _drawn_while(page: Page, ms: int) -> int:
    before = page.evaluate(FRAMES)
    page.wait_for_timeout(ms)
    return page.evaluate(FRAMES) - before


def _open(page: Page, url: str) -> None:
    page.goto(url)
    expect(page.locator("#status")).to_contain_text("Loaded", timeout=30000)
    settled(page, 10)
    # The hint bar's fade and the badges' first placing are over.
    page.wait_for_timeout(1000)
    settled(page, 10)


@pytest.mark.e2e
def test_a_page_left_alone_draws_nothing_and_a_change_draws(page: Page, base_url: str):
    page.set_viewport_size({"width": 1280, "height": 800})
    _open(page, f"{base_url}/viewer/sites/garage")
    assert _drawn_while(page, 2000) == 0

    # A row of Site chosen: the piece selected, its edges lit, drawn; then still again.
    before = page.evaluate(FRAMES)
    page.locator("#contents-list .contents-item[data-path='workbench']").click()
    settled(page, 4)
    assert page.evaluate(FRAMES) > before
    assert _drawn_while(page, 1000) == 0

    # The view turned and brought nearer by hand: drawn as it goes, still once it rests.
    before = page.evaluate(FRAMES)
    by_hand(page, "workbench", distance=1500)
    assert page.evaluate(FRAMES) - before >= 2
    assert _drawn_while(page, 1000) == 0

    # The window resized: drawn at its new size.
    before = page.evaluate(FRAMES)
    page.set_viewport_size({"width": 1024, "height": 768})
    settled(page, 4)
    assert page.evaluate(FRAMES) > before
    assert _drawn_while(page, 1000) == 0


@pytest.mark.e2e
def test_typing_in_the_scad_editor_draws_nothing_until_it_renders(page: Page, base_url: str):
    page.set_viewport_size({"width": 1280, "height": 800})
    _open(page, f"{base_url}/viewer/sites/parts_library")
    rings.on_row(page, "calibration_cube", "Part", "Edit")
    windows.open_window(page, "part-scad")  # the part's SCAD, in its window
    code = page.locator(".scad-editor .cm-content")
    expect(code).to_be_visible(timeout=20000)
    settled(page, 6)
    page.wait_for_timeout(500)
    code.click(position={"x": 24, "y": 8})  # its first line: in view in Selected's window
    page.keyboard.press("Control+End")
    before = page.evaluate(FRAMES)
    # A comment typed a key at a time, faster than the check waits for: nothing drawn.
    for key in "// a note":
        page.keyboard.type(key)
        page.wait_for_timeout(40)
    assert page.evaluate(FRAMES) == before
