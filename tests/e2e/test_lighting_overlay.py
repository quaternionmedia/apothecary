"""The lighting rig in the viewer: fixtures glow the console's levels, and the
panel lists the unplaced patches and says when the feed is silent.

The venue's files are the school's, not the repository's, so these skip when the
export is absent. The levels come from the simulator's own sweep, PUT to the
server the way a bridge would send them.
"""

import json

import pytest
from playwright.sync_api import expect

from apothecary.console_feedback import simulate_levels
from apothecary.echs_pac_site import load_echs_rig, venue_present

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not venue_present(), reason="ECHS-PAC export not on this machine"),
]

STATS = "() => window.fractalViewer.lighting.stats()"


def _feed(page, base_url: str, t: float) -> None:
    levels = simulate_levels(load_echs_rig(), t)
    response = page.request.put(
        f"{base_url}/sites/echs_pac/lighting/state",
        data=json.dumps({"levels": levels}),
        headers={"Content-Type": "application/json"},
    )
    assert response.status == 200, response.text()


def test_placed_fixtures_are_drawn_and_glow_from_the_console(page, base_url: str):
    page.goto(f"{base_url}/viewer/sites/echs_pac")
    page.wait_for_function(f"() => {STATS}().placed > 0", timeout=20000)
    assert page.evaluate(STATS)["placed"] == 156
    _feed(page, base_url, 1.0)
    page.wait_for_function(f"() => {STATS}().lit > 0", timeout=10000)
    expect(page.locator(".lighting-panel")).to_contain_text("console")
    expect(page.locator(".lighting-panel")).to_contain_text("unplaced")


def test_a_site_without_a_rig_gets_no_overlay_and_switching_away_clears_it(page, base_url: str):
    page.goto(f"{base_url}/viewer/sites/echs_pac")
    page.wait_for_function(f"() => {STATS}().placed > 0", timeout=20000)
    page.evaluate("() => window.fractalViewer.loadSite('garage')")
    page.wait_for_function(f"() => {STATS}().placed === 0", timeout=20000)
    expect(page.locator(".lighting-panel")).to_be_hidden()
    page.evaluate("() => window.fractalViewer.loadSite('echs_pac')")
    page.wait_for_function(f"() => {STATS}().placed === 156", timeout=20000)
