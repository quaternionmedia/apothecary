"""A camera in the browser, at the place it is pinned: the camera's first sanity check
is to record its own surroundings.

Runs against the shared test server (its picture folder is a temp folder the
fixture names) in a browser of its own, launched with Chromium's fake camera
(the `camera_page` fixture in conftest) so there is a camera to pin, to see
live and to keep a frame from on every machine, and no real camera is ever
opened by a test. The camera's verbs are its host's ring's (Camera › Pin here,
Live, Look, Keep, Unpin); tests/e2e/test_the_loop.py takes a look with them.

What the browser put here, it can take back: the bench walkthrough
(test_docs_bench_walkthrough.py) is that check.
"""

from __future__ import annotations

import re

import pytest
from PIL import Image
from playwright.sync_api import expect

WEDGES = (
    "() => Object.fromEntries([...document.querySelectorAll('#ring-overlay .wedge')]"
    ".filter((w) => !w.classList.contains('empty'))"
    ".map((w) => [w.dataset.cell, w.getAttribute('aria-label')]))"
)


# Whether each camera's frustum is drawn (picture_marks.js).
FRUSTA = (
    "() => window.apothecaryPictures.state().filter((e) => e.frustum).map((e) => e.frustum.visible)"
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
def test_a_camera_is_pinned_at_the_bench_and_records_its_surroundings(
    camera_page, base_url: str, picture_folder, leaves_no_trace
):
    """From the bench's own ring: the browser's camera pinned there (a badge and a
    frustum, kept for every browser), shown live on the bench's mat, a frame kept on
    this machine under its camera's id, and unpinned again -- no panel, no site
    switched."""
    page = camera_page
    before = leaves_no_trace
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"{base_url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=20000)
    page.evaluate("() => localStorage.removeItem('apothecary.panels')")
    url = page.url
    status = page.locator("#status")

    def ring_on(path):
        page.locator(f"#contents-list .contents-item[data-path='{path}']").click(button="right")
        expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)

    def press(label):
        page.wait_for_function(
            "(label) => [...document.querySelectorAll('#ring-overlay .wedge')]"
            ".some((w) => w.getAttribute('aria-label') === label)",
            arg=label,
            timeout=5000,
        )
        page.keyboard.press(_cell(page, label))

    # Camera › Pin here names this browser's cameras once it is allowed to.
    page.evaluate("() => window.apothecaryPictureVerbs.ready")
    mine = page.evaluate("() => window.apothecaryPictureVerbs.state.cameras[0]")
    assert mine and mine["id"]
    ring_on("workbench")
    press("Camera")
    press("Pin here")
    press(page.evaluate(WEDGES)["8"])
    expect(status).to_contain_text("pinned at workbench", timeout=5000)
    expect(status).not_to_have_class(re.compile(r"\berror\b"))
    expect(page.locator(".world-badge.place-mark.has-camera")).to_be_visible(timeout=5000)
    assert page.evaluate(FRUSTA) == [True]
    cameras = page.request.get(f"{base_url}/cameras?site=garage").json()
    assert [(c["id"], c["path"]) for c in cameras] == [(mine["id"], "workbench")]
    assert page.locator(".panel[data-panel='camera']").count() == 0  # never opened

    # Choosing pieces asks nothing about cameras: the page already knows.
    asked = []

    def camera_request(request):
        if "/cameras" in request.url:
            asked.append(request.url)

    page.on("request", camera_request)
    for path in ("printer_1", "workbench"):
        page.locator(f"#contents-list .contents-item[data-path='{path}']").click()
    with page.expect_request("**/health"):
        page.evaluate("() => fetch('/health')")
    page.remove_listener("request", camera_request)
    assert asked == []

    # The mark follows the focus: looking into another piece, neither the badge
    # nor the frustum stays behind; zooming back out brings both back.
    page.evaluate("() => window.fractalViewer.zoomIn('printer_1')")
    expect(page.locator(".world-badge.place-mark.has-camera")).to_be_hidden(timeout=5000)
    assert page.evaluate(FRUSTA) == [False]
    page.evaluate("() => window.fractalViewer.zoomOut()")
    expect(page.locator(".world-badge.place-mark.has-camera")).to_be_visible(timeout=5000)
    assert page.evaluate(FRUSTA) == [True]

    # Live: the video is the bench's mat; selecting elsewhere ends it.
    ring_on("workbench")
    press("Camera")
    press("Live")
    page.wait_for_function(
        "() => window.apothecaryPictures.state().some((e) => e.host === 'workbench' && e.live)",
        timeout=8000,
    )
    expect(status).to_contain_text("is live on workbench")
    page.locator("#contents-list .contents-item[data-path='printer_1']").click()
    page.wait_for_function("() => window.apothecaryPictureVerbs.live() === null", timeout=3000)

    # Its own surroundings: a frame kept on this machine, named for its camera.
    ring_on("workbench")
    press("Camera")
    press("Keep")
    expect(status).to_contain_text("kept captures/", timeout=10000)
    kept = [
        p
        for p in page.request.get(f"{base_url}/photos/pictures").json()
        if p["captured"] and p["path"] not in before
    ]
    assert len(kept) == 1 and kept[0]["name"].endswith(f"-{mine['id'][:60]}.png")
    assert (picture_folder / kept[0]["path"]).is_file()
    assert page.request.get(f"{base_url}/sites/garage/attached").json()["looks"] == []

    # Unpinned from the same ring, the camera leaves the world.
    ring_on("workbench")
    press("Camera")
    press("Unpin")
    expect(page.locator(".world-badge.place-mark.has-camera")).to_have_count(0, timeout=5000)
    assert page.request.get(f"{base_url}/cameras?site=garage").json() == []
    assert page.url == url
    assert errors == []


@pytest.mark.e2e
def test_a_place_badge_selects_its_host_and_opens_nothing(
    camera_page, base_url: str, leaves_no_trace
):
    """A place badge is read, not operated: a click selects the host its camera is
    pinned at, whether the camera is this browser's or another's, on a page whose
    camera panel was never mounted, and mounts nothing and goes live nowhere."""
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
    page.evaluate("() => window.apothecaryPictures.refresh()")
    badges = page.locator(".world-badge.place-mark.has-camera")
    expect(badges).to_have_count(2, timeout=5000)
    assert page.evaluate(FRUSTA) == [True, True]

    status = page.locator("#status")
    page.locator(f".world-badge.place-mark[data-camera='{mine}']").click()
    assert page.evaluate("() => window.fractalViewer.selectedName") == "workbench"
    expect(page.locator("#selected-body [data-facts='camera']")).to_contain_text(mine[:12])
    page.locator(".world-badge.place-mark[data-camera='another_browsers_camera']").click()
    assert page.evaluate("() => window.fractalViewer.selectedName") == "printer_1"
    # Selected says whose it is, and how a picture is taken here all the same.
    expect(page.locator("#selected-body [data-facts='camera-verbs']")).to_contain_text(
        "another browser's camera: a picture is taken here with one of this browser's "
        "cameras pinned in its place (⌗ Camera › Pin here)"
    )
    assert page.evaluate("() => window.apothecaryCamera === undefined")  # never mounted
    expect(status).not_to_have_class(re.compile(r"\berror\b"))


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
