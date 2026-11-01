"""The boards a browser test's server simulates, and the scripted tools it runs with:
the printer on ``/dev/ttyFAKE1`` pinned to printer_1's mainboard, the ESP32 devkit
on ``/dev/ttyFAKE2``, the sketch esp32_blink and its two builds, the scripted
slicer's layers, and a task's end as its card says it. A test file names none of
these itself (tests/test_e2e_helpers.py holds that)."""

from __future__ import annotations

from playwright.sync_api import expect

# The simulated Ender, and the node its board is pinned to.
PRINTER = "/dev/ttyFAKE1"
BOARD = "printer_1.frame_system.mainboard"
# The simulated ESP32 devkit, and the node whose sketch it runs.
DEVKIT = "/dev/ttyFAKE2"
NODE = "esp32_blink"
# esp32_blink's sketches, one per toolchain.
ARDUINO = "esp32_blink@arduino"
RUST = "esp32_blink@rust-esp32"
# The scripted slicer's layers, each move followed by a dwell of this many ms: a few
# seconds of printing on the simulated printer, seen running before it ends.
LAYERS, DWELL = "15", "60"


# A node's board badge standing in the world: drawn on its own, or merged into a count with
# the badges close to it, as the overview shows it once a picture mark stands beside it.
WORN = """(node) => { const el = document.querySelector(`.world-badge[data-path='${node}']`);
    return Boolean(el) && !el.hidden && (el.classList.contains("merged") || el.checkVisibility()); }"""


def worn(page, node: str = NODE) -> bool:
    """Whether the node wears its board's badge, on its own or in a count."""
    return page.evaluate(WORN, node)


def wears(page, node: str = NODE, timeout: int = 15000) -> None:
    """Wait until the node wears its board's badge, on its own or in a count."""
    page.wait_for_function(WORN, arg=node, timeout=timeout)


def ended(where, title: str, timeout: int = 15000) -> None:
    """The task log says the task of this title succeeded."""
    expect(where.locator(".task-title")).to_contain_text(title, timeout=timeout)
    expect(where.locator(".task-title")).to_contain_text("succeeded", timeout=timeout)
