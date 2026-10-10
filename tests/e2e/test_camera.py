"""A camera in the browser: a part of the site, added above a place, told which of
this browser's cameras it is, aimed by its handles, and taking pictures that lie
where it looks.

Runs against the shared test server (its picture folder is a temp folder the
fixture names) in a browser of its own, launched with Chromium's fake camera
(the `camera_page` fixture in conftest) so there is a camera to choose, to see
live and to take a picture with on every machine, and no real camera is ever
opened by a test. Camera › Add here is a place's ring's; a camera's own ring has
Device, Live or Still, Take picture, Remove and Part › Edit. Selected's Take
picture and the P key are Take picture too; tests/e2e/test_the_loop.py goes on
from a picture taken to its shapes and the pieces made from them.

Every camera, view and kept picture a test adds is taken back after it, and
garage is reset (tests/e2e/test_picture_in_the_world.py's fixture). Nothing here
reloads the page between choosing a device and using it, since Chromium may hand
a reloaded page other ids for its fake devices. The gathering is a section of
Pictures until gathering leaves core.
"""

from __future__ import annotations

import re

import pytest
from PIL import Image
from playwright.sync_api import expect
from test_picture_in_the_world import leaves_garage_as_found  # noqa: F401 - a fixture
from test_the_loop import _labels, _open_garage, _press, _ring_on, _said, _status

WEDGES = (
    "() => Object.fromEntries([...document.querySelectorAll('#ring-overlay .wedge')]"
    ".filter((w) => !w.classList.contains('empty'))"
    ".map((w) => [w.dataset.cell, w.getAttribute('aria-label')]))"
)
CAMERAS = "() => window.apothecaryPictures.cameraState()"
PLACES = "() => window.apothecaryPictures.state()"

# Where a point of the selected camera's handles is on the screen: on its turn
# ring where a turn of `deg` puts the picture's top, or on its tilt arc at a tilt
# of `deg` (the handles are drawn about the lens, in the site's frame turned to
# three.js's, y up).
HANDLE_AT = """([kind, deg]) => {
    const v = window.fractalViewer, g = v.cameraHandles;
    const cam = window.apothecaryPictures.camera(g.userData.camera);
    const t = cam.turn * Math.PI / 180, a = deg * Math.PI / 180;
    let x, y, z;
    if (kind === 'turn') { const r = g.userData.turnRadius; x = -Math.sin(a) * r; y = Math.cos(a) * r; z = 0; }
    else { const r = g.userData.tiltRadius; x = -Math.sin(t) * Math.sin(a) * r; y = Math.cos(t) * Math.sin(a) * r; z = -Math.cos(a) * r; }
    const p = g.localToWorld(v.camera.position.clone().set(x, z, y)).project(v.camera);
    const box = v.canvas.getBoundingClientRect();
    return [box.left + (p.x + 1) / 2 * box.width, box.top + (1 - p.y) / 2 * box.height];
}"""


def _cell(page, label: str) -> str:
    """The keypad cell of the wedge with this label on the open ring."""
    return next(cell for cell, got in page.evaluate(WEDGES).items() if got == label)


@pytest.fixture
def leaves_no_trace(page, base_url: str, picture_folder):
    """The pictures already in the folder; after the test, every picture, arrangement
    and camera it added is gone, so a later test finds the server as it would alone."""
    api = page.request
    pictures = {p["path"] for p in api.get(f"{base_url}/photos/pictures").json()}
    sites = set(api.get(f"{base_url}/photos").json())
    cameras = {(c["site"], c["name"]) for c in api.get(f"{base_url}/placed").json()["cameras"]}
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
    for camera in api.get(f"{base_url}/placed").json()["cameras"]:
        if (camera["site"], camera["name"]) not in cameras:
            api.delete(f"{base_url}/sites/{camera['site']}/cameras/{camera['name']}")


@pytest.fixture
def page(camera_page):
    """The fake-camera page, under the name the garage fixture expects."""
    return camera_page


def _camera(page, base_url: str, name: str) -> dict:
    return page.request.get(f"{base_url}/sites/garage/cameras/{name}").json()


def _add(page, base_url: str, host: str) -> str:
    """A camera added above ``host`` by the API, before the page is opened."""
    answer = page.request.post(f"{base_url}/sites/garage/cameras", data={"host": host})
    assert answer.status == 201, answer.text()
    return answer.json()["camera"]["name"]


def _select(page, path: str) -> None:
    page.locator(f"#contents-list .contents-item[data-path='{path}']").click()
    page.wait_for_function("(p) => window.fractalViewer.selectedName === p", arg=path)


