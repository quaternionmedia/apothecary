"""`apothecary serve --simulated`, started as a person starts it, gone round each loop.

The simulated server (apothecary/simulated.py) serves the viewer on a state folder of its own with a
simulated Ender pinned to printer_1's mainboard, a simulated ESP32 devkit and the
scripted firmware tools. These start it as a subprocess -- `python -m apothecary
serve --simulated` -- with the person's own folders (state, tools, render cache) temp
folders that must be left as they were, and go round each loop through the page:
the firmware loop (walkthrough 05), a picture to a print (03), and designing a part
and editing its SCAD (04, 06). A simulated server with no OrcaSlicer says how to install it.

No real serial port is touched, and a test says so. Every Python process of the
simulated server -- the server itself, and the scripted tools it runs -- starts with a guard
(``sitecustomize.py`` on its PYTHONPATH) that refuses, and writes down, any opening
of a serial device and any listing of the machine's real ports. The guard is shown
to work before the simulated server starts, and its record is empty when the module ends.

The slicer named is the unit tests' scripted OrcaSlicer, standing in for a person's
own: the simulated server uses the OrcaSlicer a person has installed, named where it is. Pictures
of the banner and of each loop's end are written under pytest's temp folder
(``simulated-shots``).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest
import windows
from boards import BOARD, DEVKIT, PRINTER
from garage import found as _found
from garage import kept as _kept
from garage import make as _make
from garage import open_garage as _open_garage
from garage import said as _said
from garage import status as _status
from playwright.sync_api import Page, expect
from rings import labels as _labels
from rings import open_on_row as _ring_on
from rings import press as _press
from simulated_process import guarded_env as _guarded_env
from simulated_process import start_simulated as _start_simulated
from simulated_process import stop as _stop
from slicer_helpers import write_fake_orcaslicer
from viewer_ready import settled
from windows import BENCH

from apothecary.projects.parts.skeleton import ROOT
from apothecary.projects.parts.stl_renderer import get_renderer
from apothecary.simulated import CONTROLLER, ROUTER

MACHINE = windows.MACHINE


@pytest.fixture(scope="module")
def simulated(base_url, tmp_path_factory):
    """The simulated server, its folders and its guard; the guard's record is read at the end.
    ``base_url`` is asked for only so that with no server to run against this is
    skipped, as every browser test is."""
    folder = tmp_path_factory.mktemp("simulated")
    env = _guarded_env(folder)
    env["APOTHECARY_ORCASLICER"] = str(write_fake_orcaslicer(folder / "their-orcaslicer"))
    env["FAKE_ORCA_LAYERS"], env["FAKE_ORCA_DWELL"] = "6", "20"
    # The guard works: a process with this environment that opens a serial device is
    # refused, and the opening is written down.
    tried = subprocess.run(
        [sys.executable, "-c", "import os; os.open('/dev/ttyUSB9', os.O_RDWR)"],
        env=env,
        capture_output=True,
        text=True,
    )
    touched = Path(env["APOTHECARY_TEST_SERIAL_GUARD"])
    assert tried.returncode != 0 and "a serial port was opened" in tried.stderr, tried.stderr
    assert touched.read_text() == "os.open /dev/ttyUSB9\n"
    touched.unlink()
    url, proc = _start_simulated(folder, env)
    yield {
        "url": url,
        "folder": folder,
        "root": folder / "person" / "cache" / "simulated",
        "env": env,
    }
    _stop(proc)


@pytest.fixture(scope="module")
def shots(tmp_path_factory):
    folder = tmp_path_factory.getbasetemp() / "simulated-shots"
    folder.mkdir(exist_ok=True)
    return folder


@pytest.fixture
def page(drawing_camera_browser, simulated):
    """A page on the simulated server whose camera sees the drawing, allowed."""
    url = simulated["url"]
    context = drawing_camera_browser.new_context(
        viewport={"width": 1280, "height": 800}, base_url=url
    )
    context.grant_permissions(["camera"], origin=url)
    yield context.new_page()
    context.close()


# --------------------------------------------------------------------------------


@pytest.mark.e2e
def test_the_simulated_server_says_its_machines_are_simulated_and_has_printer_1_pinned(
    page: Page, simulated, shots
):
    """A quiet line above the header says its machines are simulated and how to reach
    the real ones;
    printer_1's mainboard is pinned to the simulated Ender, which said what it is, and
    cnc_router's controller to the simulated router."""
    url = simulated["url"]
    _open_garage(page, url)
    banner = page.locator("#simulated-banner")
    expect(banner).to_be_visible()
    expect(banner).to_contain_text(
        "Simulated machines: a printer, a router, an ESP32 and a lighting console"
    )
    expect(banner).to_contain_text("For the real ones, stop the server and run apothecary serve")
    assert banner.bounding_box()["height"] < 30  # one quiet line
    pins = page.request.get(f"{url}/sites/garage/devices").json()["bindings"]
    manual = {r["path"]: r for r in pins if r["binding_source"] == "manual"}
    assert set(manual) == {BOARD, CONTROLLER}
    board = manual[BOARD]
    assert board["device"]["port"] == PRINTER
    assert board["device"]["printer"]["machine_type"] == "Simulated Ender"
    controller = manual[CONTROLLER]
    assert controller["device"]["port"] == ROUTER
    assert controller["device"]["printer"]["dialect"] == "grbl"
    settled(page)
    page.screenshot(path=str(shots / "simulated-banner.png"))


