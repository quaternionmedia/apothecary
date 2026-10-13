"""`apothecary serve --demo`, started as a person starts it, gone round each loop.

The demo (apothecary/demo.py) serves the viewer on a state folder of its own with a
simulated Ender pinned to printer_1's mainboard, a simulated ESP32 devkit and the
scripted firmware tools. These start it as a subprocess -- `python -m apothecary
serve --demo` -- with the person's own folders (state, tools, render cache) temp
folders that must be left as they were, and go round each loop through the page:
the firmware loop (walkthrough 15), a picture to a print (13), and designing a part
and editing its SCAD (14, 16). A demo with no OrcaSlicer says how to install it.

**No real serial port is touched, and a test says so.** Every Python process of the
demo -- the server, and the scripted tools it runs -- starts with a guard
(``sitecustomize.py`` on its PYTHONPATH) that refuses, and writes down, any opening
of a serial device and any listing of the machine's real ports. The guard is shown
to work before the demo starts, and its record is empty when the module ends.

The slicer named is the unit tests' scripted OrcaSlicer, standing in for a person's
own: the demo uses the OrcaSlicer a person has installed, named where it is. Pictures
of the banner and of each loop's end are written under pytest's temp folder
(``demo-shots``).
"""

from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import Page, expect
from slicer_helpers import write_fake_orcaslicer
from test_picture_to_print import (  # noqa: F401 - a fixture, and the loop's steps
    _drawing_camera_browser,
    _found,
    _kept,
    _make,
)
from test_the_loop import _labels, _open_garage, _press, _ring_on, _said, _status
from viewer_ready import settled

from apothecary.projects.parts.skeleton import ROOT
from apothecary.projects.parts.stl_renderer import get_renderer

PRINTER = "/dev/ttyFAKE1"
DEVKIT = "/dev/ttyFAKE2"
BOARD = "printer_1.frame_system.mainboard"
MACHINE = ".panel[data-panel='machine']"
BENCH = ".panel[data-panel='bench']"

# Every Python process the demo starts imports this first. Opening a serial device, by
# any route Python has, or listing the machine's ports is refused and written down.
GUARD = textwrap.dedent(
    r"""
    import builtins, io, os, re

    _LOG = os.environ.get("APOTHECARY_TEST_SERIAL_GUARD")
    _SERIAL = re.compile(r"^/dev/(tty(S|USB|ACM|AMA|FAKE)|cu\.|serial/)")


    def _note(what):
        with _open_file(_LOG, "a") as f:
            f.write(what + "\n")


    if _LOG:
        _open_file, _os_open = builtins.open, os.open

        def _path(path):
            try:
                return os.fsdecode(path)
            except TypeError:
                return ""

        def _guarded_os_open(path, *args, **kwargs):
            if _SERIAL.match(_path(path)):
                _note(f"os.open {_path(path)}")
                raise PermissionError(f"a serial port was opened: {_path(path)}")
            return _os_open(path, *args, **kwargs)

        def _guarded_open(file, *args, **kwargs):
            if not isinstance(file, int) and _SERIAL.match(_path(file)):
                _note(f"open {_path(file)}")
                raise PermissionError(f"a serial port was opened: {_path(file)}")
            return _open_file(file, *args, **kwargs)

        os.open = _guarded_os_open
        builtins.open = io.open = _guarded_open
        try:
            import serial.tools.list_ports as _ports

            def _comports(*args, **kwargs):
                _note("comports")
                raise PermissionError("the machine's serial ports were listed")

            _ports.comports = _comports
        except ImportError:
            pass
    """
)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _guarded_env(folder: Path) -> dict:
    """The environment a person's shell would have, with their folders temp ones and
    the guard on every Python process."""
    guard = folder / "guard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text(GUARD, encoding="utf-8")
    env = os.environ.copy()
    for key in [k for k in env if k.startswith(("APOTHECARY_", "FAKE_"))]:
        del env[key]  # nothing of the suite's own servers
    for key in ("ARDUINO_CLI", "ESPTOOL", "CARGO", "ESPFLASH"):
        env.pop(key, None)
    env.update(
        {
            "PYTHONPATH": os.pathsep.join(filter(None, [str(guard), env.get("PYTHONPATH")])),
            "APOTHECARY_TEST_SERIAL_GUARD": str(folder / "serial-touched.log"),
            # The person's own folders: the demo must leave them as they were.
            "APOTHECARY_STATE_DIR": str(folder / "person" / "state"),
            "APOTHECARY_TOOLS_DIR": str(folder / "person" / "tools"),
            "APOTHECARY_CACHE_DIR": str(folder / "person" / "cache"),
        }
    )
    renderer = get_renderer()
    if renderer.is_available:  # the OpenSCAD the person's own serve would use
        env["APOTHECARY_OPENSCAD"] = str(renderer.openscad_path)
    return env


