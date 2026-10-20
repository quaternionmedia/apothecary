"""The lighting rig in the viewer: the theatre's fixtures glow the console's levels, each
beam aimed as its patch says in the site's frame, and the panel lists the unplaced
patches and says when the feed is silent.

The rig is the example theatre's (examples/theatre-rig). The levels come from the
simulator's own sweep, PUT to the server the way a bridge would send them.
"""

import json

import pytest
from playwright.sync_api import expect

from apothecary.console_feedback import simulate_levels
from apothecary.theatre_site import load_theatre_rig

pytestmark = pytest.mark.e2e

# What the overlay draws, as an expression: waited on as `() => {STATS}.placed > 0`.
STATS = "window.fractalViewer.lighting.stats()"
RIG = load_theatre_rig()
LOCATED = [p for p in RIG.patches if p.location is not None]


def _feed(page, base_url: str, t: float) -> None:
    levels = simulate_levels(RIG, t)
    response = page.request.put(
        f"{base_url}/sites/theatre/lighting/state",
        data=json.dumps({"levels": levels}),
        headers={"Content-Type": "application/json"},
    )
    assert response.status == 200, response.text()


def test_placed_fixtures_are_drawn_and_glow_from_the_console(page, base_url: str):
    page.goto(f"{base_url}/viewer/sites/theatre")
    page.wait_for_function(f"() => {STATS}.placed > 0", timeout=20000)
    assert page.evaluate(f"() => {STATS}")["placed"] == len(LOCATED)
    _feed(page, base_url, 1.0)
    page.wait_for_function(f"() => {STATS}.lit > 0", timeout=10000)
    expect(page.locator(".lighting-panel")).to_contain_text("console")
    expect(page.locator(".lighting-panel")).to_contain_text("unplaced")


def test_each_beam_points_where_its_patch_aims_it(page, base_url: str):
    """Front of house tilts upstage, towards the stage, and down; the groundrow points
    up at the cyc: ORIENTATION_X tilts a straight-down beam towards the site's +y."""
    page.goto(f"{base_url}/viewer/sites/theatre")
    page.wait_for_function(f"() => {STATS}.placed > 0", timeout=20000)
    foh = next(p for p in LOCATED if p.label.startswith("FOH"))
    ground = next(p for p in LOCATED if p.label.startswith("Groundrow"))
    x, y, z = page.evaluate("(ch) => window.fractalViewer.lighting.aim(ch)", foh.channel)
    assert abs(x) < 1e-6 and y > 0.5 and z < -0.4, (x, y, z)
    x, y, z = page.evaluate("(ch) => window.fractalViewer.lighting.aim(ch)", ground.channel)
    assert abs(x) < 1e-6 and y > 0 and z > 0.9, (x, y, z)


def test_a_site_without_a_rig_gets_no_overlay_and_switching_away_clears_it(page, base_url: str):
    page.goto(f"{base_url}/viewer/sites/theatre")
    page.wait_for_function(f"() => {STATS}.placed > 0", timeout=20000)
    page.evaluate("() => window.fractalViewer.loadSite('garage')")
    page.wait_for_function(f"() => {STATS}.placed === 0", timeout=20000)
    expect(page.locator(".lighting-panel")).to_be_hidden()
    page.evaluate("() => window.fractalViewer.loadSite('theatre')")
    page.wait_for_function(f"() => {STATS}.placed === {len(LOCATED)}", timeout=20000)
