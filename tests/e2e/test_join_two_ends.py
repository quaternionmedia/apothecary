"""Two ends joined by the adapter between them, in the page (docs/viewer.md, "Presets,
and the adapter between two ends"): the port part's presets in Parameters, one staged
and applied, an end kept with ⇄ Adapter, the other end's caliper reading typed over its
preset, and ⇄ Adapter again: the adapter derived by the server, chosen in the universe,
applied, and each end's fit said in its Selected; its numbers adjusted, each fit asked
again; and two ends that meet already refused, the end kept still kept.

The server is this module's own, its render cache a temp folder; every render is
OpenSCAD's on this machine."""

from __future__ import annotations

import re

import part_editing
import pytest
from garage import status as _status
from playwright.sync_api import Page, expect

JOIN = "#part-join"
FITS = "#join-fits"


@pytest.fixture(scope="module")
def url(start_server, every_stl_built, tmp_path_factory):
    real = every_stl_built()["path"]
    if not real:
        pytest.skip("OpenSCAD not installed")
    folder = tmp_path_factory.mktemp("join-two-ends")
    return start_server(
        {"APOTHECARY_OPENSCAD": real, "APOTHECARY_CACHE_DIR": str(folder / "cache")}
    )


def _open(page: Page, url: str) -> None:
    page.goto(f"{url}/viewer/sites/apothecary")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=30000)


def _port(page: Page, url: str) -> None:
    _open(page, url)
    part_editing.edit(page, "dust_port", scad=False)
    expect(page.locator("#part-presets")).to_be_visible(timeout=15000)


def _number(page: Page, field: str, value: str) -> None:
    part_editing.param(page, field).locator(".param-number").fill(value)


def _applied(page: Page, part: str) -> None:
    expect(_status(page)).to_contain_text(re.compile(rf"{part} (from the cache|regenerated)"), timeout=120000)


@pytest.mark.e2e
def test_a_preset_is_staged_over_the_part_s_defaults_and_applied(page: Page, url):
    _port(page, url)
    options = page.locator("#part-preset option")
    expect(options).to_have_text(["as staged", "hose_40", "port_32", "port_25", "outlet_35"])
    page.select_option("#part-preset", "port_25")
    expect(_status(page)).to_contain_text("port_25 staged -- a rigid port with a 25 mm bore")
    expect(part_editing.param(page, "diameter").locator(".param-number")).to_have_value("25")
    page.locator("#apply-btn").click()
    _applied(page, "dust_port")
    # Nothing staged, the bar's Revert reads Defaults, which lets the preset go; then
    # Revert, the step back from it.
    going_back = page.locator("#revert-btn")
    expect(going_back).to_have_text("Defaults")
    going_back.click()
    expect(page.locator("#part-preset")).to_have_value("")
    expect(going_back).to_have_text("Revert")


@pytest.mark.e2e
def test_two_ends_make_the_adapter_drawn_with_each_fit_said_and_checked_again(page: Page, url):
    _port(page, url)
    join = page.locator(JOIN)
    expect(join).to_be_visible()
    page.select_option("#part-preset", "hose_40")
    page.locator("#join-btn").click()
    expect(_status(page)).to_contain_text("dust_port@hose_40 kept as one end")
    expect(join).to_contain_text("dust_port@hose_40 is kept as one end")
    # The other end: a 32 port, its bore read with calipers at 31.6.
    page.select_option("#part-preset", "port_32")
    _number(page, "diameter", "31.6")
    part_editing.param(page, "measured").locator(".param-tick").check()
    page.locator("#join-btn").click()
    expect(_status(page)).to_contain_text("derived and drawn", timeout=180000)
    page.wait_for_function("() => window.fractalViewer.selectedName === 'hose_adapter'")
    fits = page.locator(FITS)
    # What is joined, each end's fit, and the end whose numbers are still a guess.
    expect(fits.locator("li")).to_have_count(4, timeout=20000)
    expect(fits).to_contain_text("a ↔ dust_port@hose_40.end: seats, 40 in")
    expect(fits).to_contain_text("b ↔ dust_port@port_32.end (diameter=31.6, measured=true): seats, 12.5 in")
    expect(fits.locator("li").last).to_have_text("stub numbers: dust_port@hose_40.end")
    expect(page.locator(f"{JOIN} .join-said")).to_contain_text("each seats at what is drawn")
    expect(part_editing.param(page, "b_d").locator(".param-number")).to_have_value("31.6")
    # Opened past the bore: checked again once applied, and said.
    _number(page, "b_d", "33")
    page.locator("#apply-btn").click()
    _applied(page, "hose_adapter")
    expect(fits).to_contain_text("b ↔ dust_port@port_32.end (diameter=31.6, measured=true): will not enter", timeout=20000)
    expect(page.locator(f"{JOIN} .join-said")).to_contain_text(
        "an end does not seat -- b ↔ dust_port@port_32.end (diameter=31.6, measured=true): will not enter"
    )


