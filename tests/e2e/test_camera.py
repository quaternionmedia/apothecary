"""The photo workflow from the browser, with a camera: the camera's first sanity check
is to record its own surroundings.

Runs against the shared test server (its picture folder is a temp folder the
fixture names) in a browser of its own, launched with Chromium's fake camera
(the `camera_page` fixture in conftest) so there is a camera to allow, to see
live, to capture from and to place in the world on every machine, and no real
camera is ever opened by a test.

What the browser put here, it can take back: the bench walkthrough
(test_docs_bench_walkthrough.py) is that check.
"""

from __future__ import annotations

import re

import pytest
from PIL import Image, ImageDraw
from playwright.sync_api import expect

WEDGES = (
    "() => Object.fromEntries([...document.querySelectorAll('#ring-overlay .wedge')]"
    ".filter((w) => !w.classList.contains('empty'))"
    ".map((w) => [w.dataset.cell, w.getAttribute('aria-label')]))"
)


def _cell(page, label: str) -> str:
    """The keypad cell of the wedge with this label on the open ring."""
    return next(cell for cell, got in page.evaluate(WEDGES).items() if got == label)


@pytest.fixture
def leaves_no_trace(camera_page, base_url: str, picture_folder):
    """The pictures already in the folder; after the test, every picture, arrangement
    and camera placement it added is gone, so a later test finds the server as it
    would alone."""
    api = camera_page.request
    pictures = {p["path"] for p in api.get(f"{base_url}/photos/pictures").json()}
    sites = set(api.get(f"{base_url}/photos").json())
    cameras = {c["id"] for c in api.get(f"{base_url}/cameras").json()}
    yield pictures
    for picture in api.get(f"{base_url}/photos/pictures").json():
        if picture["path"] in pictures:
            continue
        if picture["kept"]:
            api.delete(f"{base_url}/photos/pictures/{picture['path']}")
        else:
            (picture_folder / picture["path"]).unlink(missing_ok=True)
    for site in set(api.get(f"{base_url}/photos").json()) - sites:
        api.delete(f"{base_url}/photos/{site}")
    for camera in api.get(f"{base_url}/cameras").json():
        if camera["id"] not in cameras:
            api.delete(f"{base_url}/cameras/{camera['id']}")


@pytest.mark.e2e
def test_a_camera_records_its_own_surroundings(
    camera_page, base_url: str, picture_folder, leaves_no_trace
):
    """Allow, see it live, place it in the world, capture a frame that is kept on this
    machine, look at it and open what the finder made of it in the world; then gather
    two captures and open them as one arrangement -- all from the browser."""
    page = camera_page
    before = leaves_no_trace
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
    panel.locator("#cam-allow").click()
    page.wait_for_function(
        "() => window.apothecaryCamera && window.apothecaryCamera.live()", timeout=8000
    )
    expect(panel.locator("#cam-preview")).to_be_visible()
    assert page.evaluate("() => window.apothecaryCamera.state.cameras.length") >= 1
    # Said once, in the status bar; a refusal is said there as an error.
    status = page.locator("#status")
    expect(status).to_contain_text("is live")
    expect(status).not_to_have_class(re.compile(r"\berror\b"))
    assert panel.locator("#cam-note").count() == 0
    page.evaluate("() => window.apothecaryCamera.act('unplace')")
    expect(status).to_contain_text("unplace: not now")
    expect(status).to_have_class(re.compile(r"\berror\b"))

    # Placed at the workbench: a badge and a frustum in the world, kept for every browser.
    page.locator("#contents-list .contents-item[data-path='workbench']").click()
    expect(panel.locator("#cam-place")).to_be_enabled(timeout=3000)
    panel.locator("#cam-place").click()
    expect(panel.locator("#cam-place-note")).to_contain_text("placed at workbench", timeout=5000)
    expect(page.locator(".world-badge.camera-mark")).to_be_visible(timeout=5000)
    assert page.evaluate("() => Object.keys(window.fractalViewer.cameraMarks).length") == 1
    cameras = page.request.get(f"{base_url}/cameras?site=garage").json()
    assert len(cameras) == 1 and cameras[0]["path"] == "workbench"

    # Choosing pieces redraws the placement from what the page knows, asking nothing.
    asked = []

    def camera_request(request):
        if "/cameras" in request.url:
            asked.append(request.url)

    page.on("request", camera_request)
    for path in ("printer_1", "workbench"):
        page.locator(f"#contents-list .contents-item[data-path='{path}']").click()
    expect(panel.locator("#cam-place-note")).to_contain_text("placed at workbench")
    with page.expect_request("**/health"):
        page.evaluate("() => fetch('/health')")
    page.remove_listener("request", camera_request)
    assert asked == []

    # The mark follows the focus: looking into another piece, neither the badge
    # nor the frustum stays behind; zooming back out brings both back.
    page.evaluate("() => window.fractalViewer.zoomIn('printer_1')")
    expect(page.locator(".world-badge.camera-mark")).to_be_hidden(timeout=5000)
    assert page.evaluate(
        "() => Object.values(window.fractalViewer.cameraMarks).map((l) => l.visible)"
    ) == [False]
    page.evaluate("() => window.fractalViewer.zoomOut()")
    expect(page.locator(".world-badge.camera-mark")).to_be_visible(timeout=5000)
    assert page.evaluate(
        "() => Object.values(window.fractalViewer.cameraMarks).map((l) => l.visible)"
    ) == [True]

    # Its own surroundings: a frame kept on this machine, looked at, opened in the world.
    panel.locator("#cam-name").fill("surroundings")
    panel.locator("#cam-width").fill("800")
    panel.locator("#cam-look").click()
    page.wait_for_function("() => window.fractalViewer.siteName === 'surroundings'", timeout=15000)
    kept = [
        p
        for p in page.request.get(f"{base_url}/photos/pictures").json()
        if p["captured"] and p["path"] not in before
    ]
    assert len(kept) == 1 and kept[0]["name"].endswith("-surroundings.png")
    assert (picture_folder / kept[0]["path"]).is_file()
    album = page.request.get(f"{base_url}/photos/surroundings").json()
    assert album["picture"].endswith("-surroundings") and album["sized"] is True
    expect(page.locator("#site-select")).to_have_value("surroundings")
    expect(panel.locator("#pic-list .pic")).to_have_count(
        len(before) + 3, timeout=5000
    )  # two drawn, one captured

    # Back in the garage the camera still stands where it was placed.
    page.evaluate("() => window.fractalViewer.openSite('garage')")
    page.wait_for_function("() => window.fractalViewer.siteName === 'garage'", timeout=15000)
    expect(page.locator(".world-badge.camera-mark")).to_be_visible(timeout=5000)

    # Two captures gathered: the report, and the two opened as one arrangement.
    panel.locator("#cam-name").fill("again")
    panel.locator("#cam-capture").click()
    expect(panel.locator("#pic-list .pic")).to_have_count(len(before) + 4, timeout=8000)
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
            + " | status: "
            + page.locator("#status").inner_text()
        ) from None
    assert page.request.get(
        f"{base_url}/sites/{page.evaluate('() => window.fractalViewer.siteName')}"
    ).ok

    # Unplaced, the camera leaves the world.
    page.evaluate("() => window.fractalViewer.openSite('garage')")
    page.wait_for_function("() => window.fractalViewer.siteName === 'garage'", timeout=15000)
    expect(page.locator(".world-badge.camera-mark")).to_be_visible(timeout=5000)
    panel.locator("#cam-unplace").click()
    expect(page.locator(".world-badge.camera-mark")).to_have_count(0, timeout=5000)
    assert page.request.get(f"{base_url}/cameras?site=garage").json() == []
    assert errors == []


