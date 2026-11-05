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


# Views whose target the orbit rounds to two neighbouring numbers in turn, every frame:
# each is a camera and a target a person's drag and wheel left. Moved to one of them from
# anywhere else, a page used to draw at full rate until its next input.
VIEWS_THAT_ROUND = [
    (
        (827.4846464530666, 1741.163449704511, 776.0549923050911),
        (32.99242313259885, 654.7572078442754, -1010.7002636794815),
    ),
    (
        (1061.8675776762364, 2061.663854859062, 1303.1651665567879),
        (32.99242313259885, 654.7572078442754, -1010.7002636794815),
    ),
    (
        (1365.395752661731, 2476.71499595963, 1985.7779676338632),
        (32.99242313259885, 654.7572078442754, -1010.7002636794814),
    ),
    (
        (920.5706972623743, 1868.4513748231427, 985.3987538428171),
        (32.99242313259885, 654.7572078442754, -1010.7002636794814),
    ),
]


@pytest.mark.e2e
@pytest.mark.parametrize(("camera", "target"), VIEWS_THAT_ROUND)
def test_a_view_left_alone_draws_nothing_whatever_its_numbers_round_to(
    page: Page, base_url: str, camera, target
):
    """Nothing moves, so nothing draws, for every view: the camera stays exactly where
    it is, and a settled page's wait for it ends at once rather than at its bound."""
    _open(page, base_url)
    page.evaluate(
        """([camera, target]) => {
            const v = window.fractalViewer;
            v.camera.position.set(...camera);
            v.orbitControls.target.set(...target);
            v.invalidate();
        }""",
        [camera, target],
    )
    page.wait_for_timeout(300)
    assert _drawn_while(page, 800) == 0
    moved = page.evaluate(
        """() => new Promise((done) => {
            const v = window.fractalViewer;
            const view = () => [...v.camera.position.toArray(), ...v.orbitControls.target.toArray()].join();
            const was = view();
            requestAnimationFrame(() => requestAnimationFrame(() => done(view() !== was)));
        })"""
    )
    assert not moved


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
