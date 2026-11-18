"""The journeys (apothecary/journeys.py) on the page, as a person goes through them.

The Print view: the windows a part is made through on a machine laid out together from
⊞ Windows, with printer_1's Machine open and the footpedal chosen -- Site with its own
windows, Selected, Parameters, and the Machine sharing a stack with its Print window,
Print in front, the Machine's sections open before it kept behind them. Greyed while
no Machine is open and the piece chosen has no board.

Print a part, its journey: entered from ⊞ Windows › Journeys, its rail in the header
at Choose, walked Next by Next to Measure, each step's windows brought forward and the
address holding the step; a window's tab chosen moves the rail and nothing else, a
reload lands on the step the address names, and ✕ leaves it, the windows where they
are.
"""

from __future__ import annotations

import re

import httpx
import pytest
import windows
from boards import PRINTER, wears
from garage import open_garage, status
from garage import select as _select
from playwright.sync_api import Page, expect

MAINBOARD = "printer_1.frame_system.mainboard"
MAKE = ".windows-menu-body .view-item[data-view='make']"
MAKE_A_THING = ".windows-menu-body .journey-item[data-journey='make']"
RAIL = "#journey-rail"
STEP_ON = "() => document.querySelector('#journey-rail [aria-current=step]')?.dataset.step"


@pytest.fixture(scope="module")
def url(start_server):
    """printer_1's board identified and pinned, as the simulated server's is."""
    url = start_server({})
    with httpx.Client(base_url=url, timeout=15.0) as http:
        http.post("/firmware/devices/identify", json={"port": PRINTER}).raise_for_status()
        http.put(
            f"/sites/garage/nodes/{MAINBOARD}/device", json={"identity": PRINTER}
        ).raise_for_status()
    return url


@pytest.fixture(autouse=True)
def no_page_errors(page: Page):
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    yield
    assert errors == [], errors


@pytest.mark.e2e
def test_the_make_view_is_greyed_until_a_machine_is_there(page: Page, url: str):
    """The footpedal chosen and no Machine open: the Print view says what it needs."""
    open_garage(page, url, settle=False)
    _select(page, "footpedal")
    page.locator("#windows-menu > summary").click()
    entry = page.locator(MAKE)
    # Greyed as every control the page greys is: its look and "Disabled: <why>".
    expect(entry).to_have_attribute("aria-disabled", "true")
    expect(entry).to_have_attribute("title", re.compile(r"^Disabled: .*footpedal"))
    expect(entry).to_have_css("opacity", "0.45")
    # Pressed all the same, as a person can: aria-disabled alone, which Playwright's own
    # wait for an enabled element counts as disabled.
    entry.click(timeout=5000, force=True)
    said = status(page)
    expect(said).to_contain_text("Print view: ")
    expect(said).to_contain_text("footpedal")
    expect(said).to_have_class(re.compile(r"\berror\b"))
    assert page.evaluate("() => window.fractalViewer.machine") is None


def _machine_open_and_the_part_chosen(page: Page, url: str) -> None:
    """printer_1's Machine open, as its Device section opens it, then the footpedal chosen."""
    open_garage(page, url, settle=False)
    wears(page, "printer_1")
    _select(page, "printer_1")
    page.locator("#selected-body .device-section .dev-open").click()
    windows.machine_ready(page, "printer")
    _select(page, "footpedal")


def _on(page: Page, step: str) -> None:
    page.wait_for_function(f"(s) => ({STEP_ON})() === s", arg=step, timeout=10000)


def _rail(page: Page) -> list:
    """The rail's steps as it shows them: number, name, whether a person is on it."""
    return page.evaluate(
        """() => [...document.querySelectorAll('#journey-rail .journey-steps button')].map((b) =>
            [b.querySelector('.journey-num').textContent, b.querySelector('.journey-label').textContent,
             b.getAttribute('aria-current') === 'step'])"""
    )


def _enter_make_a_thing(page: Page) -> None:
    page.locator("#windows-menu > summary").click()
    entry = page.locator(MAKE_A_THING)
    expect(entry).to_have_text("Print a part")
    expect(entry).to_have_attribute("title", re.compile(r"^Print a part: 1 Choose, 2 Shape"))
    entry.click(timeout=5000)
    expect(page.locator(RAIL)).to_be_visible(timeout=10000)


@pytest.mark.e2e
def test_the_make_view_lays_out_the_windows_a_part_is_made_through(page: Page, url: str):
    _machine_open_and_the_part_chosen(page, url)
    page.locator("#windows-menu > summary").click()
    entry = page.locator(MAKE)
    expect(entry).not_to_have_attribute("aria-disabled", "true")
    expect(entry).to_have_text("Print")
    entry.click(timeout=5000)
    expect(page.locator(".windows-menu-body")).to_be_hidden()
    expect(status(page)).to_contain_text("The Print view: its windows laid out together")

    # Print comes in front of the Machine's stack once its card has drawn.
    page.wait_for_function(
        "() => window.apothecaryPanels.state('machine-print').shown", timeout=10000
    )
    stacks = {pid: windows.state(page, pid)["stack"] for pid in ("site", "machine", "selected")}
    assert stacks["site"] == ["site", "problems", "pinned", "jobs", "scad"]
    assert stacks["selected"] == ["selected"]
    assert windows.state(page, "part-parameters")["stack"] == ["part-parameters"]
    assert stacks["machine"][:5] == ["machine", "machine-print", "pictures", "bench", "settings"]
    assert windows.state(page, "machine")["shown"] is False
    assert windows.world_width(page) > page.viewport_size["width"] / 2


