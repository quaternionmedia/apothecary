"""A toolpath, previewed in the page: the same steps on a printer and on a router.

The core is one (apothecary/preview); so is what the page does with it. Each case keeps
a file on its machine, moves the Print or Cut card's slider off the left, and reads what
the machine's marks draw in the world: every segment, then through one layer or pass,
then none. Then what differs: a router's file counts from its work zero, so its path
stands where the controller's zero says, and on the coupon once it is set there.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
import pytest
import rings
import windows
from boards import PRINTER, wears
from garage import open_garage
from garage import select as _select
from playwright.sync_api import Page, expect

from apothecary.cam import toolpath
from apothecary.example_hierarchy import ROUTER_COUPON_MARGIN, ROUTER_COUPON_POSITION
from apothecary.preview import ADDITIVE, SUBTRACTIVE, of
from apothecary.projects.parts.router_coupon import DEFAULT as COUPON

ROUTER = "/dev/ttyFAKE3"
CONTROLLER = "cnc_router.frame_system.controller"
MAINBOARD = "printer_1.frame_system.mainboard"
POLL_MS = 2000
WITHIN_A_POLL = 3 * POLL_MS

PRINT = """G90
M83
;LAYER_CHANGE
G1 Z0.2 F600
G1 X105 Y105 F3000
G1 X115 Y105 E0.5
G1 X115 Y115 E0.5
;LAYER_CHANGE
G1 Z0.4 F600
G1 X105 Y105 F3000
G1 X115 Y105 E0.5
G1 X5 Y176 F3000
M84 X Y E
"""
CUT = toolpath.text(toolpath.write(COUPON.cuts(), "router_coupon"))


@dataclass(frozen=True)
class Machine:
    kind: str
    node: str
    port: str
    file: str
    text: str
    expected: object  # the core's own reading of the file, which the page must draw
    word: str
    ring: str  # the Control ring's cell that holds Preview


MACHINES = {
    "printer": Machine(
        "printer",
        "printer_1",
        PRINTER,
        "two_layers.gcode",
        PRINT,
        of(PRINT.splitlines(), ADDITIVE),
        "layer",
        "Print",
    ),
    "router": Machine(
        "router",
        "cnc_router",
        ROUTER,
        "coupon.nc",
        CUT,
        of(CUT.splitlines(), SUBTRACTIVE),
        "pass",
        "Cut",
    ),
}


@pytest.fixture(scope="module")
def url(start_server):
    """Both machines identified and pinned, on one server."""
    url = start_server(
        {
            "APOTHECARY_SIMULATED_ROUTER": ROUTER,
            "APOTHECARY_SIMULATED_SPEED": "0.2",
            "FAKE_ROUTER": "1",
        }
    )
    with httpx.Client(base_url=url, timeout=15.0) as http:
        for port, board in ((PRINTER, MAINBOARD), (ROUTER, CONTROLLER)):
            http.post("/firmware/devices/identify", json={"port": port}).raise_for_status()
            http.put(
                f"/sites/garage/nodes/{board}/device", json={"identity": port}
            ).raise_for_status()
    return url


@pytest.fixture(autouse=True)
def no_page_errors(page: Page):
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    yield
    assert errors == [], errors


def _drawn(page: Page, node: str):
    """What the machine's marks draw of a file's path, or None."""
    return page.evaluate(
        "(path) => { const m = window.fractalViewer.marks[path]; return m && m.marks ? m.marks.toolpath() : null; }",
        node,
    )


def _open(page: Page, url: str, machine: Machine):
    """The machine's Machine, its Print or Cut window in view, the file kept and chosen."""
    open_garage(page, url, settle=False)
    wears(page, machine.node)
    _select(page, machine.node)
    page.locator("#selected-body .device-section .dev-open").click()
    windows.machine_ready(page, machine.kind)
    body = windows.machine(page)
    windows.from_the_windows_menu(page, "machine-print")
    body.locator("#print-file").set_input_files(
        {"name": machine.file, "mimeType": "text/plain", "buffer": machine.text.encode()}
    )
    expect(body.locator("#print-pick option", has_text=machine.file).first).to_be_attached(
        timeout=5000
    )
    body.locator("#print-pick").select_option(
        label=body.locator("#print-pick option", has_text=machine.file).first.inner_text()
    )
    return body


def _slide(page: Page, body, value: int) -> None:
    body.locator("#print-preview").evaluate(
        "(el, v) => { el.value = v; el.dispatchEvent(new Event('input', { bubbles: true })); }",
        value,
    )


