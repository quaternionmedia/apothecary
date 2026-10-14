"""The firmware loop, through the page: choose a sketch, build it, flash it, hear its
hello in the board's Machine; change it and go round again.

Loop 3 of the flows plan (docs/plans/ui-flows-2026-10-08.md), held end to end:
round once with the Arduino esp32_blink, then again with the Rust one
(docs/plans/rust-2026-10-08.md), through the Machine's own controls and the
ring's cells, asserting what a person sees at each step -- the Flashing card's
task, the board's one log, the sketch it should run against the sketch it was
heard saying.

This module is a walkthrough page too: `walkthrough/15-firmware.md` is what its
first test writes, its pictures taken as it goes, so the page shows the loop as
it is. The browser suite alone writes it -- the test is marked e2e and not
walkthrough -- so `apothecary test run` stays quick (the loops plan, 2026-10-10).

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
from viewer_ready import settled

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


# What differs on every run whatever the page does, blanked in the pictures: the
# times a task started and a log line arrived, when a board was flashed, the folders
# the scripted tools and the builds live in (a task's output names them), and the
# tools' paths in the toolchain card.
CHANGING = (
    ".task-log",
    ".task-history .meta",
    "#log .t",
    "#c-sketch .when",
    ".tc-status",
    ".tc-module .kv",
)


def _title(where) -> str:
    """A task's title as the card shows it: what ran, and how it ended."""
    return where.locator(".task-title").inner_text().strip()


def _lines(log, *wanted: str) -> str:
    """The lines of a log that hold each of ``wanted``, in order, without their times."""
    rows = [row.strip() for row in log.inner_text().splitlines() if row.strip()]
    found = []
    for want in wanted:
        line = next(row for row in rows if want in row)
        found.append(line[line.index(want) :] if line.find(want) > 0 else line)
    return "\n".join(found)


