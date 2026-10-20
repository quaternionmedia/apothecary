"""What a newcomer meets, through the page: a printer's own Pin pinning its mainboard,
where its Device, its Machine and Slice find it, and Slice's refusals saying which
of "not pinned" and "pinned, not connected" it is; no Slice on a devkit's ring; the
header's Docs and Panels › Docs opening the documentation and the walkthrough's
index; and the site drop-down keeping the address, so a reload, Back and Forward
land where they should.

The server is this module's own: the scripted arduino-cli (an Uno on
/dev/ttyFAKE0, the simulated printer, idle, on /dev/ttyFAKE1), and the scripted
OrcaSlicer of the unit tests. No real serial port is opened.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect
from slicer_helpers import write_fake_orcaslicer
from test_picture_in_the_world import (  # noqa: F401 - fixtures, and a pin of a picture
    _pin,
    fixture_picture,
    leaves_garage_as_found,
)
from viewer_ready import settled

PRINTER = "/dev/ttyFAKE1"
BOARD = "printer_1.frame_system.mainboard"
MACHINE = ".panel[data-panel='machine']"

WEDGES = (
    "() => Object.fromEntries([...document.querySelectorAll('#ring-overlay .wedge')]"
    ".filter((w) => !w.classList.contains('empty'))"
    ".map((w) => [w.dataset.cell, w.getAttribute('aria-label')]))"
)


@pytest.fixture(scope="module")
def url(base_url, start_server, tmp_path_factory):
    """This module's own server: the simulated printer idle on /dev/ttyFAKE1, nothing
    pinned, and the scripted OrcaSlicer. ``base_url`` is asked for only so that with no
    server to run against this is skipped, as every browser test is."""
    orca = write_fake_orcaslicer(tmp_path_factory.mktemp("orca"))
    return start_server(
        {"APOTHECARY_SIMULATED_PRINTER": "idle", "APOTHECARY_ORCASLICER": str(orca)}
    )


def _open(page: Page, url: str, site: str = "garage", query: str = "") -> None:
    page.goto(f"{url}/viewer/sites/{site}{query}")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=20000)
    page.evaluate("() => localStorage.removeItem('apothecary.panels')")
    settled(page)


def _status(page: Page):
    return page.locator("#status")


def _said(page: Page, text: str, timeout: int = 20000) -> None:
    expect(_status(page)).to_contain_text(text, timeout=timeout)


def _row(page: Page, path: str):
    return page.locator(f"#contents-list .contents-item[data-path='{path}']")


def _ring_on(page: Page, path: str) -> None:
    _row(page, path).click(button="right", modifiers=["Control"])
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)


def _canvas_ring(page: Page) -> None:
    page.evaluate(
        "() => { document.activeElement && document.activeElement.blur(); "
        "const v = window.fractalViewer; v.selectedName = null; v.renderSelectedPanel(); }"
    )
    page.keyboard.press("m")
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)


def _labels(page: Page) -> list:
    wedges = page.evaluate(WEDGES)
    return [wedges[cell] for cell in "86249317" if cell in wedges]


def _press(page: Page, *labels: str) -> None:
    for label in labels:
        page.wait_for_function(
            f"() => [...document.querySelectorAll('#ring-overlay .wedge')]"
            f".some((w) => w.getAttribute('aria-label') === {label!r})",
            timeout=5000,
        )
        cell = next(c for c, got in page.evaluate(WEDGES).items() if got == label)
        page.keyboard.press(cell)


def _close_ring(page: Page) -> None:
    page.keyboard.press("Escape")
    expect(page.locator("#ring-overlay")).to_be_hidden(timeout=3000)


def _pins(page: Page, url: str) -> dict:
    rows = page.request.get(f"{url}/sites/garage/devices").json()["bindings"]
    return {r["path"]: r for r in rows if r["binding_source"] == "manual"}


def _refused(page: Page, piece: str, printer: str = "printer_1") -> str:
    return page.evaluate(
        "([piece, printer]) => window.fractalViewer.slicePiece(piece, printer)"
        ".then((done) => done.refused || done.said)",
        [piece, printer],
    )


# --------------------------------------------------------------------------------
# A printer's Pin
# --------------------------------------------------------------------------------


@pytest.mark.e2e
def test_a_printers_pin_pins_its_mainboard_where_device_machine_and_slice_find_it(
    page: Page, url: str
):
    """printer_1's own Device section: Query asks the board on /dev/ttyFAKE1 what it is,
    and Pin pins it to printer_1's mainboard, not to printer_1 -- the status line says
    so. printer_1's Device then shows the board via its mainboard, its ring's Device
    opens its Machine, and Slice on a part slices for it. Device › Unpin on printer_1
    takes the board's pin back. Before the pin, and with a pin whose board is not
    connected, Slice says which it is."""
    _open(page, url)
    # Nothing pinned: Slice says so, and where the pin goes.
    assert _refused(page, "footpedal") == (
        f"printer_1 has no board pinned (its board is {BOARD}): select it and Pin its port "
        "in its Device section, then Slice again"
    )
    _row(page, "printer_1").click()
    section = page.locator("#selected-body .device-section")
    pick = section.locator(".dev-pick")
    expect(pick.locator(f"option[value='{PRINTER}']")).to_be_attached(timeout=15000)
    pick.select_option(PRINTER)
    section.locator(".dev-query").click()
    _said(page, f"{PRINTER}: Marlin Apothecary Simulator 1.0 (simulated) · Simulated Ender")
    expect(pick).to_have_value(PRINTER)
    section.locator(".dev-pin").click()
    _said(
        page,
        f"printer_1's board {BOARD} ← {PRINTER}: printer_1's Device, its Machine and Slice "
        "find it there",
    )
    assert list(_pins(page, url)) == [BOARD]
    expect(section).to_contain_text(PRINTER, timeout=10000)
    expect(section.locator(".dev-via")).to_have_text("frame_system.mainboard")

    # Its ring's Device opens its Machine.
    _ring_on(page, "printer_1")
    _press(page, "Device", "Open")
    machine = page.locator(MACHINE)
    expect(machine).to_be_visible(timeout=5000)
    expect(machine.locator(".panel-name")).to_contain_text(f"printer_1 · {PRINTER}")

    # Slice, on a part standing in the garage, slices for it.
    _ring_on(page, "footpedal")
    assert _labels(page)[-1] == "Slice", _labels(page)
    _press(page, "Slice")
    _said(page, "slicing footpedal for printer_1")
    expect(machine.locator("#print-slice-said")).to_contain_text(
        "footpedal sliced for printer_1 by OrcaSlicer 2.4.2", timeout=90000
    )

    # Device › Unpin on printer_1: the pin on its board goes.
    _ring_on(page, "printer_1")
    _press(page, "Device", "Unpin")
    _said(page, f"printer_1's board {BOARD}: device unpinned")
    assert _pins(page, url) == {}

    # A pin whose board is not here: Slice says it is pinned, and not connected.
    pinned = page.request.put(
        f"{url}/sites/garage/nodes/{BOARD}/device", data={"identity": "NOTHERE123"}
    )
    assert pinned.ok, pinned.text()
    try:
        page.evaluate("() => window.fractalViewer.boards.scan()")
        page.wait_for_function(f"() => !!window.fractalViewer.bindings['{BOARD}']", timeout=10000)
        assert _refused(page, "footpedal") == (
            f"printer_1's board {BOARD} is pinned to NOTHERE123, but not connected: connect "
            "it, or ⟳ Rescan in its Device section, then Slice again"
        )
        _row(page, "printer_1").click()
        expect(section).to_contain_text("NOTHERE123 not connected")
    finally:
        page.request.delete(f"{url}/sites/garage/nodes/{BOARD}/device")


@pytest.mark.e2e
def test_a_devkits_ring_has_no_slice(page: Page, url: str):
    """With a printer pinned in the garage, a part standing there has Slice on its ring;
    the ESP32 devkit and the boards beside it -- bought and flashed, never printed --
    have none."""
    pinned = page.request.put(
        f"{url}/sites/garage/nodes/{BOARD}/device", data={"identity": PRINTER}
    )
    assert pinned.ok, pinned.text()
    try:
        _open(page, url)
        _ring_on(page, "footpedal")
        assert "Slice" in _labels(page)
        _close_ring(page)
        for path in ("esp32_blink", "arduino_uno"):
            _ring_on(page, path)
            assert "Slice" not in _labels(page), (path, _labels(page))
            _close_ring(page)
    finally:
        page.request.delete(f"{url}/sites/garage/nodes/{BOARD}/device")


# --------------------------------------------------------------------------------
# The header's Docs
# --------------------------------------------------------------------------------


@pytest.mark.e2e
def test_the_headers_docs_and_panels_docs_open_the_docs_and_the_walkthrough(page: Page, url: str):
    """Docs in the header, beside the ring's button and on one row at 1024 px, opens
    /docs in a new tab, the world left as it was; its bar reaches the walkthrough's
    index, every page of it in order. The canvas ring's Panels › Docs opens the same,
    and the header's Docs wears its address."""
    page.set_viewport_size({"width": 1024, "height": 768})
    _open(page, url)
    docs = page.locator("#docs-link")
    expect(docs).to_be_visible()
    expect(docs).to_have_attribute("data-address", "41", timeout=15000)
    expect(docs).to_have_attribute("title", re.compile(r"Panels › Docs.* · ⌗41$"))
    tops = page.evaluate(
        "() => [...document.querySelectorAll('.toolbar > *')]"
        ".filter((el) => el.getBoundingClientRect().width > 0)"
        ".map((el) => { const r = el.getBoundingClientRect(); return [r.top, r.right]; })"
    )
    middles = {round(top) for top, _right in tops}
    assert max(middles) - min(middles) < 20, tops  # one row
    assert max(right for _top, right in tops) <= 1024, tops

    with page.context.expect_page() as opened:
        docs.click()
    tab = opened.value
    tab.wait_for_load_state()
    assert tab.url.endswith("/docs/README.md"), tab.url
    expect(tab.locator("main h1")).to_have_text("Apothecary documentation")
    assert page.url.endswith("/viewer/sites/garage")  # the world stays where it was
    tab.locator(".bar a", has_text="walkthrough").click()
    expect(tab.locator("main h1")).to_have_text("The walkthrough")
    listed = tab.locator("main ul.pages a")
    expect(listed.first).to_have_attribute("href", re.compile(r"^/walkthrough/0[01]-"))
    names = [a.get_attribute("href") for a in listed.all()]
    assert names == sorted(names) and "/walkthrough/06-editing-a-parts-scad.md" in names
    listed.first.click()
    expect(tab.locator("main h1")).to_be_visible()
    tab.close()

    _canvas_ring(page)
    _press(page, "Panels")
    assert _labels(page)[-1] == "Docs", _labels(page)
    with page.context.expect_page() as opened:
        _press(page, "Docs")
    again = opened.value
    again.wait_for_load_state()
    assert again.url.endswith("/docs/README.md"), again.url
    _said(page, "Opened the documentation in a new tab")
    again.close()


