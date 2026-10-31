"""The Working space: a printer's hour, kept from its polls and its cameras.

printer_1's board is the simulated Ender, printing. Three cameras look at
printer_1 -- one browser's three fake devices, each told to one -- as the bench
plan has the Ender's three: the bed, the head, the room. Camera › Workspace on
printer_1's ring opens the Working space on it: the window watches the board, and with a poll
it keeps a frame from each camera, so every camera's row fills; a frame opens its
evidence, and its poll every line the printer sent. Panels › Site › Workspace opens
it on the whole site, every subject the log has said of.

What the window shows is recorded as ``working-space.png`` in the test's own
temporary folder, and never compared.
"""

from __future__ import annotations

import httpx
import pytest
from boards import PRINTER
from browsers import launch
from garage import open_garage, said
from playwright.sync_api import expect
from rings import on_row, on_world

CAMERAS = 3


@pytest.fixture(scope="module")
def _three_camera_browser(browser_type):
    browser = launch(
        browser_type,
        args=[
            "--use-fake-ui-for-media-stream",
            f"--use-fake-device-for-media-stream=device-count={CAMERAS}",
        ],
    )
    yield browser
    browser.close()


@pytest.fixture
def page(_three_camera_browser, base_url):
    """A page of the three-camera browser, the camera allowed, under the name the
    garage fixture expects."""
    context = _three_camera_browser.new_context(
        viewport={"width": 1280, "height": 900}, base_url=base_url
    )
    context.grant_permissions(["camera"], origin=base_url)
    yield context.new_page()
    context.close()


@pytest.fixture
def three_cameras_on_printer_1(page, base_url, leaves_garage_as_found):
    """printer_1 pinned to the simulated Ender and three cameras added above it, each
    told one of this browser's devices; the pin taken back after."""
    with httpx.Client(base_url=base_url, timeout=15.0) as http:
        http.put(
            "/sites/garage/nodes/printer_1/device", json={"identity": PRINTER}
        ).raise_for_status()
        names = [
            http.post("/sites/garage/cameras", json={"host": "printer_1"}).json()["camera"]["name"]
            for _ in range(CAMERAS)
        ]
    open_garage(page, base_url)
    page.wait_for_function("() => window.apothecaryPictureVerbs.state.cameras.length >= 3")
    # Chosen in the page, as a camera's Device chooses one: a test browser names its
    # devices afresh at each load, so they are chosen in the load that uses them.
    devices = page.evaluate("() => window.apothecaryPictureVerbs.state.cameras")
    for name, device in zip(names, devices, strict=False):
        page.evaluate(
            "([n, id]) => window.apothecaryPictureVerbs.chooseDevice(n, id)", [name, device["id"]]
        )
    yield names
    with httpx.Client(base_url=base_url, timeout=15.0) as http:
        http.delete("/firmware/pins/garage/printer_1")
        http.post("/firmware/printers/release", json={"port": PRINTER})


@pytest.mark.e2e
def test_a_printers_working_space_keeps_a_frame_from_each_camera_with_its_polls(
    page, base_url, three_cameras_on_printer_1, tmp_path
):
    names = three_cameras_on_printer_1
    on_row(page, "printer_1", "Camera", "Workspace")
    said(page, "printer_1's hour in the Working space, a frame set kept from")
    window = page.locator(".working-space")
    expect(window.locator(".ws-title")).to_have_text("garage › printer_1")

    # A poll, then a frame from each camera kept with it: every row has one.
    for name in names:
        row = window.locator(f".ws-camera-row[data-camera='{name}'] .ws-frame")
        expect(row.first).to_be_visible(timeout=20000)
    seen = page.request.get(f"{base_url}/sites/garage/evidence").json()
    kept = [f for f in seen["frames"] if "garage:printer_1" in f["subjects"]]
    assert {f["camera"] for f in kept} == set(names)
    assert len({f["poll"] for f in kept[: len(names)]}) == 1  # one set, one poll

    # The printer's state, measured, heard; its heaters drawn over the hour.
    state = window.locator(".ws-property", has_text="state").first
    expect(state).to_contain_text("printing")
    expect(state).to_contain_text("measured")
    expect(window.locator("path.ws-hotend")).to_have_count(1)

    # A frame opens its evidence, and its poll every line the printer sent.
    window.locator(".ws-frame").first.click()
    opened = window.locator(".ws-evidence")
    expect(opened.locator("img.ws-frame-large")).to_be_visible()
    opened.locator("a[data-poll]").click()
    expect(opened.locator("pre")).to_contain_text("ok T:")

    # Maximised, as a double-click on its tab does, for its picture; then back.
    tab = page.locator(".lm_tab", has_text="Working space")
    tab.dblclick()
    page.screenshot(path=tmp_path / "working-space.png")
    tab.dblclick()

    # Panels › Site › Workspace: the whole site, every subject the log has said of.
    on_world(page, "Panels", "Site", "Workspace")
    said(page, "the Working space of garage")
    expect(window.locator(".ws-title")).to_have_text("garage")
    expect(window.locator(".ws-subject", has_text="garage:printer_1#heater:bed")).to_be_visible()