def _start_demo(folder: Path, env: dict) -> tuple[str, subprocess.Popen]:
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    log = (folder / "demo.log").open("w")
    proc = subprocess.Popen(
        [sys.executable, "-m", "apothecary", "serve", "--demo", "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            pytest.fail(f"the demo exited at start:\n{(folder / 'demo.log').read_text()}")
        try:
            if httpx.get(f"{url}/health", timeout=1.0).status_code == 200:
                return url, proc
        except httpx.TransportError:
            pass
        time.sleep(0.25)
    proc.terminate()
    pytest.fail(f"the demo did not answer within 60 s:\n{(folder / 'demo.log').read_text()}")


def _stop(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="module")
def demo(base_url, tmp_path_factory):
    """The demo, its folders and its guard; the guard's record is read at the end.
    ``base_url`` is asked for only so that with no server to run against this is
    skipped, as every browser test is."""
    folder = tmp_path_factory.mktemp("demo")
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
    url, proc = _start_demo(folder, env)
    yield {"url": url, "folder": folder, "root": folder / "person" / "cache" / "demo", "env": env}
    _stop(proc)


@pytest.fixture(scope="module")
def shots(tmp_path_factory):
    folder = tmp_path_factory.getbasetemp() / "demo-shots"
    folder.mkdir(exist_ok=True)
    return folder


@pytest.fixture
def page(_drawing_camera_browser, demo):  # noqa: F811 - the fixture imported above
    """A page on the demo whose camera sees the drawing, allowed."""
    url = demo["url"]
    context = _drawing_camera_browser.new_context(
        viewport={"width": 1280, "height": 800}, base_url=url
    )
    context.grant_permissions(["camera"], origin=url)
    yield context.new_page()
    context.close()


# --------------------------------------------------------------------------------


@pytest.mark.e2e
def test_the_demo_says_it_is_the_demo_and_has_printer_1_pinned(page: Page, demo, shots):
    """A quiet line above the header says it is the demo and how to leave it;
    printer_1's mainboard is pinned to the simulated Ender, which said what it is."""
    url = demo["url"]
    _open_garage(page, url)
    banner = page.locator("#demo-banner")
    expect(banner).to_be_visible()
    expect(banner).to_contain_text("The demo: a simulated printer and ESP32")
    expect(banner).to_contain_text("run apothecary serve without --demo")
    assert banner.bounding_box()["height"] < 30  # one quiet line
    pins = page.request.get(f"{url}/sites/garage/devices").json()["bindings"]
    (board,) = [r for r in pins if r["binding_source"] == "manual"]
    assert board["path"] == BOARD and board["device"]["port"] == PRINTER
    assert board["device"]["printer"]["machine_type"] == "Simulated Ender"
    settled(page)
    page.screenshot(path=str(shots / "demo-banner.png"))


@pytest.mark.e2e
def test_the_demo_goes_round_the_firmware_loop(page: Page, demo, shots):
    """The Bench: esp32_blink built and uploaded to the simulated devkit by the scripted
    arduino-cli; its node's Device › Query hears it say hello. Nothing real is built
    or flashed."""
    url = demo["url"]
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
    page.locator(".panel-rail .rail-tab[data-panel='bench'] .rail-tab-name").click()
    expect(page.locator(".world-badge[data-path='esp32_blink']")).to_be_visible(timeout=15000)
    _ring_on(page, "esp32_blink")
    _press(page, "Device", "Query")
    machine = page.locator(MACHINE)
    expect(machine.locator("#log")).to_contain_text("heard esp32_blink say hello", timeout=30000)
    expect(machine.locator("#c-sketch")).to_contain_text("observed esp32_blink ✓ matches")
    settled(page)
    page.screenshot(path=str(shots / "demo-firmware.png"))
    # The flash is recorded in the demo's state, never the person's.
    assert "esp32_blink" in (demo["root"] / "state" / "firmware-state.json").read_text()


@pytest.mark.e2e
def test_the_demo_goes_round_a_picture_to_a_print(page: Page, demo, shots):
    """A camera over the bench, a picture taken into the demo's own folder, its shapes
    found, one made a piece -- selected -- sliced for printer_1 from its ring by the
    OrcaSlicer named, and printed on the simulated printer to its end."""
    url = demo["url"]
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
    taken = demo["root"] / "pictures" / view["picture"]
    assert view["picture"].startswith("captures/") and taken.is_file(), view
    _found(page)
    piece = _make(page, url, "disc")  # selected, as Make selects what it made
    _ring_on(page, piece)
    assert _labels(page)[-2:] == ["Print", "Slice"], _labels(page)
    _press(page, "Slice")
    _said(page, f"slicing {piece} for printer_1")
    machine = page.locator(MACHINE)
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
    page.screenshot(path=str(shots / "demo-print.png"))
    # The slice and the print are kept in the demo's state, nowhere else.
    assert any((demo["root"] / "state" / "slices").iterdir())


@pytest.mark.e2e
def test_the_demo_goes_round_designing_a_part_and_editing_its_scad(page: Page, demo, shots):
    """calibration_cube in the parts library: its size moved and applied, drawn as a
    variant; its SCAD edited and rendered; saved as a variant into the demo's own
    clone; then Part › Defaults and Apply draw the saved part again."""
    if not get_renderer().is_available:
        pytest.skip("OpenSCAD not installed")
    url = demo["url"]
    refs = subprocess.run(
        ["git", "for-each-ref", "--format=%(refname) %(objectname)", "refs/apothecary/"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout
    page.goto(f"{url}/viewer/sites/parts_library")
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

    code = page.locator(".scad-editor .cm-content")
    expect(code).to_be_visible(timeout=20000)
    code.click()
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
    page.screenshot(path=str(shots / "demo-part.png"))
    # Saved into the demo's own clone, never the checkout's refs.
    clone = demo["root"] / "variants.git"
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
def test_the_demo_touched_no_real_port_and_left_the_persons_folders_alone(demo, browser_name):
    """Last in the module: the guard wrote nothing down -- no serial device was opened
    and no real port listed, by the server or any tool it ran -- and the person's own
    state and tools folders were never made. The demo's folder holds its state.

    ``browser_name`` makes it a [chromium] test like the ones before it: pytest runs a
    test with no browser after every test with one, so in a run with another browser
    test module after this one it ran last of all, on a second demo of its own, and
    found none of the first one's pictures."""
    touched = Path(demo["env"]["APOTHECARY_TEST_SERIAL_GUARD"])
    assert not touched.exists(), touched.read_text()
    person = demo["folder"] / "person"
    assert not (person / "state").exists() and not (person / "tools").exists()
    assert sorted(p.name for p in (person / "cache").iterdir()) == ["demo"]
    root = demo["root"]
    assert (root / "state" / "firmware-state.json").is_file()
    assert any((root / "pictures" / "captures").iterdir())


@pytest.fixture(scope="module")
def demo_without_a_slicer(base_url, tmp_path_factory):
    folder = tmp_path_factory.mktemp("demo-no-slicer")
    env = _guarded_env(folder)
    env["APOTHECARY_ORCASLICER"] = "none"  # nothing installed, whatever PATH holds
    url, proc = _start_demo(folder, env)
    yield {"url": url, "env": env}
    _stop(proc)


@pytest.mark.e2e
def test_a_demo_with_no_slicer_says_how_to_install_one(browser, demo_without_a_slicer):
    """With no OrcaSlicer installed, Slice in the demo says so and how to install it."""
    url = demo_without_a_slicer["url"]
    context = browser.new_context(viewport={"width": 1280, "height": 800}, base_url=url)
    page = context.new_page()
    try:
        _open_garage(page, url)
        _ring_on(page, "footpedal")
        assert _labels(page)[-1] == "Slice", _labels(page)
        _press(page, "Slice")
        expect(_status(page)).to_contain_text(
            "OrcaSlicer is not installed: apothecary slicer install", timeout=30000
        )
        expect(_status(page)).to_contain_text("Panels › Bench › Install › OrcaSlicer installs it")
    finally:
        context.close()
    touched = Path(demo_without_a_slicer["env"]["APOTHECARY_TEST_SERIAL_GUARD"])
    assert not touched.exists(), touched.read_text()
