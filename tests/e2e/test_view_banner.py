"""The view banner: the header's one trail of where you are.

``🧪 Apothecary › garage › cnc_router › frame_system``. The first crumb is the universe,
the page's heading and the way to it, and says in its tooltip what the prototype pill
said. The site's crumb is one crumb that goes to the site's own level and, under its ▾
(or pressed at that level), chooses another site. Each piece stepped into follows. At
the universe the trail is the first crumb alone. ⚙ View, ⊞ Windows, Docs, ⌗ Ring and
the problems' count stand where they stood.
"""

from __future__ import annotations

import re

import pytest
from garage import crumbs, row, said, status, to_site
from playwright.sync_api import Page, expect
from viewer_ready import settled

UNIVERSE = "apothecary"
FIRST = "🧪 Apothecary"

# The header's own children, left to right, by what each is.
HEADER = (
    """() => [...document.querySelector('.toolbar').children].map((el) => el.id || el.className)"""
)


def _at(page: Page, base_url: str, site: str = "garage", query: str = "") -> None:
    """The viewer on a site, its rows shown and its geometry in."""
    page.goto(f"{base_url}/viewer/sites/{site}{query}")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=20000)
    settled(page)


def _is_at(page: Page, site: str) -> None:
    page.wait_for_function("(s) => window.fractalViewer.siteName === s", arg=site)


def _focus(page: Page) -> str:
    return page.evaluate("() => window.fractalViewer.focusPath.join('.')")


@pytest.mark.e2e
def test_the_header_is_one_banner_and_what_stood_beside_it_stands(page: Page, base_url: str):
    _at(page, base_url)
    assert page.evaluate(HEADER) == [
        "view-banner",
        "spacer",
        "view-menu",
        "windows-menu",
        "docs-link",
        "ring-open",
        "validity-indicator",
    ]
    # No title beside the trail, no pill, no drop-down: the banner is all three.
    for gone in (".toolbar > h1", ".toolbar .badge", "#site-select", ".toolbar select#site-select"):
        expect(page.locator(gone)).to_have_count(0)
    first = page.locator("#universe-crumb")
    expect(page.locator("#view-banner h1")).to_have_text(FIRST)
    expect(first).to_have_attribute("title", re.compile("unratified prototype"))
    expect(first).to_have_attribute("href", re.compile(r"/viewer/sites/apothecary$"))
    assert crumbs(page) == [FIRST, "garage"]
    expect(page.locator("#view-banner")).to_have_attribute("aria-label", "Where you are")


@pytest.mark.e2e
def test_the_trail_reads_from_the_universe_down_to_the_level_in_view(page: Page, base_url: str):
    _at(page, base_url, query="?focus=cnc_router.frame_system")
    assert crumbs(page) == [FIRST, "garage", "cnc_router", "frame_system"]
    read = page.locator("#view-banner").inner_text()
    assert (
        re.sub(r"\s+", " ", read).strip() == "🧪 Apothecary › garage ▾ › cnc_router › frame_system"
    )
    # A crumb of a piece goes up to its level, as it did.
    page.locator("#breadcrumb .crumb", has_text="cnc_router").click()
    assert _focus(page) == "cnc_router"
    assert crumbs(page) == [FIRST, "garage", "cnc_router"]


@pytest.mark.e2e
def test_at_the_universe_the_trail_is_its_crumb_alone(page: Page, base_url: str):
    _at(page, base_url, UNIVERSE)
    assert crumbs(page) == [FIRST]
    expect(page.locator("#site-crumb")).to_be_hidden()
    expect(page.locator("#breadcrumb")).to_be_hidden()
    assert re.sub(r"\s+", " ", page.locator("#view-banner").inner_text()).strip() == FIRST
    # A part stepped into follows it; the first crumb is the way back to its own level.
    row(page, "calibration_cube").dblclick()
    said(page, "Stepped into calibration_cube")
    assert crumbs(page) == [FIRST, "calibration_cube"]
    page.locator("#universe-crumb").click()
    assert _focus(page) == ""
    assert crumbs(page) == [FIRST]
    assert page.evaluate("() => window.fractalViewer.siteName") == UNIVERSE
    # At its own level already, it says so and goes nowhere.
    page.locator("#universe-crumb").click()
    expect(status(page)).to_contain_text("Already at Apothecary's own level")


