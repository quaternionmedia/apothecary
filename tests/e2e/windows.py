"""The page's windows (panels.js on GoldenLayout), as a test reaches them.

The world and every panel are windows of one layout. A panel's tab is
``.lm_tab[data-panel=<id>]``, wherever its window is, and its body
``.panel[data-panel=<id>]``; the world's window has no tab. A stack too narrow for
all its tabs keeps the rest in its ▾ list, and a tab there is pressed from it.
"""

from __future__ import annotations

import rings
from playwright.sync_api import Page, expect

from apothecary.systems import AIRGAP, PART, by_id

WORLD = ".viewer-panel"
# The world's stack's header: the world's window has no tab, so this is never shown.
WORLD_HEADER = ".lm_stack:has(.world-window) > .lm_header"
# The Airgap's sections, each a window ``airgap-<section>`` of its own beside the
# Airgap, registered after it and closed until asked for: its entry in the registry
# of focused systems (apothecary/systems.py).
AIRGAP_SECTIONS = tuple(section.id for section in AIRGAP.sections)
# The Part's sections, each a window ``part-<section>``, registered at start and
# closed until asked for: Part › Edit opens Parameters, Part › View › SCAD the SCAD.
PART_SECTIONS = tuple(section.id for section in PART.sections)


def open_window(page: Page, pid: str) -> None:
    """A window opened as ⊞ Windows opens it: at its place, in front."""
    page.evaluate("(id) => window.apothecaryPanels.open(id)", pid)


def remembered(page: Page) -> None:
    """The layout as it stands remembered by the browser: panels.js writes it a moment
    after a change, and says whether what it holds is the layout as it stands."""
    page.wait_for_function("() => window.apothecaryPanels.remembered()", timeout=5000)


def from_the_windows_menu(page: Page, pid: str) -> None:
    """A window chosen in the header's ⊞ Windows, as a person chooses it."""
    page.locator("#windows-menu > summary").click()
    page.locator(f".windows-menu-body .window-item[data-window='{pid}']").click()
    expect(page.locator(".windows-menu-body")).to_be_hidden()


# A board's Machine: its main window, and every window of it -- the Machine and each
# of its sections (``machine-<section>``), which live while it is open.
MACHINE = ".panel[data-panel='machine']"
# The Machine in front's own root, in its window's body: the body scrolls, and the root,
# which moves to a window of its own when the Machine is kept, is inside it.
MACHINE_ROOT = f"{MACHINE} > .panel-body-slot > .machine"
MACHINE_BODY = f"{MACHINE} > .panel-body-slot"
MACHINE_WINDOWS = ".panel[data-panel^='machine']"
# The Bench: every toolchain's sketches, built and flashed from one window.
BENCH = ".panel[data-panel='bench']"
DECK = ".panel[data-panel='deck']"


def machine(page: Page):
    """Every window of the open board's Machine, to look in: an element of it is found
    in whichever window holds it. (The Machine itself, open or not, is ``MACHINE``.)"""
    return page.locator(MACHINE_WINDOWS)


def in_machine(page: Page, selector: str):
    """An element of a board's Machine, in whichever of its windows holds it."""
    return page.locator(f"{MACHINE_WINDOWS} {selector}")


def machine_view(page: Page) -> None:
    """Panels › Windows › Machine view: the open board's Machine and every section of
    it laid out together, as a person working on a board lays them out."""
    page.evaluate("() => window.apothecaryPanels.applyView('machine')")


def machine_ready(
    page: Page,
    kind: str | None = None,
    *,
    by_hand: bool = False,
    timeout: int = 20000,
) -> None:
    """The open board's Machine once its kind is known (``kind``, when the test knows
    which), laid out in the Machine view: every section of that kind open beside it,
    Selected and Site with them -- the default for a test that works on a board. A board
    taken for a printer until it says otherwise is waited for until it has said so.
    (Waited for from here, not by the page's timers, so a test holding the page's clock
    may call it.)

    ``by_hand`` lays it out as a person does, the world's ring's Panels › Windows ›
    Machine view: for a walk, whose pictures show what a person pressed."""
    known = f".kind-{kind}" if kind else ":is(.kind-printer, .kind-router, .kind-devkit)"
    expect(page.locator(f"{MACHINE_ROOT}{known}")).to_be_attached(timeout=timeout)
    if by_hand:
        rings.on_world(page, "Panels", "Windows", by_id("machine").cell)
        page.wait_for_function("() => window.apothecaryPanels.isOpen('machine-log')")
        # The view lands on the machine's file, or says there is none: what it says
        # and where the world looks are settled once that is done.
        page.evaluate("() => window.fractalViewer.viewDone")
    else:
        machine_view(page)


def part_view(page: Page) -> None:
    """Panels › Windows › Part view: Selected, the Part's sections and the world laid
    out together, as a person working on a part lays them out."""
    page.evaluate("() => window.apothecaryPanels.applyView('part')")


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


def light_controls(page: Page, pid: str) -> list[str]:
    """The controls shown in a window that wear a light ground -- the browser's own button,
    drop-down or box -- where the page's are dark (tokens.css, a window's controls): each
    as its tag, its id or first words, and its colour. Ticks, ranges, file pickers and
    colour wells are the browser's by design, and a control drawn with no ground of its own
    stands on the window's.

    A ground is weighed as the browser paints it: filled on a 1x1 canvas and its pixel
    read back in sRGB, so a computed colour in any syntax -- ``rgb()``, ``color(srgb ...)``,
    ``oklch()``, ``oklab()``, ``lab()``, whatever ``color-mix()`` gives -- is weighed by
    its light, not by the numbers written in it. A ground the canvas cannot read is
    listed, as "unreadable", rather than let through."""
    return page.evaluate(
        """(id) => {
            const root = document.querySelector(`.panel[data-panel='${id}']`);
            if (!root) return [`no window ${id}`];
            const own = 'input:not([type="checkbox"], [type="radio"], [type="range"], [type="file"], [type="color"], [type="hidden"])';
            const canvas = document.createElement('canvas');
            canvas.width = canvas.height = 1;
            const ctx = canvas.getContext('2d', { willReadFrequently: true });
            // A colour the canvas cannot read leaves its fill as it was: set over two
            // different fills, it is read only when it leaves the same fill on both.
            const painted = (colour) => {
                ctx.fillStyle = '#010203';
                ctx.fillStyle = colour;
                const over = ctx.fillStyle;
                ctx.fillStyle = '#040506';
                ctx.fillStyle = colour;
                if (ctx.fillStyle !== over) return null;
                ctx.clearRect(0, 0, 1, 1);
                ctx.fillRect(0, 0, 1, 1);
                return [...ctx.getImageData(0, 0, 1, 1).data];
            };
            const light = [];
            for (const el of root.querySelectorAll(`button, select, textarea, ${own}`)) {
                const box = el.getBoundingClientRect();
                if (!box.width || !box.height || !el.checkVisibility()) continue;
                const ground = getComputedStyle(el).backgroundColor;
                const said = el.id ? `#${el.id}` : (el.textContent || el.value || el.name || '').trim().slice(0, 24);
                const pixel = painted(ground);
                if (!pixel) {
                    light.push(`${el.tagName.toLowerCase()} ${said} unreadable ${ground}`);
                    continue;
                }
                const [r, g, b, a] = pixel;
                if (a === 0) continue;
                if ((0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 > 0.6) {
                    light.push(`${el.tagName.toLowerCase()} ${said} ${ground}`);
                }
            }
            return light;
        }""",
        pid,
    )


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
