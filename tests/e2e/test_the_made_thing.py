"""One made thing round the four loops: the footpedal on the garage's bench, from a
print of it to its board flashed with its own sketch and heard saying hello, each
loop's end naming the next on the same part.

The server is this module's own: the scripted arduino-cli, which finds an Uno on
/dev/ttyFAKE0, and its monitor (FAKE_DEVKIT), which says the hello of what was last
flashed to a port. A part's sizes, its SCAD and a print of it go round in the part
loop's, the SCAD loop's and the print loop's own tests; this holds the hand-off from
the print to the board, and from the board back to the part, and the same Bench on a
board that says no board (the devkit, on /dev/ttyFAKE2).
"""

from __future__ import annotations

import pytest
from boards import ARDUINO, DEVKIT, NODE
from boards import ended as _ended
from firmware_helpers import write_fake_arduino_cli
from garage import open_garage
from playwright.sync_api import Page, expect
from rings import labels as _labels
from rings import open_on_row as _ring_on
from rings import press as _choose
from windows import BENCH

PIECE = "footpedal"
UNO = "/dev/ttyFAKE0"
SKETCH = "footpedal@arduino"


@pytest.fixture(scope="module")
def url(start_server, tmp_path_factory):
    bench = tmp_path_factory.mktemp("bench")
    return start_server(
        {"ARDUINO_CLI": str(write_fake_arduino_cli(bench / "arduino-cli")), "FAKE_DEVKIT": "1"}
    )


@pytest.mark.e2e
def test_the_footpedals_own_sketch_is_flashed_to_its_board_and_heard(page: Page, url: str):
    """The footpedal never flashed: Selected offers Flash its sketch, and its ring's
    Flash sketch, the same verb, opens the Bench on its sketch and on the Uno its board
    is; the upload names Query, and the hello it hears names Part › Edit, round again."""
    page.on("dialog", lambda dialog: dialog.accept())
    open_garage(page, url, settle=False)
    page.wait_for_function("() => window.fractalViewer.bindingsLoaded")
    page.locator(f"#contents-list .contents-item[data-path='{PIECE}']").click()
    expect(page.locator("#selected-body .dev-flash-sketch")).to_be_visible(timeout=15000)
    # Its ring's Flash sketch is the same verb, where a board running it would have Device.
    _ring_on(page, PIECE)
    assert "Flash sketch" in _labels(page), _labels(page)
    _choose(page, "Flash sketch")

    bench = page.locator(BENCH)
    expect(bench).to_be_visible(timeout=5000)
    expect(bench.locator(".sketch-select")).to_have_value(SKETCH, timeout=10000)
    expect(bench.locator(".fqbn-input")).to_have_value("arduino:avr:uno")
    expect(bench.locator(".port-select")).to_have_value(UNO)
    status = page.locator("#status")
    expect(status).to_contain_text(f"The Bench, {SKETCH} chosen for {UNO}")

    bench.locator(".upload-btn").click()
    _ended(bench, f"Upload {SKETCH}")
    expect(status).to_contain_text(
        f"{SKETCH} flashed to {UNO}: {PIECE}'s ring, Device › Query hears its hello",
        timeout=15000,
    )

    expect(page.locator(f".world-badge[data-path='{PIECE}']")).to_be_visible(timeout=15000)
    _ring_on(page, PIECE)
    _choose(page, "Device", "Query")
    expect(status).to_contain_text(
        f"heard footpedal say hello; round again: {PIECE}'s ring, Part › Edit",
        timeout=20000,
    )


@pytest.mark.e2e
def test_a_port_that_says_no_board_is_not_named_as_the_sketchs(page: Page, url: str):
    """esp32_blink never flashed: its ring's Flash sketch opens the Bench on it, and as the
    devkit's bridge names no board, the line names no port as its board's. Flashed to the
    devkit's port, the upload names esp32_blink's own ring, the node its sketch binds."""
    page.on("dialog", lambda dialog: dialog.accept())
    open_garage(page, url, settle=False)
    page.wait_for_function("() => window.fractalViewer.bindingsLoaded")
    _ring_on(page, NODE)
    _choose(page, "Flash sketch")

    bench = page.locator(BENCH)
    expect(bench.locator(".sketch-select")).to_have_value(ARDUINO, timeout=10000)
    status = page.locator("#status")
    expect(status).to_contain_text(
        f"The Bench, {ARDUINO} chosen: no port is known to be its board's; choose it"
    )

    bench.locator(".port-select").select_option(DEVKIT)
    bench.locator(".upload-btn").click()
    _ended(bench, f"Upload {ARDUINO}")
    expect(status).to_contain_text(
        f"{ARDUINO} flashed to {DEVKIT}: {NODE}'s ring, Device › Query hears its hello",
        timeout=15000,
    )
