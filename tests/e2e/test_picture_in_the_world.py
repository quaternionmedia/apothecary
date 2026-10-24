"""A view drawn where it was pinned: the picture as a mat on the bench's top or on
the floor beside the site, its shapes as outlines, a place badge over each.

The fixture is a stated description of a picture 1000 by 500 pixels (the one
tests/test_views_api.py states), pinned at node ``workbench`` in site ``garage``
through ``POST /sites/garage/views`` with the page's own request context, at a
width of 1800 mm: the bench's top is x 0..1800, y 0..600 at z 780, so the mat is
centred at (900, 300, 780) and is 900 mm deep. Its three shapes: 0, ``block``,
under ``printer_1``; 1, ``coin``, in front of every printer; 2, ``bar``, behind
them. Phase 4 of the pictures plan pins it by a drop instead.

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
    v.orbitControls.target.set(x, z, y);
    v.camera.position.set(x, z + height, y - height * 0.05);
    v.orbitControls.update();
}"""

STATE = "() => window.apothecaryPictures.state()"


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
    """The mat lies on the bench's top at the view's width, one outline per shape; a
    click on an outline chooses it, a click on printer_1 standing over one selects
    printer_1, a click on the mat outside the outlines selects the bench and clears
    the choice."""
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
    assert drawn["mat"]["centre"] == [900, 300, 780]
    assert (drawn["mat"]["width"], drawn["mat"]["depth"]) == (1800, 900)
    assert [(o["index"], o["status"]) for o in drawn["outlines"]] == [
        (0, "found"),
        (1, "found"),
        (2, "found"),
    ]
    assert "px=1024" in drawn["texture"]["url"]
    badge = page.locator(".world-badge.place-mark[data-host='workbench']")
    # Its words: the place, the picture drawn there, and what was found in it.
    expect(badge).to_contain_text("workbench · world_bench.png · 3 shapes")

    # From above the bench, a little in front of it.
    page.evaluate(LOOK_DOWN, [900, 300, 780, 2600])
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

    # printer_1 stands over the block's outline: the click is the printer's.
    block = _at(page, view["id"], *_centre(SHAPES[0]))
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
    """A view at the floor lies beside the site; its pixels are the picture's; a
    click on it selects the floor, and its badge is not dimmed by it."""
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

    # The dark rectangle drawn at the picture's top left, and its light background.
    dark = _pixel(page, _at(page, view["id"], 0.15, 0.2))
    light = _pixel(page, _at(page, view["id"], 0.8, 0.6))
    assert dark < 90 < 180 < light, (dark, light)

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
        "() => window.apothecaryPictures.state().find((e) => e.host === 'workbench')"
        ".mat.centre[0] === 1400",
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
    page.wait_for_function(
        "() => !window.apothecaryPictures.state().some((e) => e.host === 'workbench')",
        timeout=5000,
    )
    expect(badge).to_have_count(0)
    views = page.request.get(f"{base_url}/sites/garage/attached").json()["views"]
    assert not [vw for vw in views if vw["picture"] == kept["path"]]
