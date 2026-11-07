"""A toolpath, previewed in the page: the same steps on a printer and on a router.

The core is one (apothecary/preview); so is what the page does with it. Each case keeps
a file on its machine, moves the Print or Cut card's slider off the left, and reads what
the machine's marks draw in the world: every segment, then through one layer or pass,
then none. Then what differs: a router's file counts from its work zero, so its path
stands where the controller's zero says, and on the coupon once it is set there.

The Machine view lands on that path, from ⊞ Windows and from the ring: the selected
machine's Machine opened when none is, the file its card has chosen drawn and framed,
or how a file comes to be kept; and with no machine to open, why not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx
import pytest
import rings
import windows
from boards import PRINTER, wears
from garage import open_garage, status
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


# --- the Machine view lands on the path ---------------------------------------------------

MACHINE_VIEW = ".windows-menu-body .view-item[data-view='machine']"


def _keep_only(url: str, *machines: Machine, cut: bool = False) -> None:
    """The files kept on the host: these machines' alone, in this order, each as a
    person keeps one with Choose File; then, with ``cut``, the coupon's toolpath written
    for the router as its Cut card's Toolpath writes it, recorded as the router's."""
    with httpx.Client(base_url=url, timeout=15.0) as http:
        for kept in http.get("/firmware/printers/prints").json():
            http.delete(f"/firmware/printers/prints/{kept['id']}").raise_for_status()
        for machine in machines:
            http.post(
                "/firmware/printers/prints",
                params={"name": machine.file, "machine": machine.kind},
                content=machine.text,
            ).raise_for_status()
        if cut:
            http.post(
                "/cam/cut",
                json={
                    "part": "router_coupon",
                    "site": "garage",
                    "router": CONTROLLER,
                    "port": ROUTER,
                },
            ).raise_for_status()


def _selected(page: Page, url: str, node: str | None) -> None:
    """The garage with no Machine open, and ``node`` selected (or nothing)."""
    open_garage(page, url, settle=False)
    wears(page, MACHINES["printer"].node)
    wears(page, MACHINES["router"].node)
    if node:
        _select(page, node)
    assert page.evaluate("() => window.fractalViewer.machine") is None


def _from_windows(page: Page) -> None:
    """⊞ Windows › Machine, as a person presses it."""
    page.locator("#windows-menu > summary").click()
    page.locator(MACHINE_VIEW).click(timeout=5000)
    expect(page.locator(".windows-menu-body")).to_be_hidden()


def _from_the_ring(page: Page) -> None:
    """The canvas ring's Panels › Windows › Machine view, the ring opened from its key:
    a world framed on a machine has a piece under any point of it."""
    rings.open_from_key(page)
    rings.press(page, "Panels", "Windows", "Machine view")


def _framed(page: Page, node: str) -> dict:
    """The middle of the drawn path's box and what the world's view turns about, in the
    world's own coordinates, and how far the eye stands from it."""
    return page.evaluate(
        """(path) => { const v = window.fractalViewer, box = v.marks[path].marks.toolpathBox();
            const mid = ["x", "y", "z"].map((k) => (box.min[k] + box.max[k]) / 2);
            const t = v.orbitControls.target;
            return { mid, target: [t.x, t.y, t.z], eye: v.camera.position.distanceTo(t),
                     across: box.min.distanceTo(box.max) }; }""",
        node,
    )


@pytest.mark.e2e
@pytest.mark.parametrize("kind", list(MACHINES))
def test_windows_machine_opens_the_selected_machine_and_lands_on_its_file_s_path(
    page: Page, url: str, kind: str
):
    """A machine selected, its Machine not open, its file kept: ⊞ Windows › Machine opens
    the Machine, lays its windows out, draws the whole of the file's path in the world
    and frames it, the slider that goes through it beside it."""
    machine = MACHINES[kind]
    expected = machine.expected
    _keep_only(url, machine)
    _selected(page, url, machine.node)
    page.locator("#windows-menu > summary").click()
    entry = page.locator(MACHINE_VIEW)
    expect(entry).not_to_have_class(re.compile(r"\bmissing\b"))
    expect(entry).to_have_attribute("title", re.compile(f"Opens {machine.node}'s Machine"))
    entry.click(timeout=5000)
    expect(page.locator(".windows-menu-body")).to_be_hidden()

    expect(page.locator(f"{windows.MACHINE} > .machine.kind-{kind}")).to_be_attached(timeout=20000)
    body = windows.machine(page)
    expect(body.locator("#print-preview-said")).to_contain_text("all of it", timeout=10000)
    assert windows.state(page, "machine-print")["shown"] is True
    slider = body.locator("#print-preview")
    expect(slider).to_have_attribute("max", str(len(expected.groups)))
    assert slider.input_value() == str(len(expected.groups))
    drawn = _drawn(page, machine.node)
    assert drawn["process"] == expected.process
    assert drawn["segments"] == drawn["drawn"] == len(expected.kind_of)

    said = status(page)
    expect(said).to_contain_text(f"{machine.file}'s path is drawn on {machine.node} and framed")
    expect(said).to_contain_text(f"the preview slider in its {machine.ring} goes through each")
    expect(said).to_contain_text(machine.word)
    expect(said).not_to_have_class(re.compile(r"\berror\b"))
    # Framed: the view turns about the path's middle, from near enough to read it.
    framed = _framed(page, machine.node)
    assert framed["target"] == pytest.approx(framed["mid"], abs=1.0)
    assert framed["eye"] < 6 * max(framed["across"], 30)


