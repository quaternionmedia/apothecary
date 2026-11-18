"""The universe in a browser (apothecary/universe.py): the site ``apothecary``, a sphere
of nested shells, every registered part a leaf of it on the shell its composition depth
gives it, facing outward, and every other site one piece on the outermost.

A site's piece is drawn in miniature from boxes the site's tree carries, with nothing
rendered for it; Selected says it is a site and how large the site really is, and
offers the step in; it has no parameters and wears no move arrows. A double-click on
it, Page Down or that button opens its site, so Back returns; Page Up or Backspace at
a site's own level goes back to the universe, the site's piece selected there. A site
reached that way is the site: a machine stepped into is drawn as its part.
"""

from __future__ import annotations

import re

import pytest
import rings
from garage import row, said, select, status
from playwright.sync_api import Page, expect
from viewer_ready import settled

UNIVERSE = "apothecary"
SITES = ("datum_core", "garage", "theatre")
PIECE = "site-garage"

# What the level draws once its geometry is in: each piece's mesh (whether it is still
# its placeholder box, and how many meshes stand inside it), what wears the move
# arrows, and where the page is.
LEVEL = """async () => {
    const v = window.fractalViewer;
    await v.waveDone;
    const arrows = v.transformControls.object;
    return {
        site: v.siteName,
        focus: v.focusPath.join('.'),
        selected: v.selectedName,
        drawn: Object.fromEntries(Object.entries(v.meshByName).map(([key, mesh]) => [key, {
            placeholder: !!mesh.userData.isPlaceholder,
            inside: mesh.children.filter((c) => c.isMesh).length,
        }])),
        arrows: arrows ? arrows.userData.key : null,
    };
}"""

# Where on the page a click in the world lands on `key`, nothing in front of it.
# A point of the canvas over a piece: of those a grid finds, the one nearest their
# middle, so the piece is still under it once a first click has selected it and it
# wears its handles. A point at the piece's edge is not.
ON_PIECE = """(key) => {
    const v = window.fractalViewer, r = v.canvas.getBoundingClientRect();
    const over = [];
    for (let i = 1; i < 64; i++) for (let j = 1; j < 64; j++) {
        const at = { clientX: r.left + (r.width * i) / 64, clientY: r.top + (r.height * j) / 64 };
        if (document.elementFromPoint(at.clientX, at.clientY) !== v.canvas) continue;
        if (v.raycastChild(at) === key) over.push({ x: at.clientX, y: at.clientY });
    }
    if (!over.length) return null;
    const mx = over.reduce((sum, p) => sum + p.x, 0) / over.length;
    const my = over.reduce((sum, p) => sum + p.y, 0) / over.length;
    return over.reduce((best, p) => (Math.hypot(p.x - mx, p.y - my) < Math.hypot(best.x - mx, best.y - my) ? p : best));
}"""


def _at(page: Page, base_url: str, site: str = UNIVERSE, query: str = "") -> None:
    """The viewer on a site, its rows shown and its geometry in."""
    page.goto(f"{base_url}/viewer/sites/{site}{query}")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=20000)
    settled(page)


def _is_at(page: Page, site: str) -> None:
    """The page holds ``site``, and its address names it."""
    page.wait_for_function("(s) => window.fractalViewer.siteName === s", arg=site)
    expect(page).to_have_url(re.compile(rf"/viewer/sites/{site}$"))


def _tree(page: Page, base_url: str) -> dict:
    return page.request.get(f"{base_url}/sites/{UNIVERSE}").json()["tree"]


@pytest.fixture(scope="module")
def opened(module_page: Page, base_url: str):
    """The universe as it opens, loaded once for the tests that read it so, and each
    request the page has made since before it loaded. Of them only Selected's test
    changes anything, the selection, which no other reads."""
    asked: list[str] = []
    module_page.on("request", lambda request: asked.append(request.url))
    _at(module_page, base_url)
    return module_page, asked


