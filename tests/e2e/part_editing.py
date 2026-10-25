"""The Part as a test works on it: a focused system (apothecary/systems.py) whose main
window is Selected and whose sections -- Parameters, SCAD, Variants, History,
Readiness -- are windows of their own, closed until asked for.

`edit` opens the editor as a person does, Part › Edit on the part's row, and by default
lays the Part out (Panels › Windows › Part view) so every section is open: the
default for a test that works on a part. ``view=False`` leaves the page's own layout,
for a test of what Part › Edit alone opens."""

from __future__ import annotations

import rings
import windows
from playwright.sync_api import Page, expect

# Each section's window, and what it holds.
PARAMETERS = ".panel[data-panel='part-parameters']"
SCAD = ".panel[data-panel='part-scad']"
READINESS = ".panel[data-panel='part-readiness']"


def edit(
    page: Page, part: str, *, view: bool = True, scad: bool = True, timeout: int = 20000
) -> None:
    """Part › Edit on the part's row: its controls built in Parameters; with ``view``,
    the Part view laid out, and with ``scad`` its SCAD editor ready there."""
    rings.on_row(page, part, "Part", "Edit")
    if view:
        windows.part_view(page)
    expect(page.locator(f"{PARAMETERS} #part-params .param")).not_to_have_count(0, timeout=timeout)
    if view and scad:
        expect(code(page)).to_be_visible(timeout=timeout)


def param(page: Page, field: str):
    """A parameter's row in Parameters."""
    return page.locator(f"#part-params > .param[data-field='{field}']")


def code(page: Page):
    """The SCAD editor's text."""
    return page.locator(".scad-editor .cm-content")