@pytest.mark.e2e  # the browser suite's alone: not walkthrough, so `test run` stays quick
def test_the_firmware_loop_goes_round_with_arduino_then_rust(page: Page, url: str, walkthrough):
    """Round one, from the Bench: the Arduino esp32_blink, chosen, built for its board
    and uploaded to the devkit's port by the ring's Panels › Bench cells. The
    garage's esp32_blink, bound by its sketch, now wears the board; its Machine says
    what it should run, and the ring's Query hears it say so. Change it -- round two,
    from the Machine's Flashing card: the Rust esp32_blink, listed beside the Arduino
    one, takes no board; built with cargo, flashed with espflash, and heard saying the
    same hello, so the Machine says it matches the sketch it should run, now the Rust
    one. Listen hears the hello on the wire. Walkthrough 15 is what it writes."""
    story = walkthrough(
        ordinal="15",
        slug="firmware",
        title="Firmware",
        written_by="the browser suite (`uv run apothecary test run --e2e`)",
        intro=(
            "A sketch chosen, built, flashed to the ESP32 devkit on the bench, and heard "
            "saying its hello in the board's Machine; then changed and round again. The "
            "first time it is the Arduino esp32_blink, from the Bench; the second, the "
            "Rust one, from the board's own Machine. Both say the same hello, so the "
            "board runs the sketch the garage's esp32_blink expects either way, and the "
            "Machine says which build it is. Every step is the page's own: a cell of a "
            "ring, a button or a drop-down, and every step's words name the next one."
        ),
        runtime=(
            "It drives a real browser against a real server of its own. arduino-cli, "
            "cargo and espflash are scripted stand-ins in one folder, and the devkit is "
            "a simulated one on /dev/ttyFAKE2 that runs whatever was last flashed to it "
            "and says that sketch's hello. It needs no network, opens no serial port, "
            "builds nothing for real, and refuses all three."
        ),
        does_not_show=[
            "**A real board.** The devkit is a simulation that says what esp32_blink "
            "says; flashing the bench's own ESP32 and hearing it is step G of the bench "
            "checklist (docs/validation/2026-09-20-ender-bench.md).",
            "**A real build.** The scripted cargo writes a stand-in image; a real one is "
            "`apothecary firmware install --rust-esp32` and then the same Compile "
            "(docs/firmware.md).",
            "**Rust with no arduino-cli.** The Rust module finds the devkit and listens "
            "to it itself when arduino-cli is not there; this module's last test goes "
            "round that way, and writes no page.",
            "**What changes on every run.** When each task started and each log line "
            "arrived, when the board was flashed, and the folders the stand-in tools "
            "and the builds live in -- which a task's output names -- are blanked in the "
            "pictures and left out of the words, so this page changes when the loop "
            "does, not when the clock does.",
        ],
        page=page,
    )
    dialogs: list[str] = []
    page.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
    _open_viewer(page, url)

    # ---------------------------------------------------------------- round one
    # 1. The Bench, from the canvas ring: Panels › Bench › Bench.
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
    expect(bench.locator(".tc-module[data-id='rust-esp32']")).to_contain_text("installed")
    bench.locator(".bench-build").scroll_into_view_if_needed()
    settled(page)
    story.shows(
        "The Bench lists both builds of esp32_blink, each with its toolchain",
        "Panels › Bench on the canvas ring opens the Bench: the toolchains as installed, "
        "arduino-cli and Rust for the ESP32 beside it, and the sketches under parts/, "
        "each named with its toolchain -- the Arduino esp32_blink and the Rust one next "
        "to each other. The Arduino one chosen, its board filled in from its "
        "firmware.json, and the devkit's port: Compile is next.",
        shown="\n".join(r for r in rows if r.startswith("esp32_blink")),
        blank=CHANGING,
    )

    # 2. Compile, from the ring: Panels › Bench › Compile.
    _canvas_ring(page, "9", "3", "2")
    _ended(bench, f"Compile {ARDUINO} (esp32:esp32:esp32)")
    expect(bench.locator(".task-log")).to_contain_text("fake compile")
    expect(page.locator("#status")).to_contain_text("⌗932")
    story.says(
        "Compile builds it for its board",
        "Panels › Bench › Compile (⌗932) builds what the Bench has chosen, as a task "
        "whose output is in the Bench's log; nothing is sent to a board. Upload is next.",
        shown=_title(bench),
    )

    # 3. Upload, from the ring, after asking.
    _canvas_ring(page, "9", "3", "4")
    _ended(bench, f"Upload {ARDUINO} → {DEVKIT}")
    expect(bench.locator(".task-log")).to_contain_text("fake upload")
    story.says(
        "Upload writes it to the devkit, after asking",
        "Panels › Bench › Upload (⌗934) asks first, naming the sketch with its toolchain "
        "and the port; then it builds again and uploads that fresh build. The garage's "
        "esp32_blink, which runs the sketch of that name, now wears the board.",
        shown=f"{dialogs[0]}\n{_title(bench)}",
    )

    # 4. The node its sketch draws is bound to the board that runs it: its Machine.
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

    # 5. Query, from the ring: a few seconds' listen for the hello.
    _ring_on(page, NODE)
    _choose(page, "Device", "Query")
    expect(log).to_contain_text("heard esp32_blink say hello", timeout=20000)
    expect(sketch).to_contain_text("observed esp32_blink ✓ matches", timeout=8000)
    sketch.scroll_into_view_if_needed()
    settled(page)
    story.shows(
        "The board's Machine hears it say hello",
        "esp32_blink's ring, Device › Open: the board's Machine, with what it should run "
        "-- esp32_blink@arduino, for its board -- and Device › Query, which listens a few "
        "seconds for the hello. Heard, the Machine says the board runs what it should. "
        "Change it next: Device › Flash.",
        shown=_lines(log, "listening 6 s", "heard esp32_blink say hello")
        + "\n"
        + _lines(sketch, "should run", "observed").replace(
            sketch.locator(".when").inner_text(), "…"
        ),
        blank=CHANGING,
    )

    # ---------------------------------------------------------------- round two
    # 6. Change it: Device › Flash, the Machine's Flashing card, the Rust one chosen.
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
    card.scroll_into_view_if_needed()
    settled(page)
    story.shows(
        "Device › Flash, and the Rust esp32_blink chosen",
        "esp32_blink's ring, Device › Flash (⌗22): the Machine's Flashing card, for this "
        "board's port alone, starting from the build it should run. The Rust "
        "esp32_blink chosen beside it: it builds for the chip its Cargo project names, "
        "so the board box goes. Compile is next.",
        shown=card.locator(".sk-note").inner_text().split(" — ")[0],
        blank=CHANGING,
    )

    # 7. Compile: cargo, offline, and the image checked for build paths.
    card.locator(".compile-btn").click()
    _ended(card, f"Compile {RUST} (esp32)")
    expect(card.locator(".task-log")).to_contain_text("Compiling esp32_blink")
    expect(card.locator(".task-log")).to_contain_text("--offline")
    expect(card.locator(".task-log")).to_contain_text("esp32_blink: no build path in the image")
    story.says(
        "Compile builds it with cargo, offline",
        "Compile runs cargo in the sketch's folder, offline, from the crates the install "
        "vendored, and then reads the image it built: no folder it was built in, and so "
        "no user name, may be in it. Compile & upload is next.",
        shown=_title(card)
        + "\n"
        + _lines(card.locator(".task-log"), "esp32_blink: no build path in the image"),
    )

    # 8. Compile & upload: espflash, and the hello heard again.
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
    sketch.scroll_into_view_if_needed()
    settled(page)
    story.shows(
        "Compile & upload flashes it with espflash, and the Machine hears the same hello",
        "Compile & upload asks, builds again and flashes that build with espflash; the "
        "Machine listens for the hello and hears it. It is the hello the Arduino build "
        "said, so the board still runs what esp32_blink expects, and the Machine says it "
        "is the Rust build now. Listen is next.",
        shown=f"{dialogs[1]}\n"
        + _lines(log, f"upload of {RUST}", "heard esp32_blink say hello")
        + "\n"
        + _lines(sketch, "should run", "observed").replace(
            sketch.locator(".when").inner_text(), "…"
        ),
        blank=CHANGING,
    )

    # 9. Listen: the hello on the wire.
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
    story.says(
        "Listen hears the hello on the wire",
        "Listen opens the port, saying it may reset the board, and streams what the board "
        "says into the Machine's one log: the hello, the chip line and a blink count, as "
        "esp32_blink says them in either build. Release lets the port go.",
        shown=_lines(
            log,
            "apothecary esp32_blink: hello",
            "chip: ESP32-D0WD-V3",
            "blink 1",
        ),
    )

    # 10. Opened again, the card starts from what the board should run: the Rust one.
    page.evaluate("() => window.fractalViewer.closeMachine()")
    expect(machine).to_have_count(0)
    _ring_on(page, NODE)
    _choose(page, "Device", "Flash")
    expect(machine.locator("#flash-card .sketch-select")).to_have_value(RUST, timeout=10000)
    expect(machine.locator("#flash-card .sk-board-row")).to_be_hidden()
    story.says(
        "Opened again, the Machine starts from the Rust build",
        "Closed and opened again by Device › Flash, the Flashing card starts from the build "
        "the board should run, esp32_blink@rust-esp32; the next round starts there.",
        shown=machine.locator("#flash-card .sketch-select option:checked").inner_text(),
    )


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
