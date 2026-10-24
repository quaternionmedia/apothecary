"""The first time: a camera's device chosen from a browser that has not been asked yet.

The browser is full Chromium (Playwright's `chromium` channel, in its new
headless mode) with a fake device and no fake UI, in a context with no camera
permission (conftest's ``unasked_page``): the browser's own prompt stands, and
headless there is nobody at it, so Allow is refused at once -- what a person sees
when they dismiss the prompt. ``context.grant_permissions`` is their yes, as
answering the prompt or allowing the camera in the address bar would be.

A camera part is added above the bench with no permission at all (Camera › Add
here is the server's); what needs the browser's yes is its Device, which offers
Allow until the browser's cameras are named.

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


def _device(page, base_url: str, name: str):
    return page.request.get(f"{base_url}/sites/garage/cameras/{name}").json()["device"]


def _mine(page) -> list:
    return page.evaluate("() => window.apothecaryPictureVerbs.state.cameras")


def _add_at_the_bench(page) -> str:
    """Camera › Add here on the bench's ring, which asks the browser nothing; the
    camera it adds, selected."""
    _ring_on(page, "workbench")
    _press(page, "Camera", "Add here")
    page.wait_for_function("() => /^camera_/.test(window.fractalViewer.selectedName || '')")
    return page.evaluate("() => window.fractalViewer.selectedName")


@pytest.mark.e2e
def test_allow_before_the_yes_is_refused_and_says_what_to_do(
    page,
    base_url: str,
    leaves_garage_as_found,  # noqa: F811
):
    """Selected names the way in at a bare bench; Camera › Add here adds a camera
    without asking the browser; its Device offers Allow; Allow, with the prompt
    unanswered, is a refusal that names the prompt, the address bar and the cell to
    press again."""
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    _open_garage(page, base_url)
    page.locator("#contents-list .contents-item[data-path='workbench']").click()
    facts = page.locator("#selected-body [data-facts='way-in']")
    expect(facts).to_contain_text(
        "⌗ Camera › Add here stands a camera above workbench, looking down"
    )
    expect(facts).to_contain_text("⌗ Picture › Add pins a picture from disk")
    expect(facts).to_contain_text("m, or right-click, opens the ring")
    assert _mine(page) == []

    name = _add_at_the_bench(page)
    _ring_on(page, name)
    _press(page, "Device")
    assert _labels(page) == ["Allow"]
    _press(page, "Allow")
    status = _status(page)
    expect(status).to_contain_text(
        "Allow: the browser refused the camera (Permission denied): answer its prompt, or "
        f"allow the camera for this site in the address bar, then {name}'s Device again (⌗",
        timeout=10000,
    )
    expect(status).to_have_class(re.compile(r"\berror\b"))
    assert _device(page, base_url, name) is None
    assert errors == []


@pytest.mark.e2e
def test_the_yes_makes_the_one_camera_its_device_and_a_picture_follows(
    page,
    base_url: str,
    leaves_garage_as_found,  # noqa: F811
):
    """With the ring open at Allow, the person's yes: Allow makes the one camera the
    camera part's device at once and names Take picture; Selected says which it is;
    Take picture keeps a frame that lies on the bench, naming Find shapes."""
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    _open_garage(page, base_url)
    name = _add_at_the_bench(page)
    _ring_on(page, name)
    _press(page, "Device")
    assert _labels(page) == ["Allow"]
    page.context.grant_permissions(["camera"], origin=base_url)
    _press(page, "Allow")
    _said(page, f"{name} is ")
    (mine,) = _mine(page)
    expect(_status(page)).to_contain_text(
        f"{name} is {mine['label']}, allowed: Take picture (P) keeps a frame where it looks"
    )
    expect(page.locator("#ring-overlay")).to_have_count(0)
    assert _device(page, base_url, name) == {"id": mine["id"], "label": mine["label"]}
    expect(page.locator("#selected-body .camera-section [data-facts='device']")).to_have_text(
        mine["label"]
    )

    # Take picture: a frame kept, lying on the bench, with its camera.
    _ring_on(page, name)
    assert _labels(page)[3:] == ["Device", "Live", "Take picture", "Remove", "Part"]
    _press(page, "Take picture")
    _said(page, f"{name}'s picture lies on workbench: Picture › Find shapes")
    views = page.request.get(f"{base_url}/sites/garage/attached").json()["views"]
    assert [(vw["host"], vw["camera"]) for vw in views] == [("workbench", name)]
    assert views[0]["picture"].startswith("captures/")
    page.wait_for_function(
        "() => window.apothecaryPictures.state().some((e) => e.host === 'workbench' && e.mat)",
        timeout=10000,
    )
    assert errors == []


@pytest.mark.e2e
def test_a_yes_given_elsewhere_names_the_camera_under_device(
    page,
    base_url: str,
    leaves_garage_as_found,  # noqa: F811
):
    """The camera allowed for the site with no ring open -- the address bar's way:
    the page notices, and the camera part's next Device names the camera in place
    of Allow, and chooses it."""
    _open_garage(page, base_url)
    name = _add_at_the_bench(page)
    _ring_on(page, name)
    _press(page, "Device")
    assert _labels(page) == ["Allow"]
    page.keyboard.press("Escape")
    expect(page.locator("#ring-overlay")).to_have_count(0)
    assert not page.evaluate("() => window.apothecaryPictureVerbs.state.asked")

    page.context.grant_permissions(["camera"], origin=base_url)
    # Chromium says so on the permission status, and the cameras are named.
    page.wait_for_function("() => window.apothecaryPictureVerbs.state.asked", timeout=5000)
    (mine,) = _mine(page)
    _ring_on(page, name)
    _press(page, "Device")
    labels = _labels(page)
    assert labels != ["Allow"] and len(labels) == 1, labels
    _press(page, labels[0])
    _said(page, f"{name} is {mine['label']}")
    assert _device(page, base_url, name)["id"] == mine["id"]


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
def test_with_several_cameras_allow_reopens_the_ring_at_device(_two_camera_browser, base_url: str):
    """The yes names two cameras: Allow chooses neither, says so, and the camera's
    ring opens again at its Device with both to choose from, so the choice is made
    without another trip."""
    context = _two_camera_browser.new_context(
        viewport={"width": 1280, "height": 800}, base_url=base_url
    )
    page = context.new_page()
    api = page.request
    added = None
    try:
        _open_garage(page, base_url)
        added = _add_at_the_bench(page)
        _ring_on(page, added)
        _press(page, "Device")
        assert _labels(page) == ["Allow"]
        context.grant_permissions(["camera"], origin=base_url)
        _press(page, "Allow")
        _said(page, f"2 cameras allowed: choose which is {added}")
        expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
        expect(page.locator("#ring-overlay .title")).to_have_text("Device")
        labels = _labels(page)
        assert len(labels) == 2 and "Allow" not in labels, labels
        assert _device(page, base_url, added) is None
        mine = _mine(page)
        assert len(mine) == 2
        _press(page, labels[1])
        _said(page, f"{added} is {mine[1]['label']}")
        assert _device(page, base_url, added)["id"] == mine[1]["id"]
    finally:
        if added:
            api.delete(f"{base_url}/sites/garage/cameras/{added}")
        api.post(f"{base_url}/sites/garage/reset")
        context.close()
