"""The ring as a test presses it: opened on a row of Site's tree or on the world, its
cells pressed by their labels, by the digit each cell is (docs/viewer.md, the ring).

A label is waited for before it is pressed, so a ring that grows a cell once the
page has read something (a part's Variants after its first save) is pressed when the
cell is there."""

from __future__ import annotations

from playwright.sync_api import Page, expect

# How long a ring, or a cell of it, may take to come.
RING_MS = 15000

# label -> cell, for every cell that holds something.
WEDGES = (
    "() => Object.fromEntries([...document.querySelectorAll('#ring-overlay .wedge')]"
    ".filter((w) => !w.classList.contains('empty'))"
    ".map((w) => [w.getAttribute('aria-label'), w.dataset.cell]))"
)


def press(page: Page, *labels: str) -> None:
    """Each label's cell pressed in turn, in the ring that is open."""
    for label in labels:
        page.wait_for_function(
            "(label) => [...document.querySelectorAll('#ring-overlay .wedge')]"
            ".some((w) => w.getAttribute('aria-label') === label)",
            arg=label,
            timeout=RING_MS,
        )
        page.keyboard.press(page.evaluate(WEDGES)[label])


def on_row(page: Page, path: str, *labels: str) -> None:
    """The ring of a piece, opened on its row in Site's tree (Ctrl + right-click)."""
    page.locator(f"#contents-list .contents-item[data-path='{path}']").click(
        button="right", modifiers=["Control"]
    )
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=RING_MS)
    press(page, *labels)


def on_world(page: Page, *labels: str, at: tuple[int, int] = (40, 40)) -> None:
    """The canvas ring, opened on the world away from any piece."""
    page.locator("#viewer-canvas").click(
        button="right", modifiers=["Control"], position={"x": at[0], "y": at[1]}
    )
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=RING_MS)
    press(page, *labels)
