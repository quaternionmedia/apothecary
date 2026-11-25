"""A stage of the tour is the same from wherever a person opens it.

The tour opened in the universe takes the page to the garage, where the journeys'
pieces and machines stand, before the stage's own puts; and the See stage draws a
file made from its own piece -- another part's file chosen before is not its, and a
file of its piece kept before is chosen rather than sliced again.

Runs against a server of its own with nothing pinned: printer_1 is taken as the garage
plans it, not connected, so no port is touched. The slicer is the scripted
OrcaSlicer of the unit tests (tests/slicer_helpers.py). No word is kept.
"""

from __future__ import annotations

import re

import pytest
import windows
from garage import open_garage, to_site
from playwright.sync_api import Page, expect
from slicer_helpers import write_fake_orcaslicer

BOX = "#tour-pop"
SLICED_MS = 30000
STEP_ON = "() => window.fractalViewer.journey?.step"


@pytest.fixture(scope="module")
def url(base_url, start_server, tmp_path_factory):
    """This module's own server, the scripted OrcaSlicer its slicer. ``base_url`` is
    asked for only so that with no server to run against this is skipped, as every
    browser test is."""
    orca = write_fake_orcaslicer(tmp_path_factory.mktemp("orca"))
    return start_server({"APOTHECARY_ORCASLICER": str(orca)})


def _taken_to(page: Page, step: str) -> None:
    expect(page.locator(BOX)).not_to_have_class(re.compile(r"\bbusy\b"), timeout=60000)
    page.wait_for_function(f"(s) => ({STEP_ON})() === s", arg=step, timeout=15000)


def _did(page: Page) -> list[str]:
    return [t.strip() for t in page.locator(f"{BOX} .tour-pop-did li").all_text_contents()]


def _sliced(page: Page, part: str) -> None:
    """``part`` chosen under printer_1's makes and sliced there, as a person does it."""
    windows.in_machine(page, "#print-part").select_option(part)
    windows.in_machine(page, "#print-slice").click()
    expect(page.locator("#status")).to_contain_text(
        f"{part}.gcode kept and chosen", timeout=SLICED_MS
    )


@pytest.mark.e2e
def test_a_stage_opens_its_site_and_draws_its_own_piece_s_file(page: Page, url: str):
    errors: list = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    box = page.locator(BOX)
    open_garage(page, url, settle=False)
    to_site(page, "apothecary")

    # Print a part, chosen in the universe: the garage opened first, then its stage.
    page.locator("#tour-pop-open").click()
    expect(box).to_be_visible()
    journeys = page.request.get(f"{url}/tour").json()["journeys"]
    at = next(i for i, j in enumerate(journeys) if j["name"] == "Print a part")
    box.locator(".tour-pop-journeys").select_option(value=str(at))
    _taken_to(page, "choose")
    assert page.evaluate("() => window.fractalViewer.siteName") == "garage"
    assert _did(page)[0] == "garage opened, where Print a part stands (apothecary was open)"
    assert page.evaluate("() => window.fractalViewer.selectedName") == "footpedal"

    # Another part's file chosen in the Print window: not See's. The footpedal is sliced.
    _sliced(page, "calibration_cube")
    box.locator(".tour-pop-stages button", has_text="4 See").click()
    _taken_to(page, "see")
    assert "footpedal sliced for printer_1, as Slice does: footpedal.gcode" in _did(page)
    expect(windows.in_machine(page, "#print-pick")).to_have_value(re.compile("footpedal"))

    # The cube's file chosen again, and See again: the footpedal's kept file is chosen.
    _sliced(page, "calibration_cube")
    box.locator(".tour-pop-stages button", has_text="3 Slice").click()
    _taken_to(page, "slice")
    # The Slice stage stands on its own part: footpedal under makes, its kept file chosen,
    # not the cube's that was.
    expect(windows.in_machine(page, "#print-part")).to_have_value("footpedal")
    expect(windows.in_machine(page, "#print-pick")).to_have_value(re.compile("footpedal"))
    assert any("footpedal.gcode, made from footpedal before, chosen" in t for t in _did(page))
    # So See has nothing left to choose or slice.
    box.locator(".tour-pop-stages button", has_text="4 See").click()
    _taken_to(page, "see")
    assert not any("sliced for printer_1" in t for t in _did(page))
    expect(box.locator(".tour-pop-did li").last).to_contain_text("path is drawn on printer_1")

    # Print names ▶ Print, which is in the Print window: that tab is brought forward.
    box.locator(".tour-pop-stages button", has_text="5 Print").click()
    _taken_to(page, "print")
    expect(windows.in_machine(page, "#print-start")).to_be_visible()
    assert errors == []


@pytest.mark.e2e
def test_a_stage_chooses_its_machine_when_that_machine_is_open_already(page: Page, url: str):
    """Drive a machine › Knobs is about printer_1: chosen in Selected whether its Machine
    opens for the stage or was open already, not left on the deck the stage before chose."""
    errors: list = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    box = page.locator(BOX)
    open_garage(page, url, settle=False)
    page.locator("#tour-pop-open").click()
    expect(box).to_be_visible()
    journeys = page.request.get(f"{url}/tour").json()["journeys"]
    at = next(i for i, j in enumerate(journeys) if j["name"] == "Drive a machine")
    box.locator(".tour-pop-journeys").select_option(value=str(at))
    _taken_to(page, "deck")
    assert page.evaluate("() => window.fractalViewer.selectedName") == "stream_deck"
    box.locator(".tour-pop-stages button", has_text="2 Knobs").click()
    _taken_to(page, "knobs")
    assert page.evaluate("() => window.fractalViewer.selectedName") == "printer_1"
    # Its Machine open, the deck stage again and then Knobs again.
    box.locator(".tour-pop-stages button", has_text="1 Deck").click()
    _taken_to(page, "deck")
    assert page.evaluate("() => window.fractalViewer.selectedName") == "stream_deck"
    assert page.evaluate("() => Boolean(window.fractalViewer.machine)")
    box.locator(".tour-pop-stages button", has_text="2 Knobs").click()
    _taken_to(page, "knobs")
    assert page.evaluate("() => window.fractalViewer.selectedName") == "printer_1"
    assert errors == []


@pytest.mark.e2e
def test_a_stage_opens_a_planned_machine_once_its_site_s_machines_answer(page: Page, url: str):
    """The garage's machines (GET /sites/garage/machines) answering after its boards
    are scanned: printer_1 is chosen, and its Machine waits for them rather than saying
    it has no board pinned; once they answer it opens as the garage plans it, and the
    footpedal is chosen."""
    errors: list = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    box = page.locator(BOX)
    open_garage(page, url, settle=False)
    to_site(page, "apothecary")
    held: list = []
    page.route("**/sites/garage/machines", lambda route: held.append(route))

    page.locator("#tour-pop-open").click()
    expect(box).to_be_visible()
    journeys = page.request.get(f"{url}/tour").json()["journeys"]
    at = next(i for i, j in enumerate(journeys) if j["name"] == "Print a part")
    box.locator(".tour-pop-journeys").select_option(value=str(at))
    page.wait_for_function(
        "() => window.fractalViewer.siteName === 'garage'"
        " && window.fractalViewer.selectedName === 'printer_1'"
    )
    assert len(held) == 1
    held[0].continue_()
    _taken_to(page, "choose")
    assert page.locator(f"{BOX} .tour-pop-needs").text_content() == ""
    planned = "printer_1's Machine opened, not connected: what it makes is planned there"
    assert planned in _did(page)
    assert page.evaluate("() => window.fractalViewer.selectedName") == "footpedal"
    assert errors == []
