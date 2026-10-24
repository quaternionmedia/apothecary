"""The first time: a camera pinned from a browser that has not been asked yet.

The browser is full Chromium (Playwright's `chromium` channel, in its new
headless mode) with a fake device and no fake UI, in a context with no camera
permission (conftest's ``unasked_page``): the browser's own prompt stands, and
headless there is nobody at it, so Allow is refused at once -- what a person sees
when they dismiss the prompt. ``context.grant_permissions`` is their yes, as
answering the prompt or allowing the camera in the address bar would be.

The other camera tests run in the headless shell with the fake UI, where the
camera is allowed before the page loads and Allow never appears; nothing here is
covered there.

Every camera and view a test adds is taken back after it, and garage is reset
(tests/e2e/test_picture_in_the_world.py's fixture).
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import expect
from test_picture_in_the_world import leaves_garage_as_found  # noqa: F401 - a fixture
from test_the_loop import _labels, _open_garage, _press, _ring_on, _said, _status


@pytest.fixture
def page(unasked_page):
    """The unasked browser's page, under the name the garage fixture expects."""
    return unasked_page


def _pinned(page, base_url: str) -> list:
    return [c["path"] for c in page.request.get(f"{base_url}/cameras?site=garage").json()]


def _mine(page) -> list:
    return page.evaluate("() => window.apothecaryPictureVerbs.state.cameras")


@pytest.mark.e2e
def test_allow_before_the_yes_is_refused_and_says_what_to_do(
    page,
    base_url: str,
    leaves_garage_as_found,  # noqa: F811
):
    """Selected names the way in before anything is pinned at the bench; Camera ›
    Pin here offers Allow; Allow, with the prompt unanswered, is a refusal that
    names the prompt, the address bar and the cell to press again."""
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    _open_garage(page, base_url)
    page.locator("#contents-list .contents-item[data-path='workbench']").click()
    facts = page.locator("#selected-body [data-facts='way-in']")
    expect(facts).to_contain_text("⌗ Camera › Pin here puts this browser's camera at workbench")
    expect(facts).to_contain_text("⌗ Picture › Add pins a picture from disk")
    expect(facts).to_contain_text("m, or right-click, opens the ring")
    assert _mine(page) == []

    _ring_on(page, "workbench")
    _press(page, "Camera", "Pin here")
    assert _labels(page) == ["Allow"]
    _press(page, "Allow")
    status = _status(page)
    expect(status).to_contain_text(
        "Allow: the browser refused the camera (Permission denied): answer its prompt, or "
        "allow the camera for this site in the address bar, then Camera › Pin here again (⌗",
        timeout=10000,
    )
    expect(status).to_have_class(re.compile(r"\berror\b"))
    assert _pinned(page, base_url) == []
    assert errors == []


@pytest.mark.e2e
def test_the_yes_pins_the_one_camera_and_a_view_follows(
    page,
    base_url: str,
    leaves_garage_as_found,  # noqa: F811
):
    """With the ring open at Allow, the person's yes: Allow pins the one camera at
    the bench at once and names Take picture; Selected says what Take picture and
    Live do; Camera › Take picture takes a picture, and a view stands at the bench,
    naming Find shapes."""
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    _open_garage(page, base_url)
    _ring_on(page, "workbench")
    _press(page, "Camera", "Pin here")
    assert _labels(page) == ["Allow"]
    page.context.grant_permissions(["camera"], origin=base_url)
    _press(page, "Allow")
    _said(
        page,
        "allowed and pinned at workbench: Camera › Take picture keeps a frame and pins it here "
        "as a view",
    )
    expect(page.locator("#ring-overlay")).to_have_count(0)
    expect(page.locator(".world-badge.place-mark[data-host='workbench'].has-camera")).to_be_visible(
        timeout=5000
    )
    cameras = page.request.get(f"{base_url}/cameras?site=garage").json()
    assert [c["path"] for c in cameras] == ["workbench"]
    assert [c["id"] for c in _mine(page)] == [cameras[0]["id"]]
    expect(_status(page)).to_contain_text(f"{cameras[0]['label']} allowed and pinned")

    # Selected: the camera, and what its verbs do; the way in is no longer needed.
    expect(page.locator("#selected-body [data-facts='camera']")).to_contain_text(
        cameras[0]["label"]
    )
    verbs = page.locator("#selected-body [data-facts='camera-verbs']")
    expect(verbs).to_contain_text(
        "⌗ Camera › Take picture keeps a frame and pins it here as a view; "
        "⌗ Picture › Find shapes then finds its shapes"
    )
    expect(verbs).to_contain_text("Live shows the camera on the mat")
    expect(verbs).not_to_contain_text("Keep")
    expect(page.locator("#selected-body [data-facts='way-in']")).to_have_count(0)

    # Camera › Take picture: a frame kept and pinned at the bench, with its camera.
    _ring_on(page, "workbench")
    _press(page, "Camera")
    assert _labels(page) == ["Pin here", "Live", "Take picture", "Unpin"]
    _press(page, "Take picture")
    _said(page, "pinned at workbench as a view: Picture › Find shapes")
    views = page.request.get(f"{base_url}/sites/garage/attached").json()["views"]
    assert [(vw["host"], vw["camera"]) for vw in views] == [("workbench", cameras[0]["id"])]
    assert views[0]["picture"].startswith("captures/")
    page.wait_for_function(
        "() => window.apothecaryPictures.state().some((e) => e.host === 'workbench' && e.mat)",
        timeout=10000,
    )
    assert errors == []