def _pyramid(page, name: str):
    """Whether the camera's pyramid is drawn, or None while it has none."""
    for entry in page.evaluate(CAMERAS):
        if entry["camera"] == name:
            return entry["pyramid"]["visible"] if entry["pyramid"] else None
    return None


def _choose_device(page, name: str) -> dict:
    """Device › this browser's camera, from the camera's own ring: the one it names."""
    (mine,) = page.evaluate("() => window.apothecaryPictureVerbs.state.cameras")
    _ring_on(page, name)
    _press(page, "Device")
    # The ring writes a label short enough for its wedge.
    (label,) = _labels(page)
    _press(page, label)
    _said(page, f"{name} is {mine['label']}")
    return mine


def _views_by(page, base_url: str, name: str) -> list:
    views = page.request.get(f"{base_url}/sites/garage/attached").json()["views"]
    return [vw for vw in views if vw["camera"] == name]


@pytest.mark.e2e
def test_a_camera_added_at_the_bench_takes_pictures_where_it_looks(
    page,
    base_url: str,
    picture_folder,
    leaves_garage_as_found,  # noqa: F811
):
    """From the bench's ring, Camera › Add here: a camera part stands above the bench,
    selected, in Contents, with its 📷 badge, its handles and its pyramid. Its Device
    is this browser's camera; Take picture by its ring, by Selected's button and by
    P each keeps a frame that lies on the bench, named for the camera; Selected
    shows its pictures, newest first, and one clicked is drawn where it landed;
    Remove takes the camera away and leaves its pictures. No site is switched."""
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    _open_garage(page, base_url)
    url = page.url

    _ring_on(page, "workbench")
    _press(page, "Camera", "Add here")
    _said(page, "above workbench, looking straight down")
    page.wait_for_function("() => /^camera_/.test(window.fractalViewer.selectedName || '')")
    name = page.evaluate("() => window.fractalViewer.selectedName")
    expect(page.locator(f"#contents-list .contents-item[data-path='{name}']")).to_be_visible()
    badge = page.locator(f".world-badge.camera-mark[data-camera='{name}']")
    expect(badge).to_be_visible(timeout=5000)
    assert page.evaluate(
        "(n) => { const v = window.fractalViewer; return !!v.cameraHandles"
        " && v.transformControls.object && v.transformControls.object.userData.camera === n; }",
        name,
    )
    page.wait_for_function(
        "(n) => window.apothecaryPictures.cameraState()"
        ".some((c) => c.camera === n && c.pyramid && c.pyramid.visible)",
        arg=name,
    )
    section = page.locator("#selected-body .camera-section")
    expect(section.locator("[data-facts='device']")).to_contain_text("none yet")
    expect(section.locator("[data-facts='lands']")).to_have_text("lands on workbench")
    assert _camera(page, base_url, name)["lands"]["host"] == "workbench"

    # Device: this browser's camera, from the camera's own ring.
    mine = _choose_device(page, name)
    expect(section.locator("[data-facts='device']")).to_have_text(mine["label"])
    assert _camera(page, base_url, name)["device"] == {"id": mine["id"], "label": mine["label"]}

    # Take picture, three ways: its ring's cell, Selected's button, and P.
    _ring_on(page, name)
    assert _labels(page) == [
        "Zoom in",
        "Move",
        "Why this",
        "Device",
        "Live",
        "Take picture",
        "Remove",
        "Part",
    ]
    _press(page, "Take picture")
    _said(page, f"{name}'s picture lies on workbench: Picture › Find shapes finds what is in it")
    expect(_status(page)).not_to_have_class(re.compile(r"\berror\b"))
    assert page.evaluate("() => window.fractalViewer.selectedName") == name
    expect(section.locator(".cam-take")).to_have_attribute("data-address", re.compile(r"\d+"))
    section.locator(".cam-take").click()
    page.wait_for_function(
        "(n) => window.apothecaryPictures.viewsBy(n).length === 2", arg=name, timeout=10000
    )
    page.locator("#viewer-canvas").focus()
    page.keyboard.press("p")
    page.wait_for_function(
        "(n) => window.apothecaryPictures.viewsBy(n).length === 3", arg=name, timeout=10000
    )
    views = _views_by(page, base_url, name)
    assert [vw["host"] for vw in views] == ["workbench"] * 3
    kept = {p["path"]: p for p in page.request.get(f"{base_url}/photos/pictures").json()}
    for vw in views:
        assert vw["picture"].startswith("captures/") and f"garage--{name}." in vw["picture"]
        assert kept[vw["picture"]]["camera"] == {"site": "garage", "name": name}
        assert (picture_folder / vw["picture"]).is_file()
    # The newest lies on the bench, its ▣ badge naming the camera that took it.
    page.wait_for_function(
        "(id) => window.apothecaryPictures.state().some((e) => e.host === 'workbench' && e.view === id)",
        arg=views[-1]["id"],
    )
    expect(page.locator(".world-badge.place-mark[data-host='workbench']")).to_contain_text(
        f"by {name}"
    )

    # Selected's thumbnails: newest first, the drawn one marked; the oldest clicked
    # is drawn on the bench, and the camera stays selected.
    thumbs = section.locator(".camera-thumbs .cam-thumb")
    expect(thumbs).to_have_count(3)
    assert thumbs.evaluate_all("(ts) => ts.map((t) => t.dataset.view)") == [
        vw["id"] for vw in reversed(views)
    ]
    expect(thumbs.first).to_have_class(re.compile(r"\bdrawn\b"))
    thumbs.last.click()
    page.wait_for_function(
        "(id) => window.apothecaryPictures.state().some((e) => e.host === 'workbench' && e.view === id)",
        arg=views[0]["id"],
    )
    expect(section.locator(".camera-thumbs .cam-thumb").last).to_have_class(
        re.compile(r"\bdrawn\b")
    )
    assert page.evaluate("() => window.fractalViewer.selectedName") == name

    # Remove: the camera goes, its pictures stay, and so does the page.
    _ring_on(page, name)
    _press(page, "Remove")
    _said(page, f"removed {name}; the pictures it took, and the pieces made from them, stay")
    expect(badge).to_have_count(0, timeout=5000)
    expect(page.locator(f"#contents-list .contents-item[data-path='{name}']")).to_have_count(0)
    assert page.request.get(f"{base_url}/sites/garage/cameras/{name}").status == 404
    assert len(page.request.get(f"{base_url}/sites/garage/attached").json()["views"]) >= 3
    assert page.url == url
    assert errors == []


