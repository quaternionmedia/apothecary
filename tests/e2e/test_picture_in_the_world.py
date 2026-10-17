"""A view drawn where it was pinned: the picture as a mat on the bench's top or on
the floor beside the site, its shapes as outlines, a place badge over each.

The fixture is a stated description of a picture 1000 by 500 pixels (the one
tests/test_views_api.py states), pinned at node ``workbench`` in site ``garage``
through ``POST /sites/garage/views`` with the page's own request context, at a
width of 1800 mm: the bench's top is x 0..1800, y 0..600 at z 780, and the mat is
laid in its clear stretch between ``printer_1`` and the footpedal, centred at
(1094, 300, 780), 900 mm deep. Its three shapes: 0, ``block``, under
``printer_1``'s right side; 1, ``coin``, in front of everything; 2, ``bar``,
behind them.

Every view, camera and kept picture a test adds is taken back after it, and the
bench is put back where the site's code has it, so a later test finds the server
as it would alone.
"""

from __future__ import annotations

import io
import json

import pytest
from PIL import Image, ImageDraw
from playwright.sync_api import expect
from viewer_ready import OCCLUSION_TESTED, settled

WIDE, HIGH = 1000, 500
NAME = "world_bench"
SHAPES = [
    {
        "kind": "rect",
        "min": [0.135, 0.41],
        "max": [0.235, 0.51],
        "label": "block",
        "points": [[0.135, 0.41], [0.235, 0.41], [0.235, 0.51], [0.135, 0.51]],
    },
    {
        "kind": "disc",
        "min": [0.585, 0.7478],
        "max": [0.615, 0.8078],
        "label": "coin",
        "confidence": 0.9,
    },
    {
        "kind": "rect",
        "min": [0.3178, 0.1578],
        "max": [0.3378, 0.1978],
        "label": "bar",
        "confidence": 0.8,
    },
]

# Where a fraction of a drawn view's picture lands on the page, in page pixels.
PROJECT = """([view, fx, fy]) => {
    const v = window.fractalViewer;
    const p = window.apothecaryPictures.scenePoint(view, fx, fy);
    if (!p) return null;
    p.project(v.camera);
    const r = v.canvas.getBoundingClientRect();
    return { x: r.left + (p.x + 1) / 2 * r.width, y: r.top + (1 - p.y) / 2 * r.height };
}"""

# Look down from `height` mm over (x, y, z) in the site's frame, from a little in front.
LOOK_DOWN = """([x, y, z, height]) => {
    const v = window.fractalViewer;
    v.orbitControls.target.copy(v.sceneAt(x, y, z));
    v.camera.position.copy(v.sceneAt(x, y - height * 0.05, z + height));
    v.orbitControls.update();
}"""

STATE = "() => window.apothecaryPictures.state()"
FOUND_COLOR, OVER_COLOR = 0xFFCC66, 0xFF5544  # picture_marks.js: a shape found, and one flagged


# A point of a shape's outline, in page pixels, where printer_1 stands over it as seen:
# the first mesh a ray from the camera meets there is printer_1's, and nothing stands
# over the canvas there. Null where it covers none of it.
UNDER_THE_PRINTER = """([view, box]) => {
    const v = window.fractalViewer, r = v.canvas.getBoundingClientRect();
    const step = (lo, hi) => (hi - lo) / 8;
    for (let fy = box.min[1]; fy <= box.max[1]; fy += step(box.min[1], box.max[1])) {
        for (let fx = box.min[0]; fx <= box.max[0]; fx += step(box.min[0], box.max[0])) {
            const p = window.apothecaryPictures.scenePoint(view, fx, fy);
            if (!p) continue;
            const s = p.clone().project(v.camera);
            const x = r.left + (s.x + 1) / 2 * r.width, y = r.top + (1 - s.y) / 2 * r.height;
            if (document.elementFromPoint(x, y) !== v.canvas) continue;
            v.raycaster.setFromCamera({ x: s.x, y: s.y }, v.camera);
            const hit = v.raycaster.intersectObjects(Object.values(v.meshByName), false)[0];
            if (hit && hit.object.userData.key === 'printer_1') return { x, y };
        }
    }
    return null;
}"""


def _picture(pen_shapes: bool = True) -> bytes:
    img = Image.new("L", (WIDE, HIGH), 245)
    pen = ImageDraw.Draw(img)
    if pen_shapes:
        pen.rectangle((40, 40, 260, 160), fill=30)
        pen.polygon([(80, 420), (300, 420), (190, 280)], fill=25)
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


