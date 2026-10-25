"""The ring as a test presses it: opened on a row of Site's tree, on the world, or from
its key, and its cells pressed by their labels or by the digit each cell is
(docs/viewer.md, the ring). Every browser test reaches the ring through these, so a
change to how the ring opens or reads is made once; a test file defines none of its
own (tests/test_e2e_helpers.py holds that).

A label is waited for before it is pressed, so a ring that grows a cell once the
page has read something (a part's Variants after its first save) is pressed when the
cell is there."""

from __future__ import annotations

from playwright.sync_api import Page, expect

# How long a ring, or a cell of it, may take to come.
RING_MS = 15000
# The order a ring seats its options in (apothecary/menu.py).
PLACEMENT = "86249317"
# cell -> label, for every cell that holds something.
CELLS = (
    "() => Object.fromEntries([...document.querySelectorAll('#ring-overlay .wedge')]"
    ".filter((w) => !w.classList.contains('empty'))"
    ".map((w) => [w.dataset.cell, w.getAttribute('aria-label')]))"
)


def cells(page: Page) -> dict:
    """The open ring's cells: cell -> label, for every cell that holds something."""
    return page.evaluate(CELLS)


def by_label(page: Page) -> dict:
    """The open ring's cells the other way round: label -> cell."""
    return {label: cell for cell, label in cells(page).items()}


def labels(page: Page) -> list:
    """The open ring's labels, in the order its options were given."""
    held = cells(page)
    return [held[cell] for cell in PLACEMENT if cell in held]


def press(page: Page, *labels: str) -> str:
    """Each label's cell pressed in turn, in the ring that is open; the address pressed,
    the digits one after another."""
    address = ""
    for label in labels:
        page.wait_for_function(
            "(label) => [...document.querySelectorAll('#ring-overlay .wedge')]"
            ".some((w) => w.getAttribute('aria-label') === label)",
            arg=label,
            timeout=RING_MS,
        )
        cell = by_label(page)[label]
        page.keyboard.press(cell)
        address += cell
    return address


def past_the_chord(page: Page) -> None:
    """Past the chord window: the next arrow walks from the cell lit, rather than
    making a corner with the arrow before it."""
    page.wait_for_function("() => !window.apothecaryRing.chordOpen()", timeout=RING_MS)


def press_cells(page: Page, *digits: str) -> str:
    """The cells named by their digits pressed in turn; the address pressed."""
    for digit in digits:
        page.keyboard.press(digit)
    return "".join(digits)


def open_on_row(page: Page, path: str) -> None:
    """The ring of a piece, opened on its row in Site's tree (Ctrl + right-click)."""
    page.locator(f"#contents-list .contents-item[data-path='{path}']").click(
        button="right", modifiers=["Control"]
    )
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=RING_MS)


def open_on_world(page: Page, at: tuple[int, int] = (40, 40)) -> None:
    """The canvas ring, opened on the world away from any piece, once the page has its
    ring."""
    page.wait_for_function("() => !!window.apothecaryRing", timeout=RING_MS)
    page.locator("#viewer-canvas").click(
        button="right", modifiers=["Control"], position={"x": at[0], "y": at[1]}
    )
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=RING_MS)


def open_from_key(page: Page) -> None:
    """The canvas ring from its key, `m`, with nothing selected and the focus on no box."""
    page.evaluate(
        "() => { document.activeElement && document.activeElement.blur(); "
        "const v = window.fractalViewer; v.selectedName = null; v.renderSelectedPanel(); }"
    )
    page.keyboard.press("m")
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=RING_MS)


def on_row(page: Page, path: str, *labels: str) -> str:
    """The ring of a piece, opened on its row, and the cells the labels name."""
    open_on_row(page, path)
    return press(page, *labels)


def on_world(page: Page, *labels: str, at: tuple[int, int] = (40, 40)) -> str:
    """The canvas ring, opened on the world, and the cells the labels name."""
    open_on_world(page, at)
    return press(page, *labels)


def cells_on_world(page: Page, *digits: str, at: tuple[int, int] = (40, 40)) -> str:
    """The canvas ring, opened on the world, and the cells named by their digits."""
    open_on_world(page, at)
    return press_cells(page, *digits)