@pytest.mark.e2e
def test_a_camera_badge_shows_its_camera_before_the_panel_was_ever_opened(
    camera_page, base_url: str, leaves_no_trace
):
    """The first click on a badge, on a page whose camera panel was never mounted,
    selects the node the camera stands at and shows that camera live: the page
    waits for this browser's cameras before deciding whose camera it is. A camera
    another browser placed is refused in the status bar, as an error."""
    page = camera_page
    page.goto(f"{base_url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=20000)
    page.evaluate("() => localStorage.removeItem('apothecary.panels')")
    mine = page.evaluate(
        "async () => (await navigator.mediaDevices.enumerateDevices())"
        ".find((d) => d.kind === 'videoinput').deviceId"
    )
    assert mine
    for camera, path in ((mine, "workbench"), ("another_browsers_camera", "printer_1")):
        placed = page.request.put(
            f"{base_url}/cameras/{camera}",
            data={"label": camera[:12], "site": "garage", "path": path},
        )
        assert placed.ok, placed.text()
    # Not a reload: Chromium may hand a reloaded page other device ids.
    page.evaluate("() => window.fractalViewer.syncCameras()")
    badges = page.locator(".world-badge.camera-mark")
    expect(badges).to_have_count(2, timeout=5000)
    assert page.evaluate("() => window.apothecaryCamera === undefined")  # never mounted

    status = page.locator("#status")
    page.locator(f".world-badge.camera-mark[data-camera='{mine}']").click()
    page.wait_for_function(
        "() => window.apothecaryCamera && window.apothecaryCamera.live()", timeout=8000
    )
    assert page.evaluate("() => window.fractalViewer.selectedName") == "workbench"
    expect(status).to_contain_text("is live")
    expect(status).not_to_have_class(re.compile(r"\berror\b"))

    page.locator(".world-badge.camera-mark[data-camera='another_browsers_camera']").click()
    expect(status).to_contain_text("another browser", timeout=5000)
    expect(status).to_have_class(re.compile(r"\berror\b"))
    assert page.evaluate("() => window.fractalViewer.selectedName") == "printer_1"


@pytest.mark.e2e
def test_gather_says_what_it_refused_and_what_it_set_aside(
    camera_page, base_url: str, picture_folder, leaves_no_trace
):
    """Forty-one ticked pictures are refused with the server's sentence; a file that
    will not open is listed as set aside, with its reason, beside what was gathered."""
    page = camera_page
    for i in range(41):
        Image.new("L", (64, 48), 200 + i).save(picture_folder / f"pile_{i:02}.png")
    (picture_folder / "broken.png").write_bytes(b"not a picture at all")
    page.goto(f"{base_url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=20000)
    page.evaluate("() => window.apothecaryPanels.open('camera')")
    panel = page.locator(".panel[data-panel='camera']")
    expect(panel.locator("#pic-list .pic")).to_have_count(len(leaves_no_trace) + 42, timeout=5000)

    panel.locator("#pic-all").check()
    panel.locator("#pic-gather").click()
    expect(panel.locator("#gather-out .bad")).to_contain_text(
        "is too many: every pair is compared, so 40 is the most", timeout=10000
    )

    panel.locator("#pic-all").uncheck()
    for name in ("pile_00.png", "pile_01.png", "broken.png"):
        panel.locator(f"#pic-list input[value='{name}']").check()
    panel.locator("#pic-gather").click()
    # Blank, the two piles are set aside too: for too few shapes, and still opened.
    unopened = panel.locator("#gather-out .aside", has_text="broken")
    expect(unopened).to_contain_text("broken: the finder could not read it", timeout=20000)
    expect(panel.locator("#gather-out .aside")).to_have_count(3)
    expect(panel.locator("#gather-out")).to_contain_text("Groups")
