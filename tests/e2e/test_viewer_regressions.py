"""The viewer does what its controls say: a double-click on a piece zooms into it at
any depth, Apply draws what it rendered and keeps what is staged until then, and the
a board's Machine's polling ends with the Machine.

The Machine's case runs against a server of its own (the conftest's ``start_server``),
with the scripted arduino-cli and the simulated printer, so nothing polls a real port.
"""

import re

import httpx
import pytest
import windows
from playwright.sync_api import Page, expect
from viewer_ready import settled

from apothecary.projects.parts.skeleton import ROOT
from apothecary.projects.parts.stl_renderer import get_renderer, params_sidecar_path

PRINTER = "/dev/ttyFAKE1"
BOARD = "printer_1.frame_system.mainboard"
POLL_MS = 2000  # the Machine's default interval (widgets/machine.js)
POLLS = ("/firmware/printers/status", "/firmware/printers/log")

# A point on the canvas where the first piece hit is one at this level with pieces
# inside it, and nothing is drawn over the canvas there.
POINT_ON_A_PIECE_WITH_PIECES = """() => {
    const v = window.fractalViewer, rect = v.canvas.getBoundingClientRect();
    const focus = v.focusPath.join('.');
    const wanted = new Set(v.currentFocusNode().children.filter((c) => c.children.length)
        .map((c) => (focus ? `${focus}.${c.name}` : c.name)));
    for (let j = 1; j < 30; j++) for (let i = 1; i < 40; i++) {
        const at = { clientX: rect.left + (rect.width * i) / 40, clientY: rect.top + (rect.height * j) / 30 };
        const key = v.raycastChild(at);
        if (wanted.has(key) && document.elementFromPoint(at.clientX, at.clientY) === v.canvas) {
            return { name: v.renderNodeByKey[key].name, x: at.clientX, y: at.clientY };
        }
    }
    return null;
}"""

# The size of the mesh drawn for a node, in the scene's units (mm).
MESH_SIZE = """(key) => {
    const g = window.fractalViewer.meshByName[key].geometry;
    g.computeBoundingBox();
    const s = g.boundingBox.max.clone().sub(g.boundingBox.min);
    return [s.x, s.y, s.z];
}"""


def _open(page: Page, url: str) -> None:
    page.goto(url)
    expect(page.locator("#status")).to_contain_text("Loaded", timeout=20000)
    page.evaluate("() => window.fractalViewer.waveDone")


@pytest.mark.e2e
def test_double_clicking_a_piece_below_the_root_zooms_into_it(page: Page, base_url: str):
    _open(page, f"{base_url}/viewer/sites/garage")
    page.locator("#contents-list .contents-item", has_text="printer_1").dblclick()
    page.wait_for_function("() => window.fractalViewer.focusPath.join('.') === 'printer_1'")
    page.evaluate("() => window.fractalViewer.waveDone")

    point = page.evaluate(POINT_ON_A_PIECE_WITH_PIECES)
    assert point, "no piece of printer_1 with pieces inside it is on the canvas"
    page.mouse.dblclick(point["x"], point["y"])

    page.wait_for_function(
        "(path) => window.fractalViewer.focusPath.join('.') === path",
        arg=f"printer_1.{point['name']}",
        timeout=5000,
    )
    expect(page.locator("#breadcrumb")).to_contain_text(point["name"])


# Where the floor grid lies, where the middle of a piece is (the site's x and y), and
# how much of the canvas's height the piece's box takes: its corners through the camera.
ON_THE_GRID = """(key) => {
    const v = window.fractalViewer, b = v.renderNodeByKey[key].world_bounds;
    const ys = [];
    for (const x of [b.min[0], b.max[0]]) for (const y of [b.min[1], b.max[1]])
        for (const z of [b.min[2], b.max[2]]) ys.push(v.sceneAt(x, y, z).project(v.camera).y);
    return {
        grid: v.siteAt(v.gridHelper.position).slice(0, 2),
        middle: [(b.min[0] + b.max[0]) / 2, (b.min[1] + b.max[1]) / 2],
        share: (Math.max(...ys) - Math.min(...ys)) / 2,
    };
}"""


