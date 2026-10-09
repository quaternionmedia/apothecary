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


# Slide the view until printer_1's board badge stands at the world's bottom-left,
# where the hint bar is.
TO_THE_HINT = """async () => {
    const v = window.fractalViewer;
    for (let i = 0; i < 6; i++) {
        const s = v.anchors.at('printer_1');
        const h = v.canvas.clientHeight;
        const dx = s.x - 60, dy = s.y - (h - 6);
        const k = v.camera.position.distanceTo(v.orbitControls.target)
            * 2 * Math.tan(v.camera.fov * Math.PI / 360) / h;
        const e = v.camera.matrixWorld.elements;
        for (const [i, key] of [[0, 'x'], [1, 'y'], [2, 'z']]) {
            const d = e[i] * dx * k - e[4 + i] * dy * k;
            v.camera.position[key] += d;
            v.orbitControls.target[key] += d;
        }
        v.orbitControls.update();
        await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    }
}"""


@pytest.mark.e2e
def test_an_open_card_keeps_off_the_hint_bar(page: Page, bench: str):
    """A first visit shows the hint bar at the world's bottom-left; the selected
    printer's board, slid down onto it, opens its card clear of the bar, and
    inside the world."""
    _open(page, bench)
    _select(page, "printer_1")
    page.evaluate(TO_THE_HINT)
    page.evaluate(FRAMES, 3)
    hint = _rect(page, "#viewer-hint")
    board = _rect(page, BOARD_BADGE)
    assert board["b"] > hint["t"], (board, hint)  # the badge is down by the bar
    expect(page.locator("#viewer-hint")).not_to_have_class(re.compile(r"\bfaded\b"))
    card = page.locator(".world-badge.open .badge-words")
    expect(card).to_have_count(1)
    expect(card).to_contain_text(PRINTER)
    got = _rect(page, ".world-badge.open .badge-words")
    assert not _meet(got, hint), (got, hint)
    world = _rect(page, ".viewer-panel")
    assert got["t"] >= world["t"] + 8 and got["b"] <= world["b"] - 8, (got, world)


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



# --------------------------------------------------------------------------
# The Machine in the rail
# --------------------------------------------------------------------------

MACHINE = ".panel[data-panel='machine']"


def _rail_machine(page: Page):
    rail = page.locator(".panel-rail")
    machine = rail.locator(f".panel-tabbody {MACHINE}")
    expect(machine).to_be_visible(timeout=5000)
    expect(rail.locator(".rail-tab[data-panel='machine']")).to_have_class(
        re.compile(r"\bactive\b")
    )
    assert page.evaluate("() => window.apothecaryPanels.state('machine').where") == "rail"
    expect(page.locator(f".panel-free-layer {MACHINE}")).to_have_count(0)
    return machine


@pytest.mark.e2e
def test_the_machine_opens_in_the_rail_and_floats_only_when_floated(page: Page, bench: str):
    """Every way into a Machine -- its badge, Selected's Open, the ring's Device › Open,
    the monitor's address -- shows it in the rail's tab strip beside Pictures and the
    Bench, its tab active, over none of the world; floated from its tab it floats, and
    opened again while it floats it stays where a person put it; closed and opened, it
    is in the rail again."""
    _open(page, bench)
    page.locator(BOARD_BADGE).click()
    machine = _rail_machine(page)
    tabs = page.locator(".panel-rail .rail-tab .rail-tab-name")
    expect(tabs).to_have_text(["Pictures", "Bench", re.compile(r"^printer_1")])
    expect(machine.locator("#c-state")).to_contain_text("printing", timeout=10000)

    page.evaluate("() => window.fractalViewer.closeMachine()")
    _select(page, "footpedal")
    page.locator("#selected-body .dev-open").click()
    machine = _rail_machine(page)
    expect(machine.locator("#c-board")).to_contain_text("Arduino Uno", timeout=10000)

    page.evaluate("() => window.fractalViewer.closeMachine()")
    page.locator("#contents-list .contents-item[data-path='printer_1']").click(button="right")
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    page.keyboard.press("2")  # Device
    page.keyboard.press("8")  # Open
    _rail_machine(page)

    page.goto(f"{bench}/firmware/monitor?port={PRINTER}")
    expect(page).to_have_url(re.compile(r"machine="))
    expect(_rail_machine(page).locator("#c-state")).to_contain_text("printing", timeout=15000)

    # Floated from its tab, it floats; opened again, it stays floating.
    page.locator(".panel-rail .rail-tab[data-panel='machine'] .rail-tab-float").click()
    free = page.locator(f".panel-free-layer {MACHINE}")
    expect(free).to_be_visible(timeout=3000)
    assert page.evaluate("() => window.apothecaryPanels.state('machine').where") == "free"
    _select(page, "printer_1")
    page.locator("#selected-body .dev-open").click()
    expect(free).to_be_visible()
    assert page.evaluate("() => window.apothecaryPanels.state('machine').where") == "free"
    page.evaluate("() => window.fractalViewer.closeMachine()")
    page.evaluate("() => window.fractalViewer.openMachine('printer_1')")
    _rail_machine(page)


