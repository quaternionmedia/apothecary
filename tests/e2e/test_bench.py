"""The Bench: the firmware page's toolchain, sketches, build and upload, raw flash
and task log, as a panel in front of the world.

The consolidation plan's Phase 5 (docs/plans/consolidation-2026-10-03.md): the
firmware page's sections are the Bench, a tab of the rail's strip, closed until
asked for; its verbs are cells of the canvas ring's Panels › Bench.

Runs against a server of its own from the conftest's ``start_server``: the
scripted ``arduino-cli`` (version 9.9.9, an Uno on ``/dev/ttyFAKE0``,
``/dev/ttyFAKE1`` unmatched), with the same script already installed in its
tools dir, so Install and Update say it is there and download nothing. Nothing
here opens a real port or reaches the network.
"""

from __future__ import annotations

import re

import pytest
from firmware_helpers import write_fake_arduino_cli
from playwright.sync_api import Page, expect

BENCH = ".panel[data-panel='bench']"


@pytest.fixture(scope="module")
def url(start_server, tmp_path_factory):
    """A server whose tools dir already holds the scripted arduino-cli."""
    tools = tmp_path_factory.mktemp("tools")
    (tools / "arduino-cli").mkdir()
    write_fake_arduino_cli(tools / "arduino-cli" / "arduino-cli")
    return start_server({"APOTHECARY_TOOLS_DIR": str(tools)})


