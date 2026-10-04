"""Less on the screen: the cameras-and-clutter plan's Phase 2
(docs/plans/cameras-and-clutter-2026-10-04.md).

A busy bench, on a server of its own from the conftest's ``start_server``:
printer_1's mainboard pinned to the simulated printer (``/dev/ttyFAKE1``,
identified), the footpedal to the scripted Uno (``/dev/ttyFAKE0``), a view pinned
at the workbench with three stated shapes (tests/e2e/test_picture_in_the_world.py's
picture), and a camera pinned there. Nothing here opens a real port.

- Badges: one small icon at its thing's own spot; its words on hover or while its
  thing is selected; badges in each other's way step aside or merge into a count;
  open cards never overlap and keep off the edges.
"""

from __future__ import annotations

import io
import json
import re

import httpx
import pytest
from PIL import Image, ImageDraw
from playwright.sync_api import Page, expect
from viewer_ready import FRAMES, OCCLUSION_TESTED, settled

PRINTER = "/dev/ttyFAKE1"
UNO = "/dev/ttyFAKE0"
BOARD = "printer_1.frame_system.mainboard"
PICTURE = "busy_bench"
SHAPES = [
    {"kind": "rect", "min": [0.135, 0.41], "max": [0.235, 0.51], "label": "block"},
    {"kind": "disc", "min": [0.585, 0.7478], "max": [0.615, 0.8078], "label": "coin"},
    {"kind": "rect", "min": [0.3178, 0.1578], "max": [0.3378, 0.1978], "label": "bar"},
]
BOARD_BADGE = ".world-badge[data-path='printer_1']"
PLACE_BADGE = ".world-badge.place-mark[data-host='workbench']"
FOOTPEDAL_BADGE = ".world-badge[data-path='footpedal']"


def _picture() -> bytes:
    img = Image.new("L", (1000, 500), 245)
    pen = ImageDraw.Draw(img)
    pen.rectangle((40, 40, 260, 160), fill=30)
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


@pytest.fixture(scope="module")
def bench(start_server, tmp_path_factory) -> str:
    """The busy bench: printer_1's board and the footpedal pinned, a view and a camera
    at the workbench."""
    folder = tmp_path_factory.mktemp("busy_bench_pictures")
    (folder / f"{PICTURE}.png").write_bytes(_picture())
    (folder / f"{PICTURE}.shapes.json").write_text(
        json.dumps({"name": PICTURE, "pixel_width": 1000, "pixel_height": 500, "shapes": SHAPES}),
        encoding="utf-8",
    )
    url = start_server({"APOTHECARY_PICTURE_ROOT": str(folder)})
    with httpx.Client(base_url=url, timeout=15.0) as http:
        http.post("/firmware/devices/identify", json={"port": PRINTER}).raise_for_status()
        http.put(f"/sites/garage/nodes/{BOARD}/device", json={"identity": PRINTER}).raise_for_status()
        http.put("/sites/garage/nodes/footpedal/device", json={"identity": UNO}).raise_for_status()
        view = http.post(
            "/sites/garage/views",
            json={"host": "workbench", "picture": f"{PICTURE}.png", "mm_across": 1800},
        )
        view.raise_for_status()
        http.post(
            f"/sites/garage/views/{view.json()['id']}/find", json={"finder": "stated"}
        ).raise_for_status()
        http.put(
            "/cameras/bench_camera",
            json={"label": "Bench webcam", "site": "garage", "path": "workbench"},
        ).raise_for_status()
    return url


