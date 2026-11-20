"""The page keeps up with a hand where a frame is slow to draw (docs/viewer.md, "How the
world is drawn"). A browser that draws the world in software takes a tenth of a second
and more for a frame, and a turn of the view is one frame after another: typing and
clicks wait behind each. So while the view turns on slow frames they are drawn coarser,
fewer pixels stretched over the canvas, and the frame the view comes to rest on is
drawn whole; what moves by itself is drawn whole and less often.

A frame is made slow here whatever draws it: each one drawn is followed by a wait, as
software drawing is, so the page measures what it would there. The tests read the
canvas's own pixels and the count of frames drawn, not a picture.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from viewer_ready import settled

V = "window.fractalViewer"
# Every frame drawn costs this long, as the time until the next one can start.
SLOW = f"""(ms) => {{
    const v = {V}, draw = v.renderer.render.bind(v.renderer);
    v.renderer.render = (...a) => {{ draw(...a); const until = performance.now() + ms; while (performance.now() < until); }};
}}"""
PIXELS = f"() => [{V}.canvas.width, Math.round({V}.canvas.clientWidth * window.devicePixelRatio), {V}.coarse]"


def _open(page: Page, url: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(url)
    expect(page.locator("#status")).to_contain_text("Loaded", timeout=30000)
    settled(page, 10)
    page.wait_for_timeout(1000)
    settled(page, 10)


def _turn(page: Page, ms: int) -> list:
    """The view dragged round for ``ms``, and the canvas's pixels read as it goes."""
    box = page.locator("canvas").first.bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    seen, moved = [], 0
    end = page.evaluate("() => performance.now()") + ms
    while page.evaluate("() => performance.now()") < end:
        moved += 9
        page.mouse.move(x + moved % 300, y + (moved // 3) % 80)
        seen.append(page.evaluate(PIXELS))
    page.mouse.up()
    return seen


@pytest.mark.e2e
def test_a_turning_view_is_drawn_coarser_on_slow_frames_and_whole_at_rest(
    page: Page, base_url: str
):
    _open(page, f"{base_url}/viewer/sites/garage")
    drawn, whole, coarse = page.evaluate(PIXELS)
    assert (drawn, coarse) == (whole, 0)

    page.evaluate(SLOW, 70)
    seen = _turn(page, 2500)
    least = min(width for width, _, _ in seen)
    assert least < whole * 0.6, f"never drawn coarser: {sorted({tuple(s) for s in seen})}"
    assert max(level for _, _, level in seen) >= 1
    # The canvas is the size it was on the page throughout: only its pixels are fewer.
    assert (
        page.evaluate(f"() => Math.round({V}.canvas.clientWidth * window.devicePixelRatio)")
        == whole
    )

    # At rest: the whole frame, drawn once more, and then nothing.
    frames = page.evaluate(f"() => {V}.framesDrawn")
    settled(page, 4)
    assert page.evaluate(PIXELS) == [whole, whole, 0]
    assert page.evaluate(f"() => {V}.framesDrawn") > frames
    still = page.evaluate(f"() => {V}.framesDrawn")
    page.wait_for_timeout(1000)
    assert page.evaluate(f"() => {V}.framesDrawn") == still


@pytest.mark.e2e
def test_what_moves_by_itself_on_slow_frames_is_drawn_whole_and_less_often(
    page: Page, base_url: str
):
    _open(page, f"{base_url}/viewer/sites/garage")
    whole = page.evaluate(PIXELS)[1]
    page.evaluate(SLOW, 70)
    # Something that moves every frame, as a machine's tool does while it prints.
    page.evaluate(
        f"""() => {{
            const v = {V}, moved = v.scene.children.find((o) => o.isGroup || o.isMesh);
            v.marks.__moving = {{ marks: {{ tick: () => {{ moved.rotation.y += 0.0005; return true; }} }}, port: null }};
        }}"""
    )
    page.wait_for_timeout(1500)  # the first frames measure what a frame costs
    before, t = page.evaluate(f"() => [{V}.framesDrawn, performance.now()]")
    page.wait_for_timeout(3000)
    after, now, cost = page.evaluate(f"() => [{V}.framesDrawn, performance.now(), {V}.frameCost]")
    page.evaluate(f"() => {{ delete {V}.marks.__moving; }}")
    drawn, took = after - before, now - t
    # It is drawn, and drawing is about one part in three of the time: under half of it.
    assert cost >= 70, cost
    assert drawn >= 3 and drawn * cost <= took / 2, (drawn, cost, took)
    assert page.evaluate(PIXELS) == [whole, whole, 0]  # whole throughout: nothing turned


# The view slid sideways at once, camera and target together, as a script or a re-centre
# does: the orbit is updated by the caller, so the page's own frame finds nothing moving.
# Called just after a frame is drawn, which is when a thing moving by itself is held back.
SLIDE_AFTER_A_DRAW = f"""async () => {{
    const v = {V};
    const seen = v.framesDrawn;
    await new Promise((done) => {{
        const wait = () => (v.framesDrawn > seen ? done() : requestAnimationFrame(wait));
        wait();
    }});
    const before = v.framesDrawn;
    const right = v.camera.matrixWorld.elements.slice(0, 3);
    for (const [i, k] of [[0, 'x'], [1, 'y'], [2, 'z']]) {{
        v.camera.position[k] += right[i] * 40;
        v.orbitControls.target[k] += right[i] * 40;
    }}
    v.orbitControls.update();
    await new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)));
    return v.framesDrawn - before;
}}"""


@pytest.mark.e2e
def test_a_view_moved_between_frames_is_drawn_at_once_though_something_else_moves(
    page: Page, base_url: str
):
    """What moves by itself is drawn one frame in three on slow frames; a view moved
    meanwhile is not held back with it, or a badge read after the move is where the view
    was (the machine's tool moves for as long as the world follows a printer printing)."""
    _open(page, f"{base_url}/viewer/sites/garage")
    page.evaluate(SLOW, 70)
    page.evaluate(
        f"""() => {{
            const v = {V}, moved = v.scene.children.find((o) => o.isGroup || o.isMesh);
            v.marks.__moving = {{ marks: {{ tick: () => {{ moved.rotation.y += 0.0005; return true; }} }}, port: null }};
        }}"""
    )
    page.wait_for_timeout(1500)  # the first frames measure what a frame costs
    assert page.evaluate(f"() => {V}.frameCost") >= 70
    try:
        for _ in range(3):
            assert page.evaluate(SLIDE_AFTER_A_DRAW) >= 1
    finally:
        page.evaluate(f"() => {{ delete {V}.marks.__moving; }}")