@pytest.mark.e2e
def test_two_ends_that_meet_already_are_refused_and_the_end_kept_stays_kept(page: Page, url):
    _port(page, url)
    page.select_option("#part-preset", "outlet_35")
    page.locator("#join-btn").click()
    expect(_status(page)).to_contain_text("dust_port@outlet_35 kept as one end")
    page.select_option("#part-preset", "port_32")
    _number(page, "diameter", "35")
    page.locator("#join-btn").click()
    expect(_status(page)).to_contain_text("No adapter: dust_port@outlet_35.end and dust_port@port_32.end (diameter=35) meet without an adapter", timeout=30000)
    expect(_status(page)).to_contain_text("dust_port@outlet_35 is still kept")
    assert page.evaluate("() => window.fractalViewer.selectedName") == "dust_port"


@pytest.mark.e2e
def test_the_kept_end_survives_a_reload_and_a_cross_lets_it_go(page: Page, url):
    _port(page, url)
    page.select_option("#part-preset", "outlet_35")
    page.locator("#join-btn").click()
    expect(page.locator(f"{JOIN} .join-said")).to_contain_text("dust_port@outlet_35 is kept as one end")
    expect(page.locator("#join-let-go")).to_be_visible()
    # A reload forgets the page's state, not this tab's kept end.
    _port(page, url)
    expect(page.locator(f"{JOIN} .join-said")).to_contain_text("dust_port@outlet_35 is kept as one end")
    # Let go, it stays let go across another reload.
    page.locator("#join-let-go").click()
    expect(_status(page)).to_contain_text("dust_port@outlet_35 let go")
    expect(page.locator(f"{JOIN} .join-said")).to_contain_text("⇄ Adapter keeps it")
    expect(page.locator("#join-let-go")).to_be_hidden()
    _port(page, url)
    expect(page.locator(f"{JOIN} .join-said")).to_contain_text("⇄ Adapter keeps it")


@pytest.mark.e2e
def test_both_ends_stand_beside_the_adapter_made_between_them(page: Page, url):
    _port(page, url)
    page.select_option("#part-preset", "hose_40")
    page.locator("#join-btn").click()
    expect(_status(page)).to_contain_text("dust_port@hose_40 kept as one end")
    page.select_option("#part-preset", "port_32")
    page.locator("#join-btn").click()
    expect(_status(page)).to_contain_text("between its two ends", timeout=180000)
    # Each end is drawn, and stands against the adapter: the bounding spheres of the two
    # meshes meet, where the adapter alone was a metre from the port.
    reach = page.evaluate(
        """() => {
            const v = window.fractalViewer;
            const radius = (m) => { m.geometry.computeBoundingSphere(); return m.geometry.boundingSphere.radius; };
            const adapter = v.meshByName.hose_adapter;
            return v.joinEnds.map((end) => ({
                part: end.userData.joinEnd,
                apart: end.position.distanceTo(adapter.position),
                touching: radius(end) + radius(adapter),
            }));
        }"""
    )
    assert [r["part"] for r in reach] == ["dust_port", "dust_port"]
    for r in reach:
        assert 0 < r["apart"] <= r["touching"] + 1, reach