@pytest.mark.e2e
def test_the_simulated_server_goes_round_the_firmware_loop(page: Page, simulated, shots):
    """The Bench: esp32_blink built and uploaded to the simulated devkit by the scripted
    arduino-cli; its node's Device › Query hears it say hello. Nothing real is built
    or flashed."""
    url = simulated["url"]
    dialogs: list = []
    page.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
    _open_garage(page, url)
    page.evaluate("() => window.apothecaryPanels.open('bench')")
    bench = page.locator(BENCH)
    select = bench.locator(".sketch-select")
    expect(select.locator("option[value='esp32_blink@arduino']")).to_have_count(1, timeout=15000)
    select.select_option("esp32_blink@arduino")
    expect(bench.locator(".fqbn-input")).to_have_value("esp32:esp32:esp32")
    expect(bench.locator(f".port-select option[value='{DEVKIT}']")).to_have_count(1, timeout=10000)
    bench.locator(".port-select").select_option(DEVKIT)
    bench.locator(".upload-btn").click()
    expect(bench.locator(".task-title")).to_contain_text(
        f"Upload esp32_blink@arduino → {DEVKIT}", timeout=30000
    )
    expect(bench.locator(".task-title")).to_contain_text("succeeded", timeout=30000)
    expect(bench.locator(".task-log")).to_contain_text("fake upload")
    assert dialogs == [f'Compile and upload "esp32_blink@arduino" to {DEVKIT}?'], dialogs
    windows.show(page, "pictures")
    expect(page.locator(".world-badge[data-path='esp32_blink']")).to_be_visible(timeout=15000)
    _ring_on(page, "esp32_blink")
    _press(page, "Device", "Query")
    machine = windows.machine(page)
    expect(machine.locator("#log")).to_contain_text("heard esp32_blink say hello", timeout=30000)
    expect(machine.locator("#c-sketch")).to_contain_text("observed esp32_blink ✓ matches")
    settled(page)
    page.screenshot(path=str(shots / "simulated-firmware.png"))
    # The flash is recorded in the simulated server's state, never the person's.
    assert "esp32_blink" in (simulated["root"] / "state" / "firmware-state.json").read_text()