@pytest.mark.e2e
def test_a_printers_machine_has_no_flashing(page: Page, start_server):
    """A board pinned inside a printer is the printer's, whatever it has been identified
    as so far: its Machine folds Flashing away, and Device › Flash -- a cell the ring
    keeps -- says why instead. A devkit's Machine keeps its Flashing."""
    url = start_server()
    httpx.put(  # never asked M115: not yet known to be a printer
        f"{url}/sites/garage/nodes/{BOARD}/device", json={"identity": PRINTER}, timeout=15.0
    ).raise_for_status()
    page.goto(f"{url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=20000)
    badge = page.locator(f".world-badge[data-path='{BOARD}']")
    expect(badge).to_be_visible(timeout=15000)
    badge.click()
    machine = _rail_machine(page)
    expect(machine.locator("#c-board")).to_be_visible(timeout=10000)
    expect(machine.locator("#flash-card")).to_be_hidden()
    page.locator("#contents-list .contents-item[data-path='printer_1']").click(button="right")
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    page.keyboard.press("2")  # Device
    page.keyboard.press("2")  # Flash
    expect(page.locator("#status")).to_contain_text(
        "a printer keeps its own firmware", timeout=5000
    )
    expect(machine.locator("#flash-card")).to_be_hidden()

    httpx.put(
        f"{url}/sites/garage/nodes/footpedal/device", json={"identity": UNO}, timeout=15.0
    ).raise_for_status()
    page.evaluate("() => window.fractalViewer.rescanDevices()")
    page.evaluate("() => window.fractalViewer.openMachine('footpedal')")
    expect(_rail_machine(page).locator("#flash-card")).to_be_visible(timeout=10000)


# --------------------------------------------------------------------------
# One header row, and the View menu
# --------------------------------------------------------------------------

# Whether the header is one row: every one of its parts centred on one line, and the
# bar no taller than one.
ONE_ROW = """() => {
    const bar = document.querySelector('.toolbar');
    const mids = [...bar.children].map((el) => el.getBoundingClientRect())
        .filter((r) => r.width > 0).map((r) => (r.top + r.bottom) / 2);
    return { spread: Math.max(...mids) - Math.min(...mids), height: bar.offsetHeight };
}"""


def _canvas_ring(page: Page) -> None:
    """The canvas ring, from the key, with nothing selected."""
    page.evaluate(
        "() => { document.activeElement && document.activeElement.blur(); "
        "const v = window.fractalViewer; v.selectedName = null; v.renderSelectedPanel(); }"
    )
    page.keyboard.press("m")
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)