# --------------------------------------------------------------------------------
# The site drop-down and the address
# --------------------------------------------------------------------------------


@pytest.mark.e2e
def test_the_site_drop_down_keeps_the_address_for_a_reload_and_back(page: Page, url: str):
    """The site drop-down puts the site it chooses in the address, leaving the old
    site's focus, Machine and variants behind: a reload stays on that site, and Back
    and Forward go between the two. The ring's Site chooses the same way."""
    _open(page, url, query="?focus=workbench&variant=calibration_cube:0000000000000000")
    expect(page.locator("#breadcrumb")).to_contain_text("workbench")
    page.locator("#site-select").select_option("parts_library")
    page.wait_for_url(f"{url}/viewer/sites/parts_library", timeout=10000)
    _said(page, "Loaded")
    expect(_row(page, "calibration_cube")).to_be_visible(timeout=20000)
    page.reload()
    expect(_row(page, "calibration_cube")).to_be_visible(timeout=20000)
    expect(page.locator("#site-select")).to_have_value("parts_library")

    page.go_back()
    page.wait_for_url(re.compile(r"/viewer/sites/garage\?focus=workbench"), timeout=10000)
    expect(page.locator("#site-select")).to_have_value("garage")
    expect(page.locator("#breadcrumb")).to_contain_text("workbench", timeout=20000)
    expect(_row(page, "calibration_cube")).to_have_count(0)
    page.go_forward()
    page.wait_for_url(f"{url}/viewer/sites/parts_library", timeout=10000)
    expect(page.locator("#site-select")).to_have_value("parts_library")
    expect(_row(page, "calibration_cube")).to_be_visible(timeout=20000)

    # The ring's Site chooses the same way.
    _canvas_ring(page)
    _press(page, "Site", "garage")
    page.wait_for_url(f"{url}/viewer/sites/garage", timeout=10000)
    expect(page.locator("#site-select")).to_have_value("garage")