# The sphere as the page holds it: how far each node's middle is from the site's origin,
# where the camera stands, how near it may come, whether the whole of it is in view, and
# whether the floor grid is drawn.
SPHERE = """() => {
    const v = window.fractalViewer;
    const nodes = Object.values(v.renderNodeByKey).filter((n) => n.world_bounds);
    const middle = (n) => n.world_bounds.min.map((m, i) => (m + n.world_bounds.max[i]) / 2);
    const radius = (n) => Math.hypot(...middle(n));
    const radii = nodes.map(radius);
    const inView = nodes.every((n) => {
        const p = v.sceneAt(...middle(n)).project(v.camera);
        return Math.abs(p.x) <= 1 && Math.abs(p.y) <= 1 && p.z <= 1;
    });
    return {
        outermost: Math.max(...radii),
        innermost: Math.min(...radii),
        camera: v.camera.position.length(),
        nearest: v.orbitControls.minDistance,
        inView,
        grid: v.gridHelper.visible,
    };
}"""

# A turned leaf's mesh: whether its up (three.js's +y) points along the ray from the
# middle of the universe, which is where sceneAt puts the site's origin.
FACES_OUT = """(key) => {
    const v = window.fractalViewer, mesh = v.meshByName[key];
    const q = mesh.quaternion, dir = mesh.position.clone().normalize();
    const up = mesh.position.clone().set(0, 1, 0).applyQuaternion(q);
    return { dot: up.dot(dir), turned: !(q.x === 0 && q.y === 0 && q.z === 0 && q.w === 1) };
}"""


@pytest.mark.e2e
def test_the_universe_opens_as_a_whole_sphere_seen_from_outside_and_the_camera_may_enter(opened):
    page, _ = opened
    seen = page.evaluate(SPHERE)
    assert seen["camera"] > seen["outermost"], f"the camera starts inside the sphere: {seen}"
    assert seen["inView"], f"some of the sphere is out of the opening view: {seen}"
    assert seen["nearest"] < seen["innermost"], f"the camera may not come inside: {seen}"
    assert seen["grid"] is False, "the floor grid cuts through the sphere"


@pytest.mark.e2e
def test_a_part_faces_outward_and_a_site_stands_upright(opened, base_url: str):
    page, _ = opened
    tree = _tree(page, base_url)
    leaves = [c for c in tree["children"] if c["part_ref"] and c["turn"][1] > 1]
    assert leaves, "no leaf is turned"
    for leaf in leaves[:6]:
        facing = page.evaluate(FACES_OUT, leaf["name"])
        assert facing["turned"] and facing["dot"] > 0.999, f"{leaf['name']} faces {facing}"
    garage = next(c for c in tree["children"] if c["site_ref"] == "garage")
    assert not page.evaluate(FACES_OUT, garage["name"])["turned"]


@pytest.mark.e2e
def test_the_webcam_part_is_drawn_from_its_stl(opened, base_url: str):
    """The universe's webcam leaf is the part, not a camera of a site waiting to be
    aimed: its STL is asked for and drawn, where it stood as its box for good."""
    page, asked = opened
    leaf = next(c for c in _tree(page, base_url)["children"] if c["part_ref"] == "webcam")
    page.wait_for_function(
        "(k) => { const m = window.fractalViewer.meshByName[k]; return !!m && !m.userData.isPlaceholder; }",
        arg=leaf["name"],
        timeout=30000,
    )
    assert any("/parts/webcam/stl" in u for u in asked)