@pytest.mark.e2e
def test_the_simulated_server_goes_round_a_picture_to_a_print(page: Page, simulated, shots):
    """A camera over the bench, a picture taken into the simulated server's own folder, its shapes
    found, one made a piece -- selected -- sliced for printer_1 from its ring by the
    OrcaSlicer named, and printed on the simulated printer to its end."""
    url = simulated["url"]
    _open_garage(page, url)
    _ring_on(page, "workbench")
    _press(page, "Camera", "Add here")
    _said(page, "above workbench, looking straight down")
    page.wait_for_function("() => /^camera_/.test(window.fractalViewer.selectedName || '')")
    camera = page.evaluate("() => window.fractalViewer.selectedName")
    _ring_on(page, camera)
    _press(page, "Device")
    (label,) = _labels(page)
    _press(page, label)
    _said(page, "Take picture (P) keeps a frame where it looks")
    _ring_on(page, camera)
    _press(page, "Take picture")
    _said(page, f"{camera}'s picture lies on workbench")
    (view,) = page.request.get(f"{url}/sites/garage/attached").json()["views"]
    taken = simulated["root"] / "pictures" / view["picture"]
    assert view["picture"].startswith("captures/") and taken.is_file(), view
    _found(page)
    piece = _make(page, url, "disc")  # selected, as Make selects what it made
    _ring_on(page, piece)
    assert _labels(page)[-2:] == ["Print", "Slice"], _labels(page)
    _press(page, "Slice")
    _said(page, f"slicing {piece} for printer_1")
    machine = windows.machine(page)
    expect(machine.locator("#print-slice-said")).to_contain_text(
        f"{piece} sliced for printer_1 by OrcaSlicer 2.4.2", timeout=60000
    )
    kept = _kept(page, url, piece)
    machine.locator("#ctl").check()
    expect(machine.locator("#print-start")).to_be_enabled(timeout=10000)
    page.once("dialog", lambda d: d.accept())
    machine.locator("#print-start").click()
    progress = machine.locator("#print-progress")
    expect(progress).to_contain_text(f"{piece}.gcode · done", timeout=60000)
    lines = kept["lines"]
    _said(page, f"{piece}.gcode on {PRINTER}, making {piece}, ended: done, {lines}/{lines} lines")
    machine.locator("#print-card").scroll_into_view_if_needed()
    settled(page)
    page.screenshot(path=str(shots / "simulated-print.png"))
    # The slice and the print are kept in the simulated server's state, nowhere else.
    assert any((simulated["root"] / "state" / "slices").iterdir())