@pytest.mark.e2e
@pytest.mark.parametrize("kind", list(MACHINES))
def test_a_kept_file_s_path_is_drawn_and_scrubbed(page: Page, url: str, kind: str):
    """Off until it is asked for; all of it at the right; through one group below that;
    nothing again at the left. What is drawn is what the core reads of the file."""
    machine = MACHINES[kind]
    expected = machine.expected
    body = _open(page, url, machine)
    slider, said = body.locator("#print-preview"), body.locator("#print-preview-said")
    expect(said).to_have_text("off")
    assert _drawn(page, machine.node) is None

    _slide(page, body, 1)
    groups = expected.groups
    expect(slider).to_have_attribute("max", str(len(groups)), timeout=5000)
    expect(said).to_contain_text("all of it")
    expect(said).to_contain_text(machine.expected.kinds[0])
    drawn = _drawn(page, machine.node)
    assert drawn["process"] == expected.process
    assert drawn["segments"] == drawn["drawn"] == len(expected.kind_of)

    # Through the first group alone, and its name said.
    _slide(page, body, 1)
    expect(said).to_contain_text(groups[0].label)
    assert _drawn(page, machine.node)["drawn"] == groups[0].count < len(expected.kind_of)

    _slide(page, body, 0)
    expect(said).to_have_text("off")
    assert _drawn(page, machine.node) is None


@pytest.mark.e2e
@pytest.mark.parametrize("kind", list(MACHINES))
def test_the_ring_turns_it_on_and_off(page: Page, url: str, kind: str):
    machine = MACHINES[kind]
    body = _open(page, url, machine)
    on_the_ring = ("Device", "Control", machine.ring, "Preview")
    rings.on_row(page, machine.node, *on_the_ring)
    expect(body.locator("#print-preview-said")).to_contain_text("all", timeout=5000)
    assert _drawn(page, machine.node)["drawn"] == len(machine.expected.kind_of)
    rings.on_row(page, machine.node, *on_the_ring)
    expect(body.locator("#print-preview-said")).to_have_text("off")
    assert _drawn(page, machine.node) is None


@pytest.mark.e2e
def test_a_printer_s_file_stands_at_its_bed(page: Page, url: str):
    """A printer's file is in the bed's coordinates: its zero is the volume's."""
    machine = MACHINES["printer"]
    body = _open(page, url, machine)
    _slide(page, body, 1)
    expect(body.locator("#print-preview-said")).to_contain_text("all", timeout=5000)
    assert _drawn(page, machine.node)["origin"] == {"x": 0, "y": 0, "z": 0}


@pytest.mark.e2e
def test_a_router_s_file_stands_at_its_work_zero_and_on_the_coupon_once_zeroed_there(
    page: Page, url: str
):
    """A router's file counts from its work zero, which moves it. Touched off at the
    stock's corner, the file's outline stands on the coupon the garage draws."""
    machine = MACHINES["router"]
    body = _open(page, url, machine)
    _slide(page, body, 1)
    expect(body.locator("#print-preview-said")).to_contain_text("all", timeout=5000)
    with httpx.Client(base_url=url, timeout=15.0) as http:
        http.post(
            "/firmware/printers/control", json={"port": ROUTER, "armed": True}
        ).raise_for_status()
        at = http.get("/firmware/printers/status", params={"port": ROUTER}).json()["position"]
        # The stock's corner, in machine coordinates: the working area's corner, 15 mm up
        # (the spoilboard and the stock), counted down from the home corner.
        dx, dy, dz = -400 - at["x"], -600 - at["y"], -65 - at["z"]
        jog = f"$J=G91 G21 X{dx:.3f} Y{dy:.3f} Z{dz:.3f} F4000"
        http.post(
            "/firmware/printers/command", json={"port": ROUTER, "command": jog}
        ).raise_for_status()
        expect(body.locator("#c-pos-s")).to_contain_text(
            "machine X-400.0 Y-600.0 Z-65.00", timeout=4 * WITHIN_A_POLL
        )
        http.post(
            "/firmware/printers/command", json={"port": ROUTER, "command": "G10 L20 P1 X0 Y0 Z0"}
        ).raise_for_status()
    page.wait_for_function(
        "() => { const t = window.fractalViewer.marks.cnc_router.marks.toolpath(); return t && t.origin.z === 15; }",
        timeout=2 * WITHIN_A_POLL,
    )
    placed = page.evaluate(
        """() => { const m = window.fractalViewer.marks.cnc_router.marks;
            return { machine: { x: m.group.position.x, y: -m.group.position.z, z: m.group.position.y },
                     volume: m.volumeOrigin, origin: m.toolpath().origin }; }"""
    )
    assert placed["origin"] == {"x": 0, "y": 0, "z": 15}
    # In the world, in the site's coordinates: the file's zero is the stock's corner, and
    # the plate stands the margin in from it, its top the file's z 0.
    for axis in "xy":
        zero = placed["machine"][axis] + placed["volume"][axis] + placed["origin"][axis]
        assert zero == pytest.approx(getattr(ROUTER_COUPON_POSITION, axis) - ROUTER_COUPON_MARGIN)
    top = placed["machine"]["z"] + placed["volume"]["z"] + placed["origin"]["z"]
    assert top == pytest.approx(ROUTER_COUPON_POSITION.z + COUPON.cuts().stock.thickness)
