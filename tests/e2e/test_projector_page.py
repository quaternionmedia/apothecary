"""The projector's page in a browser: black and one canvas, drawing the server's answer
for printer_1; a marker dragged and dropped keeps four points of the bed and draws the
grid through them; the machine followed as the world follows it, its polls moving
what is drawn by the surfaces' stream; a click asking for full screen; and Camera ›
Projector on printer_1's ring opening the page in a window of its own.

Runs against a server of its own: the simulated printer mid-print, pinned to
printer_1's mainboard by a test that needs it. Nothing here opens a real port, and no
pixel is judged but a corner's, which must be black.
"""

from __future__ import annotations

import httpx
import pytest
from boards import BOARD, PRINTER
from garage import open_garage
from playwright.sync_api import Page
from rings import on_row

pytestmark = pytest.mark.e2e

PAGE = "/projector/sites/garage/machines/printer_1"
ANSWER = "/sites/garage/machines/printer_1/projector"
STATS = "window.apothecaryProjector.stats()"
READY = "() => !!window.apothecaryProjector && window.apothecaryProjector.stats().key !== null"


@pytest.fixture(scope="module")
def url(start_server):
    return start_server()


@pytest.fixture(autouse=True)
def _as_it_starts(url):
    """Nothing pinned, no calibration kept, the garage rebuilt and the link released."""
    with httpx.Client(base_url=url, timeout=15.0) as http:
        for pin in http.get("/firmware/pins").json()["pins"]:
            http.delete(f"/firmware/pins/{pin['site']}/{pin['path']}").raise_for_status()
        http.delete(ANSWER).raise_for_status()
        http.post("/sites/garage/reset").raise_for_status()
        http.post("/firmware/printers/release", json={"port": PRINTER}).raise_for_status()
    yield


def _pinned_and_polled(url: str) -> None:
    """The simulated printer identified, pinned to printer_1's mainboard and polled
    once, as a person's Pin and the world's first poll do: its link held."""
    with httpx.Client(base_url=url, timeout=15.0) as http:
        http.post("/firmware/devices/identify", json={"port": PRINTER}).raise_for_status()
        http.put(f"/sites/garage/nodes/{BOARD}/device", json={"identity": PRINTER}).raise_for_status()
        http.get("/firmware/printers/status", params={"port": PRINTER}).raise_for_status()


def _open(page: Page, url: str) -> dict:
    page.goto(f"{url}{PAGE}")
    page.wait_for_function(READY, timeout=15000)
    return page.evaluate(f"() => {STATS}")


def test_the_page_is_black_and_one_canvas_and_says_it_is_not_calibrated(page: Page, url: str):
    errors: list = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    stats = _open(page, url)
    assert stats["calibrated"] is False and stats["calibrating"] is True
    assert len(stats["markers"]) == 4
    assert any(line.startswith("not calibrated") for line in stats["band"]), stats["band"]
    shape = page.evaluate(
        """() => {
            const canvas = document.querySelector('canvas'), box = canvas.getBoundingClientRect();
            const corner = canvas.getContext('2d').getImageData(1, 1, 1, 1).data;
            return {
                presses: document.querySelectorAll('button, input, select, textarea, a, form').length,
                canvases: document.querySelectorAll('canvas').length,
                body: getComputedStyle(document.body).backgroundColor,
                covers: box.width === innerWidth && box.height === innerHeight,
                corner: [...corner],
            };
        }"""
    )
    assert shape == {
        "presses": 0,
        "canvases": 1,
        "body": "rgb(0, 0, 0)",
        "covers": True,
        "corner": [0, 0, 0, 255],
    }
    assert errors == []


def test_a_marker_dropped_keeps_the_calibration_and_the_grid_is_drawn_through_it(
    page: Page, url: str
):
    _pinned_and_polled(url)
    stats = _open(page, url)
    ratio = page.evaluate("() => window.devicePixelRatio || 1")
    x, y = (v / ratio for v in stats["markers"][0])
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 30, y - 12, steps=5)
    page.mouse.up()
    page.wait_for_function(f"() => {STATS}.calibrated", timeout=10000)
    after = page.evaluate(f"() => {STATS}")
    assert after["drawn"]["grid"] > 0 and after["calibrating"] is True
    kept = httpx.get(f"{url}{ANSWER}", timeout=15.0).json()["calibration"]
    assert kept["size"] == after["size"]
    assert kept["pixels"][0] == pytest.approx([(x + 30) * ratio, (y - 12) * ratio], abs=2 * ratio)
    assert kept["bed"] == [[20, 20], [200, 20], [200, 200], [20, 200]]
    # C leaves calibrating; what the machine is about to make and its band remain.
    page.keyboard.press("c")
    assert page.evaluate(f"() => {STATS}.calibrating") is False


def test_the_machine_is_followed_and_its_polls_move_what_is_drawn(page: Page, url: str):
    """The page watches the board as the world does, live while the server holds its
    link; each poll is relayed on the stream and what moves is taken without asking
    for the answer again."""
    _pinned_and_polled(url)
    with httpx.Client(base_url=url, timeout=15.0) as http:
        body = {
            "bed": [[20, 20], [200, 20], [200, 200], [20, 200]],
            "pixels": [[300, 600], [900, 600], [900, 150], [300, 150]],
            "size": [1200, 700],
        }
        http.put(ANSWER, json=body).raise_for_status()
    _open(page, url)
    page.wait_for_function(f"() => {STATS}.live && {STATS}.port === '{PRINTER}'", timeout=15000)
    was = page.evaluate("() => window.apothecaryProjector.answer().moving.status.polled_at")
    page.wait_for_function(
        "(was) => window.apothecaryProjector.answer().moving.status.polled_at !== was",
        arg=was,
        timeout=15000,
    )
    stats = page.evaluate(f"() => {STATS}")
    assert stats["calibrated"] and stats["drawn"]["tool"] is True
    assert stats["band"][0] == page.evaluate(
        "() => window.apothecaryProjector.answer().moving.status.lines[0]"
    )


def test_a_click_asks_for_full_screen(page: Page, url: str):
    _open(page, url)
    page.evaluate(
        "() => { window.__asked = 0; document.documentElement.requestFullscreen ="
        " () => { window.__asked += 1; return Promise.resolve(); }; }"
    )
    page.mouse.click(5, 5)
    assert page.evaluate("() => window.__asked") == 1


def test_camera_projector_on_a_printer_s_ring_opens_its_page(page: Page, url: str):
    _pinned_and_polled(url)
    open_garage(page, url, settle=False)
    page.wait_for_function(
        "() => Object.values(window.fractalViewer.bindings || {}).some((r) => r.device)",
        timeout=15000,
    )
    with page.expect_popup() as opened:
        on_row(page, "printer_1", "Camera", "Projector")
    popup = opened.value
    popup.wait_for_function(READY, timeout=15000)
    assert popup.url.endswith(PAGE)