@pytest.mark.e2e
def test_the_site_crumb_goes_to_the_sites_own_level_and_chooses_another_site(
    page: Page, base_url: str
):
    _at(page, base_url, query="?focus=cnc_router.frame_system")
    level, menu = page.locator("#site-level"), page.locator("#site-menu")
    expect(level).to_have_attribute("title", "garage: up to its own level")
    # Its ▾ chooses from any level, and leaves the level where it is until a site is chosen.
    menu.locator("summary").click()
    expect(menu.locator(".site-item")).to_have_text(["○ datum_core", "● garage", "○ theatre"])
    assert _focus(page) == "cnc_router.frame_system"
    page.keyboard.press("Escape")
    expect(menu.locator(".site-menu-body")).to_be_hidden()
    assert _focus(page) == "cnc_router.frame_system"
    # The crumb goes to the site's own level.
    level.click()
    assert _focus(page) == ""
    assert crumbs(page) == [FIRST, "garage"]
    expect(menu.locator(".site-menu-body")).to_be_hidden()
    # At that level it has nowhere to go up to: it opens the sites, as its ▾ does.
    expect(level).to_have_attribute("title", "garage, at its own level: choose another site")
    level.click()
    expect(menu.locator(".site-menu-body")).to_be_visible()
    # A press anywhere else folds it away.
    page.locator("#status").click()
    expect(menu.locator(".site-menu-body")).to_be_hidden()
    level.click()
    menu.locator(".site-item[data-site='theatre']").click()
    _is_at(page, "theatre")
    expect(page).to_have_url(re.compile(r"/viewer/sites/theatre$"))
    assert crumbs(page) == [FIRST, "theatre"]
    expect(menu.locator(".site-menu-body")).to_be_hidden()
    page.go_back()
    _is_at(page, "garage")
    assert crumbs(page)[:2] == [FIRST, "garage"]


@pytest.mark.e2e
def test_the_first_crumb_goes_to_the_universe_from_anywhere(page: Page, base_url: str):
    _at(page, base_url, query="?focus=printer_1")
    page.locator("#universe-crumb").click()
    _is_at(page, UNIVERSE)
    expect(page).to_have_url(re.compile(r"/viewer/sites/apothecary$"))
    said(page, "Stepped out of the site garage to Apothecary (the first crumb)")
    page.wait_for_function("() => window.fractalViewer.selectedName === 'site-garage'")
    assert crumbs(page) == [FIRST]
    # Back returns to the site, at the piece it was in.
    page.go_back()
    _is_at(page, "garage")
    page.wait_for_function("() => window.fractalViewer.focusPath.join('.') === 'printer_1'")
    assert crumbs(page) == [FIRST, "garage", "printer_1"]


@pytest.mark.e2e
def test_the_banner_follows_a_site_chosen_any_other_way(page: Page, base_url: str):
    """A step into a site's piece, a step out of a site, and Back: the banner says where."""
    _at(page, base_url, UNIVERSE)
    to_site(page, "datum_core")
    assert crumbs(page) == [FIRST, "datum_core"]
    expect(page.locator("#site-level")).to_have_attribute(
        "href", re.compile(r"/viewer/sites/datum_core$")
    )
    page.locator("#viewer-canvas").focus()
    page.keyboard.press("PageUp")
    _is_at(page, UNIVERSE)
    assert crumbs(page) == [FIRST]
    page.go_back()
    _is_at(page, "datum_core")
    assert crumbs(page) == [FIRST, "datum_core"]


@pytest.mark.e2e
def test_the_crumbs_are_reached_and_pressed_from_the_keyboard(page: Page, base_url: str):
    _at(page, base_url, query="?focus=workbench")
    page.locator("#site-level").focus()
    page.keyboard.press("Enter")
    assert _focus(page) == ""
    page.locator("#site-menu > summary").focus()
    page.keyboard.press("Enter")
    expect(page.locator("#site-menu .site-item.open")).to_be_focused()
    page.keyboard.press("ArrowDown")
    expect(page.locator("#site-menu .site-item[data-site='theatre']")).to_be_focused()
    page.keyboard.press("Enter")
    _is_at(page, "theatre")
    page.locator("#universe-crumb").focus()
    page.keyboard.press("Enter")
    _is_at(page, UNIVERSE)