@pytest.mark.e2e
def test_every_other_site_is_a_miniature_and_nothing_is_rendered_to_draw_one(opened, base_url: str):
    page, asked = opened
    tree = _tree(page, base_url)
    pieces = {child["site_ref"]: child for child in tree["children"] if child["site_ref"]}
    assert set(pieces) == set(SITES)
    level = page.evaluate(LEVEL)
    for name, piece in pieces.items():
        drawn = level["drawn"][piece["name"]]
        assert not drawn["placeholder"], f"{name}'s piece is still its box"
        assert drawn["inside"] == len(piece["miniature"]) > 0
        # Named for its site in Site's rows, where a part of the same name is a part.
        expect(row(page, piece["name"]).locator(".item-label")).to_have_text(f"{name} (site)")
    expect(row(page, "datum_core").locator(".item-label")).to_have_text("datum_core (part)")
    # The first rows, in their sites' order, before any part.
    first = page.locator("#contents-list .contents-item").evaluate_all(
        "(rows) => rows.slice(0, 3).map((li) => li.dataset.path)"
    )
    assert first == [f"site-{name}" for name in SITES]
    renders = [url for url in asked if f"/sites/{UNIVERSE}/nodes/" in url]
    assert renders == [], "a site's piece was asked for as a render"


@pytest.mark.e2e
def test_selected_on_a_sites_piece_says_it_is_a_site_and_its_real_size(opened, base_url: str):
    page, _ = opened
    select(page, PIECE)
    piece = next(c for c in _tree(page, base_url)["children"] if c["site_ref"] == "garage")
    real = " × ".join(f"{side:.0f}" for side in piece["site_size"]) + " mm"
    body = page.locator("#selected-body")
    expect(body.locator(".prop-row").first).to_contain_text("garage")
    expect(body.locator("[data-facts='site']")).to_contain_text("A site")
    expect(body.locator("[data-facts='site-size']")).to_have_text(real)
    expect(body.locator("[data-facts='site']")).to_contain_text("in miniature, 1:")
    expect(body.locator(".zoom-in-btn")).to_have_text("⤵ Step into garage")
    # Nothing of it is edited from here: no place to type, no part, no detail, no arrows.
    for absent in ("#pos-x", ".part-editor", "#part-params", ".detail-select", ".device-section"):
        expect(body.locator(absent)).to_have_count(0)
    assert page.evaluate(LEVEL)["arrows"] is None
    # A site smaller than its cell is drawn the size it is, and says so.
    select(page, "site-datum_core")
    expect(body.locator("[data-facts='site']")).to_contain_text("Drawn here the size it is")
    # A part's leaf beside it is a part still: its section, and no word of a site.
    select(page, "calibration_cube")
    expect(body.locator("[data-facts='site']")).to_have_count(0)
    expect(body.locator(".part-editor")).to_be_attached(timeout=20000)


def _by_its_row(page: Page) -> None:
    row(page, PIECE).dblclick()


def _by_the_world(page: Page) -> None:
    # At the opening view the sphere's inner shells and the near side of its outer ones
    # stand between the camera and most pieces: the piece is framed first, as f does.
    select(page, PIECE)
    page.evaluate("() => window.fractalViewer.fitSelected()")
    settled(page)
    on_it = page.evaluate(ON_PIECE, PIECE)
    assert on_it, "the garage's piece is nowhere under the pointer"
    page.mouse.dblclick(on_it["x"], on_it["y"])


def _by_page_down(page: Page) -> None:
    select(page, PIECE)
    page.locator("#viewer-canvas").focus()
    page.keyboard.press("PageDown")


def _by_selected(page: Page) -> None:
    select(page, PIECE)
    page.locator("#selected-body .zoom-in-btn").click()


@pytest.mark.e2e
@pytest.mark.parametrize("step_in", [_by_its_row, _by_the_world, _by_page_down, _by_selected])
def test_a_step_into_a_sites_piece_opens_the_site_and_back_returns(
    page: Page, base_url: str, step_in
):
    _at(page, base_url)
    step_in(page)
    _is_at(page, "garage")
    said(page, "Stepped into the site garage")
    expect(status(page)).to_contain_text("Back returns to Apothecary")
    assert page.evaluate(LEVEL)["focus"] == ""
    expect(row(page, "workbench")).to_be_visible()
    page.go_back()
    _is_at(page, UNIVERSE)
    expect(row(page, PIECE)).to_be_visible()


