"""The measurement layer (apothecary/static/measure.js, the Layers window's Measure row):
off, the page is as it was; shown, the selection reads its size with where the number
comes from, a click in the world drops a point and selects nothing, two points read a
distance, two pieces a gap, and Escape starts again. A click also reads the shape under
it from the mesh drawn (measure_features.js): inside a dust port's bore a hole's diameter,
beside the socket the part declares there; on a plate's top the wall behind it; on a
steep cone that it cannot tell, and why. A measurement is a reading of the model and of
the mesh drawn, not of a made part. Walkthrough page 42 is what it writes.

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
# A dust port: a 32 mm bore its part.json declares as a socket, port. A plate 10 mm thick.
# A hose adapter, its flare a cone at 45 degrees.
PORT = "dust_port_32"
PLATE = "router_coupon"
CONE = "hose_adapter"
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

# A point where a click lands on `key`'s mesh on a face of the kind asked, of those a grid
# finds the one nearest their middle. In the mesh's own frame, its axis upright: 'bore' a
# face standing upright and facing the middle (inside a hole), 'top' a face looking straight
# up at the mesh's top, 'cone' a face leaning 37 to 53 degrees from upright.
FACE = """([key, want]) => {
    const v = window.fractalViewer, r = v.canvas.getBoundingClientRect(), mesh = v.meshByName[key];
    if (!mesh.geometry.boundingBox) mesh.geometry.computeBoundingBox();
    const top = mesh.geometry.boundingBox.max.y;
    const over = [];
    for (let i = 1; i < 64; i++) for (let j = 1; j < 64; j++) {
        const at = { clientX: r.left + (r.width * i) / 64, clientY: r.top + (r.height * j) / 64 };
        if (document.elementFromPoint(at.clientX, at.clientY) !== v.canvas) continue;
        const hit = v.raycastHits(at).find((h) => v.renderNodeByKey[h.object.userData.key]);
        if (!hit || hit.object.userData.key !== key || !hit.face) continue;
        const p = hit.object.worldToLocal(hit.point.clone()), n = hit.face.normal;
        const ok = want === 'bore' ? Math.abs(n.y) < 0.05 && n.x * p.x + n.z * p.z < 0
            : want === 'top' ? n.y > 0.999 && Math.abs(p.y - top) < 1e-3
            : want === 'cone' ? Math.abs(n.y) > 0.6 && Math.abs(n.y) < 0.8 : false;
        if (ok) over.push({ x: at.clientX, y: at.clientY });
    }
    if (!over.length) return null;
    const mx = over.reduce((s, p) => s + p.x, 0) / over.length, my = over.reduce((s, p) => s + p.y, 0) / over.length;
    return over.reduce((b, p) => (Math.hypot(p.x - mx, p.y - my) < Math.hypot(b.x - mx, b.y - my) ? p : b));
}"""


def _into(page: Page, key: str) -> None:
    """Up to the universe's own level, if not there, and into ``key``, framed and at rest."""
    page.evaluate("() => { const v = window.fractalViewer; if (v.focusPath.length) v.goUpTo(0, 'test'); }")
    page.wait_for_function("() => window.fractalViewer.focusPath.length === 0")
    settled(page)
    page.evaluate("(k) => window.fractalViewer.stepIn(k, 'test')", key)
    page.wait_for_function("(k) => window.fractalViewer.focusPath.join('.') === k", arg=key)
    settled(page)
    page.wait_for_function(
        "(k) => { const m = window.fractalViewer.meshByName[k]; return !!m && !m.userData.isPlaceholder; }",
        arg=key,
        timeout=60000,
    )
    settled(page)


