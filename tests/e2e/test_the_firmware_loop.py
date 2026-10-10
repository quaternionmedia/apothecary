"""The firmware loop, through the page: choose a sketch, build it, flash it, hear its
hello in the board's Machine; change it and go round again.

Loop 3 of the flows plan (docs/plans/ui-flows-2026-10-08.md), held end to end:
round once with the Arduino esp32_blink, then again with the Rust one
(docs/plans/rust-2026-10-08.md), through the Machine's own controls and the
ring's cells, asserting what a person sees at each step -- the Flashing card's
task, the board's one log, the sketch it should run against the sketch it was
heard saying.

Runs against servers of their own: the scripted arduino-cli, cargo and espflash
in one folder (tests/firmware_helpers.py), and the simulated devkit they share
(FAKE_DEVKIT): an ESP32 on /dev/ttyFAKE2 that runs what was last flashed to it
and says that sketch's hello, as esp32_blink does. And a server with Rust alone,
no arduino-cli anywhere, where the Rust module finds the devkit and listens to it
itself, through the simulated serial engine (APOTHECARY_SIMULATED_DEVKIT).
Nothing here opens a real port, builds for real or reaches the network;
flashing the bench's own ESP32 is a step of the bench checklist
(docs/validation/2026-09-20-ender-bench.md).
"""

from __future__ import annotations

import pytest
from firmware_helpers import write_fake_arduino_cli, write_fake_cargo, write_fake_espflash
from playwright.sync_api import Page, expect

DEVKIT = "/dev/ttyFAKE2"
NODE = "esp32_blink"
ARDUINO = "esp32_blink@arduino"
RUST = "esp32_blink@rust-esp32"
MACHINE = ".panel[data-panel='machine']"
BENCH = ".panel[data-panel='bench']"


@pytest.fixture(scope="module")
def url(start_server, tmp_path_factory):
    """A bench of fakes: arduino-cli, cargo and espflash in one folder, one simulated
    devkit between them."""
    bench = tmp_path_factory.mktemp("bench")
    return start_server(
        {
            "ARDUINO_CLI": str(write_fake_arduino_cli(bench / "arduino-cli")),
            "CARGO": str(write_fake_cargo(bench / "cargo")),
            "ESPFLASH": str(write_fake_espflash(bench / "espflash")),
            "FAKE_DEVKIT": "1",
        }
    )


@pytest.fixture(scope="module")
def rust_only_url(start_server, tmp_path_factory):
    """Rust for the ESP32 and no arduino-cli anywhere: the Rust module finds the
    simulated devkit on /dev/ttyFAKE2 and listens to it itself."""
    bench = tmp_path_factory.mktemp("rust-bench")
    return start_server(
        {
            "ARDUINO_CLI": "none",
            "CARGO": str(write_fake_cargo(bench / "cargo")),
            "ESPFLASH": str(write_fake_espflash(bench / "espflash")),
            "APOTHECARY_SIMULATED_DEVKIT": DEVKIT,
        }
    )


def _open_viewer(page: Page, url: str) -> None:
    page.goto(f"{url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)


def _select(page: Page, path: str) -> None:
    page.locator(f"#contents-list .contents-item[data-path='{path}']").click()
    expect(page.locator("#selected-body .prop-row", has_text="Name")).to_be_visible(timeout=5000)


def _wedges(page: Page) -> dict:
    return page.evaluate(
        """() => Object.fromEntries([...document.querySelectorAll('#ring-overlay .wedge')]
            .filter((w) => !w.classList.contains('empty'))
            .map((w) => [w.getAttribute('aria-label'), w.dataset.cell]))"""
    )


def _choose(page: Page, *labels: str) -> None:
    for label in labels:
        cells = _wedges(page)
        assert label in cells, f"no {label!r} in this ring: {sorted(cells)}"
        page.keyboard.press(cells[label])


def _ring_on(page: Page, path: str) -> None:
    page.locator(f"#contents-list .contents-item[data-path='{path}']").click(button="right")
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)


def _ended(where, title: str, timeout: int = 15000) -> None:
    """The task log says the task of this title succeeded."""
    expect(where.locator(".task-title")).to_contain_text(title, timeout=timeout)
    expect(where.locator(".task-title")).to_contain_text("succeeded", timeout=timeout)


