"""Firmware, a step at a time, as walkthrough page 05 goes: the Arduino esp32_blink chosen in
the Bench, compiled, uploaded to the devkit after asking, and heard saying hello in its
Machine; then from the Machine's Flashing card the Rust one, compiled with cargo, flashed
with espflash and heard again; Listen; and the card opened again on the Rust build.

Each step first checks that the page is where the step before it leaves it, then acts as
a person does and holds what the page says. In the suite every step runs in order on a
server of the test's own: arduino-cli, cargo and espflash scripted in one folder, and the
simulated devkit on ``/dev/ttyFAKE2`` that runs what was last flashed to it
(tests/firmware_helpers.py), as the demo's are. Given ``--step N`` and ``--base-url``
naming the demo, only step N runs, on the demo's walk tab, and the tab is left there
(tests/e2e/stepping.py); its picture is ``.cache/walk/firmware-step-N.png``::

    uv run pytest tests/e2e/test_steps_firmware.py --base-url http://127.0.0.1:8000 --step 1
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Tuple

import pytest
import windows
from boards import ARDUINO, DEVKIT, NODE, RUST
from boards import ended as _ended
from firmware_helpers import write_fake_arduino_cli, write_fake_cargo, write_fake_espflash
from playwright.sync_api import Page, expect
from rings import cells_on_world as _canvas_ring
from rings import open_on_row as _ring_on
from rings import press as _choose
from stepping import chosen, where
from viewer_ready import settled
from windows import BENCH, MACHINE

ARDUINO_ROW = "esp32_blink@arduino · esp32:esp32:esp32"
RUST_ROW = "esp32_blink@rust-esp32 · esp32"


@dataclass
class Walk:
    """The page a step acts on, the server it is on, and whether it is the demo's tab."""

    page: Page
    base: str
    on_the_demo: bool

    @property
    def bench(self):
        return self.page.locator(BENCH)

    @property
    def machine(self):
        """Every window of the open Machine, to look in."""
        return windows.machine(self.page)

    def machine_open(self) -> bool:
        return self.page.locator(MACHINE).is_visible()

    @property
    def card(self):
        return self.machine.locator("#flash-card")

    def asked(self) -> List[str]:
        """The next dialog's words, the dialog accepted, as a person who meant it does."""
        said: List[str] = []
        self.page.once("dialog", lambda d: (said.append(d.message), d.accept()))
        return said


