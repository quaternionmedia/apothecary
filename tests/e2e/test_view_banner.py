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
        "make-here",
        "spacer",
        "view-menu",
        "windows-menu",
        "tour-pop-open",
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
def test_a_crumb_says_what_it_stepped_out_of_and_where_to(page: Page, base_url: str):
    """Page Up says what it stepped out of; a crumb says that too, and where it went."""
    _at(page, base_url, query="?focus=cnc_router.frame_system")
    trail = page.locator("#breadcrumb .crumb")
    # The level in view's own crumb goes nowhere, and says so.
    trail.filter(has_text="frame_system").click()
    said(page, "Already at cnc_router.frame_system's own level")
    assert _focus(page) == "cnc_router.frame_system"
    trail.filter(has_text="cnc_router").click()
    said(page, "Stepped out of cnc_router.frame_system to cnc_router (its crumb)")
    page.locator("#site-level").click()
    said(page, "Stepped out of cnc_router to garage (its crumb)")
    # Two levels at once: the whole way it came.
    page.evaluate("() => window.fractalViewer.stepIn('cnc_router.frame_system')")
    said(page, "Stepped into cnc_router.frame_system")
    page.locator("#site-level").click()
    said(page, "Stepped out of cnc_router.frame_system to garage (its crumb)")
    assert _focus(page) == ""
    # In the universe, the first crumb is the way up to its own level.
    _at(page, base_url, UNIVERSE)
    row(page, "calibration_cube").dblclick()
    said(page, "Stepped into calibration_cube")
    page.locator("#universe-crumb").click()
    said(page, "Stepped out of calibration_cube to Apothecary (the first crumb)")


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
    # At that level it has nowhere to go up to: it opens the sites, as its ▾ does, and
    # wears the address of the ring's Site, which does the same.
    expect(level).to_have_attribute(
        "title", re.compile(r"^garage, at its own level: choose another site · ⌗\d+$")
    )
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


# Every load of a site the page starts, kept as it is started, so a test can wait for
# each to have answered -- landed (true) or let go (false) -- in whatever order the
# answers come.
LOADS_KEPT = """() => {
    const v = window.fractalViewer, own = v.loadSite.bind(v);
    window.loadsKept = [];
    v.loadSite = (...asked) => { const load = own(...asked); window.loadsKept.push(load); return load; };
}"""
ALL_ANSWERED = "() => Promise.all(window.loadsKept)"


@pytest.mark.e2e
def test_a_site_left_before_it_loads_answers_nothing_when_it_comes(page: Page, base_url: str):
    """theatre's piece double-clicked in the universe, then Back before theatre has
    loaded: the address names theatre from the press, the universe stays the site drawn,
    and theatre's answer, coming after the universe's, changes nothing."""
    _at(page, base_url, UNIVERSE)
    page.evaluate(LOADS_KEPT)
    held: list = []
    page.route(re.compile(r"/sites/theatre$"), lambda route: held.append(route))
    row(page, "site-theatre").dblclick()
    expect(page).to_have_url(re.compile(r"/viewer/sites/theatre$"))
    page.wait_for_function("() => window.loadsKept.length === 1")
    assert page.evaluate("() => window.fractalViewer.siteName") == UNIVERSE
    assert crumbs(page) == [FIRST]
    page.go_back()
    page.wait_for_function("() => window.loadsKept.length === 2")
    assert page.evaluate("() => window.loadsKept[1]") is True
    assert len(held) == 1
    held[0].continue_()
    assert page.evaluate(ALL_ANSWERED) == [False, True]
    assert page.evaluate("() => window.fractalViewer.siteName") == UNIVERSE
    expect(page).to_have_url(re.compile(r"/viewer/sites/apothecary$"))
    assert crumbs(page) == [FIRST]
    expect(status(page)).not_to_contain_text("theatre")


@pytest.mark.e2e
def test_the_first_crumb_pressed_while_a_site_loads_steps_out_of_that_site(
    page: Page, base_url: str
):
    """garage drawn, theatre chosen under the site crumb's ▾ and still loading, the first
    crumb pressed: the page steps out of theatre, the site the address names and Back
    returns to, its piece selected in the universe; theatre's answer, coming last,
    changes nothing."""
    _at(page, base_url)
    page.evaluate(LOADS_KEPT)
    held: list = []
    page.route(
        re.compile(r"/sites/theatre$"),
        lambda route: held.append(route) if not held else route.continue_(),
    )
    page.locator("#site-menu > summary").click()
    page.locator("#site-menu .site-item[data-site='theatre']").click()
    expect(page).to_have_url(re.compile(r"/viewer/sites/theatre$"))
    assert crumbs(page)[:2] == [FIRST, "garage"]
    page.locator("#universe-crumb").click()
    _is_at(page, UNIVERSE)
    said(page, "Stepped out of the site theatre to Apothecary (the first crumb)")
    page.wait_for_function("() => window.fractalViewer.selectedName === 'site-theatre'")
    assert len(held) == 1
    held[0].continue_()
    assert page.evaluate(ALL_ANSWERED) == [False, True]
    assert page.evaluate("() => window.fractalViewer.siteName") == UNIVERSE
    assert page.evaluate("() => window.fractalViewer.selectedName") == "site-theatre"
    expect(page).to_have_url(re.compile(r"/viewer/sites/apothecary$"))
    page.go_back()
    _is_at(page, "theatre")
    assert crumbs(page) == [FIRST, "theatre"]


@pytest.mark.e2e
def test_a_site_s_machines_are_its_own_from_the_moment_it_is_drawn(page: Page, base_url: str):
    """The garage's machines known, the universe drawn while its own are still asked
    for: none of the garage's stands for the universe's meanwhile."""
    _at(page, base_url)
    page.wait_for_function(
        "() => window.fractalViewer.machinesHere.some((m) => m.path === 'printer_1')"
    )
    held: list = []
    page.route(re.compile(r"/sites/apothecary/machines$"), lambda route: held.append(route))
    page.locator("#universe-crumb").click()
    _is_at(page, UNIVERSE)
    assert page.evaluate("() => window.fractalViewer.machinesHere") == []
    assert len(held) == 1
    held[0].continue_()
    page.wait_for_function("() => window.fractalViewer.machinesHere.length > 0")
    garage = {"printer_1", "cnc_router"}
    here = page.evaluate("() => window.fractalViewer.machinesHere.map((m) => m.path)")
    assert garage.isdisjoint(here), here


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