@pytest.mark.e2e
def test_a_part_stepped_into_stands_on_the_grid_and_fills_the_view(page: Page, base_url: str):
    """calibration_cube stands in the parts library far from the site's origin. Stepped
    into, it stands on the floor grid, which lies under the level in view, and is framed
    near enough to take a good share of the view, as View › Fit frames it."""
    _open(page, f"{base_url}/viewer/sites/parts_library")
    page.locator("#contents-list .contents-item[data-path='calibration_cube']").dblclick()
    page.wait_for_function("() => window.fractalViewer.focusPath.join('.') === 'calibration_cube'")
    page.evaluate("() => window.fractalViewer.waveDone")
    settled(page)
    seen = page.evaluate(ON_THE_GRID, "calibration_cube")
    assert abs(seen["middle"][0]) > 100, (
        f"the cube stands near the origin, which tests nothing: {seen}"
    )
    for grid, middle in zip(seen["grid"], seen["middle"], strict=True):
        assert abs(grid - middle) < 10, f"the grid lies away from the cube: {seen}"
    assert seen["share"] > 0.2, f"the cube takes {seen['share']:.0%} of the view's height"


# The view put in front of a piece (its -y side, level with its middle), and for each point
# of the site's frame named: where across the canvas it falls (0 the left edge, 1 the
# right) and how far behind the piece's front a ray through it meets the mesh. With them,
# where the axes drawn point, in the site's frame.
FROM_THE_FRONT = """([key, points]) => {
    const v = window.fractalViewer, m = v.meshByName[key], b = v.renderNodeByKey[key].world_bounds;
    const mid = [0, 1, 2].map((i) => (b.min[i] + b.max[i]) / 2);
    v.orbitControls.target.copy(v.sceneAt(...mid));
    v.camera.position.copy(v.sceneAt(mid[0], b.min[1] - 60, mid[2]));
    v.orbitControls.update();
    v.camera.updateMatrixWorld();
    const seen = points.map((p) => {
        const s = v.sceneAt(...p).project(v.camera);
        v.raycaster.setFromCamera({ x: s.x, y: s.y }, v.camera);
        const hit = v.raycaster.intersectObject(m, false)[0];
        return { across: (s.x + 1) / 2, behind: hit ? v.siteAt(hit.point)[1] - b.min[1] : null };
    });
    const vec = (x, y, z) => v.camera.position.clone().set(x, y, z);
    const axis = (x, y, z) => v.siteAt(
        v.axesHelper.localToWorld(vec(x, y, z)).sub(v.axesHelper.localToWorld(vec(0, 0, 0))),
    ).map((n) => Math.round(n));
    return { seen, axes: { red: axis(1, 0, 0), green: axis(0, 1, 0), blue: axis(0, 0, 1) } };
}"""


@pytest.mark.e2e
def test_the_site_is_drawn_as_openscad_draws_it_not_mirrored(page: Page, base_url: str):
    """calibration_cube's SCAD cuts a 1.5 mm notch from its top edge at its origin corner:
    its -x, its -y side, its top. Seen from the site's front, the notch is at the top left,
    as OpenSCAD draws it -- a ray through it meets the mesh 1.5 mm in, one through the
    top right meets the front face -- and the axes are the site's: red x, green y, blue z."""
    _open(page, f"{base_url}/viewer/sites/parts_library")
    page.locator("#contents-list .contents-item[data-path='calibration_cube']").dblclick()
    page.wait_for_function("() => window.fractalViewer.focusPath.join('.') === 'calibration_cube'")
    page.wait_for_function(
        "() => { const m = window.fractalViewer.meshByName['calibration_cube'];"
        " return m && !m.userData.isPlaceholder; }",
        timeout=60000,
    )
    page.evaluate("() => window.fractalViewer.waveDone")
    settled(page)
    bounds = page.evaluate(
        "() => window.fractalViewer.renderNodeByKey['calibration_cube'].world_bounds"
    )
    (x0, y0, _), (x1, _, top) = bounds["min"], bounds["max"]
    notch, other = [x0 + 0.75, y0, top - 0.75], [x1 - 0.75, y0, top - 0.75]
    found = page.evaluate(FROM_THE_FRONT, ["calibration_cube", [notch, other]])
    at_notch, at_other = found["seen"]
    assert at_notch["behind"] == pytest.approx(1.5, abs=0.1), (
        f"no notch at the origin corner: {found}"
    )
    assert at_other["behind"] == pytest.approx(0, abs=0.1), f"the front face is not whole: {found}"
    assert at_notch["across"] < 0.5 < at_other["across"], (
        f"seen from the front, the notch at the site's -x is drawn on the right, mirrored: {found}"
    )
    assert found["axes"] == {"red": [1, 0, 0], "green": [0, 1, 0], "blue": [0, 0, 1]}, found


