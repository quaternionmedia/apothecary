"""The measurement layer (apothecary/static/measure.js, the Layers window's Measure row):
off, the page is as it was; shown, the selection reads its size with where the number
comes from, a click in the world drops a point and selects nothing, two points read a
distance, two pieces a gap, and Escape starts again. A measurement is a reading of the
model and of the mesh drawn, not of a made part. Walkthrough page 42 is what it writes.

Runs against a server of its own, so the site it draws is the code's whatever ran before.
"""

from __future__ import annotations

import math
import re

import pytest
import windows
from doc_capture import moments
from garage import open_garage, row, said
from playwright.sync_api import Page, expect
from viewer_ready import settled

UNIVERSE = "apothecary"
PART = "calibration_cube"
CHANGING = tuple(moments(".panel", "#status"))

# What the page holds of the measurement, and of the selection.
STATE = """() => {
    const v = window.fractalViewer;
    return { selected: v.selectedName, drawn: !!v.measure.group,
             points: v.measure.points.map((p) => ({ site: p.site, kind: p.kind, key: p.key })),
             lines: v.measure.lines, on: v.measureOn() };
}"""

# Two corners of the part's mesh, both at the end of an edge of its box, the nearest
# corner to the camera and the neighbour farthest from it on screen, as page pixels.
CORNERS = """(key) => {
    const v = window.fractalViewer, mesh = v.meshByName[key], r = v.canvas.getBoundingClientRect();
    mesh.updateWorldMatrix(true, false);
    if (!mesh.geometry.boundingBox) mesh.geometry.computeBoundingBox();
    const b = mesh.geometry.boundingBox;
    const corner = (i, j, k) => new v.camera.position.constructor(
        i ? b.max.x : b.min.x, j ? b.max.y : b.min.y, k ? b.max.z : b.min.z).applyMatrix4(mesh.matrixWorld);
    const screen = (p) => { const s = p.clone().project(v.camera);
        return { x: r.left + ((s.x + 1) / 2) * r.width, y: r.top + ((1 - s.y) / 2) * r.height }; };
    const all = [];
    for (let i = 0; i < 2; i++) for (let j = 0; j < 2; j++) for (let k = 0; k < 2; k++) all.push({ ijk: [i, j, k], p: corner(i, j, k) });
    all.sort((a, b2) => a.p.distanceTo(v.camera.position) - b2.p.distanceTo(v.camera.position));
    const first = all[0], at = screen(first.p);
    const neighbours = all.filter((c) => c.ijk.filter((n, m) => n !== first.ijk[m]).length === 1)
        .map((c) => ({ ...screen(c.p), c })).sort((a, b2) => Math.hypot(b2.x - at.x, b2.y - at.y) - Math.hypot(a.x - at.x, a.y - at.y));
    return { a: at, b: { x: neighbours[0].x, y: neighbours[0].y } };
}"""

# A point where a click picks `key`.
PICKING = """(key) => {
    const v = window.fractalViewer, r = v.canvas.getBoundingClientRect();
    const over = [];
    for (let i = 1; i < 64; i++) for (let j = 1; j < 64; j++) {
        const at = { clientX: r.left + (r.width * i) / 64, clientY: r.top + (r.height * j) / 64 };
        if (document.elementFromPoint(at.clientX, at.clientY) !== v.canvas) continue;
        const hit = v.raycastHits(at).find((h) => v.renderNodeByKey[h.object.userData.key]);
        if (hit && hit.object.userData.key === key) over.push({ x: at.clientX, y: at.clientY });
    }
    if (!over.length) return null;
    const mx = over.reduce((s, p) => s + p.x, 0) / over.length, my = over.reduce((s, p) => s + p.y, 0) / over.length;
    return over.reduce((b, p) => (Math.hypot(p.x - mx, p.y - my) < Math.hypot(b.x - mx, b.y - my) ? p : b));
}"""

SOURCES = r"\((declared footprint|envelope of its pieces|the drawn mesh, as loaded|a stand-in box, no size declared)\)"


@pytest.fixture(scope="module")
def url(start_server):
    return start_server()


def _tick(page: Page, layer: str, kind: str):
    return page.locator(
        f".panel[data-panel='layers'] input[data-layer='{layer}'][data-kind='{kind}']"
    )


def _measuring(page: Page, url: str, site: str = UNIVERSE) -> None:
    """The site, the Layers window open, Measure ticked."""
    page.goto(f"{url}/viewer/sites/{site}")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=20000)
    settled(page)
    windows.from_the_windows_menu(page, "layers")
    _tick(page, "measure", "shown").check()
    said(page, "Measure: on")


def _reading(page: Page) -> str:
    """What the Layers window reads; empty where it reads nothing, as it then draws no
    reading at all (nothing selected, no point dropped)."""
    return "\n".join(page.locator(".panel[data-panel='layers'] .layers-reading").all_inner_texts())