def _drag(page, kind: str, degrees: list) -> None:
    """A press on the handle at the first of ``degrees``, moved through the rest, let go."""
    points = [page.evaluate(HANDLE_AT, [kind, d]) for d in degrees]
    page.mouse.move(*points[0])
    page.mouse.down()
    for point in points[1:]:
        page.mouse.move(*point, steps=3)
    page.mouse.up()


@pytest.mark.e2e
def test_a_cameras_ring_and_arc_turn_and_tilt_it_and_its_picture_lies_as_the_server_lays_it(
    page,
    base_url: str,
    leaves_garage_as_found,  # noqa: F811
):
    """The selected camera's turn ring and tilt arc: dragged, the camera turns or tilts
    as the pointer goes, its pyramid with it, and on release the pose is the
    server's; nothing else is selected or moved. A picture taken tilted lies where
    the server lays it: the mat's corners on the page are the server's corners."""
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    name = _add(page, base_url, "workbench")
    _open_garage(page, base_url)
    _select(page, name)
    page.wait_for_function(
        "(n) => window.fractalViewer.cameraHandles?.userData.camera === n", arg=name
    )
    assert _pyramid(page, name) is True
    ends = lambda: next(c for c in page.evaluate(CAMERAS) if c["camera"] == name)["pyramid"]["ends"]  # noqa: E731
    straight_down = ends()

    # A quarter turn clockwise, seen from above: the picture's top goes from +y to +x,
    # away from the wall behind the bench.
    with page.expect_response(lambda r: r.url.endswith(f"/cameras/{name}/pose")) as posed:
        _drag(page, "turn", [0, -30, -60, -90])
    assert posed.value.ok
    turned = _camera(page, base_url, name)
    assert turned["turn"] == pytest.approx(270, abs=6), turned
    assert turned["tilt"] == 0
    _said(page, f"{name} turned to")
    assert page.evaluate("() => window.fractalViewer.selectedName") == name
    # Straight down, a turn spins the picture about its middle: the same patch, turned.
    page.wait_for_function(
        "(n) => window.fractalViewer.cameraHandles?.userData.camera === n", arg=name
    )

    # Tilted toward the picture's top, from the knob straight below the lens.
    with page.expect_response(lambda r: r.url.endswith(f"/cameras/{name}/pose")) as posed:
        _drag(page, "tilt", [0, 10, 20, 30])
    assert posed.value.ok
    tilted = _camera(page, base_url, name)
    assert tilted["tilt"] == pytest.approx(30, abs=6), tilted
    assert tilted["lands"] is not None, tilted
    assert tilted["turn"] == pytest.approx(turned["turn"])
    _said(page, f"{name} tilted")
    page.wait_for_function("(n) => window.apothecaryPictures.camera(n).tilt > 0", arg=name)
    assert ends() != straight_down
    assert _pyramid(page, name) is True

    # A picture taken tilted: the page lays its corners where the server does.
    _choose_device(page, name)
    page.locator("#selected-body .camera-section .cam-take").click()
    page.wait_for_function(
        "(n) => window.apothecaryPictures.viewsBy(n).length === 1", arg=name, timeout=10000
    )
    (view,) = _views_by(page, base_url, name)
    assert view["host"] == tilted["lands"]["host"]
    assert view["taken"]["tilt"] == pytest.approx(tilted["tilt"])
    page.wait_for_function(
        "(id) => window.apothecaryPictures.state().some((e) => e.view === id && e.mat)",
        arg=view["id"],
    )
    drawn = next(e for e in page.evaluate(PLACES) if e["view"] == view["id"])
    server = view["mat"]["corners"]
    assert all(c is not None for c in server), server
    for got, want in zip(drawn["mat"]["corners"], server, strict=True):
        assert got[:2] == pytest.approx(want[:2], abs=0.5), (drawn["mat"]["corners"], server)
    # Tilted, it is no rectangle: the far edge is the wider.
    near = abs(server[2][0] - server[3][0]) + abs(server[2][1] - server[3][1])
    far = abs(server[0][0] - server[1][0]) + abs(server[0][1] - server[1][1])
    assert far > near * 1.05, server
    assert errors == []


