"""The projector's page in a browser: black and one canvas, drawing the server's answer
for printer_1; a marker dragged and dropped keeps four points of the bed and draws the
grid through them; the machine followed as the world follows it, its polls moving
what is drawn by the surfaces' stream; a click asking for full screen; and Camera ›
Projector on printer_1's ring opening the page in a window of its own; a second plane,
at a known height, marked by dragging the same markers and kept, the band naming which
plane the picture is drawn for; and a printer plan's footprint drawn on the bed before
any file is sliced.

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
PLAN = "/sites/garage/machines/printer_1/plan"
# Four points of the bed, the pixels that light them on a 1200 by 700 output, and the pixels
# that light the same four on a plane 20 mm up: the picture is displaced outward from the
# point under the lens, which stands near the middle of the output.
BED = [[20, 20], [200, 20], [200, 200], [20, 200]]
FIRST = {"bed": BED, "pixels": [[300, 600], [900, 600], [900, 150], [300, 150]], "size": [1200, 700]}
SECOND = [[294, 612], [906, 612], [906, 144], [294, 144]]
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
        http.delete(PLAN).raise_for_status()
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


def _open(page: Page, url: str, query: str = "") -> dict:
    page.goto(f"{url}{PAGE}{query}")
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


def test_a_second_plane_is_marked_by_dragging_and_kept_and_the_band_names_the_plane(
    page: Page, url: str
):
    """With the bed plane calibrated the band says it is the only plane; the page opened
    for a piece 20 mm thick marks the same four points again, a drop keeps them as the second
    plane, and the band says which planes are calibrated and which the picture is drawn for."""
    _pinned_and_polled(url)
    with httpx.Client(base_url=url, timeout=15.0) as http:
        http.put(ANSWER, json=FIRST).raise_for_status()
        # The second plane's pixels are kept where they stand: only the drop below is the drag.
        ratio_free = http.get(ANSWER).json()
    assert ratio_free["plane"]["how"] == "bed plane only"
    stats = _open(page, url)
    assert any("bed plane only" in line for line in stats["band"]), stats["band"]
    assert stats["plane"] == {"z": 0.0, "for": "the bed plane", "how": "bed plane only"}

    stats = _open(page, url, "?upper=20")
    assert stats["marking"] == "upper" and stats["calibrating"] is True
    ratio = page.evaluate("() => window.devicePixelRatio || 1")
    width, height = stats["size"]
    # The markers start where the bed plane's were, scaled to this canvas; each is dragged to
    # where its cross lights the piece's top (the pixels SECOND says, scaled the same way).
    for i, (u, v) in enumerate(SECOND):
        start = stats["markers"][i]
        goal = (u * width / 1200, v * height / 700)
        x, y = start[0] / ratio, start[1] / ratio
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(goal[0] / ratio, goal[1] / ratio, steps=4)
        page.mouse.up()
        page.wait_for_function(
            f"() => window.apothecaryProjector.answer().calibration.upper !== null"
            f" && Math.abs(window.apothecaryProjector.stats().markers[{i}][0] - {goal[0]}) < 2",
            timeout=10000,
        )
    kept = httpx.get(f"{url}{ANSWER}", timeout=15.0).json()
    upper = kept["calibration"]["upper"]
    assert upper["height"] == 20.0 and upper["bed"] == BED
    for (u, v), want in zip(upper["pixels"], SECOND, strict=True):
        assert (u, v) == pytest.approx(want, abs=3.0)
    assert kept["calibration"]["pixels"] == FIRST["pixels"]
    assert kept["plane"]["heights"] == [0.0, 20.0] and kept["upper_mapping"] is not None
    page.wait_for_function(
        "() => window.apothecaryProjector.stats().plane.how === 'measured at the bed plane'",
        timeout=10000,
    )
    stats = page.evaluate(f"() => {STATS}")
    assert any("planes calibrated at 0 and 20 mm" in line for line in stats["band"]), stats["band"]
    assert not any("bed plane only" in line for line in stats["band"])
    # Asked at a height between, the server answers a plane of its own.
    between = httpx.get(f"{url}{ANSWER}", params={"height": 10}, timeout=15.0).json()["plane"]
    assert between["z"] == 10.0 and between["how"] == "between the two calibrated planes"
    # A thickness not named leaves the second plane unmarked and says so.
    page.keyboard.press("c")
    page.keyboard.press("u")
    assert page.evaluate(f"() => {STATS}.marking") == "upper"


def test_a_printer_plan_s_footprint_is_drawn_before_a_file_is_sliced(page: Page, url: str):
    _pinned_and_polled(url)
    with httpx.Client(base_url=url, timeout=15.0) as http:
        http.put(ANSWER, json=FIRST).raise_for_status()
        http.put(PLAN, json={"part": "calibration_cube", "file_id": None}).raise_for_status()
        answer = http.get(ANSWER).json()
    footprint = answer["picture"]["footprint"]
    assert footprint["source"] == "plan" and footprint["part"] == "calibration_cube"
    stats = _open(page, url)
    assert stats["drawn"]["footprint"] == 5 and stats["calibrated"] is True
    assert any(line.startswith("planned footprint of calibration_cube") for line in stats["band"])
    # No plan: nothing drawn of it.
    httpx.delete(f"{url}{PLAN}", timeout=15.0).raise_for_status()
    page.evaluate("() => window.apothecaryProjector.ask()")
    page.wait_for_function(f"() => {STATS}.drawn.footprint === 0", timeout=15000)