def _click_on(page: Page, key: str, want: str) -> None:
    spot = page.evaluate(FACE, [key, want])
    assert spot, f"no point of the world where a click lands on {key}'s {want}"
    page.mouse.click(spot["x"], spot["y"])


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
            "the world drops a point to measure between rather than selecting, and reads the "
            "shape under it from the mesh drawn: a curved face a diameter, a flat face a wall. "
            "A reading is of the model and of the mesh drawn, not of a made part. "
            "[docs/viewer.md](../docs/viewer.md#layers) is the reference."
        ),
        runtime=(
            "It drives a real browser against a real server of its own, on the universe as "
            "the code has it. A measurement is kept nowhere: Measure is off after a reload."
        ),
        does_not_show=[
            "**A made part.** A reading is of the model's declared bounds and of the mesh "
            "drawn; a printed part differs by what the printer does, and a printed hole is "
            "smaller than its mesh's.",
            "**What it cannot tell.** A steep cone, a sphere drawn as triangles, a face too "
            "small for the pointer: the reading says why and gives no number "
            "(`test_a_face_that_cannot_decide_says_why_and_gives_no_number`).",
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

    # Inside a dust port's bore: a hole's diameter, beside the socket its part declares.
    _into(page, PORT)
    before = page.evaluate(STATE)["selected"]
    _click_on(page, PORT, "bore")
    reading = page.locator(".panel[data-panel='layers'] .layers-reading")
    expect(reading).to_contain_text(f"point 1 on {PORT}: a hole ⌀ 32.00 mm across its vertices")
    expect(reading).to_contain_text(
        f"point 1 on {PORT}, declared: port, a socket ⌀ 32.00 mm (its bore at the mouth; "
        "the part's interface, source stub); the mesh reads ⌀ 32.00 mm there, the same"
    )
    said(
        page,
        f"Measure: point 1 on {PORT}: a hole ⌀ 32.00 mm across its vertices; a flat face reads its "
        "wall, a second click the distance",
    )
    state = page.evaluate(STATE)
    assert state["selected"] == before, "a click while measuring selected something"
    assert state["points"][0]["key"] == PORT
    # The reading in view, under the Layers window's rows, as the caption reads it.
    reading.scroll_into_view_if_needed()
    settled(page)
    story.shows(
        "A click inside a bore reads its diameter, beside the declared socket",
        "The dust port stepped into and framed, a click on the far side of its bore: the "
        "circle fitted to the bore's facets, drawn round its axis at the click with the line "
        "across it, labelled. The reading under the Layers window's rows says it is a hole, "
        "what it was fitted to and how well, and the socket the part declares on the same "
        "axis, with how far apart the two are; the status line says it in a line, and how to "
        "read the others.",
        blank=CHANGING,
    )

    # On a plate's top: the wall behind it, cast through to the face beneath.
    page.keyboard.press("Escape")
    _into(page, PLATE)
    before = page.evaluate(STATE)["selected"]
    _click_on(page, PLATE, "top")
    expect(reading).to_contain_text(
        f"point 1 on {PLATE}: a flat face, its wall 10.00 mm thick (cast from the click along "
        "the face's inward normal to the face behind it, parallel to it; the drawn mesh)"
    )
    said(page, f"Measure: point 1 on {PLATE}: a wall 10.00 mm thick; a curved face reads its diameter")
    assert page.evaluate(STATE)["selected"] == before
    reading.scroll_into_view_if_needed()
    settled(page)
    story.shows(
        "A click on a flat face reads the wall behind it",
        "The router coupon, a plate, stepped into and framed, a click on its top: the line "
        "from the click through the plate to the face beneath, labelled with the wall's "
        "thickness; the reading under the Layers window's rows says the two faces are parallel.",
        blank=CHANGING,
    )


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


@pytest.mark.e2e
def test_a_face_that_cannot_decide_says_why_and_gives_no_number(page: Page, url: str):
    """A click on the hose adapter's flare, a cone at 45 degrees: too few of its faces turn
    about one axis to fit a round, and it is not flat, so the reading says it cannot tell,
    and why, with no diameter and no wall; the click selects nothing."""
    _measuring(page, url)
    _into(page, CONE)
    before = page.evaluate(STATE)["selected"]
    _click_on(page, CONE, "cone")
    expect(page.locator(".panel[data-panel='layers'] .layers-reading")).to_contain_text(
        f"point 1 on {CONE}: cannot tell a diameter or a wall here: the faces around the click "
        "turn about no one axis"
    )
    line = next(text for text in _reading(page).splitlines() if text.startswith(f"point 1 on {CONE}:"))
    assert "⌀" not in line and "thick" not in line, line
    said(page, f"Measure: point 1 on {CONE}: cannot tell; a curved face reads a diameter, a flat face a wall")
    assert page.evaluate(STATE)["selected"] == before