@pytest.mark.e2e
def test_the_header_is_one_row_at_1024_px(page: Page, bench: str):
    """At 1024 px wide the header is one row, at the top of the site and deep in it: the
    site's drop-down (choosing loads; Load is gone), the trail (Zoom Out is gone), ⚙ View,
    the ring and the problems' count, and a short pill whose tooltip is the whole of it."""
    page.set_viewport_size({"width": 1024, "height": 700})
    _open(page, bench)
    for gone in ("#load-btn", "#zoom-out-btn"):
        expect(page.locator(gone)).to_have_count(0)
    pill = page.locator(".toolbar .badge")
    expect(pill).to_have_text("prototype")
    expect(pill).to_have_attribute("title", "FRACTAL VIEWER — unratified prototype")
    row = page.evaluate(ONE_ROW)
    assert row["spread"] < 4 and row["height"] < 60, row

    # Deep in the site the trail is longest; still one row, the level in view.
    page.evaluate("() => window.fractalViewer.selectAtItsLevel('printer_1.frame_system.mainboard')")
    expect(page.locator("#breadcrumb .crumb")).to_have_count(3)
    row = page.evaluate(ONE_ROW)
    assert row["spread"] < 4 and row["height"] < 60, row
    trail, last = _rect(page, "#breadcrumb"), _rect(page, "#breadcrumb .crumb >> nth=-1")
    assert last["r"] <= trail["r"] + 1 and last["l"] >= trail["l"] - 1, (trail, last)
    # A crumb goes up to its level; Backspace goes up one.
    page.locator("#breadcrumb .crumb").nth(1).click()
    expect(page.locator("#breadcrumb .crumb")).to_have_count(2)
    assert page.evaluate("() => window.fractalViewer.selectedName") == "printer_1.frame_system"
    page.keyboard.press("Backspace")
    expect(page.locator("#breadcrumb .crumb")).to_have_count(1)

    # Choosing a site loads it.
    page.locator("#site-select").select_option("parts_library")
    expect(page.locator("#contents-list")).not_to_contain_text("workbench", timeout=15000)
    expect(page.locator("#breadcrumb .crumb").first).not_to_have_text("garage")
    page.locator("#site-select").select_option("garage")
    expect(page.locator("#contents-list")).to_contain_text("workbench", timeout=15000)

    # The View menu, opened, stays inside the page.
    page.locator("#view-menu > summary").click()
    body = _rect(page, "#view-menu .view-menu-body")
    assert body["r"] <= 1024 and body["l"] >= 0, body


@pytest.mark.e2e
def test_the_tab_strip_and_the_hint_are_one_line_at_1024_px(page: Page, bench: str):
    """At 1024 px wide, with a Machine open, the rail's tab strip is one row -- the
    Machine's tab names its node, the whole title with the port its tooltip -- and
    the hint bar is one line, nothing of it cut."""
    page.set_viewport_size({"width": 1024, "height": 700})
    _open(page, bench)
    cut = page.evaluate(
        "() => { const h = document.getElementById('viewer-hint'); "
        "return h.scrollWidth > h.clientWidth; }"
    )
    assert not cut
    assert page.locator("#viewer-hint").bounding_box()["height"] < 40  # one line
    page.locator(BOARD_BADGE).click()
    _rail_machine(page)
    tab = page.locator(".panel-rail .rail-tab[data-panel='machine'] .rail-tab-name")
    expect(tab).to_have_text("printer_1")
    expect(tab).to_have_attribute("title", re.compile(re.escape(PRINTER)))
    tops = page.evaluate(
        "() => [...document.querySelectorAll('.panel-rail .rail-tab')]"
        ".map((t) => Math.round(t.getBoundingClientRect().top))"
    )
    assert len(tops) == 3 and len(set(tops)) == 1, tops


@pytest.mark.e2e
def test_the_view_menu_holds_snap_detail_and_outlines_and_the_ring_backs_each(
    page: Page, bench: str
):
    """Snap to grid, Detail and Assembly outlines are in one ⚙ View menu, folded until
    opened and folded away by a press elsewhere; each wears the address of its cell of
    the canvas ring's View (a cell of its own, in Fit's seat, with Fit first in it),
    and the cell does what the item does."""
    _open(page, bench)
    for item in ("#snap-toggle", "#detail-mode", "#overlay-toggle"):
        expect(page.locator(item)).to_be_hidden()
    page.locator("#view-menu > summary").click()
    for item in ("#snap-toggle", "#detail-mode", "#overlay-toggle"):
        expect(page.locator(item)).to_be_visible()
    label = lambda item: page.locator(f"#view-menu label:has({item})")  # noqa: E731
    expect(label("#snap-toggle")).to_have_attribute("data-address", "46", timeout=5000)
    expect(label("#detail-mode")).to_have_attribute("data-address", "428")
    expect(label("#overlay-toggle")).to_have_attribute("data-address", "44")
    expect(label("#walls-toggle")).to_have_attribute("data-address", "49")
    expect(page.locator("#view-menu > summary")).to_have_attribute("title", re.compile("⌗4"))
    page.locator("#snap-toggle").uncheck()
    assert page.evaluate("() => window.fractalViewer.transformControls.translationSnap") is None
    page.locator("#status").click()
    expect(page.locator("#snap-toggle")).to_be_hidden()

    # View › Snap to grid: the tick-box's own work, and the tick-box follows.
    _canvas_ring(page)
    for digit in "46":
        page.keyboard.press(digit)
    expect(page.locator("#status")).to_contain_text("⌗46")
    assert page.evaluate("() => window.fractalViewer.transformControls.translationSnap") == 50
    expect(page.locator("#snap-toggle")).to_be_checked()
    # View › Detail › Dot, and › Outlines.
    _canvas_ring(page)
    for digit in "422":
        page.keyboard.press(digit)
    expect(page.locator("#detail-mode")).to_have_value("dot")
    page.wait_for_function(
        "() => Object.values(window.fractalViewer.meshByName).some((m) => m.userData.isDot)"
    )
    _canvas_ring(page)
    for digit in "44":
        page.keyboard.press(digit)
    expect(page.locator("#overlay-toggle")).not_to_be_checked()
    assert page.evaluate("() => Object.keys(window.fractalViewer.compoundOverlayByKey).length") == 0
    # View › Fit: Fit, one ring down from where it was.
    _canvas_ring(page)
    for digit in "48":
        page.keyboard.press(digit)
    expect(page.locator("#status")).to_contain_text("Framed")
    expect(page.locator("#status")).to_contain_text("⌗48")