@pytest.fixture
def v_slot_as_it_was():
    """Apply renders a variant into the cache, but opening the part draws its own STL,
    built into parts/v_slot/ when a fresh clone lacks it; that STL and its parameter
    record are put back."""
    stl = ROOT / "parts" / "v_slot" / "v_slot.stl"
    files = (stl, params_sidecar_path(stl))
    kept = {path: path.read_bytes() for path in files if path.exists()}
    yield
    for path in files:
        if path in kept:
            path.write_bytes(kept[path])
        else:
            path.unlink(missing_ok=True)


@pytest.mark.e2e
@pytest.mark.skipif(not get_renderer().is_available, reason="OpenSCAD not installed")
def test_apply_draws_what_it_rendered(page: Page, base_url: str, v_slot_as_it_was):
    """A staged length survives re-selecting the part from the ring; Apply renders it,
    the mesh on screen is the new one, and nothing is left staged."""
    _open(page, f"{base_url}/viewer/sites/parts_library")
    row = page.locator("#contents-list .contents-item[data-path='v_slot']")
    row.click()
    windows.open_window(page, "part-parameters")
    length = page.locator("#part-params input[type=range]").first
    expect(length).to_be_visible(timeout=10000)
    page.wait_for_function(
        "() => !window.fractalViewer.meshByName['v_slot'].userData.isPlaceholder"
    )
    before = page.evaluate(MESH_SIZE, "v_slot")

    length.evaluate("(el) => { el.value = 30; el.dispatchEvent(new Event('input')); }")
    apply = page.locator("#apply-btn")
    expect(apply).to_have_text("Apply 1 change", timeout=10000)

    # Ctrl+right-clicking the part to open its ring selects it again; what is staged stays.
    row.click(button="right", modifiers=["Control"])
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    page.keyboard.press("Escape")
    expect(apply).to_have_text("Apply 1 change")
    expect(apply).to_be_enabled(timeout=10000)

    apply.click()
    # Rendered now, or found in the variant cache from an earlier Apply of the same length.
    expect(page.locator("#status")).to_contain_text(
        re.compile(r"v_slot (regenerated|from the cache, nothing rendered): an applied variant"),
        timeout=60000,
    )
    page.evaluate("() => window.fractalViewer.waveDone")
    after = page.evaluate(MESH_SIZE, "v_slot")
    assert max(after) == pytest.approx(max(before) + 10, abs=0.5), (before, after)
    expect(page.locator("#stage-summary")).to_have_text("No staged changes")


@pytest.fixture(scope="module")
def printer_url(start_server):
    """A server of this module's own: its printer is identified, the Machine's subject."""
    url = start_server()
    httpx.post(
        f"{url}/firmware/devices/identify", json={"port": PRINTER}, timeout=15.0
    ).raise_for_status()
    return url


@pytest.fixture
def pinned(printer_url):
    """printer_1's mainboard pinned to the printer's port, however the last test left it."""
    httpx.put(
        f"{printer_url}/sites/garage/nodes/{BOARD}/device", json={"identity": PRINTER}, timeout=15.0
    ).raise_for_status()
    return printer_url


def _leave_the_site(page: Page, url: str) -> None:
    page.locator("#site-select").select_option("parts_library")


def _unpin(page: Page, url: str) -> None:
    page.request.delete(f"{url}/sites/garage/nodes/{BOARD}/device")
    page.evaluate("() => window.fractalViewer.rescanDevices()")


def _close(page: Page, url: str) -> None:
    # Its tab's ✕.
    windows.close(page, "machine")


@pytest.mark.e2e
@pytest.mark.parametrize(
    "leave",
    [_leave_the_site, _unpin, _close],
    ids=["site-left", "unpinned", "closed"],
)
def test_the_machine_popup_stops_polling_when_it_goes(page: Page, pinned: str, leave):
    page.clock.install()
    page.goto(f"{pinned}/viewer/sites/garage")
    badge = page.locator(".world-badge[data-path='printer_1']")
    expect(badge).to_be_visible(timeout=15000)
    badge.click()
    machine = page.locator(".panel[data-panel='machine']")
    expect(machine.locator("#c-state")).to_contain_text("printing", timeout=10000)
    with page.expect_request(lambda r: POLLS[0] in r.url, timeout=POLL_MS + 3000):
        pass  # it polls while it is open

    leave(page, pinned)
    expect(machine).to_have_count(0, timeout=10000)
    polls = []
    page.on("request", lambda r: polls.append(r.url) if any(p in r.url for p in POLLS) else None)
    page.clock.pause_at(page.evaluate("Date.now()") + 1000)
    page.clock.fast_forward(POLL_MS * 3)
    # Anything the timers started was requested before this is.
    with page.expect_request("**/health"):
        page.evaluate("() => fetch('/health')")
    assert polls == []