@pytest.mark.e2e
def test_the_layer_off_changes_nothing_and_a_click_selects(page: Page, url: str):
    """Measure is off at first: a click selects as it did, nothing is drawn for a
    measurement, the Layers window has no reading, and a reload finds it off."""
    open_garage(page, url)
    windows.from_the_windows_menu(page, "layers")
    expect(_tick(page, "measure", "shown")).not_to_be_checked()
    state = page.evaluate(STATE)
    assert state["on"] is False and state["drawn"] is False and state["lines"] == []
    spot = page.evaluate(PICKING, "workbench")
    assert spot, "no point of the world where a click picks the workbench"
    page.mouse.click(spot["x"], spot["y"])
    assert page.evaluate(STATE)["selected"] == "workbench"
    assert page.locator(".panel[data-panel='layers'] .layers-reading").count() == 0
    _tick(page, "measure", "shown").check()
    page.reload()
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=20000)
    assert page.evaluate(STATE)["on"] is False


@pytest.mark.e2e
def test_the_selection_reads_its_size_and_where_it_comes_from(page: Page, url: str, walkthrough):
    """A selected calibration cube reads its size along its own axes, each number saying
    its source; two clicks on its corners read a distance and the components, and Escape
    starts again, and no click while measuring selects."""
    story = walkthrough(
        ordinal="42",
        slug="measuring-in-the-world",
        title="Measuring in the world",
        intro=(
            "The Measure layer, ticked in the Layers window, makes the selection read its "
            "size along its own axes, each number with where it comes from, and a click in "
            "the world drops a point to measure between rather than selecting. A reading is "
            "of the model and of the mesh drawn, not of a made part. "
            "[docs/viewer.md](../docs/viewer.md#layers) is the reference."
        ),
        runtime=(
            "It drives a real browser against a real server of its own, on the universe as "
            "the code has it. A measurement is kept nowhere: Measure is off after a reload."
        ),
        does_not_show=[
            "**A made part.** A reading is of the model's declared bounds and of the mesh "
            "drawn; a printed part differs by what the printer does.",
            "**What changes on every run.** Moments are blanked in the pictures.",
        ],
        browser_suite_only=True,
    )
    _measuring(page, url)
    row(page, PART).click()
    page.wait_for_function("(p) => window.fractalViewer.selectedName === p", arg=PART)
    expect(page.locator(".panel[data-panel='layers'] .layers-reading")).to_contain_text(
        f"{PART} measures x 10.00 mm"
    )
    text = _reading(page)
    assert re.search(r"along its own axes " + SOURCES, text), text
    # Framed, as `f` frames the selection, so its three dimension lines stand apart.
    page.locator("#viewer-canvas").focus()
    page.keyboard.press("f")
    settled(page)
    story.shows(
        "The selection reads its size, with its source",
        "Measure ticked, the calibration cube selected from Site's rows and framed with `f`: "
        "a dimension line along each of its own axes, each length labelled with where it "
        "comes from, and the same words as text under the Layers window's rows.",
        blank=CHANGING,
    )

    # Stepped in and framed, two corners of the cube clicked: a distance and its parts.
    page.evaluate("(k) => window.fractalViewer.stepIn(k, 'test')", PART)
    page.wait_for_function("(k) => window.fractalViewer.focusPath.join('.') === k", arg=PART)
    settled(page)
    before = page.evaluate(STATE)["selected"]
    corners = page.evaluate(CORNERS, PART)
    page.mouse.click(corners["a"]["x"], corners["a"]["y"])
    page.mouse.click(corners["b"]["x"], corners["b"]["y"])
    state = page.evaluate(STATE)
    assert state["selected"] == before, "a click while measuring selected something"
    assert len(state["points"]) == 2
    (a, b) = state["points"]
    expected = math.dist(a["site"], b["site"])
    text = _reading(page)
    assert f"{expected:.2f} mm between point 1 ({a['kind']})" in text, text
    for axis, i in (("dx", 0), ("dy", 1), ("dz", 2)):
        assert f"{axis} {b['site'][i] - a['site'][i]:.2f} mm" in text, (axis, text)
    story.shows(
        "Two clicks read the distance between the points",
        "Two corners of the cube clicked, each snapped to a vertex where one is near: the line "
        "between them, its straight length, and dx, dy and dz in the site's millimetres, "
        "each point saying whether it is a vertex or the surface.",
        blank=CHANGING,
    )

    # A third click starts again; Escape lets go.
    page.mouse.click(corners["a"]["x"], corners["a"]["y"])
    assert len(page.evaluate(STATE)["points"]) == 1
    page.keyboard.press("Escape")
    assert page.evaluate(STATE)["points"] == []
    assert page.evaluate(STATE)["selected"] == before
    assert "between point" not in _reading(page)


@pytest.mark.e2e
def test_two_pieces_read_the_gap_between_their_bounds(page: Page, url: str):
    """A click on the workbench and a click on the printer: the reading also gives the clear
    distance between their declared bounds, or says they touch or overlap."""
    _measuring(page, url, "garage")
    spots = {key: page.evaluate(PICKING, key) for key in ("workbench", "printer_1")}
    assert all(spots.values()), spots
    page.mouse.click(spots["workbench"]["x"], spots["workbench"]["y"])
    page.mouse.click(spots["printer_1"]["x"], spots["printer_1"]["y"])
    text = _reading(page)
    assert re.search(
        r"gap between workbench and printer_1: (\d+\.\d\d mm|overlap|touching)", text
    ), text
    assert page.evaluate(STATE)["selected"] is None