def _canvas_ring(page: Page, *digits: str) -> None:
    """The ring on the world, nothing chosen, and the cells named by their digits."""
    page.wait_for_function("() => !!window.apothecaryRing", timeout=15000)
    page.locator("#viewer-canvas").click(button="right", position={"x": 30, "y": 30})
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=15000)
    for digit in digits:
        page.keyboard.press(digit)


@pytest.mark.e2e
def test_the_firmware_loop_goes_round_with_arduino_then_rust(page: Page, url: str):
    """Round one, from the Bench: the Arduino esp32_blink, chosen, built for its board
    and uploaded to the devkit's port by the ring's Panels › Bench cells. The
    garage's esp32_blink, bound by its sketch, now wears the board; its Machine says
    what it should run, and the ring's Query hears it say so. Change it -- round two,
    from the Machine's Flashing card: the Rust esp32_blink, listed beside the Arduino
    one, takes no board; built with cargo, flashed with espflash, and heard saying the
    same hello, so the Machine says it matches the sketch it should run, now the Rust
    one. Listen hears the hello on the wire."""
    dialogs: list[str] = []
    page.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
    _open_viewer(page, url)

    # Round one, from the Bench: Panels › Bench › Bench opens it.
    _canvas_ring(page, "9", "3", "8")
    bench = page.locator(BENCH)
    expect(bench).to_be_visible(timeout=5000)
    select = bench.locator(".sketch-select")
    expect(select.locator(f"option[value='{RUST}']")).to_have_count(1, timeout=10000)
    rows = select.locator("option").all_text_contents()
    # Each sketch named with its toolchain, the board it is built for after it.
    arduino_row = "esp32_blink@arduino · esp32:esp32:esp32"
    rust_row = "esp32_blink@rust-esp32 · esp32"
    assert rows.index(arduino_row) + 1 == rows.index(rust_row), rows
    select.select_option(ARDUINO)
    expect(bench.locator(".fqbn-input")).to_have_value("esp32:esp32:esp32")
    bench.locator(".port-select").select_option(DEVKIT)
    _canvas_ring(page, "9", "3", "2")  # Panels › Bench › Compile
    _ended(bench, f"Compile {ARDUINO} (esp32:esp32:esp32)")
    expect(bench.locator(".task-log")).to_contain_text("fake compile")
    _canvas_ring(page, "9", "3", "4")  # Panels › Bench › Upload, after asking
    _ended(bench, f"Upload {ARDUINO} → {DEVKIT}")
    expect(bench.locator(".task-log")).to_contain_text("fake upload")

    # The node its sketch draws is bound to the board that runs it: its badge, its Machine.
    badge = page.locator(f".world-badge[data-path='{NODE}']")
    expect(badge).to_be_visible(timeout=15000)
    page.locator(".panel-rail .rail-tab[data-panel='bench'] .rail-tab-name").click()  # fold it
    expect(bench).to_be_hidden(timeout=5000)
    _ring_on(page, NODE)
    _choose(page, "Device", "Open")
    machine = page.locator(MACHINE)
    sketch = machine.locator("#c-sketch")
    log = machine.locator("#log")
    # Which build it should run, its toolchain said.
    expect(sketch).to_contain_text(f"should run {ARDUINO} · esp32:esp32:esp32", timeout=8000)
    expect(machine.locator("#c-board")).to_contain_text(DEVKIT)
    _ring_on(page, NODE)
    _choose(page, "Device", "Query")  # Identify: a few seconds' listen for the hello
    expect(log).to_contain_text("heard esp32_blink say hello", timeout=20000)
    expect(sketch).to_contain_text("observed esp32_blink ✓ matches", timeout=8000)

    # Change it. Round two, from the Machine's Flashing card (Device › Flash).
    _ring_on(page, NODE)
    _choose(page, "Device", "Flash")
    card = machine.locator("#flash-card")
    expect(card).to_be_visible(timeout=8000)
    expect(card.locator(".port-select")).to_be_hidden()  # this board's port, no other
    expect(card.locator(".sketch-select")).to_have_value(ARDUINO, timeout=10000)
    expect(card.locator(".sketch-select option").nth(0)).to_be_attached()
    card_rows = card.locator(".sketch-select option").all_text_contents()
    assert card_rows.index(arduino_row) + 1 == card_rows.index(rust_row), card_rows
    card.locator(".sketch-select").select_option(RUST)
    expect(card.locator(".sk-board-row")).to_be_hidden()
    expect(card.locator(".sk-note")).to_contain_text("built by Rust for the ESP32 for esp32")
    card.locator(".compile-btn").click()
    _ended(card, f"Compile {RUST} (esp32)")
    expect(card.locator(".task-log")).to_contain_text("Compiling esp32_blink")
    expect(card.locator(".task-log")).to_contain_text("--offline")
    machine.locator("#clear").click()  # this round's hello, not the last one's
    card.locator(".upload-btn").click()
    _ended(card, f"Upload {RUST} → {DEVKIT}")
    expect(card.locator(".task-log")).to_contain_text("Flashing has completed!")
    expect(log).to_contain_text(f"upload of {RUST} (esp32): succeeded")
    expect(log).to_contain_text("listening 6 s for the sketch's hello", timeout=8000)
    expect(log).to_contain_text("heard esp32_blink say hello", timeout=20000)
    # The same hello as the Arduino one's, and the Machine says it is the Rust build.
    expect(sketch).to_contain_text(f"should run {RUST} · esp32", timeout=8000)
    expect(sketch).to_contain_text("observed esp32_blink ✓ matches")
    assert dialogs == [
        f'Compile and upload "{ARDUINO}" to {DEVKIT}?',
        f'Compile and upload "{RUST}" to {DEVKIT}?',
    ], dialogs

    # Its hello in the board's Machine as it says it on the wire: Listen streams it.
    machine.locator("#listen").click()
    expect(log).to_contain_text("apothecary esp32_blink: hello", timeout=10000)
    expect(log).to_contain_text("chip: ESP32-D0WD-V3 rev 301, 2 core(s), 240 MHz, LED on GPIO 2")
    expect(log).to_contain_text("blink 1")
    expect(badge).to_contain_text("⚡")
    expect(page.locator("#selected-body .device-section")).to_contain_text(f"runs {RUST} ✓")
    machine.locator("#release").click()
    page.wait_for_function(
        f"() => !window.fractalViewer.boards.board('{DEVKIT}').stream", timeout=5000
    )
    # Opened again, the card starts from what the board should run: the Rust one.
    page.evaluate("() => window.fractalViewer.closeMachine()")
    expect(machine).to_have_count(0)
    _ring_on(page, NODE)
    _choose(page, "Device", "Flash")
    expect(machine.locator("#flash-card .sketch-select")).to_have_value(RUST, timeout=10000)
    expect(machine.locator("#flash-card .sk-board-row")).to_be_hidden()