@pytest.mark.e2e
def test_the_benchs_disabled_compile_says_why(page: Page, url: str):
    """A disabled Compile says why it is disabled and what to do, and is enabled once
    that is done."""
    _open(page, url)
    page.evaluate("() => window.apothecaryPanels.open('bench')")
    bench = page.locator(".panel[data-panel='bench']")
    select = bench.locator(".sketch-select")
    expect(select.locator("option[value='esp32_blink@arduino']")).to_have_count(1, timeout=15000)
    select.select_option("esp32_blink@arduino")
    compile_ = bench.locator(".compile-btn")
    expect(compile_).to_be_enabled()
    bench.locator(".fqbn-input").fill("")
    expect(compile_).to_be_disabled()
    expect(compile_).to_have_attribute(
        "title", re.compile(r"^Disabled: give the board to build for, its FQBN")
    )
    upload = bench.locator(".upload-btn")
    expect(upload).to_have_attribute("title", re.compile(r"^Disabled: give the board"))
    bench.locator(".fqbn-input").fill("esp32:esp32:esp32")
    expect(compile_).to_be_enabled()
    expect(compile_).to_have_attribute("title", re.compile(r"^Build the sketch for the board"))


@pytest.fixture(scope="module")
def bare_url(base_url, start_server):
    """A server with nothing that finds boards: no arduino-cli, no Rust."""
    return start_server({"ARDUINO_CLI": "none", "APOTHECARY_SIMULATED_PRINTER": "idle"})


