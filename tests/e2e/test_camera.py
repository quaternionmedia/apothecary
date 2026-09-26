"""The photo workflow from the browser, with a camera: the camera's first sanity check
is to record its own surroundings.

Runs against the shared test server (its picture folder is a temp folder the
fixture names) in a browser of its own, launched with Chromium's fake camera
(the `camera_page` fixture in conftest) so there is a camera to allow, to see
live, to capture from and to place in the world on every machine, and no real
camera is ever opened by a test.
"""

from __future__ import annotations

import re
import time

import pytest
from PIL import Image, ImageDraw
from playwright.sync_api import expect

WEDGES = (
    "() => Object.fromEntries([...document.querySelectorAll('#ring-overlay .wedge')]"
    ".filter((w) => !w.classList.contains('empty'))"
    ".map((w) => [w.dataset.cell, w.getAttribute('aria-label')]))"
)


def _take_back_every_pin(page, base_url: str) -> None:
    """No pins at all, whatever an earlier test in this session left behind."""
    for pin in page.request.get(f"{base_url}/firmware/pins").json()["pins"]:
        page.request.delete(f"{base_url}/firmware/pins/{pin['site']}/{pin['path']}")


def _cell(page, label: str) -> str:
    """The keypad cell of the wedge with this label on the open ring."""
    return next(cell for cell, got in page.evaluate(WEDGES).items() if got == label)


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
    expect(page.locator(".world-badge.camera-mark")).to_be_visible(timeout=5000)
    assert page.evaluate("() => Object.keys(window.fractalViewer.cameraMarks).length") == 1
    cameras = page.request.get(f"{base_url}/cameras?site=garage").json()
    assert len(cameras) == 1 and cameras[0]["path"] == "workbench"

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
    expect(page.locator(".world-badge.camera-mark")).to_be_visible(timeout=5000)

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
    expect(page.locator(".world-badge.camera-mark")).to_be_visible(timeout=5000)
    panel.locator("#cam-unplace").click()
    expect(page.locator(".world-badge.camera-mark")).to_have_count(0, timeout=5000)
    assert page.request.get(f"{base_url}/cameras?site=garage").json() == []
    assert errors == []