@pytest.mark.e2e
def test_the_bench_lists_the_rust_sketch_and_its_toolchain_beside_arduino(page: Page, url: str):
    """The Bench's toolchain card draws Rust for the ESP32 beside arduino-cli, its tools
    as found and its own Install; the sketches list the Rust esp32_blink beside the
    Arduino one, and the ring's Compile builds whichever the Bench has chosen."""
    _open_viewer(page, url)
    page.evaluate("() => window.apothecaryPanels.open('bench')")
    bench = page.locator(BENCH)
    rust = bench.locator(".tc-module[data-id='rust-esp32']")
    expect(rust).to_contain_text("Rust for the ESP32", timeout=10000)
    expect(rust).to_contain_text("rust for esp32")
    expect(rust).to_contain_text("can build, flash, find ports, listen, probe with espflash")
    expect(rust).to_contain_text("cargo 1.99.0-nightly")
    expect(rust).to_contain_text("espflash 4.6.0")
    install = rust.locator(".module-install")
    expect(install).to_have_text("Update Rust for the ESP32")
    expect(install).to_have_attribute("data-address", "9366")  # Panels › Bench › Install › Rust
    expect(install).to_be_enabled()
    assert "vendor every Rust sketch's crates" in (install.get_attribute("title") or "")
    expect(bench.locator(".tc-status")).to_contain_text("✓ 9.9.9")  # arduino-cli, as it was

    select = bench.locator(".sketch-select")
    expect(select.locator(f"option[value='{RUST}']")).to_have_count(1, timeout=10000)
    select.select_option(ARDUINO)
    expect(bench.locator(".fqbn-input")).to_have_value("esp32:esp32:esp32")
    select.select_option(RUST)
    expect(bench.locator(".sk-board-row")).to_be_hidden()
    expect(bench.locator(".compile-btn")).to_be_enabled()
    page.locator("#viewer-canvas").click(button="right", position={"x": 30, "y": 30})
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    for digit in ("9", "3", "2"):  # Panels › Bench › Compile
        page.keyboard.press(digit)
    _ended(bench, f"Compile {RUST} (esp32)")
    expect(bench.locator(".task-log")).to_contain_text("--offline")
    expect(page.locator("#status")).to_contain_text("⌗932")


