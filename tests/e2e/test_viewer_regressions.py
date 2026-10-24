"""The viewer does what its controls say: a double-click on a piece zooms into it at
any depth, Apply draws what it rendered and keeps what is staged until then, and the
a board's Machine's polling ends with the Machine.

The Machine's case runs against a server of its own (the conftest's ``start_server``),
with the scripted arduino-cli and the simulated printer, so nothing polls a real port.
"""

import httpx
import pytest
from playwright.sync_api import Page, expect

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


@pytest.fixture
def v_slot_as_it_was():
    """Apply renders into parts/v_slot/; its STL and parameter record are put back."""
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
    length = page.locator("#part-params input[type=range]").first
    expect(length).to_be_visible(timeout=10000)
    page.wait_for_function(
        "() => !window.fractalViewer.meshByName['v_slot'].userData.isPlaceholder"
    )
    before = page.evaluate(MESH_SIZE, "v_slot")

    length.evaluate("(el) => { el.value = 30; el.dispatchEvent(new Event('input')); }")
    apply = page.locator("#apply-btn")
    expect(apply).to_have_text("Apply 1 change", timeout=10000)

    # Right-clicking the part to open its ring selects it again; what is staged stays.
    row.click(button="right")
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    page.keyboard.press("Escape")
    expect(apply).to_have_text("Apply 1 change")
    expect(apply).to_be_enabled(timeout=10000)

    apply.click()
    expect(page.locator("#status")).to_contain_text("v_slot regenerated", timeout=60000)
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
    # In the rail, its tab's ✕.
    page.locator(".panel-rail .rail-tab[data-panel='machine'] .rail-tab-close").click()


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