@pytest.fixture
def fixture_picture(picture_folder):
    (picture_folder / f"{NAME}.png").write_bytes(_picture())
    (picture_folder / f"{NAME}.shapes.json").write_text(
        json.dumps({"name": NAME, "pixel_width": WIDE, "pixel_height": HIGH, "shapes": SHAPES}),
        encoding="utf-8",
    )
    yield f"{NAME}.png"
    (picture_folder / f"{NAME}.png").unlink(missing_ok=True)
    (picture_folder / f"{NAME}.shapes.json").unlink(missing_ok=True)


@pytest.fixture
def leaves_garage_as_found(page, base_url: str):
    """After the test: garage's views, cameras and kept pictures it added are taken
    back, and its layout is the code's again."""
    api = page.request
    attached = api.get(f"{base_url}/sites/garage/attached").json()
    views = {vw["id"] for vw in attached["views"]}
    cameras = {c["name"] for c in attached["cameras"]}
    pictures = {p["path"] for p in api.get(f"{base_url}/photos/pictures").json()}
    yield
    attached = api.get(f"{base_url}/sites/garage/attached").json()
    for view in attached["views"]:
        if view["id"] not in views:
            api.delete(f"{base_url}/sites/garage/views/{view['id']}")
    for camera in attached["cameras"]:
        if camera["name"] not in cameras:
            api.delete(f"{base_url}/sites/garage/cameras/{camera['name']}")
    for picture in api.get(f"{base_url}/photos/pictures").json():
        if picture["path"] not in pictures and picture["kept"]:
            api.delete(f"{base_url}/photos/pictures/{picture['path']}")
    api.post(f"{base_url}/sites/garage/reset")


def _pin(page, base_url: str, host: str, picture: str, mm_across: float | None = None) -> dict:
    """Pin the picture as a view and Find shapes in it with the stated finder."""
    body = {"host": host, "picture": picture}
    if mm_across:
        body["mm_across"] = mm_across
    answer = page.request.post(f"{base_url}/sites/garage/views", data=body)
    assert answer.status == 201, answer.text()
    found = page.request.post(
        f"{base_url}/sites/garage/views/{answer.json()['id']}/find", data={"finder": "stated"}
    )
    assert found.status == 200, found.text()
    return found.json()