@pytest.mark.e2e
def test_with_no_arduino_cli_a_printer_says_why_and_the_bench_asks_for_nothing_missing(
    page: Page, bare_url: str
):
    """With no arduino-cli, a printer's Device section says arduino-cli is wanted there
    only to find the board, and the Bench asks for neither the boards arduino-cli knows
    nor the ports: a tool that is not there would answer each with a 503 in the
    console."""
    failed: list = []
    page.on(
        "response",
        lambda r: failed.append(f"{r.status} {r.url}") if r.status >= 500 else None,
    )
    _open(page, bare_url)
    _row(page, "printer_1").click()
    section = page.locator("#selected-body .device-section")
    expect(section).to_contain_text(
        "arduino-cli finds the boards on this machine, and it is not installed", timeout=15000
    )
    expect(section).to_contain_text("A printer needs it only to be found")
    # A structure holds no board, and has no Device section to say it in.
    _row(page, "workbench").click()
    expect(page.locator("#selected-body .device-section")).to_have_count(0)
    page.evaluate("() => window.apothecaryPanels.open('bench')")
    bench = page.locator(".panel[data-panel='bench']")
    expect(bench.locator(".tc-status")).to_contain_text("not installed", timeout=15000)
    expect(bench.locator(".port-select")).to_contain_text("(none detected)")
    settled(page)
    assert failed == [], failed


# --------------------------------------------------------------------------------
# A printer's Pin asks its board once, when nothing is known to print on it
# --------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def printing_url(base_url, start_server):
    """The simulated printer mid-way through an SD print, on /dev/ttyFAKE1."""
    return start_server({"APOTHECARY_SIMULATED_PRINTER": "printing"})


def _m115s(page: Page, url: str) -> int:
    """How many M115s were sent on /dev/ttyFAKE1, by its comms log."""
    log = page.request.get(f"{url}/firmware/printers/log", params={"port": PRINTER}).json()
    return sum(1 for e in log["entries"] if e["kind"] == "tx" and e["text"] == "M115")


def _pin_printer_1(page: Page) -> None:
    _row(page, "printer_1").click()
    section = page.locator("#selected-body .device-section")
    pick = section.locator(".dev-pick")
    expect(pick.locator(f"option[value='{PRINTER}']")).to_be_attached(timeout=15000)
    pick.select_option(PRINTER)
    section.locator(".dev-pin").click()