# --------------------------------------------------------------------------
# Problems once
# --------------------------------------------------------------------------


@pytest.mark.e2e
def test_problems_are_one_folded_line_in_site_and_the_headers_count_opens_it(
    page: Page, start_server
):
    """Site says its problems in one folded line, "N problems ›", where the list stood
    above Contents; the header's count opens the fold, and each problem still selects
    its piece."""
    url = start_server()
    page.goto(f"{url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=20000)
    problems = page.locator("#site-problems")
    expect(problems).to_be_hidden()
    _select(page, "printer_1")
    page.locator("#pos-x").fill("650")
    page.locator("#pos-x").press("Tab")
    expect(page.locator("#validity-indicator")).to_contain_text("1 violation", timeout=5000)
    expect(problems).to_be_visible()
    expect(problems.locator("summary")).to_have_text("1 problem ›")
    rows = page.locator("#problem-list li")
    expect(rows.first).to_be_hidden()
    assert problems.bounding_box()["height"] < 32  # one line, above Contents
    assert problems.bounding_box()["y"] < page.locator("#contents-list").bounding_box()["y"]

    page.locator("#validity-indicator").click()
    expect(rows.first).to_be_visible(timeout=2000)
    expect(rows.first).to_have_text("printer_1 and printer_2 overlap")
    _select(page, "workbench")
    rows.first.click()
    assert page.evaluate("() => window.fractalViewer.selectedName") == "printer_1"

    page.locator("#pos-x").fill("100")
    page.locator("#pos-x").press("Tab")
    expect(page.locator("#validity-indicator")).to_have_text("Layout valid", timeout=5000)
    expect(problems).to_be_hidden()


# --------------------------------------------------------------------------
# The hint bar
# --------------------------------------------------------------------------


@pytest.mark.e2e
def test_the_hint_shows_on_a_first_visit_fades_after_a_few_actions_and_question_mark_restores_it(
    page: Page, bench: str
):
    """A first visit shows the hint bar; a few things done and it fades, and a later
    visit starts without it; ? brings it back, and puts it away again."""
    _open(page, bench)
    hint = page.locator("#viewer-hint")
    faded = re.compile(r"\bfaded\b")
    expect(hint).not_to_have_class(faded)
    expect(hint).to_have_css("opacity", "1")
    for path in ("workbench", "printer_1", "printer_2"):
        _select(page, path)
    expect(hint).not_to_have_class(faded)
    page.evaluate("() => window.fractalViewer.zoomIn('printer_2')")
    expect(hint).to_have_class(faded)
    expect(hint).to_have_css("opacity", "0", timeout=3000)

    _open(page, bench)
    expect(hint).to_have_class(faded)  # remembered for this browser
    page.keyboard.press("?")
    expect(hint).not_to_have_class(faded)
    expect(hint).to_have_css("opacity", "1", timeout=3000)
    page.keyboard.press("?")
    expect(hint).to_have_class(faded)
    page.keyboard.press("?")
    for path in ("workbench", "printer_1", "printer_2", "printer_3"):
        _select(page, path)
    expect(hint).to_have_class(faded)  # and fades again after as many


@pytest.mark.e2e
def test_the_hint_shows_and_fades_with_no_storage(page: Page, bench: str):
    """A browser that keeps nothing (storage refused) still shows the hint, and still
    fades it: what is remembered is a convenience."""
    page.add_init_script(
        "Object.defineProperty(window, 'localStorage', { get() { throw new Error('refused'); } });"
    )
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    _open(page, bench)
    hint = page.locator("#viewer-hint")
    expect(hint).not_to_have_class(re.compile(r"\bfaded\b"))
    for path in ("workbench", "printer_1", "printer_2", "printer_3"):
        _select(page, path)
    expect(hint).to_have_class(re.compile(r"\bfaded\b"))
    assert errors == []


# --------------------------------------------------------------------------
# Walls
# --------------------------------------------------------------------------

# A point of the world, in page pixels, where the first mesh a ray from the camera
# meets is the garage's wall and another piece stands behind or inside it: found by
# casting through a grid of points, as a click there would, walls included.
THROUGH_THE_WALL = """() => {
    const v = window.fractalViewer;
    const rect = v.canvas.getBoundingClientRect();
    const meshes = Object.values(v.meshByName);
    for (let gy = 0.15; gy < 0.95; gy += 0.025) {
        for (let gx = 0.05; gx < 0.95; gx += 0.025) {
            v.pointer.set(gx * 2 - 1, -(gy * 2 - 1));
            v.raycaster.setFromCamera(v.pointer, v.camera);
            const hits = v.raycaster.intersectObjects(meshes, false).map((h) => h.object.userData.key);
            if (hits[0] !== 'garage_building') continue;
            const behind = hits.find((k) => k !== 'garage_building' && !k.startsWith('garage_building.'));
            if (behind) return { x: rect.left + gx * rect.width, y: rect.top + gy * rect.height, behind };
        }
    }
    return null;
}"""

WALL = """() => {
    const m = window.fractalViewer.meshByName['garage_building'];
    return { opacity: m.material.opacity, through: !!m.userData.passThrough };
}"""


@pytest.mark.e2e
def test_a_click_passes_through_a_wall_and_the_toggle_restores_it(page: Page, bench: str):
    """The garage's walls are drawn faded, and a click on them in the world selects what
    is behind or inside; Contents still selects a wall, drawn solid then and with its
    handles; ⚙ View › Walls selectable -- or View › Select walls on the ring -- lets a
    click pick it again."""
    _open(page, bench)
    wall = page.evaluate(WALL)
    assert wall["opacity"] == pytest.approx(0.25, abs=0.01) and wall["through"], wall
    spot = page.evaluate(THROUGH_THE_WALL)
    assert spot, "no point of the world where a wall stands in front of a piece"
    page.mouse.click(spot["x"], spot["y"])
    assert page.evaluate("() => window.fractalViewer.selectedName") == spot["behind"]

    _select(page, "garage_building")
    wall = page.evaluate(WALL)
    assert wall["opacity"] > 0.5 and not wall["through"], wall
    assert page.evaluate(HANDLES)["on"] == "garage_building"
    page.mouse.click(spot["x"], spot["y"])  # still passes through, solid or not
    assert page.evaluate("() => window.fractalViewer.selectedName") == spot["behind"]
    assert page.evaluate(WALL)["opacity"] == pytest.approx(0.25, abs=0.01)

    page.locator("#view-menu > summary").click()
    page.locator("#walls-toggle").check()
    page.locator("#status").click()
    page.mouse.click(spot["x"], spot["y"])
    assert page.evaluate("() => window.fractalViewer.selectedName") == "garage_building"

    # The ring's cell turns it back off: the click passes through again.
    _canvas_ring(page)
    for digit in "49":
        page.keyboard.press(digit)
    expect(page.locator("#status")).to_contain_text("⌗49")
    expect(page.locator("#walls-toggle")).not_to_be_checked()
    page.mouse.click(spot["x"], spot["y"])
    assert page.evaluate("() => window.fractalViewer.selectedName") == spot["behind"]


@pytest.mark.e2e
def test_a_faded_wall_does_not_dim_the_badges_inside(page: Page, bench: str):
    """Seen through the garage's faded wall, the badges inside are not dimmed as being
    behind something."""
    _open(page, bench)
    page.evaluate(FRAMES, OCCLUSION_TESTED)
    for badge in (BOARD_BADGE, PLACE_BADGE, FOOTPEDAL_BADGE):
        expect(page.locator(badge)).not_to_have_class(re.compile(r"\bbehind\b"))