def _open_viewer(page: Page, url: str) -> None:
    page.goto(f"{url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)


def _wedges(page: Page) -> dict:
    """label -> cell of every wedge of the open ring that holds something."""
    return page.evaluate(
        """() => Object.fromEntries([...document.querySelectorAll('#ring-overlay .wedge')]
            .filter((w) => !w.classList.contains('empty'))
            .map((w) => [w.getAttribute('aria-label'), w.dataset.cell]))"""
    )


def _ended(bench, title: str, timeout: int = 10000):
    """The task log says the task of this title succeeded."""
    expect(bench.locator(".task-title")).to_contain_text(title, timeout=timeout)
    expect(bench.locator(".task-title")).to_contain_text("succeeded", timeout=timeout)


@pytest.mark.e2e
def test_the_bench_is_a_tab_of_the_strip_closed_until_asked_for(page: Page, url: str):
    """Registered at start as a tab of the rail's strip, shown only when pressed; its
    body is filled the first time it is shown, so the page asks nothing of the
    toolchain until then."""
    asked = []
    page.on("request", lambda r: asked.append(r.url) if "/firmware/status" in r.url else None)
    _open_viewer(page, url)
    tab = page.locator(".panel-rail .rail-tab[data-panel='bench']")
    expect(tab).to_be_visible()
    expect(page.locator(BENCH)).to_be_hidden()
    assert page.evaluate("() => window.apothecaryPanels.state('bench').shown") is False
    assert asked == [], asked
    tab.locator(".rail-tab-name").click()
    expect(page.locator(BENCH)).to_be_visible(timeout=2000)
    expect(page.locator(BENCH).locator(".tc-status")).to_contain_text("9.9.9", timeout=10000)


@pytest.mark.e2e
def test_the_bench_lists_the_sketches_and_installs_with_the_scripted_cli(page: Page, url: str):
    """The toolchain as installed (the scripted arduino-cli, 9.9.9), the suggested
    cores, the sketches under parts/ each with its board; Update says the one installed
    is kept, a core and a library install through the scripted cli, and a compile runs
    -- each a task whose output is in the log and whose row is in Recent tasks."""
    _open_viewer(page, url)
    page.evaluate("() => window.apothecaryPanels.open('bench')")
    bench = page.locator(BENCH)
    status = bench.locator(".tc-status")
    expect(status).to_contain_text("arduino-cli", timeout=10000)
    expect(status).to_contain_text("✓ 9.9.9")
    expect(bench.locator(".install-btn")).to_have_text("Update arduino-cli")
    assert bench.locator(".tc-cores li").count() >= 5
    expect(bench.locator(".tc-cores li[data-id='arduino:avr']")).to_contain_text("✓ 1.8.8")

    # The sketches under parts/, each with the board its firmware.json names.
    sketch = bench.locator(".sketch-select")
    expect(sketch.locator("option[value='footpedal']")).to_have_count(1, timeout=10000)
    expect(sketch.locator("option[value='esp32_blink']")).to_have_count(1)
    sketch.select_option("footpedal")
    expect(bench.locator(".fqbn-input")).to_have_value("arduino:avr:uno")
    expect(bench.locator(".sk-note")).to_contain_text("FastLED")
    sketch.select_option("esp32_blink")
    expect(bench.locator(".fqbn-input")).to_have_value("esp32:esp32:esp32")
    # The detected ports to upload to.
    ports = bench.locator(".port-select option").all_text_contents()
    assert any("/dev/ttyFAKE0" in p for p in ports), ports

    # Update: the scripted cli is already installed, so it is kept and nothing is fetched.
    bench.locator(".install-btn").click()
    _ended(bench, "Install arduino-cli")
    expect(bench.locator(".task-log")).to_contain_text("already installed")
    expect(bench.locator(".task-history li", has_text="Install arduino-cli")).to_have_count(1)

    # A core, through the scripted cli: its index first, then the core.
    bench.locator(".core-install[data-id='esp32:esp32']").click()
    _ended(bench, "Install core esp32:esp32")
    expect(bench.locator(".task-log")).to_contain_text("fake core install esp32:esp32")

    # A library, typed.
    bench.locator(".lib-input").fill("FastLED")
    bench.locator(".lib-btn").click()
    _ended(bench, "Install libraries FastLED")
    expect(bench.locator(".task-log")).to_contain_text("fake lib install FastLED")

    # A compile: nothing is sent to a board.
    sketch.select_option("footpedal")
    bench.locator(".compile-btn").click()
    _ended(bench, "Compile footpedal (arduino:avr:uno)")
    expect(bench.locator(".task-log")).to_contain_text("fake compile")
    assert bench.locator(".task-history li[data-id]").count() >= 4
    expect(bench.locator(".cancel-btn")).to_be_hidden()  # nothing running


@pytest.mark.e2e
def test_the_bench_s_verbs_are_cells_of_panels_bench(page: Page, url: str):
    """Panels › Bench holds the panel and its verbs, and the Bench's buttons wear their
    addresses; Compile from the ring compiles what the Bench has chosen."""
    _open_viewer(page, url)
    page.locator("#viewer-canvas").click(button="right", position={"x": 30, "y": 30})
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    page.keyboard.press(_wedges(page)["Panels"])
    panels = _wedges(page)
    assert panels["Rail"] == "9" and panels["Bench"] == "3", panels  # Rail keeps its cell
    page.keyboard.press("3")
    bench_cells = _wedges(page)
    assert bench_cells == {
        "Bench": "8",
        "Install": "6",
        "Compile": "2",
        "Upload": "4",
        "Raw flash": "9",
        "Cancel": "3",
        "Cores": "1",
        "Libraries": "7",
    }, bench_cells
    page.keyboard.press("8")  # the panel itself
    expect(page.locator("#ring-overlay")).to_have_count(0)
    bench = page.locator(BENCH)
    expect(bench).to_be_visible(timeout=2000)
    expect(bench.locator(".sketch-select option[value='footpedal']")).to_have_count(
        1, timeout=10000
    )
    expect(bench.locator(".compile-btn")).to_have_attribute("data-address", "932", timeout=5000)
    expect(bench.locator(".install-btn")).to_have_attribute("data-address", "936")
    expect(bench.locator(".core-install[data-id='esp8266:esp8266']")).to_have_attribute(
        "data-address", re.compile(r"^931\d$")
    )
    bench.locator(".sketch-select").select_option("footpedal")
    page.locator("#viewer-canvas").click(button="right", position={"x": 30, "y": 30})
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    for digit in ("9", "3", "2"):
        page.keyboard.press(digit)
    expect(page.locator("#ring-overlay")).to_have_count(0)
    _ended(bench, "Compile footpedal (arduino:avr:uno)")
    expect(page.locator("#status")).to_contain_text("⌗932")


@pytest.mark.e2e
def test_the_firmware_address_opens_the_viewer_with_the_bench(page: Page, url: str):
    """/firmware, the firmware page's address, is the viewer on the default site with
    the Bench open -- on a fresh load, as a link handed out lands -- and the toolbar
    leads to no page of its own: Panels › Bench and a board's Machine are the way."""
    page.goto(f"{url}/firmware")
    expect(page).to_have_url(re.compile(r"/viewer/sites/garage\?panel=bench$"))
    bench = page.locator(BENCH)
    expect(bench).to_be_visible(timeout=15000)
    expect(page.locator(".panel-rail .rail-tab[data-panel='bench']")).to_have_class(
        re.compile(r"\bactive\b")
    )
    expect(bench.locator(".tc-status")).to_contain_text("✓ 9.9.9", timeout=10000)
    expect(bench.locator(".sketch-select option[value='footpedal']")).to_have_count(1)
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
    for gone in ("#firmware-link", "#monitor-link", ".toolbar a.toolbar-link"):
        expect(page.locator(gone)).to_have_count(0)