@pytest.mark.e2e
def test_the_simulated_server_goes_round_designing_a_part_and_editing_its_scad(
    page: Page, simulated, shots
):
    """calibration_cube in the universe: its size moved and applied, drawn as a
    variant; its SCAD edited and rendered; saved as a variant into the simulated server's own
    clone; then Part › Defaults and Apply draw the saved part again."""
    if not get_renderer().is_available:
        pytest.skip("OpenSCAD not installed")
    url = simulated["url"]
    refs = subprocess.run(
        ["git", "for-each-ref", "--format=%(refname) %(objectname)", "refs/apothecary/"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout
    page.goto(f"{url}/viewer/sites/apothecary")
    _said(page, "Loaded")
    page.wait_for_function(
        "() => { const m = window.fractalViewer.meshByName['calibration_cube'];"
        " return m && !m.userData.isPlaceholder; }",
        timeout=90000,
    )
    _ring_on(page, "calibration_cube")
    _press(page, "Part", "Edit")
    slider = page.locator("#part-params .param[data-field='size'] input[type=range]")
    expect(slider).to_be_visible(timeout=15000)
    slider.evaluate("(el) => { el.value = 12; el.dispatchEvent(new Event('input')); }")
    expect(page.locator("#stage-summary")).to_contain_text("valid", timeout=10000)
    page.locator("#apply-btn").click()
    expect(_status(page)).to_contain_text(
        "calibration_cube regenerated: an applied variant, not saved", timeout=90000
    )
    assert re.search(r"[?&]variant=calibration_cube", page.url), page.url

    windows.open_window(page, "part-scad")  # the part's SCAD, in its window
    code = page.locator(".scad-editor .cm-content")
    expect(code).to_be_visible(timeout=20000)
    # Pressed near its first line: the code runs on below what Selected's window shows.
    code.click(position={"x": 24, "y": 8})
    page.keyboard.press("Control+End")
    page.keyboard.insert_text("\ntranslate([0, 0, size]) cube(size / 3);")
    expect(_status(page)).to_contain_text(
        "from its edited SCAD: an applied variant, not saved", timeout=90000
    )
    _ring_on(page, "calibration_cube")
    _press(page, "Part", "Save")
    expect(_status(page)).to_contain_text(
        "calibration_cube saved as the variant variant-1", timeout=30000
    )

    _ring_on(page, "calibration_cube")
    _press(page, "Part", "Defaults")
    _said(page, "the part's own SCAD is back in its editor")
    _ring_on(page, "calibration_cube")
    _press(page, "Part", "Apply")
    expect(_status(page)).to_contain_text("drawn as saved", timeout=90000)
    assert "variant=" not in page.url, page.url
    settled(page)
    page.screenshot(path=str(shots / "simulated-part.png"))
    # Saved into the simulated server's own clone, never the checkout's refs.
    clone = simulated["root"] / "variants.git"
    saved = subprocess.run(
        ["git", "for-each-ref", "--format=%(refname)", "refs/apothecary/variants/"],
        cwd=clone,
        capture_output=True,
        text=True,
    ).stdout.split()
    assert saved == ["refs/apothecary/variants/calibration_cube/variant-1"], saved
    assert (
        subprocess.run(
            ["git", "for-each-ref", "--format=%(refname) %(objectname)", "refs/apothecary/"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        ).stdout
        == refs
    )


@pytest.mark.e2e
def test_the_simulated_server_touched_no_real_port_and_left_the_persons_folders_alone(
    simulated, browser_name
):
    """Last in the module: the guard wrote nothing down -- no serial device was opened
    and no real port listed, by the server or any tool it ran -- and the person's own
    state and tools folders were never made. The simulated server's folder holds its state.

    ``browser_name`` makes it a [chromium] test like the ones before it: pytest runs a
    test with no browser after every test with one, so in a run with another browser
    test module after this one it would run last of all, on a second simulated server of its own,
    and find none of the first one's pictures."""
    touched = Path(simulated["env"]["APOTHECARY_TEST_SERIAL_GUARD"])
    assert not touched.exists(), touched.read_text()
    person = simulated["folder"] / "person"
    assert not (person / "state").exists() and not (person / "tools").exists()
    assert sorted(p.name for p in (person / "cache").iterdir()) == ["simulated"]
    root = simulated["root"]
    assert (root / "state" / "firmware-state.json").is_file()
    assert any((root / "pictures" / "captures").iterdir())


@pytest.fixture(scope="module")
def simulated_without_a_slicer(base_url, tmp_path_factory):
    folder = tmp_path_factory.mktemp("simulated-no-slicer")
    env = _guarded_env(folder)
    env["APOTHECARY_ORCASLICER"] = "none"  # nothing installed, whatever PATH holds
    url, proc = _start_simulated(folder, env)
    yield {"url": url, "env": env}
    _stop(proc)


@pytest.mark.e2e
def test_a_simulated_server_with_no_slicer_says_how_to_install_one(
    browser, simulated_without_a_slicer
):
    """With no OrcaSlicer installed, Slice in the simulated server says so and how to install it."""
    url = simulated_without_a_slicer["url"]
    context = browser.new_context(viewport={"width": 1280, "height": 800}, base_url=url)
    page = context.new_page()
    try:
        _open_garage(page, url)
        _ring_on(page, "footpedal")
        assert "Slice" in _labels(page), _labels(page)  # Flash sketch may follow it
        _press(page, "Slice")
        expect(_status(page)).to_contain_text(
            "OrcaSlicer is not installed: apothecary slicer install", timeout=30000
        )
        expect(_status(page)).to_contain_text("Panels › Bench › Install › OrcaSlicer installs it")
    finally:
        context.close()
    touched = Path(simulated_without_a_slicer["env"]["APOTHECARY_TEST_SERIAL_GUARD"])
    assert not touched.exists(), touched.read_text()