@pytest.mark.e2e
@pytest.mark.parametrize("kind", list(MACHINES))
def test_windows_machine_lands_on_the_path_of_the_machine_stepped_into(
    page: Page, url: str, kind: str
):
    """Double-clicked into, nothing selected: the machine stepped into is the one its
    view opens, and its file's path is drawn and framed, still stepped in."""
    machine = MACHINES[kind]
    _keep_only(url, machine)
    _selected(page, url, None)
    page.locator(f"#contents-list .contents-item[data-path='{machine.node}']").dblclick()
    expect(status(page)).to_contain_text(f"Stepped into {machine.node}")
    assert not page.evaluate("() => window.fractalViewer.selectedName")
    _from_windows(page)
    expect(page.locator(f"{windows.MACHINE} > .machine.kind-{kind}")).to_be_attached(timeout=20000)
    body = windows.machine(page)
    expect(body.locator("#print-preview-said")).to_contain_text("all of it", timeout=10000)
    assert _drawn(page, machine.node)["drawn"] == len(machine.expected.kind_of)
    expect(status(page)).to_contain_text(
        f"{machine.file}'s path is drawn on {machine.node} and framed"
    )
    assert page.evaluate("() => window.fractalViewer.focusPath.join('.')") == machine.node


@pytest.mark.e2e
def test_stepped_into_a_piece_with_no_board_the_machine_view_says_which(page: Page, url: str):
    """The piece stepped into is what the view is asked of, and it has no board to open."""
    _selected(page, url, None)
    page.locator("#contents-list .contents-item[data-path='workbench']").dblclick()
    expect(status(page)).to_contain_text("Stepped into workbench")
    _from_windows(page)
    expect(status(page)).to_contain_text("no Machine is open, and workbench has no board pinned")
    assert page.evaluate("() => window.fractalViewer.machine") is None


@pytest.mark.e2e
def test_windows_machine_lands_on_the_path_in_a_site_reached_through_the_universe(
    page: Page, url: str
):
    """The garage stepped into from its piece in the universe is the garage: its
    router selected, ⊞ Windows › Machine opens the Machine and draws and frames the
    file's path, as it does in the garage opened by its address."""
    machine = MACHINES["router"]
    _keep_only(url, machine)
    page.goto(f"{url}/viewer/sites/apothecary")
    piece = page.locator("#contents-list .contents-item[data-path='site-garage']")
    piece.dblclick(timeout=20000)
    page.wait_for_function("() => window.fractalViewer.siteName === 'garage'")
    wears(page, machine.node)
    _select(page, machine.node)
    assert page.evaluate("() => window.fractalViewer.machine") is None
    _from_windows(page)
    expect(page.locator(f"{windows.MACHINE} > .machine.kind-router")).to_be_attached(timeout=20000)
    body = windows.machine(page)
    expect(body.locator("#print-preview-said")).to_contain_text("all of it", timeout=10000)
    assert _drawn(page, machine.node)["drawn"] == len(machine.expected.kind_of)
    expect(status(page)).to_contain_text(
        f"{machine.file}'s path is drawn on {machine.node} and framed"
    )
    framed = _framed(page, machine.node)
    assert framed["target"] == pytest.approx(framed["mid"], abs=1.0)