@pytest.mark.e2e
@pytest.mark.parametrize("key, how", [("PageUp", "Page Up"), ("Backspace", "Backspace")])
def test_a_step_out_of_a_sites_own_level_goes_to_the_universe(
    page: Page, base_url: str, key: str, how: str
):
    _at(page, base_url, "garage")
    page.locator("#viewer-canvas").focus()
    page.keyboard.press(key)
    _is_at(page, UNIVERSE)
    said(page, f"Stepped out of the site garage to Apothecary ({how})")
    # It lands on what was left, as a step out does at any level, and that wears no arrows.
    page.wait_for_function("(p) => window.fractalViewer.selectedName === p", arg=PIECE)
    assert page.evaluate(LEVEL)["arrows"] is None
    page.go_back()
    _is_at(page, "garage")
    # One level in, a step out is the level above, as it was: no other site.
    row(page, "workbench").dblclick()
    said(page, "Stepped into workbench")
    page.locator("#viewer-canvas").focus()
    page.keyboard.press(key)
    said(page, "Stepped out of workbench")
    assert page.evaluate(LEVEL)["site"] == "garage"


@pytest.mark.e2e
def test_the_universe_has_nothing_above_it(opened):
    page, _ = opened
    page.locator("#viewer-canvas").focus()
    page.keyboard.press("PageUp")
    expect(status(page)).to_contain_text("Already at the top of apothecary")
    assert page.evaluate(LEVEL)["site"] == UNIVERSE


@pytest.mark.e2e
def test_a_link_to_a_sites_piece_lands_at_the_universes_own_level(page: Page, base_url: str):
    """A site's piece is no level of the universe: its site is."""
    _at(page, base_url, query=f"?focus={PIECE}")
    level = page.evaluate(LEVEL)
    assert (level["site"], level["focus"]) == (UNIVERSE, "")
    assert len(level["drawn"]) > len(SITES)


@pytest.mark.e2e
def test_a_parts_leaf_stepped_into_is_the_part_alone(page: Page, base_url: str):
    _at(page, base_url)
    row(page, "calibration_cube").dblclick()
    said(page, "Stepped into calibration_cube")
    level = page.evaluate(LEVEL)
    assert list(level["drawn"]) == ["calibration_cube"]
    assert not level["drawn"]["calibration_cube"]["placeholder"]


@pytest.mark.e2e
def test_the_rings_site_lists_apothecary_and_goes_there(page: Page, base_url: str):
    _at(page, base_url, "garage")
    rings.on_world(page, "Site", "Apothecary")
    _is_at(page, UNIVERSE)
    rings.on_world(page, "Site", "garage")
    _is_at(page, "garage")


@pytest.mark.e2e
def test_a_machine_in_a_site_reached_through_the_universe_is_drawn_as_its_part(
    page: Page, base_url: str
):
    _at(page, base_url)
    _by_its_row(page)
    _is_at(page, "garage")
    settled(page)
    body = page.evaluate(LEVEL)["drawn"]["cnc_router"]
    assert not body["placeholder"], "cnc_router is drawn from its part's STL in the garage"
    select(page, "cnc_router")
    page.locator("#selected-body .zoom-in-btn").click()
    said(page, "Stepped into cnc_router")
    inside = page.evaluate(LEVEL)
    assert inside["focus"] == "cnc_router"
    assert inside["drawn"]["cnc_router"] == body, "the whole of the part"
    assert sorted(inside["drawn"]) == [
        "cnc_router",
        "cnc_router.frame_system",
        "cnc_router.gantry_system",
    ], "its pieces inside it, and nothing else of the site"
    # Out again, twice: the garage's own level, then the universe.
    page.locator("#viewer-canvas").focus()
    page.keyboard.press("PageUp")
    said(page, "Stepped out of cnc_router")
    page.keyboard.press("PageUp")
    _is_at(page, UNIVERSE)