def bench(w: Walk) -> None:
    """Panels › Bench › Bench on the canvas ring: the Bench lists both builds of esp32_blink,
    each with its toolchain, side by side; the Arduino one chosen, its board filled in, and
    the devkit's port."""
    w.page.goto(f"{w.base}/viewer/sites/garage")
    expect(w.page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
    settled(w.page)
    # The cell toggles the Bench: pressed only when it is not open already, as the page
    # keeps a person's panels over a reload.
    if not w.bench.is_visible():
        _canvas_ring(w.page, "4", "3", "8")
    expect(w.bench).to_be_visible(timeout=5000)
    select = w.bench.locator(".sketch-select")
    expect(select.locator(f"option[value='{RUST}']")).to_have_count(1, timeout=10000)
    rows = select.locator("option").all_text_contents()
    assert rows.index(ARDUINO_ROW) + 1 == rows.index(RUST_ROW), rows
    select.select_option(ARDUINO)
    expect(w.bench.locator(".fqbn-input")).to_have_value("esp32:esp32:esp32")
    w.bench.locator(".port-select").select_option(DEVKIT)
    expect(w.bench.locator(".tc-module[data-id='rust-esp32']")).to_contain_text("installed")
    # Its sketch scrolled to the top of its body, as far as the body scrolls: the page
    # under the layout stays where it is.
    w.bench.locator(".bench-build").evaluate(
        """(el) => { const body = el.closest('.panel-body-slot');
            body.scrollTop += el.getBoundingClientRect().top
                - body.getBoundingClientRect().top; }"""
    )


def _bench_ready(w: Walk) -> bool:
    return (
        w.bench.is_visible()
        and w.bench.locator(".sketch-select").input_value() == ARDUINO
        and w.bench.locator(".port-select").input_value() == DEVKIT
    )


def compile_(w: Walk) -> None:
    """Panels › Bench › Compile: built for its board, as a task in the Bench's log."""
    where(
        "Compile", "the Bench open, the Arduino esp32_blink and the devkit chosen", _bench_ready(w)
    )
    _canvas_ring(w.page, "4", "3", "2")
    _ended(w.bench, f"Compile {ARDUINO} (esp32:esp32:esp32)")
    expect(w.bench.locator(".task-log")).to_contain_text("fake compile")
    w.bench.locator(".task-title").scroll_into_view_if_needed()


def upload(w: Walk) -> None:
    """Panels › Bench › Upload, after asking: built again and written to the devkit; the
    garage's esp32_blink, which runs that sketch, wears the board."""
    where(
        "Upload", "the Bench open, the Arduino esp32_blink and the devkit chosen", _bench_ready(w)
    )
    asked = w.asked()
    _canvas_ring(w.page, "4", "3", "4")
    _ended(w.bench, f"Upload {ARDUINO} → {DEVKIT}")
    assert asked == [f'Compile and upload "{ARDUINO}" to {DEVKIT}?'], asked
    expect(w.page.locator(f".world-badge[data-path='{NODE}']")).to_be_visible(timeout=15000)
    w.bench.locator(".task-title").scroll_into_view_if_needed()


def hello(w: Walk) -> None:
    """esp32_blink's ring, Device › Open, and the world's ring's Panels › Windows ›
    Machine view: its Machine's Sketch says what it should run; Device › Query hears it
    say hello."""
    where(
        "Hello",
        "esp32_blink wearing the devkit it was uploaded to",
        w.page.locator(f".world-badge[data-path='{NODE}']").is_visible(),
    )
    if w.bench.is_visible():
        windows.show(w.page, "pictures")  # Pictures in front: the Bench behind it
        expect(w.bench).to_be_hidden(timeout=5000)
    _ring_on(w.page, NODE)
    _choose(w.page, "Device", "Open")
    windows.machine_ready(w.page, "devkit", by_hand=True)
    sketch = w.machine.locator("#c-sketch")
    expect(sketch).to_contain_text(f"should run {ARDUINO} · esp32:esp32:esp32", timeout=8000)
    expect(w.machine.locator("#c-board")).to_contain_text(DEVKIT)
    _ring_on(w.page, NODE)
    _choose(w.page, "Device", "Query")
    expect(w.machine.locator("#log")).to_contain_text("heard esp32_blink say hello", timeout=20000)
    expect(sketch).to_contain_text("observed esp32_blink ✓ matches", timeout=8000)
    sketch.scroll_into_view_if_needed()
    settled(w.page)


def flash(w: Walk) -> None:
    """esp32_blink's ring, Device › Flash: the Machine's Flashing card for this board's port
    alone, starting from the build it should run; the Rust one chosen, and the board box
    gone."""
    where(
        "Flash",
        "esp32_blink's Machine open, running the Arduino build",
        w.machine_open() and f"should run {ARDUINO}" in w.machine.locator("#c-sketch").inner_text(),
    )
    _ring_on(w.page, NODE)
    _choose(w.page, "Device", "Flash")
    expect(w.card).to_be_visible(timeout=8000)
    expect(w.card.locator(".port-select")).to_be_hidden()
    expect(w.card.locator(".sketch-select")).to_have_value(ARDUINO, timeout=10000)
    rows = w.card.locator(".sketch-select option").all_text_contents()
    assert rows.index(ARDUINO_ROW) + 1 == rows.index(RUST_ROW), rows
    w.card.locator(".sketch-select").select_option(RUST)
    expect(w.card.locator(".sk-board-row")).to_be_hidden()
    expect(w.card.locator(".sk-note")).to_contain_text("built by Rust for the ESP32 for esp32")
    w.card.scroll_into_view_if_needed()
    settled(w.page)


def _rust_chosen(w: Walk) -> bool:
    return w.card.is_visible() and w.card.locator(".sketch-select").input_value() == RUST


def cargo(w: Walk) -> None:
    """Compile, on the card: cargo, offline, and the image read for build paths."""
    where(
        "Compile with cargo",
        "the Flashing card open with the Rust esp32_blink chosen",
        _rust_chosen(w),
    )
    w.card.locator(".compile-btn").click()
    _ended(w.card, f"Compile {RUST} (esp32)")
    log = w.card.locator(".task-log")
    expect(log).to_contain_text("--offline")
    expect(log).to_contain_text("esp32_blink: no build path in the image")


def espflash(w: Walk) -> None:
    """Compile & upload, after asking: flashed with espflash, the same hello heard, and the
    Machine saying it is the Rust build now."""
    where(
        "Compile & upload",
        "the Flashing card open with the Rust esp32_blink chosen",
        _rust_chosen(w),
    )
    w.machine.locator("#clear").click()  # this round's hello, not the last one's
    asked = w.asked()
    w.card.locator(".upload-btn").click()
    _ended(w.card, f"Upload {RUST} → {DEVKIT}")
    assert asked == [f'Compile and upload "{RUST}" to {DEVKIT}?'], asked
    log, sketch = w.machine.locator("#log"), w.machine.locator("#c-sketch")
    expect(w.card.locator(".task-log")).to_contain_text("Flashing has completed!")
    expect(log).to_contain_text("heard esp32_blink say hello", timeout=20000)
    expect(sketch).to_contain_text(f"should run {RUST} · esp32", timeout=8000)
    expect(sketch).to_contain_text("observed esp32_blink ✓ matches")
    sketch.scroll_into_view_if_needed()
    settled(w.page)


def listen(w: Walk) -> None:
    """Listen: the port opened and the hello, the chip line and a blink on the wire; Release
    lets it go."""
    where(
        "Listen",
        "esp32_blink's Machine open, running the Rust build",
        w.machine_open() and f"should run {RUST}" in w.machine.locator("#c-sketch").inner_text(),
    )
    log = w.machine.locator("#log")
    w.machine.locator("#listen").click()
    expect(log).to_contain_text("apothecary esp32_blink: hello", timeout=10000)
    expect(log).to_contain_text("chip: ESP32-D0WD-V3")
    expect(log).to_contain_text("blink 1")
    expect(w.page.locator("#selected-body .device-section")).to_contain_text(f"runs {RUST} ✓")
    w.machine.locator("#release").click()
    log.scroll_into_view_if_needed()
    w.page.wait_for_function(
        f"() => !window.fractalViewer.boards.board('{DEVKIT}').stream", timeout=5000
    )


def again(w: Walk) -> None:
    """The Machine closed and opened again by Device › Flash: the card starts from the build
    the board should run, the Rust one."""
    where(
        "Opened again",
        "esp32_blink's Machine open, running the Rust build",
        w.machine_open() and f"should run {RUST}" in w.machine.locator("#c-sketch").inner_text(),
    )
    w.page.evaluate("() => window.fractalViewer.closeMachine()")
    expect(w.machine).to_have_count(0)
    _ring_on(w.page, NODE)
    _choose(w.page, "Device", "Flash")
    expect(w.machine.locator("#flash-card .sketch-select")).to_have_value(RUST, timeout=10000)
    expect(w.machine.locator("#flash-card .sk-board-row")).to_be_hidden()


STEPS: List[Tuple[str, Callable[[Walk], None]]] = [
    ("The Bench lists both builds", bench),
    ("Compile", compile_),
    ("Upload", upload),
    ("The Machine hears it say hello", hello),
    ("Device › Flash, the Rust one chosen", flash),
    ("Compile with cargo", cargo),
    ("Compile & upload with espflash", espflash),
    ("Listen", listen),
    ("Opened again on the Rust build", again),
]


@pytest.fixture
def steps(request, base_url):
    """One step on the demo's walk tab under --step; every step on a server of the
    test's own otherwise (stepping.chosen)."""

    def own():
        return request.getfixturevalue("page"), request.getfixturevalue("own_server")

    yield from chosen(request, base_url, "firmware", STEPS, own)


@pytest.fixture
def own_server(start_server, tmp_path_factory):
    """The test's own server: arduino-cli, cargo and espflash scripted in one folder, and
    one simulated devkit between them."""
    tools = tmp_path_factory.mktemp("bench")
    return start_server(
        {
            "ARDUINO_CLI": str(write_fake_arduino_cli(tools / "arduino-cli")),
            "CARGO": str(write_fake_cargo(tools / "cargo")),
            "ESPFLASH": str(write_fake_espflash(tools / "espflash")),
            "FAKE_DEVKIT": "1",
        }
    )


@pytest.mark.e2e
def test_firmware_a_step_at_a_time(steps):
    page, url, on_the_demo, numbers = steps
    walk = Walk(page, url, on_the_demo)
    for n in numbers:
        STEPS[n - 1][1](walk)
