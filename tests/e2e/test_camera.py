"""The photo workflow from the browser, with a camera: the camera's first sanity check
is to record its own surroundings.

Runs against the shared test server (its picture folder is a temp folder the
fixture names) in a browser of its own, launched with Chromium's fake camera
-- a synthetic picture with colour bars and a moving mark -- so there is a
camera to allow, to see live, to capture from and to place in the world on
every machine, and no real camera is ever opened by a test.
"""

from __future__ import annotations

import time

import pytest
from PIL import Image, ImageDraw
from playwright.sync_api import expect

FAKE_CAMERA = ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"]
WEDGES = (
    "() => Object.fromEntries([...document.querySelectorAll('#ring-overlay .wedge')]"
    ".filter((w) => !w.classList.contains('empty'))"
    ".map((w) => [w.dataset.cell, w.getAttribute('aria-label')]))"
)


def _cell(page, label: str) -> str:
    """The keypad cell of the wedge with this label on the open ring."""
    return next(cell for cell, got in page.evaluate(WEDGES).items() if got == label)


@pytest.fixture
def camera_page(browser_type, base_url):
    browser = browser_type.launch(args=FAKE_CAMERA)
    context = browser.new_context(viewport={"width": 1280, "height": 800}, base_url=base_url)
    context.grant_permissions(["camera"], origin=base_url)
    page = context.new_page()
    yield page
    context.close()
    browser.close()


@pytest.mark.e2e
def test_a_camera_records_its_own_surroundings(camera_page, base_url: str, picture_folder):
    """Allow, see it live, place it in the world, capture a frame that is kept on this
    machine, look at it and open what the finder made of it in the world; then gather
    two captures and open them as one arrangement -- all from the browser."""
    page = camera_page
    # Two drawn pictures of one bench in the folder, beside what the camera will
    # capture: the fake camera's frame is a test pattern the finder reads little
    # from, and a gathering needs pictures it can read to have anything to say.
    for name in ("bench.png", "bench_again.png"):
        drawn = Image.new("L", (640, 480), 245)
        pen = ImageDraw.Draw(drawn)
        pen.rectangle((40, 40, 260, 160), fill=30)
        pen.ellipse((360, 60, 520, 220), fill=20)
        pen.polygon([(80, 420), (300, 420), (190, 280)], fill=25)
        drawn.save(picture_folder / name)
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"{base_url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=20000)
    page.evaluate("() => localStorage.removeItem('apothecary.panels')")

    # The panel, from the ring's Panels cell, and the cameras once allowed.
    page.locator("#viewer-canvas").click(button="right", position={"x": 30, "y": 30})
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    page.keyboard.press(_cell(page, "Panels"))
    page.keyboard.press(_cell(page, "Camera"))
    panel = page.locator(".panel[data-panel='camera']")
    expect(panel).to_be_visible(timeout=3000)
    expect(panel.locator("#cam-capture")).to_be_visible()
    t0 = time.monotonic()
    panel.locator("#cam-allow").click()
    page.wait_for_function(
        "() => window.apothecaryCamera && window.apothecaryCamera.live()", timeout=8000
    )
    assert time.monotonic() - t0 < 8
    expect(panel.locator("#cam-preview")).to_be_visible()
    assert page.evaluate("() => window.apothecaryCamera.state.cameras.length") >= 1
    expect(panel.locator("#cam-note")).to_contain_text("is live")

    # Placed at the workbench: a badge and a frustum in the world, kept for every browser.
    page.locator("#contents-list .contents-item[data-path='workbench']").click()
    expect(panel.locator("#cam-place")).to_be_enabled(timeout=3000)
    panel.locator("#cam-place").click()
    expect(panel.locator("#cam-place-note")).to_contain_text("placed at workbench", timeout=5000)
    expect(page.locator(".world-badge.camera")).to_be_visible(timeout=5000)
    assert page.evaluate("() => Object.keys(window.fractalViewer.cameraMarks).length") == 1
    cameras = page.request.get(f"{base_url}/cameras?site=garage").json()
    assert len(cameras) == 1 and cameras[0]["path"] == "workbench"

    # Its own surroundings: a frame kept on this machine, looked at, opened in the world.
    panel.locator("#cam-name").fill("surroundings")
    panel.locator("#cam-width").fill("800")
    t0 = time.monotonic()
    panel.locator("#cam-look").click()
    page.wait_for_function("() => window.fractalViewer.siteName === 'surroundings'", timeout=15000)
    assert time.monotonic() - t0 < 15
    kept = [p for p in page.request.get(f"{base_url}/photos/pictures").json() if p["captured"]]
    assert len(kept) == 1 and kept[0]["name"].endswith("-surroundings.png")
    assert (picture_folder / kept[0]["path"]).is_file()
    album = page.request.get(f"{base_url}/photos/surroundings").json()
    assert album["picture"].endswith("-surroundings") and album["sized"] is True
    expect(page.locator("#site-select")).to_have_value("surroundings")
    expect(panel.locator("#pic-list .pic")).to_have_count(
        3, timeout=5000
    )  # two drawn, one captured

    # Back in the garage the camera still stands where it was placed.
    page.evaluate("() => window.fractalViewer.openSite('garage')")
    page.wait_for_function("() => window.fractalViewer.siteName === 'garage'", timeout=15000)
    expect(page.locator(".world-badge.camera")).to_be_visible(timeout=5000)

    # Two captures gathered: the report, and the two opened as one arrangement.
    panel.locator("#cam-name").fill("again")
    panel.locator("#cam-capture").click()
    expect(panel.locator("#pic-list .pic")).to_have_count(4, timeout=8000)
    panel.locator("#pic-all").check()
    panel.locator("#pic-gather").click()
    expect(panel.locator("#gather-out")).to_contain_text("Groups", timeout=20000)
    expect(panel.locator("#gather-out")).to_contain_text(
        "bench"
    )  # the two drawings are of one thing
    expect(panel.locator("#gather-out details")).to_be_visible()
    panel.locator("#pic-open").click()
    try:
        page.wait_for_function(
            "() => window.fractalViewer.siteName.startsWith('gathered_')", timeout=20000
        )
    except Exception:
        raise AssertionError(
            "the gathering did not open: "
            + panel.locator("#gather-out").inner_text()[:600]
            + " | note: "
            + panel.locator("#cam-note").inner_text()
        ) from None
    assert page.request.get(
        f"{base_url}/sites/{page.evaluate('() => window.fractalViewer.siteName')}"
    ).ok

    # Unplaced, the camera leaves the world.
    page.evaluate("() => window.fractalViewer.openSite('garage')")
    page.wait_for_function("() => window.fractalViewer.siteName === 'garage'", timeout=15000)
    expect(page.locator(".world-badge.camera")).to_be_visible(timeout=5000)
    panel.locator("#cam-unplace").click()
    expect(page.locator(".world-badge.camera")).to_have_count(0, timeout=5000)
    assert page.request.get(f"{base_url}/cameras?site=garage").json() == []
    assert errors == []