@pytest.mark.e2e
@pytest.mark.parametrize("kind", list(MACHINES))
def test_the_ring_s_machine_view_draws_the_open_machine_s_file_and_keeps_a_slider_left_part_way(
    page: Page, url: str, kind: str
):
    """The ring's Panels › Windows › Machine view on an open Machine whose preview is
    off: the chosen file's path drawn, all of it. Asked for again with the slider left
    on one layer or pass, it stays there."""
    machine = MACHINES[kind]
    expected = machine.expected
    body = _open(page, url, machine)
    said = body.locator("#print-preview-said")
    expect(said).to_have_text("off")
    _from_the_ring(page)
    expect(said).to_contain_text("all of it", timeout=10000)
    assert _drawn(page, machine.node)["drawn"] == len(expected.kind_of)
    expect(status(page)).to_contain_text(f"{machine.file}'s path is drawn on {machine.node}")

    _slide(page, body, 1)
    first = expected.groups[0]
    expect(said).to_contain_text(first.label)
    _from_the_ring(page)
    expect(status(page)).to_contain_text(f"and framed, {first.label}")
    assert body.locator("#print-preview").input_value() == "1"
    assert _drawn(page, machine.node)["drawn"] == first.count


@pytest.mark.e2e
@pytest.mark.parametrize("kind", list(MACHINES))
def test_with_no_file_kept_the_machine_view_says_how_one_comes_to_be(
    page: Page, url: str, kind: str
):
    """Nothing kept: the Machine opens and is laid out, nothing is drawn, and the status
    line names the card and the two ways a file comes to be kept in it."""
    machine = MACHINES[kind]
    _keep_only(url)
    _selected(page, url, machine.node)
    _from_windows(page)
    expect(page.locator(f"{windows.MACHINE} > .machine.kind-{kind}")).to_be_attached(timeout=20000)
    said = status(page)
    expect(said).to_contain_text("No path is drawn: no file is kept yet", timeout=10000)
    expect(said).to_contain_text(
        f"In {machine.node}'s {machine.ring}, choose a part under makes, or Choose File"
    )
    expect(said).not_to_have_class(re.compile(r"\berror\b"))
    assert windows.state(page, "machine-print")["shown"] is True
    assert windows.machine(page).locator("#print-preview").input_value() == "0"
    assert _drawn(page, machine.node) is None


@pytest.mark.e2e
def test_with_no_machine_to_open_the_entry_is_greyed_and_a_press_says_why(page: Page, url: str):
    """No Machine open, and nothing selected or a piece with no board: the entry is
    greyed, and pressed it says what to select and leaves the layout as it was."""
    _selected(page, url, None)
    before = page.evaluate(
        "() => window.apothecaryPanels.list().filter((w) => w.open).map((w) => w.id)"
    )
    page.locator("#windows-menu > summary").click()
    entry = page.locator(MACHINE_VIEW)
    expect(entry).to_have_class(re.compile(r"\bmissing\b"))
    other = page.locator(".windows-menu-body .view-item[data-view='part']")
    grey = "(el) => getComputedStyle(el).color"
    assert entry.evaluate(grey) != other.evaluate(grey)
    entry.click(timeout=5000)
    expect(page.locator(".windows-menu-body")).to_be_hidden()
    said = status(page)
    expect(said).to_contain_text("Machine view: no Machine is open and nothing is selected")
    expect(said).to_contain_text("select a machine with a board pinned to it")
    expect(said).to_have_class(re.compile(r"\berror\b"))

    _select(page, "workbench")
    rings.on_world(page, "Panels", "Windows", "Machine view")
    expect(said).to_contain_text("no Machine is open, and workbench has no board pinned")
    assert page.evaluate("() => window.fractalViewer.machine") is None
    after = page.evaluate(
        "() => window.apothecaryPanels.list().filter((w) => w.open).map((w) => w.id)"
    )
    assert after == before


@pytest.mark.e2e
def test_a_printer_draws_its_own_file_not_the_router_s_newer_toolpath(page: Page, url: str):
    """The files kept are every machine's. A router's toolpath, the newest kept, is not
    what a printer's card chooses or its Machine view draws while a file of its own is
    kept; with the toolpath alone kept, nothing is drawn and the status line says whose
    it is."""
    printer = MACHINES["printer"]
    _keep_only(url, printer, cut=True)
    _selected(page, url, printer.node)
    _from_windows(page)
    body = windows.machine(page)
    expect(body.locator("#print-preview-said")).to_contain_text("all of it", timeout=10000)
    expect(body.locator("#print-pick option:checked")).to_contain_text(printer.file)
    assert _drawn(page, printer.node)["process"] == printer.expected.process

    _keep_only(url, cut=True)
    _selected(page, url, printer.node)
    _from_windows(page)
    said = status(page)
    expect(said).to_contain_text(
        "No path is drawn: the file chosen, router_coupon-cnc_router.nc", timeout=10000
    )
    expect(said).to_contain_text("was made for a router, and none is kept for this printer yet")
    assert _drawn(page, printer.node) is None