@pytest.mark.e2e
def test_a_device_is_one_cameras_at_a_time(
    page,
    base_url: str,
    leaves_garage_as_found,  # noqa: F811
):
    """Device › this browser's camera, chosen for a second camera, is taken off the
    first: the status says so, the first says it has no device, in Selected and on
    its badge."""
    first = _add(page, base_url, "workbench")
    second = _add(page, base_url, "printer_1")
    _open_garage(page, base_url)
    _choose_device(page, first)
    mine = _choose_device(page, second)
    expect(_status(page)).to_contain_text(f", taken off {first}")
    assert _camera(page, base_url, first)["device"] is None
    assert _camera(page, base_url, second)["device"]["id"] == mine["id"]
    expect(page.locator(f".world-badge.camera-mark[data-camera='{first}']")).to_contain_text(
        "no device yet"
    )
    _select(page, first)
    expect(page.locator("#selected-body .camera-section [data-facts='device']")).to_contain_text(
        "none yet"
    )


@pytest.mark.e2e
def test_a_cameras_pyramid_shows_while_it_is_selected_or_live(
    page,
    base_url: str,
    leaves_garage_as_found,  # noqa: F811
):
    """Unselected, a camera is its body and its latest picture; selected, or live, its
    pyramid shows from its lens to where it looks. Live, Selected shows its video."""
    name = _add(page, base_url, "workbench")
    _open_garage(page, base_url)
    page.wait_for_function("(n) => window.apothecaryPictures.camera(n) !== null", arg=name)
    assert _pyramid(page, name) is False
    _select(page, name)
    assert _pyramid(page, name) is True
    _select(page, "workbench")
    assert _pyramid(page, name) is False

    _choose_device(page, name)
    _ring_on(page, name)
    _press(page, "Live")
    _said(page, f"{name} is live where it looks")
    page.wait_for_function(
        "(n) => window.apothecaryPictures.cameraState().some((c) => c.camera === n && c.live && c.live.visible)",
        arg=name,
        timeout=8000,
    )
    expect(page.locator("#selected-body .camera-section video.camera-preview")).to_be_visible()
    _select(page, "workbench")
    assert _pyramid(page, name) is True  # live, so shown
    _ring_on(page, name)
    _press(page, "Still")
    _said(page, f"{name}: still again")
    _select(page, "workbench")
    assert _pyramid(page, name) is False