def _open_garage(page, base_url: str) -> None:
    page.goto(f"{base_url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=20000)
    page.evaluate("() => localStorage.removeItem('apothecary.panels')")
    settled(page)


def _drawn(page, host: str):
    return next((entry for entry in page.evaluate(STATE) if entry["host"] == host), None)


def _at(page, view: str, fx: float, fy: float) -> dict:
    point = page.evaluate(PROJECT, [view, fx, fy])
    assert point, f"view {view} is not drawn"
    return point


def _centre(shape) -> tuple:
    return ((shape["min"][0] + shape["max"][0]) / 2, (shape["min"][1] + shape["max"][1]) / 2)


def _pixel(page, point) -> int:
    """The grey level the page shows at a point (the mean of its three channels)."""
    shot = page.screenshot(clip={"x": point["x"] - 1, "y": point["y"] - 1, "width": 3, "height": 3})
    r, g, b = Image.open(io.BytesIO(shot)).convert("RGB").getpixel((1, 1))
    return (r + g + b) // 3


@pytest.mark.e2e
def test_a_view_at_the_bench_is_a_mat_with_its_outlines(
    page, base_url: str, fixture_picture, leaves_garage_as_found
):
    """The mat lies on the bench's top at the view's width, where it was laid clear of
    what rests on the bench, one outline per shape; the block's, under printer_1, is
    flagged in its own colour and on the badge. A click on an outline chooses it, a
    click on printer_1 standing over one selects printer_1, a click on the mat outside
    the outlines selects the bench and clears the choice."""
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    view = _pin(page, base_url, "workbench", fixture_picture, mm_across=1800)
    _open_garage(page, base_url)
    page.wait_for_function(
        "() => window.apothecaryPictures.state().some((e) => e.host === 'workbench' && e.mat)",
        timeout=5000,
    )
    drawn = _drawn(page, "workbench")
    assert drawn["view"] == view["id"]
    assert drawn["mat"]["visible"] and drawn["mat"]["sized"]
    # Laid in the bench top's clear stretch, between printer_1 and the footpedal.
    assert drawn["mat"]["centre"] == [1094, 300, 780]
    assert (drawn["mat"]["width"], drawn["mat"]["depth"]) == (1800, 900)
    assert [(o["index"], o["status"]) for o in drawn["outlines"]] == [
        (0, "found"),
        (1, "found"),
        (2, "found"),
    ]
    # The block lies over printer_1: its outline in the flag's colour, the others as found,
    # and its area filled to be seen from across the room.
    assert [o["colour"] for o in drawn["outlines"]] == [OVER_COLOR, FOUND_COLOR, FOUND_COLOR]
    assert drawn["fills"] == [{"index": 0, "overlaps": ["printer_1"], "colour": OVER_COLOR}]
    # An overlay on the bench, not a made part: seen through at half, and hatched.
    assert drawn["mat"]["opacity"] == 0.5 and drawn["mat"]["hatched"]
    assert "px=1024" in drawn["texture"]["url"]
    badge = page.locator(".world-badge.place-mark[data-host='workbench']")
    # Its words: the place, the picture drawn there, how many shapes are in it, and
    # what of it lies over something resting on the bench.
    expect(badge).to_contain_text("workbench · world_bench.png · 3 shapes · 1 over printer_1")

    # From above the mat, a little in front of it.
    page.evaluate(LOOK_DOWN, [1094, 300, 780, 2600])
    settled(page)

    # An outline chooses its shape, and selects the bench.
    coin = _at(page, view["id"], *_centre(SHAPES[1]))
    page.mouse.click(coin["x"], coin["y"])
    assert page.evaluate("() => window.fractalViewer.selectedName") == "workbench"
    assert page.evaluate("() => window.apothecaryPictures.chosen()") == {
        "view": view["id"],
        "index": 1,
    }
    expect(page.locator("#selected-body [data-facts='shape']")).to_contain_text("Shape 1: a disc")
    expect(page.locator("#selected-body [data-facts='host']")).to_contain_text(fixture_picture)

    # printer_1 stands over the block's outline: a click where it covers it is the printer's.
    block = page.evaluate(UNDER_THE_PRINTER, [view["id"], SHAPES[0]])
    assert block, "printer_1 covers no point of the block's outline as seen"
    page.mouse.click(block["x"], block["y"])
    assert page.evaluate("() => window.fractalViewer.selectedName") == "printer_1"
    assert page.evaluate("() => window.apothecaryPictures.chosen()") is None

    # The mat past the bench's back edge, outside every outline: the bench, no choice.
    page.mouse.click(coin["x"], coin["y"])
    assert page.evaluate("() => window.apothecaryPictures.chosen()") is not None
    bare = _at(page, view["id"], 0.9, 0.05)
    page.mouse.click(bare["x"], bare["y"])
    assert page.evaluate("() => window.fractalViewer.selectedName") == "workbench"
    assert page.evaluate("() => window.apothecaryPictures.chosen()") is None

    # Looking into printer_1, the mat is not drawn; its badge goes with its level.
    page.evaluate("() => window.fractalViewer.zoomIn('printer_1')")
    assert _drawn(page, "workbench")["mat"]["visible"] is False
    expect(badge).to_be_hidden()
    page.evaluate("() => window.fractalViewer.zoomOut()")
    assert _drawn(page, "workbench")["mat"]["visible"] is True
    assert errors == []


@pytest.mark.e2e
def test_the_mat_shows_the_picture_and_the_floor_is_a_selection(
    page, base_url: str, fixture_picture, leaves_garage_as_found
):
    """A view at the floor lies beside the site; its pixels are the picture's, seen
    through at half; a click on it selects the floor, and its badge is not dimmed by it."""
    view = _pin(page, base_url, "", fixture_picture, mm_across=1000)
    _open_garage(page, base_url)
    page.wait_for_function(
        "() => window.apothecaryPictures.state().some((e) => e.host === '' && e.mat)",
        timeout=5000,
    )
    drawn = _drawn(page, "")
    anchor = view["anchor"]
    assert drawn["mat"]["centre"] == [anchor[0] + 500, anchor[1], 0]
    page.wait_for_function(
        "() => window.apothecaryPictures.state().find((e) => e.host === '').texture.loaded",
        timeout=10000,
    )
    centre = drawn["mat"]["centre"]
    page.evaluate(LOOK_DOWN, [centre[0], centre[1], 0, 1400])
    settled(page, frames=OCCLUSION_TESTED)

    # The dark rectangle drawn at the picture's top left reads apart from its light
    # background, the picture seen through at half over the floor.
    dark = _pixel(page, _at(page, view["id"], 0.15, 0.2))
    light = _pixel(page, _at(page, view["id"], 0.8, 0.6))
    assert light - dark > 50, (dark, light)

    badge = page.locator(".world-badge.place-mark[data-host='']")
    expect(badge).to_be_visible()
    expect(badge).to_contain_text("floor")
    expect(badge).not_to_have_class("behind")

    bare = _at(page, view["id"], 0.8, 0.6)
    page.mouse.click(bare["x"], bare["y"])
    assert page.evaluate("() => window.fractalViewer.selectedName") == "@floor"
    expect(page.locator("#selected-body")).to_contain_text("the floor")
    expect(page.locator("#selected-body [data-facts='floor']")).to_contain_text(fixture_picture)

    # An outline on the floor's mat chooses its shape, the floor selected.
    coin = _at(page, view["id"], *_centre(SHAPES[1]))
    page.mouse.click(coin["x"], coin["y"])
    assert page.evaluate("() => window.fractalViewer.selectedName") == "@floor"
    assert page.evaluate("() => window.apothecaryPictures.chosen()")["index"] == 1

    # The badge selects the floor too, from anything else.
    page.locator("#contents-list .contents-item[data-path='workbench']").click()
    badge.click()
    assert page.evaluate("() => window.fractalViewer.selectedName") == "@floor"


@pytest.mark.e2e
def test_the_mat_follows_its_bench_when_the_gizmo_moves_it(
    page, base_url: str, fixture_picture, leaves_garage_as_found
):
    """Moved with the gizmo and let go, the bench carries its mat, its outlines and
    its badge: the page asks where the view lies now, once."""
    view = _pin(page, base_url, "workbench", fixture_picture, mm_across=1800)
    _open_garage(page, base_url)
    page.wait_for_function(
        "() => window.apothecaryPictures.state().some((e) => e.host === 'workbench' && e.mat)",
        timeout=5000,
    )
    page.locator("#contents-list .contents-item[data-path='workbench']").click()
    laid_x = _drawn(page, "workbench")["mat"]["centre"][0]
    before = page.evaluate("() => window.fractalViewer.anchors.at('place:workbench')")
    assert before
    asked = []
    page.on(
        "request",
        lambda request: asked.append(request.url) if "/attached" in request.url else None,
    )
    with page.expect_response("**/sites/garage/attached"):
        page.evaluate(
            """() => {
                const v = window.fractalViewer;
                const tc = v.transformControls;
                tc.object.position.x += 500;
                tc.dispatchEvent({ type: 'objectChange' });
                tc.dispatchEvent({ type: 'mouseUp' });
            }"""
        )
    page.wait_for_function(
        "(x) => window.apothecaryPictures.state().find((e) => e.host === 'workbench')"
        ".mat.centre[0] === x",
        arg=laid_x + 500,
        timeout=5000,
    )
    settled(page)
    after = page.evaluate("() => window.fractalViewer.anchors.at('place:workbench')")
    assert after["x"] > before["x"]
    point = page.evaluate(PROJECT, [view["id"], 0, 0])
    # An anchor's point is the canvas's (anchors.js), PROJECT's the page's: the
    # canvas starts where Site's rail ends.
    left = page.evaluate("() => window.fractalViewer.canvas.getBoundingClientRect().left")
    # The badge stands at the picture's top-left corner, its own spot, and not at
    # the middle of the bench, where the printers stand.
    assert abs(point["x"] - left - after["x"]) < 2
    assert len(asked) == 1


@pytest.mark.e2e
def test_a_forgotten_pictures_view_leaves_the_world(page, base_url: str, leaves_garage_as_found):
    """A picture kept from the browser and pinned at the bench is drawn there;
    forgotten from its row in Pictures, its view is unpinned and its mat goes."""
    kept = page.request.post(
        f"{base_url}/photos/pictures?name=forget_me.png&kept=upload&site=garage&host=workbench",
        data=_picture(),
        headers={"Content-Type": "image/png"},
    )
    assert kept.status == 201, kept.text()
    kept = kept.json()
    assert kept["view"], kept
    _open_garage(page, base_url)
    page.wait_for_function(
        "() => window.apothecaryPictures.state().some((e) => e.host === 'workbench' && e.mat)",
        timeout=5000,
    )
    badge = page.locator(".world-badge.place-mark[data-host='workbench']")
    expect(badge).to_be_visible()

    page.evaluate("() => window.apothecaryPanels.open('pictures')")
    panel = page.locator(".panel[data-panel='pictures']")
    card = panel.locator(f".pictures-forget[data-path='{kept['path']}']")
    expect(card).to_be_visible(timeout=5000)
    card.click()
    expect(card).to_have_text("Again to forget")
    card.click()
    page.wait_for_function(
        "() => !window.apothecaryPictures.state().some((e) => e.host === 'workbench')",
        timeout=5000,
    )
    expect(badge).to_have_count(0)
    views = page.request.get(f"{base_url}/sites/garage/attached").json()["views"]
    assert not [vw for vw in views if vw["picture"] == kept["path"]]