@pytest.mark.e2e
def test_a_yes_given_elsewhere_names_the_camera_under_pin_here(
    page,
    base_url: str,
    leaves_garage_as_found,  # noqa: F811
):
    """The camera allowed for the site with no ring open -- the address bar's way:
    the page notices, and the next ring's Camera › Pin here names the camera in
    place of Allow, and pins it."""
    _open_garage(page, base_url)
    _ring_on(page, "workbench")
    _press(page, "Camera", "Pin here")
    assert _labels(page) == ["Allow"]
    page.keyboard.press("Escape")
    expect(page.locator("#ring-overlay")).to_have_count(0)
    assert not page.evaluate("() => window.apothecaryPictureVerbs.state.asked")

    page.context.grant_permissions(["camera"], origin=base_url)
    # Chromium says so on the permission status, and the cameras are named.
    page.wait_for_function("() => window.apothecaryPictureVerbs.state.asked", timeout=5000)
    (mine,) = _mine(page)
    _ring_on(page, "workbench")
    _press(page, "Camera", "Pin here")
    labels = _labels(page)
    assert labels != ["Allow"] and len(labels) == 1, labels
    _press(page, labels[0])
    _said(page, f"{mine['label']} pinned at workbench")
    assert _pinned(page, base_url) == ["workbench"]


@pytest.fixture(scope="module")
def _two_camera_browser(browser_type):
    """Full Chromium with two fake cameras, and no permission for either."""
    try:
        browser = browser_type.launch(
            channel="chromium", args=["--use-fake-device-for-media-stream=device-count=2"]
        )
    except PlaywrightError as exc:
        pytest.skip(
            "full Chromium (Playwright's `chromium` channel) is not installed here; "
            "`uv run playwright install chromium` installs it beside the headless shell: "
            + str(exc).splitlines()[0]
        )
    yield browser
    browser.close()


@pytest.mark.e2e
def test_with_several_cameras_allow_reopens_the_ring_at_pin_here(
    _two_camera_browser, base_url: str
):
    """The yes names two cameras: Allow pins neither, says so, and the ring opens
    again at the bench's Camera › Pin here with both to choose from, so the choice
    is made without another trip."""
    context = _two_camera_browser.new_context(
        viewport={"width": 1280, "height": 800}, base_url=base_url
    )
    page = context.new_page()
    api = page.request
    before = {c["id"] for c in api.get(f"{base_url}/cameras").json()}
    try:
        _open_garage(page, base_url)
        _ring_on(page, "workbench")
        _press(page, "Camera", "Pin here")
        assert _labels(page) == ["Allow"]
        context.grant_permissions(["camera"], origin=base_url)
        _press(page, "Allow")
        _said(page, "2 cameras allowed: choose one to pin at workbench")
        expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
        expect(page.locator("#ring-overlay .title")).to_have_text("Pin here")
        labels = _labels(page)
        assert len(labels) == 2 and "Allow" not in labels, labels
        assert _pinned(page, base_url) == []
        mine = _mine(page)
        assert len(mine) == 2
        _press(page, labels[1])
        _said(page, f"{mine[1]['label']} pinned at workbench")
        assert [c["id"] for c in api.get(f"{base_url}/cameras?site=garage").json()] == [
            mine[1]["id"]
        ]
    finally:
        for camera in api.get(f"{base_url}/cameras").json():
            if camera["id"] not in before:
                api.delete(f"{base_url}/cameras/{camera['id']}")
        context.close()