@pytest.mark.e2e
def test_part_edit_on_a_camera_opens_its_numbers_in_selected(
    page,
    base_url: str,
    leaves_garage_as_found,  # noqa: F811
):
    """Part › Edit on a camera: its position, turn, tilt and field of view in
    Selected's editor, under its camera section; a tilt staged and applied is the
    camera's, and its pyramid follows."""
    name = _add(page, base_url, "workbench")
    _open_garage(page, base_url)
    _ring_on(page, name)
    _press(page, "Part", "Edit")
    _said(page, f"Editing {name}: its parameters are in Selected")
    params = page.locator("#part-params")
    expect(params.locator(".param")).to_have_count(6, timeout=10000)
    fields = params.locator(".param").evaluate_all("(ps) => ps.map((p) => p.dataset.field)")
    assert sorted(fields) == ["fov", "tilt", "turn", "x", "y", "z"]
    expect(page.locator("#part-scad-content")).to_have_count(0)
    section = page.locator("#selected-body .camera-section")
    assert section.evaluate(
        "(el) => !!(el.compareDocumentPosition(document.getElementById('part-params')) & Node.DOCUMENT_POSITION_FOLLOWING)"
    )
    tilt = params.locator(".param[data-field='tilt'] input[type=range]").evaluate(
        "(el) => { el.value = 25; el.dispatchEvent(new Event('input')); return Number(el.value); }"
    )
    expect(page.locator("#stage-summary")).to_contain_text("1 change staged, valid", timeout=10000)
    page.locator("#apply-btn").click()
    _said(page, f"{name} set: its next picture lands on")
    assert _camera(page, base_url, name)["tilt"] == pytest.approx(tilt)
    page.wait_for_function("(n) => window.apothecaryPictures.camera(n).tilt > 0", arg=name)
    # The editor reads the camera as it is now: nothing staged.
    expect(page.locator("#stage-summary")).to_have_text("No staged changes", timeout=10000)


@pytest.mark.e2e
def test_pictures_are_grouped_by_the_camera_that_took_them(
    page,
    base_url: str,
    picture_folder,
    leaves_garage_as_found,  # noqa: F811
):
    """Pictures shows thumbnails, grouped by camera: this site's cameras first, each
    with the frames it took, and the pictures no camera took -- added, and the
    folder's own -- last."""
    Image.new("RGB", (64, 48), (200, 180, 120)).save(picture_folder / "loose_on_the_bench.png")
    try:
        name = _add(page, base_url, "workbench")
        _open_garage(page, base_url)
        _choose_device(page, name)
        _select(page, name)
        page.locator("#selected-body .camera-section .cam-take").click()
        page.wait_for_function(
            "(n) => window.apothecaryPictures.viewsBy(n).length === 1", arg=name, timeout=10000
        )
        page.evaluate("() => window.apothecaryPanels.open('pictures')")
        panel = page.locator(".panel[data-panel='pictures']")
        groups = panel.locator(".picture-group")
        expect(groups.first).to_have_attribute("data-camera", f"garage/{name}", timeout=10000)
        expect(groups.first.locator(".picture-group-title")).to_contain_text(name)
        expect(groups.first.locator(".picture-tile")).to_have_count(1)
        expect(groups.first.locator(".picture-tile img")).to_have_count(1)
        loose = groups.last
        expect(loose).to_have_attribute("data-camera", "")
        expect(loose.locator(".picture-group-title")).to_contain_text("No camera")
        expect(loose.locator(".picture-tile", has_text="loose_on_the_bench.png")).to_have_count(1)
    finally:
        (picture_folder / "loose_on_the_bench.png").unlink(missing_ok=True)


@pytest.mark.e2e
def test_gather_says_what_it_refused_and_what_it_set_aside(
    page, base_url: str, picture_folder, leaves_no_trace
):
    """Forty-one ticked pictures are refused with the server's sentence; a file that
    will not open is listed as set aside, with its reason, beside what was gathered."""
    for i in range(41):
        Image.new("L", (64, 48), 200 + i).save(picture_folder / f"pile_{i:02}.png")
    (picture_folder / "broken.png").write_bytes(b"not a picture at all")
    page.goto(f"{base_url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=20000)
    # The canvas ring's Pictures › Gather opens Pictures with its gathering section
    # unfolded and gathers what is ticked: nothing yet, which it refuses.
    page.locator("#viewer-canvas").click(button="right", position={"x": 8, "y": 8})
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    page.keyboard.press(_cell(page, "Pictures"))
    page.wait_for_function(
        "() => [...document.querySelectorAll('#ring-overlay .wedge')]"
        ".some((w) => w.getAttribute('aria-label') === 'Gather')",
        timeout=5000,
    )
    page.keyboard.press(_cell(page, "Gather"))
    panel = page.locator(".panel[data-panel='pictures']")
    expect(panel.locator("#pictures-gather")).to_have_attribute("open", "", timeout=3000)
    expect(page.locator("#status")).to_contain_text("tick at least two pictures to gather")
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