@pytest.mark.e2e
def test_a_printers_pin_asks_an_idle_board_once_what_it_is(page: Page, url: str):
    """Nothing printing on it: printer_1's Pin pins its mainboard and asks it once
    (M115), so its Machine opens as a printer's straight away; the status line says it
    asked. printer_1's own Unpin, beside it, takes the pin back -- the ring's
    Device › Unpin."""
    _open(page, url)
    before = _m115s(page, url)
    _pin_printer_1(page)
    _said(
        page,
        f"printer_1's board {BOARD} ← {PRINTER}: printer_1's Device, its Machine and Slice "
        "find it there; asked it once what it is (M115): Marlin Apothecary Simulator 1.0 "
        "(simulated) · Simulated Ender",
    )
    assert _m115s(page, url) == before + 1
    section = page.locator("#selected-body .device-section")
    expect(section.locator(".dev-open")).to_be_visible(timeout=10000)
    section.locator(".dev-open").click()
    machine = page.locator(MACHINE)
    expect(machine.locator("#ident")).to_contain_text("Marlin Apothecary Simulator", timeout=8000)
    page.evaluate("() => window.fractalViewer.closeMachine()")
    unpin = section.locator(".dev-unpin")
    expect(unpin).to_have_attribute("data-address", "79", timeout=8000)  # Device › Unpin
    unpin.click()
    _said(page, f"printer_1's board {BOARD}: device unpinned")
    assert _pins(page, url) == {}


@pytest.mark.e2e
def test_a_printers_pin_never_asks_a_board_known_to_be_printing(page: Page, printing_url: str):
    """Its last poll said it prints: printer_1's Pin pins its mainboard and asks it
    nothing, and the status line says so and why; no M115 goes out."""
    url = printing_url
    polled = page.request.get(f"{url}/firmware/printers/status", params={"port": PRINTER})
    assert polled.ok and polled.json()["state"] == "printing", polled.text()
    _open(page, url)
    before = _m115s(page, url)
    _pin_printer_1(page)
    _said(
        page,
        "not asked what it is (M115), since its last poll said it is printing: its "
        "Machine's Identify asks once it is idle",
    )
    assert _m115s(page, url) == before
    assert list(_pins(page, url)) == [BOARD]
    page.locator("#selected-body .device-section .dev-unpin").click()
    _said(page, f"printer_1's board {BOARD}: device unpinned")


# --------------------------------------------------------------------------------
# A piece made from a picture holds no board
# --------------------------------------------------------------------------------


@pytest.mark.e2e
def test_a_piece_made_from_a_picture_has_no_device_section(
    page: Page,
    base_url: str,
    picture_folder,
    fixture_picture,  # noqa: F811 - the fixture's value, the picture's name
    leaves_garage_as_found,  # noqa: F811
):
    """A piece made from a picture holds no board: neither it nor a piece made at a place
    has a Device section, nor the structure it was made on; a printer has one (only
    where a board belongs)."""
    answer = page.request.post(
        f"{base_url}/photos",
        data={
            "picture": str(picture_folder / fixture_picture),
            "name": "onb_words",
            "finder": "stated",
        },
    )
    assert answer.ok, answer.text()
    try:
        _open(page, base_url, site="onb_words")
        page.locator("#contents-list .contents-item").first.click()
        expect(page.locator("#selected-body .prop-row", has_text="Name")).to_be_visible()
        settled(page)
        expect(page.locator("#selected-body .device-section")).to_have_count(0)
    finally:
        page.request.delete(f"{base_url}/photos/onb_words")

    view = _pin(page, base_url, "workbench", fixture_picture, mm_across=1800)
    made = page.request.post(f"{base_url}/sites/garage/views/{view['id']}/make", data={"shape": 1})
    assert made.ok, made.text()
    (piece,) = made.json()["made"]
    _open(page, base_url)
    _row(page, piece).click()
    expect(page.locator("#selected-body .picture-facts[data-facts='made']")).to_be_visible(
        timeout=10000
    )
    expect(page.locator("#selected-body .device-section")).to_have_count(0)
    # Only where a board belongs: not the workbench it was made on,
    # a structure; a printer, yes.
    _row(page, "workbench").click()
    expect(page.locator("#selected-body .prop-row", has_text="workbench")).to_be_visible()
    expect(page.locator("#selected-body .device-section")).to_have_count(0)
    _row(page, "printer_1").click()
    expect(page.locator("#selected-body .device-section")).to_be_visible(timeout=10000)