def _open(page: Page, url: str) -> None:
    page.goto(f"{url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=20000)
    for badge in (BOARD_BADGE, PLACE_BADGE, FOOTPEDAL_BADGE):
        expect(page.locator(badge)).to_be_visible(timeout=15000)
    settled(page, frames=OCCLUSION_TESTED)


def _rect(page: Page, selector: str) -> dict:
    return page.locator(selector).evaluate(
        "(el) => { const r = el.getBoundingClientRect(); "
        "return { l: r.left, r: r.right, t: r.top, b: r.bottom }; }"
    )


def _meet(a: dict, b: dict) -> bool:
    return a["l"] < b["r"] and b["l"] < a["r"] and a["t"] < b["b"] and b["t"] < a["b"]


# Slide the view sideways (camera and target together) until printer_1's board
# badge stands 4 px inside the world's left or right edge.
PAN_TO_EDGE = """(edge) => {
    const v = window.fractalViewer;
    const s = v.anchors.at('printer_1');
    const w = v.canvas.clientWidth;
    const px = edge === 'left' ? s.x - 4 : s.x - (w - 4);
    const along = v.camera.position.distanceTo(v.orbitControls.target);
    const mm = px * along * 2 * Math.tan(v.camera.fov * Math.PI / 360) / v.canvas.clientHeight;
    const right = v.camera.matrixWorld.elements.slice(0, 3);
    for (const [i, k] of [[0, 'x'], [1, 'y'], [2, 'z']]) {
        v.camera.position[k] += right[i] * mm;
        v.orbitControls.target[k] += right[i] * mm;
    }
    v.orbitControls.update();
}"""


def _select(page: Page, path: str) -> None:
    page.locator(f"#contents-list .contents-item[data-path='{path}']").click()


@pytest.mark.e2e
def test_the_board_and_the_place_badge_at_the_garage_top_level_do_not_overlap(
    page: Page, bench: str
):
    """At the garage's top level printer_1's board badge and the workbench's place
    badge stood 30 px over their structures' middles and printed over each other. Each
    is an icon at its own spot now -- the board inside the printer, the picture's
    corner -- and two in each other's way step aside: they never intersect."""
    _open(page, bench)
    board, place = _rect(page, BOARD_BADGE), _rect(page, PLACE_BADGE)
    assert not _meet(board, place), (board, place)
    # Icons, their words folded away until hovered or selected.
    expect(page.locator(f"{BOARD_BADGE} .badge-icon")).to_have_text("⚡")
    expect(page.locator(f"{PLACE_BADGE} .badge-icon")).to_have_text("📷")
    expect(page.locator(f"{FOOTPEDAL_BADGE} .badge-icon")).to_have_text("⚡")
    for badge in (BOARD_BADGE, PLACE_BADGE, FOOTPEDAL_BADGE):
        expect(page.locator(f"{badge} .badge-words")).to_be_hidden()
        assert page.locator(badge).bounding_box()["width"] < 40
    # The board's spot is the board's, not the printer's middle; the place's is the
    # picture's corner, not the bench's middle.
    spots = page.evaluate(
        """() => {
            const v = window.fractalViewer;
            const at = (p) => { const s = p.clone().project(v.camera);
                return { x: (s.x + 1) / 2 * v.canvas.clientWidth, y: (1 - s.y) / 2 * v.canvas.clientHeight }; };
            return {
                board: v.anchors.at('printer_1'), mainboard: at(v.anchorPointFor('printer_1.frame_system.mainboard')),
                printer: at(v.anchorPointFor('printer_1')),
                place: v.anchors.at('place:workbench'), bench: at(v.anchorPointFor('workbench')),
            };
        }"""
    )
    assert abs(spots["board"]["x"] - spots["mainboard"]["x"]) < 1
    assert abs(spots["board"]["y"] - spots["mainboard"]["y"]) < 1
    assert abs(spots["board"]["y"] - spots["printer"]["y"]) > 10
    assert abs(spots["place"]["x"] - spots["bench"]["x"]) > 10


@pytest.mark.e2e
def test_a_badges_words_show_on_hover_and_while_its_thing_is_selected(page: Page, bench: str):
    """A badge's words -- the board's state, readings and port; the place's camera and
    shape count -- are a card shown while the pointer is on the badge, or while its
    thing is selected; a click still selects it."""
    _open(page, bench)
    words = page.locator(f"{BOARD_BADGE} .badge-words")
    page.locator(BOARD_BADGE).hover()
    expect(words).to_be_visible(timeout=3000)
    expect(words).to_contain_text("printing")
    expect(words).to_contain_text(PRINTER)
    page.mouse.move(5, 5)
    expect(words).to_be_hidden(timeout=3000)

    _select(page, "printer_1")
    expect(words).to_be_visible(timeout=3000)
    place_words = page.locator(f"{PLACE_BADGE} .badge-words")
    expect(place_words).to_be_hidden()
    _select(page, "workbench")
    expect(place_words).to_be_visible(timeout=3000)
    expect(place_words).to_contain_text("view: 3 shapes")
    expect(words).to_be_hidden(timeout=3000)
    expect(page.locator(PLACE_BADGE)).to_have_class(re.compile(r"\bselected\b"))

    page.locator(BOARD_BADGE).click()
    assert page.evaluate("() => window.fractalViewer.selectedName") == "printer_1"


@pytest.mark.e2e
def test_badges_in_each_others_way_merge_into_a_count_until_zoomed_in(page: Page, bench: str):
    """Pulled far back, the three badges stand in each other's way and merge into one
    count, ×3, whose card lists each and whose rows do what each badge does; framed
    again, they part."""
    _open(page, bench)
    page.evaluate(
        """() => { const v = window.fractalViewer;
            const t = v.orbitControls.target, c = v.camera.position;
            c.sub(t).multiplyScalar(30).add(t); v.orbitControls.maxDistance = 1e7;
            v.updateCameraClipping(1e6); v.orbitControls.update(); }"""
    )
    page.evaluate(FRAMES, 3)
    count = page.locator(".world-badge.cluster")
    expect(count).to_have_count(1, timeout=3000)
    expect(count.locator(".badge-icon")).to_have_text("×3")
    for badge, key in ((BOARD_BADGE, "printer_1"), (PLACE_BADGE, "place:workbench"), (FOOTPEDAL_BADGE, "footpedal")):
        expect(page.locator(badge)).to_have_class(re.compile(r"\bmerged\b"))
        assert page.evaluate("(k) => window.fractalViewer.anchors.drawn(k).merged", key) == 3
    count.hover()
    rows = count.locator(".cluster-row")
    expect(rows).to_have_count(3, timeout=3000)
    rows.filter(has_text="view: 3 shapes").click()
    assert page.evaluate("() => window.fractalViewer.selectedName") == "workbench"

    page.evaluate(
        "() => { const v = window.fractalViewer; "
        "v.frameCameraForChildren(v.currentRenderNodes(v.currentFocusNode())); }"
    )
    page.evaluate(FRAMES, 3)
    expect(count).to_have_count(0, timeout=3000)
    for badge in (BOARD_BADGE, PLACE_BADGE, FOOTPEDAL_BADGE):
        expect(page.locator(badge)).to_be_visible()


@pytest.mark.e2e
def test_open_cards_never_overlap_and_keep_off_the_edges(page: Page, bench: str):
    """Two cards open at once -- the selected printer's, the hovered place's -- never
    overlap; a badge at the world's edge keeps its card inside it, clear of the edge."""
    _open(page, bench)
    _select(page, "printer_1")
    page.locator(PLACE_BADGE).hover()
    board_words = page.locator(f"{BOARD_BADGE} .badge-words")
    place_words = page.locator(f"{PLACE_BADGE} .badge-words")
    expect(board_words).to_be_visible(timeout=3000)
    expect(place_words).to_be_visible(timeout=3000)
    page.evaluate(FRAMES, 2)
    a, b = _rect(page, f"{BOARD_BADGE} .badge-words"), _rect(page, f"{PLACE_BADGE} .badge-words")
    assert not _meet(a, b), (a, b)

    # The printer's board at the world's left edge, then its right: its card stays
    # inside the world, clear of the edge.
    page.mouse.move(5, 5)
    world = _rect(page, ".viewer-panel")
    for edge in ("left", "right"):
        for _ in range(4):  # the board is nearer than the target: a few steps get it there
            page.evaluate(PAN_TO_EDGE, edge)
            page.evaluate(FRAMES, 2)
        x = page.evaluate("() => window.fractalViewer.anchors.at('printer_1').x")
        assert abs(x - (4 if edge == "left" else world["r"] - world["l"] - 4)) < 8, (edge, x)
        # Its card, or the count's it merged into there, is the one open.
        card = page.locator(".world-badge.open .badge-words")
        expect(card).to_have_count(1)
        expect(card).to_contain_text(PRINTER)
        got = _rect(page, ".world-badge.open .badge-words")
        assert got["l"] >= world["l"] + 8 and got["r"] <= world["r"] - 8, (edge, got, world)
        assert got["t"] >= world["t"] + 8 and got["b"] <= world["b"] - 8, (edge, got, world)


# --------------------------------------------------------------------------
# Handles: one compact set on a movable thing
# --------------------------------------------------------------------------

HANDLES = """() => {
    const v = window.fractalViewer, tc = v.transformControls;
    const seen = new Set();
    tc._gizmo.gizmo.translate.traverse((o) => {
        if (o.material) seen.add(o.material._opacity ?? o.material.opacity);
    });
    return { on: tc.object ? tc.object.userData.key : null, mode: tc.mode, size: tc.size,
             most: Math.max(...seen) };
}"""


@pytest.mark.e2e
def test_a_movable_thing_selected_wears_one_compact_set_of_handles(page: Page, bench: str):
    """Selected, a piece that can be moved wears the move arrows, smaller and lighter
    than three.js draws them; a piece inside another, which cannot be moved from
    here, and the floor wear none."""
    _open(page, bench)
    _select(page, "printer_1")
    got = page.evaluate(HANDLES)
    assert got["on"] == "printer_1" and got["mode"] == "translate"
    assert got["size"] < 1 and got["most"] < 1, got
    page.evaluate("() => window.fractalViewer.selectPath('printer_1.frame_system')")
    assert page.evaluate(HANDLES)["on"] is None
    page.evaluate("() => window.fractalViewer.selectPlace('')")
    assert page.evaluate(HANDLES)["on"] is None
    _select(page, "workbench")
    assert page.evaluate(HANDLES)["on"] == "workbench"