@pytest.mark.e2e
def test_make_a_thing_is_walked_step_by_step_on_its_rail(page: Page, url: str):
    """Its view laid out and its rail at Choose; Next by Next to Measure, each step's
    window in front and the address holding the step; Start has no Next."""
    _machine_open_and_the_part_chosen(page, url)
    expect(page.locator(RAIL)).to_be_hidden()
    _enter_make_a_thing(page)
    _on(page, "choose")
    expect(page.locator(f"{RAIL} .journey-name")).to_have_text("Print a part")
    assert _rail(page) == [
        ["1", "Choose", True],
        ["2", "Shape", False],
        ["3", "Slice", False],
        ["4", "See", False],
        ["5", "Start", False],
        ["6", "Measure", False],
    ]
    expect(status(page)).to_contain_text("Print a part › 1 Choose (⊞ Windows › Print a part)")
    assert windows.state(page, "site")["shown"] is True
    assert windows.state(page, "machine")["stack"][:2] == ["machine", "machine-print"]
    expect(page).to_have_url(re.compile(r"[?&]journey=make\b"))
    expect(page).to_have_url(re.compile(r"[?&]step=choose\b"))

    for step, window, number, label in (
        ("shape", "part-parameters", 2, "Shape"),
        ("slice", "machine-print", 3, "Slice"),
        ("see", "machine-print", 4, "See"),
        ("print", "machine-print", 5, "Start"),
        ("measure", "machine-print", 6, "Measure"),
    ):
        nxt = page.locator(f"{RAIL} .journey-next")
        expect(nxt).to_have_attribute("data-next", step)
        expect(nxt).to_contain_text(f"Next {number}{label}")
        nxt.click()
        _on(page, step)
        page.wait_for_function("(w) => window.apothecaryPanels.state(w).shown", arg=window)
        expect(page).to_have_url(re.compile(f"[?&]step={step}\\b"))
        expect(status(page)).to_contain_text(f"Print a part › {number} {label} (Next)")
        if step == "print":
            assert windows.state(page, "jobs")["shown"] is True
    expect(page.locator(f"{RAIL} .journey-next")).to_have_count(0)


@pytest.mark.e2e
def test_a_window_chosen_moves_the_rail_and_a_reload_lands_on_its_step(page: Page, url: str):
    """Parameters' tab pressed says Shape and moves no window; Print's says Slice; a
    reload lands on Slice with Print in front; ✕ leaves, the windows where they are."""
    _machine_open_and_the_part_chosen(page, url)
    _enter_make_a_thing(page)
    _on(page, "choose")
    site_shown = windows.state(page, "site")["shown"]
    page.locator(".lm_tab .lm_title", has_text=re.compile(r"^Parameters$")).click()
    _on(page, "shape")
    assert windows.state(page, "site")["shown"] == site_shown
    expect(page).to_have_url(re.compile(r"[?&]step=shape\b"))
    page.locator(".lm_tab .lm_title", has_text=re.compile(r"^Print$")).click()
    _on(page, "slice")

    page.reload()
    expect(page.locator(RAIL)).to_be_visible(timeout=20000)
    _on(page, "slice")
    page.wait_for_function("() => window.apothecaryPanels.state('machine-print').shown")
    expect(status(page)).to_contain_text("Print a part › 3 Slice (the address)")

    page.locator(f"{RAIL} .journey-leave").click()
    expect(page.locator(RAIL)).to_be_hidden()
    expect(page).not_to_have_url(re.compile(r"[?&](journey|step)="))
    expect(status(page)).to_contain_text("Left Print a part")
    assert windows.state(page, "machine-print")["shown"] is True


@pytest.mark.e2e
def test_at_1280_the_rail_names_the_step_a_person_is_on_and_next_and_make_stay_in_view(
    page: Page, url: str
):
    """Six steps, Next and ⚒ Make in one row: the other steps show their numbers alone,
    so Next and ⚒ Make are in view, Make naming what it makes."""
    page.set_viewport_size({"width": 1280, "height": 800})
    _machine_open_and_the_part_chosen(page, url)
    _enter_make_a_thing(page)
    _on(page, "choose")
    shown = page.evaluate(
        """() => [...document.querySelectorAll('#journey-rail .journey-steps button')].map((b) =>
            getComputedStyle(b.querySelector('.journey-label')).display !== 'none')"""
    )
    assert shown == [True, False, False, False, False, False]
    expect(page.locator(f"{RAIL} .journey-next")).to_be_in_viewport(ratio=1)
    expect(page.locator("#make-here")).to_have_text(re.compile(r"^⚒ Make footpedal on "))
    expect(page.locator("#make-here")).to_be_in_viewport(ratio=1)


@pytest.mark.e2e
def test_on_a_narrow_page_the_rail_gives_way_and_the_banner_stays_whole(page: Page, url: str):
    """At a page 1000 px wide the rail drops its name and its steps' names, and is never
    drawn over the banner: the site's crumb and its ▾ stay whole."""
    page.set_viewport_size({"width": 1000, "height": 800})
    _machine_open_and_the_part_chosen(page, url)
    _enter_make_a_thing(page)
    _on(page, "choose")
    laid = page.evaluate(
        """() => { const box = (s) => document.querySelector(s).getBoundingClientRect();
            const rail = document.querySelector('#journey-rail');
            return { rail: box('#journey-rail').left, crumb: box('#site-menu').right,
                     name: getComputedStyle(rail.querySelector('.journey-name')).display,
                     label: getComputedStyle(rail.querySelector('.journey-steps .journey-label')).display }; }"""
    )
    assert laid["rail"] >= laid["crumb"], laid
    assert laid["name"] == laid["label"] == "none", laid