@pytest.mark.e2e
def test_with_rust_alone_the_loop_goes_round_with_no_arduino_cli(page: Page, rust_only_url: str):
    """No arduino-cli anywhere. The Rust module finds the devkit itself -- the Bench's
    port list and the board's Machine say so -- and listens to it itself: round one
    from the Bench, the Rust esp32_blink built and flashed, the node bound to the board
    by its sketch, its hello heard by the ring's Query; round two from the Machine's
    card, flashed again and heard again; Listen streams it and Probe asks espflash
    what the chip is."""
    url = rust_only_url
    dialogs: list[str] = []
    page.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
    _open_viewer(page, url)
    _canvas_ring(page, "9", "3", "8")
    bench = page.locator(BENCH)
    expect(bench.locator(".tc-status")).to_contain_text("not installed", timeout=10000)
    expect(bench.locator(".tc-module[data-id='rust-esp32']")).to_contain_text("installed: can")
    select = bench.locator(".sketch-select")
    expect(select.locator(f"option[value='{RUST}']")).to_have_count(1, timeout=10000)
    select.select_option(RUST)
    ports = bench.locator(".port-select option").all_text_contents()
    assert any(DEVKIT in p for p in ports), ports
    bench.locator(".port-select").select_option(DEVKIT)
    expect(bench.locator(".compile-btn")).to_be_enabled(timeout=5000)
    bench.locator(".compile-btn").click()
    _ended(bench, f"Compile {RUST} (esp32)")
    bench.locator(".upload-btn").click()
    _ended(bench, f"Upload {RUST} → {DEVKIT}")
    expect(bench.locator(".task-log")).to_contain_text("Flashing has completed!")

    badge = page.locator(f".world-badge[data-path='{NODE}']")
    expect(badge).to_be_visible(timeout=15000)
    page.locator(".panel-rail .rail-tab[data-panel='bench'] .rail-tab-name").click()
    expect(bench).to_be_hidden(timeout=5000)
    _ring_on(page, NODE)
    _choose(page, "Device", "Open")
    machine = page.locator(MACHINE)
    sketch, log = machine.locator("#c-sketch"), machine.locator("#log")
    expect(machine.locator("#c-board")).to_contain_text("found by rust-esp32", timeout=8000)
    expect(sketch).to_contain_text(f"should run {RUST} · esp32", timeout=8000)
    _ring_on(page, NODE)
    _choose(page, "Device", "Query")
    expect(log).to_contain_text("heard esp32_blink say hello", timeout=20000)
    expect(sketch).to_contain_text("observed esp32_blink ✓ matches", timeout=8000)

    # Round two, from the Machine's card: the same sketch, flashed again, heard again.
    _ring_on(page, NODE)
    _choose(page, "Device", "Flash")
    card = machine.locator("#flash-card")
    expect(card.locator(".sketch-select")).to_have_value(RUST, timeout=10000)
    machine.locator("#clear").click()
    card.locator(".upload-btn").click()
    _ended(card, f"Upload {RUST} → {DEVKIT}")
    expect(log).to_contain_text("heard esp32_blink say hello", timeout=20000)
    assert dialogs == [f'Compile and upload "{RUST}" to {DEVKIT}?'] * 2, dialogs

    # Listen: the Rust module's own monitor, the hello on the wire.
    machine.locator("#listen").click()
    expect(log).to_contain_text("apothecary esp32_blink: hello", timeout=10000)
    expect(log).to_contain_text("blink 1")
    machine.locator("#release").click()
    page.wait_for_function(
        f"() => !window.fractalViewer.boards.board('{DEVKIT}').stream", timeout=5000
    )
    # Probe: espflash asks the chip (the scripted one answers).
    machine.locator("#probe").click()
    expect(machine.locator("#c-board")).to_contain_text("24:6f:28:00:00:02", timeout=15000)
