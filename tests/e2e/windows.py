"""The page's windows (panels.js on GoldenLayout), as a test reaches them.

The world and every panel are windows of one layout. A panel's tab is
``.lm_tab[data-panel=<id>]``, wherever its window is, and its body
``.panel[data-panel=<id>]``; the world's window has no tab. A stack too narrow for
all its tabs keeps the rest in its ▾ list, and a tab there is pressed from it.
"""

from __future__ import annotations

from playwright.sync_api import Page

WORLD = ".viewer-panel"
# The world's stack's header: the world's window has no tab, so this is never shown.
WORLD_HEADER = ".lm_stack:has(.world-window) > .lm_header"
# The Airgap's sections, each a window ``airgap-<section>`` of its own beside the
# Airgap, registered after it and closed until asked for (widgets/airgap.js).
AIRGAP_SECTIONS = (
    "metrics", "field", "gap-map", "inductance", "torque", "harmonics",
    "run-up", "orbit", "vibration", "rig", "sweep",
)  # fmt: skip


def tab(page: Page, pid: str):
    """A window's tab, wherever the window is."""
    return page.locator(f".lm_tab[data-panel='{pid}']")


def panel(page: Page, pid: str):
    """A window's body: the panel's own element."""
    return page.locator(f".panel[data-panel='{pid}']")


def show(page: Page, pid: str) -> None:
    """A window's tab pressed, from its stack's ▾ list when the stack is too narrow
    for it: its panel in front."""
    t = tab(page, pid)
    if not t.is_visible():
        header = page.locator(".lm_header", has=t)
        header.locator(".lm_tabdropdown").click()
    t.locator(".lm_title").click()


def close(page: Page, pid: str) -> None:
    """A window closed by its tab's ✕."""
    show(page, pid)
    tab(page, pid).locator(".lm_close_tab").click()


def state(page: Page, pid: str) -> dict | None:
    """What panels.js says of a window: open, shown, home, loud, its stack."""
    return page.evaluate("(id) => window.apothecaryPanels.state(id)", pid)


def world_width(page: Page) -> float:
    return page.evaluate(f"() => document.querySelector('{WORLD}').offsetWidth")


def world_is(page: Page, width: float) -> None:
    """Waits for the world's window to be this wide (within 2 px)."""
    page.wait_for_function(
        f"(w) => Math.abs(document.querySelector('{WORLD}').offsetWidth - w) <= 2", arg=width
    )


def drag(page: Page, source, to: tuple[float, float]) -> None:
    """A tab or a splitter dragged by the pointer to a point of the page, in steps, as
    a hand does: GoldenLayout starts a drag only after the pointer has moved."""
    box = source.bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 12, y + 12, steps=3)
    page.mouse.move(*to, steps=12)
    page.mouse.up()