@pytest.mark.e2e
def test_what_the_browser_put_here_it_can_take_back(camera_page, base_url: str, picture_folder):
    """The management controls on the same panel: pictures added from a file
    picker and kept as they were named, one forgotten from its thumbnail, every
    placed camera and every pin listed -- whatever site, even one that is gone --
    each taken back with its own button, and a purge that forgets everything the
    browser put here and nothing a person put in the folder by hand."""
    page = camera_page
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    for name in ("shelf.png", "shelf_again.png"):
        drawn = Image.new("L", (320, 240), 245)
        ImageDraw.Draw(drawn).rectangle((30, 30, 200, 120), fill=30)
        drawn.save(picture_folder / name)
    page.goto(f"{base_url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=20000)
    page.evaluate("() => window.apothecaryPanels.open('camera')")
    panel = page.locator(".panel[data-panel='camera']")
    expect(panel.locator("#pic-file")).to_be_visible(timeout=3000)
    page.wait_for_function("() => window.apothecaryCamera.state.pictures.length > 0")
    before = page.evaluate("() => window.apothecaryCamera.state.pictures.length")
    own_before = page.evaluate(
        "() => window.apothecaryCamera.state.pictures.filter((p) => !p.kept).length"
    )

    # Added from the file picker, kept under uploads/ as they were named; the
    # folder's own pictures have no forget button, the added ones do.
    panel.locator("#pic-file").set_input_files(
        [str(picture_folder / "shelf.png"), str(picture_folder / "shelf_again.png")]
    )
    expect(panel.locator("#pic-list .pic")).to_have_count(before + 2, timeout=8000)
    expect(panel.locator("#cam-note")).to_contain_text("added 2 picture(s)")
    added = [
        p for p in page.request.get(f"{base_url}/photos/pictures").json() if p["kept"] == "upload"
    ]
    assert sorted(p["path"] for p in added) == ["uploads/shelf.png", "uploads/shelf_again.png"]
    assert (picture_folder / "uploads" / "shelf.png").is_file()
    assert panel.locator("#pic-list .pic .pic-forget").count() == before - own_before + 2
    # Forgotten from its thumbnail, without ticking it.
    row = panel.locator("#pic-list .pic", has_text="shelf_again.png")
    row.locator(".pic-forget").click()
    expect(panel.locator("#pic-list .pic")).to_have_count(before + 1, timeout=5000)
    assert not (picture_folder / "uploads" / "shelf_again.png").exists()
    assert (
        page.evaluate("() => [...document.querySelectorAll('#pic-list input:checked')].length") == 0
    )

    # Every placed camera is listed, and taken back from its row.
    panel.locator("#cam-allow").click()
    page.wait_for_function(
        "() => window.apothecaryCamera && window.apothecaryCamera.live()", timeout=8000
    )
    page.locator("#contents-list .contents-item[data-path='workbench']").click()
    expect(panel.locator("#cam-place")).to_be_enabled(timeout=3000)
    panel.locator("#cam-place").click()
    expect(panel.locator("#cam-placed .kept-row")).to_have_count(1, timeout=5000)
    expect(panel.locator("#cam-placed .kept-row")).to_contain_text("garage › workbench")
    expect(page.locator(".world-badge.camera-mark")).to_be_visible(timeout=5000)
    panel.locator("#cam-placed .cam-unplace-one").click()
    expect(page.locator(".world-badge.camera-mark")).to_have_count(0, timeout=5000)
    expect(panel.locator("#cam-placed")).to_contain_text("none placed")
    assert page.request.get(f"{base_url}/cameras").json() == []

    # Every pin is listed -- this site's, and one whose site is gone -- and each
    # taken back from its row; the piece's Device section follows at once. The
    # server outlives every test in the run, so this starts from no pins rather
    # than from whatever an earlier test left pinned.
    _take_back_every_pin(page, base_url)
    r = page.request.put(
        f"{base_url}/sites/garage/nodes/esp32_blink/device", data={"identity": "aa:bb:cc:dd:ee:ff"}
    )
    assert r.ok, r.text()
    drawn = Image.new("L", (400, 300), 245)
    ImageDraw.Draw(drawn).rectangle((40, 40, 200, 160), fill=30)
    drawn.save(picture_folder / "pins_check.png")
    built = page.request.post(
        f"{base_url}/photos",
        data={"picture": "pins_check.png", "name": "pins_check", "width_mm": 400},
    )
    assert built.ok, built.text()
    piece = next(iter(built.json()["pieces"]))
    r = page.request.put(
        f"{base_url}/sites/pins_check/nodes/{piece}/device", data={"identity": "/dev/ttyNOWHERE"}
    )
    assert r.ok, r.text()
    assert page.request.delete(f"{base_url}/photos/pins_check").ok
    panel.locator("#pin-refresh").click()
    rows = panel.locator("#pin-list .kept-row")
    expect(rows).to_have_count(2, timeout=5000)
    expect(rows.filter(has_text="pins_check")).to_have_class(re.compile(r"\bstale\b"))
    expect(rows.filter(has_text="pins_check")).to_contain_text("site gone")
    # "not connected" on a machine with arduino-cli; "cannot look: ..." on one
    # without it, which is not the same thing and does not say it is.
    expect(rows.filter(has_text="esp32_blink")).to_contain_text(
        re.compile(r"not connected|cannot look:")
    )
    rows.filter(has_text="pins_check").locator(".pin-unpin").click()
    expect(rows).to_have_count(1, timeout=5000)
    page.locator("#contents-list .contents-item[data-path='esp32_blink']").click()
    expect(page.locator("#selected-body .device-section .dev-unpin")).to_be_visible(timeout=8000)
    rows.first.locator(".pin-unpin").click()
    expect(rows).to_have_count(0, timeout=5000)
    expect(panel.locator("#pin-list")).to_contain_text("none pinned")
    # The piece offers pinning again: the typed identity is there whether or not
    # this machine has a toolchain to list ports with.
    expect(page.locator("#selected-body .dev-pin-manual")).to_be_visible(timeout=3000)
    expect(page.locator("#selected-body .dev-unpin")).to_have_count(0)
    assert page.request.get(f"{base_url}/firmware/pins").json()["pins"] == []

    # Purge: everything the browser put here goes, the folder's own stay.
    page.once("dialog", lambda d: d.accept())
    panel.locator("#pic-purge").click()
    expect(panel.locator("#cam-note")).to_contain_text("of the folder's own stay", timeout=8000)
    left = page.request.get(f"{base_url}/photos/pictures").json()
    assert all(not p["kept"] for p in left)
    assert {p["name"] for p in left} >= {"shelf.png", "shelf_again.png"}
    assert not any((picture_folder / "uploads").glob("*.png"))
    assert not any((picture_folder / "captures").glob("*.png"))
    assert errors == []
