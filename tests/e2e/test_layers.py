"""Layers and depth: how deep a click reaches, and which layers are drawn and which a
click can select (apothecary/static/pick_scope.js, the Layers window beside the world).

In the universe -- a sphere of nested shells, seen from outside -- the shells are sparse,
so the view is turned until a piece of an outer shell stands in front of one of an inner
shell, as a person orbits to line them up; the nearest hit wins, and with the outer
shell not selectable a click on it selects what is behind. A shell hidden is neither drawn
nor hit. Depth 2 lets a click reach a piece of a piece. What was chosen is kept by the
browser over a reload, and Select walls is the wall layer's Selectable tick.
Walkthrough page 40 is what it writes.

Runs against a server of its own, so the site it draws is the code's whatever ran before.
"""

from __future__ import annotations

import re

import pytest
import windows
from doc_capture import moments
from garage import open_garage, row, said
from playwright.sync_api import Page, expect
from viewer_ready import settled

UNIVERSE = "apothecary"
CHANGING = tuple(moments(".panel", "#status"))

# A point of the world, in page pixels, where the nearest mesh a ray from the camera
# meets, whatever the scope says, satisfies ``first``, and a mesh behind it satisfies
# ``behind``: found by casting through a grid of points, as a click there would, where
# nothing stands over the canvas. ``mode`` 'shell': the nearest is on a shell and a mesh
# behind it is on an inner shell; 'wall': the nearest is a wall and another piece is
# behind or inside it.
FIND = """(mode) => {
    const v = window.fractalViewer;
    const rect = v.canvas.getBoundingClientRect();
    const meshes = Object.values(v.meshByName);
    const node = (k) => v.renderNodeByKey[k];
    const shell = (k) => (node(k) && Number.isInteger(node(k).shell) ? node(k).shell : null);
    for (let gy = 0.1; gy < 0.95; gy += 0.02) {
        for (let gx = 0.05; gx < 0.95; gx += 0.02) {
            const x = rect.left + gx * rect.width, y = rect.top + gy * rect.height;
            if (document.elementFromPoint(x, y) !== v.canvas) continue;
            v.pointer.set(gx * 2 - 1, -(gy * 2 - 1));
            v.raycaster.setFromCamera(v.pointer, v.camera);
            const hits = v.raycaster.intersectObjects(meshes, false).map((h) => h.object.userData.key);
            const first = hits[0];
            if (!first) continue;
            if (mode === 'shell' && shell(first) !== null) {
                const behind = hits.find((k) => shell(k) !== null && shell(k) < shell(first));
                if (behind) return { x, y, first, behind, shell: shell(first), inner: shell(behind) };
            }
            if (mode === 'wall' && node(first)?.category === 'wall') {
                const behind = hits.find((k) => k !== first && !k.startsWith(first + '.'));
                if (behind) return { x, y, first, behind };
            }
        }
    }
    return null;
}"""

# The view turned, as a person orbits it, until a piece of one shell stands in front of
# a piece of the shell inside it: the camera on the line from the inner one's middle
# through the outer one's, beyond the outer by half again its size, looking at the
# inner. The two are the largest of the two innermost shells, so a grid of points finds
# the one over the other. At the opening view the shells are too sparse for that.
LINE_UP = """() => {
    const v = window.fractalViewer;
    const on = Object.entries(v.renderNodeByKey)
        .filter(([key, n]) => Number.isInteger(n.shell) && n.world_bounds && v.meshByName[key]);
    const middle = (n) => v.sceneAt(...n.world_bounds.min.map((m, i) => (m + n.world_bounds.max[i]) / 2));
    const across = (n) => Math.hypot(...n.world_bounds.max.map((m, i) => m - n.world_bounds.min[i]));
    const shells = [...new Set(on.map(([, n]) => n.shell))].sort((a, b) => a - b);
    if (shells.length < 2) return null;
    const largest = (s) => on.filter(([, n]) => n.shell === s).sort(([, a], [, b]) => across(b) - across(a))[0];
    const [[innerKey, inner], [outerKey, outer]] = [largest(shells[0]), largest(shells[1])];
    const from = middle(inner), through = middle(outer);
    const ray = through.clone().sub(from).normalize();
    v.orbitControls.target.copy(from);
    v.camera.position.copy(through.clone().addScaledVector(ray, 1.5 * across(outer)));
    v.orbitControls.update();
    v.invalidate();
    return { inner: innerKey, outer: outerKey };
}"""

# What the scope and the drawn world say, at once.
STATE = """() => {
    const v = window.fractalViewer;
    return { scope: v.pickScope.toJSON(), selected: v.selectedName,
             walls: document.getElementById('walls-toggle').checked };
}"""

# A mesh: whether the world draws it, and whether a cast reaches it.
MESH = """(key) => {
    const v = window.fractalViewer, mesh = v.meshByName[key];
    return { drawn: !!mesh && mesh.visible };
}"""

# Whether any ray of a grid over the canvas reaches the piece, as a click would.
REACHED = """(key) => {
    const v = window.fractalViewer, r = v.canvas.getBoundingClientRect();
    for (let i = 1; i < 64; i++) for (let j = 1; j < 64; j++) {
        const at = { clientX: r.left + (r.width * i) / 64, clientY: r.top + (r.height * j) / 64 };
        if (v.raycastHits(at).some((h) => h.object.userData.key === key)) return true;
    }
    return false;
}"""

# A point where a click picks `key`: of those a grid finds, the one nearest their middle.
PICKING = """(key) => {
    const v = window.fractalViewer, r = v.canvas.getBoundingClientRect();
    const over = [];
    for (let i = 1; i < 64; i++) for (let j = 1; j < 64; j++) {
        const at = { clientX: r.left + (r.width * i) / 64, clientY: r.top + (r.height * j) / 64 };
        if (document.elementFromPoint(at.clientX, at.clientY) !== v.canvas) continue;
        const pick = v.raycastPick(at);
        if (pick && pick.key === key) over.push({ x: at.clientX, y: at.clientY });
    }
    if (!over.length) return null;
    const mx = over.reduce((s, p) => s + p.x, 0) / over.length;
    const my = over.reduce((s, p) => s + p.y, 0) / over.length;
    return over.reduce((b, p) => (Math.hypot(p.x - mx, p.y - my) < Math.hypot(b.x - mx, b.y - my) ? p : b));
}"""

# What a click at a point would pick now.
PICK_AT = """([x, y]) => {
    const pick = window.fractalViewer.raycastPick({ clientX: x, clientY: y });
    return pick && pick.key ? pick.key : null;
}"""

# The level's grid: whether it is drawn, whether it is a machine's bed's, and how many
# build-volume boxes are drawn.
GRID = """() => {
    const v = window.fractalViewer;
    return { drawn: v.gridHelper.visible, bed: v.gridHelper.userData.path === v.focusPath.join('.'),
             volumes: Object.values(v.buildVolumeMeshByName).filter((m) => m.visible).length };
}"""

# A piece of the level that holds pieces of its own, and one of those.
NESTED = """() => {
    const v = window.fractalViewer;
    for (const [key, node] of Object.entries(v.renderNodeByKey)) {
        if (key.includes('.') || !node.children.length || !node.world_bounds) continue;
        const inner = node.children.find((c) => c.world_bounds);
        if (inner) return { outer: key, inner: `${key}.${inner.name}` };
    }
    return null;
}"""


@pytest.fixture(scope="module")
def url(start_server):
    return start_server()


def _universe(page: Page, url: str) -> None:
    page.goto(f"{url}/viewer/sites/{UNIVERSE}")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=20000)
    settled(page)


def _lined_up(page: Page) -> dict:
    """The view turned until an outer shell's piece stands in front of an inner one's,
    and drawn so; where a click lands on the one in front, the other behind it."""
    assert page.evaluate(LINE_UP), "the site has fewer than two shells"
    settled(page)
    spot = page.evaluate(FIND, "shell")
    assert spot, "no point of the sphere where an outer shell stands in front of an inner one"
    return spot


def _tick(page: Page, layer: str, kind: str):
    """A layer's Shown or Selectable tick in the Layers window."""
    return page.locator(
        f".panel[data-panel='layers'] input[data-layer='{layer}'][data-kind='{kind}']"
    )


@pytest.mark.e2e
def test_with_the_outer_shell_not_selectable_a_click_on_it_selects_the_piece_behind(
    page: Page, url: str, walkthrough
):
    """A click where an outer shell's piece stands over
    an inner shell's selects the outer one; with the outer shell's Selectable ticked off
    in the Layers window it selects what is behind, the outer shell still drawn."""
    story = walkthrough(
        ordinal="40",
        slug="layers-and-depth",
        title="Layers and depth",
        intro=(
            "A click in the world picks the nearest thing under it; in the universe, a "
            "sphere of shells, where the view lines a piece of an outer shell up in front "
            "of one of an inner shell, that is the outer one. The Layers window, beside "
            "the world, says which layers a click may pick and which "
            "the world draws, and how many levels down a click reaches. "
            "[docs/viewer.md](../docs/viewer.md#layers) is the reference."
        ),
        runtime=(
            "It drives a real browser against a real server of its own, on the universe as "
            "the code has it. What is chosen is kept by the browser, as a person's settings "
            "are; nothing is kept on the server."
        ),
        does_not_show=[
            "**Another browser.** The choice is this browser's own.",
            "**What changes on every run.** Moments are blanked in the pictures.",
        ],
        browser_suite_only=True,
    )
    _universe(page, url)
    windows.from_the_windows_menu(page, "layers")
    spot = _lined_up(page)
    outer = f"shell:{spot['shell']}"

    page.mouse.click(spot["x"], spot["y"])
    assert page.evaluate("() => window.fractalViewer.selectedName") == spot["first"]
    story.shows(
        "A click on the outer shell picks the outer shell's piece",
        "The Layers window beside the world, every layer shown and selectable; the view "
        "turned until an outer shell's piece stands in front of an inner one, a click "
        "there selects the outer one.",
        blank=CHANGING,
    )

    # The outer shell no longer selectable: still drawn, and the click passes through.
    _tick(page, outer, "selectable").uncheck()
    said(page, "a click passes through it")
    assert page.evaluate(MESH, spot["first"])["drawn"] is True
    assert page.evaluate(PICK_AT, [spot["x"], spot["y"]]) not in (None, spot["first"])
    page.mouse.click(spot["x"], spot["y"])
    picked = page.evaluate("() => window.fractalViewer.selectedName")
    assert picked != spot["first"]
    assert picked is not None
    shell = page.evaluate("(k) => window.fractalViewer.renderNodeByKey[k].shell", picked)
    assert shell != spot["shell"], (picked, shell)
    expect(_tick(page, outer, "shown")).to_be_checked()
    story.shows(
        "With the outer shell not selectable, the click selects what is behind",
        "The outer shell's Selectable ticked off, its Shown still on: the shell is drawn "
        "as it was, and the same click selects the piece behind it.",
        blank=CHANGING,
    )


@pytest.mark.e2e
def test_a_hidden_shell_is_not_drawn_and_not_hit_and_the_choice_survives_a_reload(
    page: Page, url: str
):
    """Shown ticked off on a shell: its meshes are not drawn and no ray reaches
    them; Selectable goes with it, and comes back with Shown ticked on again. The scope
    is the browser's own: after a reload the tick is still off."""
    _universe(page, url)
    windows.from_the_windows_menu(page, "layers")
    spot = _lined_up(page)
    outer = f"shell:{spot['shell']}"
    assert page.evaluate(REACHED, spot["first"]) is True

    _tick(page, outer, "shown").uncheck()
    said(page, "hidden")
    expect(_tick(page, outer, "selectable")).not_to_be_checked()
    assert page.evaluate(MESH, spot["first"])["drawn"] is False
    assert page.evaluate(REACHED, spot["first"]) is False
    settled(page)

    page.reload()
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=20000)
    settled(page)
    assert outer in page.evaluate(STATE)["scope"]["hidden"]
    assert page.evaluate(MESH, spot["first"])["drawn"] is False
    windows.from_the_windows_menu(page, "layers")
    expect(_tick(page, outer, "shown")).not_to_be_checked()
    expect(_tick(page, outer, "selectable")).not_to_be_checked()

    _tick(page, outer, "shown").check()
    assert page.evaluate(MESH, spot["first"])["drawn"] is True
    expect(_tick(page, outer, "selectable")).to_be_checked()

    # A mesh whose node the level no longer holds, a stale one, is drawn and never
    # picked: what the scope cannot place is not picked past it.
    assert page.evaluate(REACHED, spot["first"]) is True
    page.evaluate("(k) => { delete window.fractalViewer.renderNodeByKey[k]; }", spot["first"])
    assert page.evaluate(MESH, spot["first"])["drawn"] is True
    assert page.evaluate(REACHED, spot["first"]) is False


@pytest.mark.e2e
def test_a_shell_s_row_says_what_the_sphere_calls_it(page: Page, url: str):
    """Layers' row for a shell is worded as the world's label on that shell is
    (orbits.js shellLabel): one name for one shell."""
    _universe(page, url)
    windows.from_the_windows_menu(page, "layers")
    rows = page.locator(".layers-table tr[data-row^='shell:'] > th")
    expect(rows.first).to_be_visible(timeout=10000)
    said = rows.all_inner_texts()
    shells = page.locator(".layers-table tr[data-row^='shell:']").evaluate_all(
        "(trs) => trs.map((tr) => Number(tr.dataset.row.slice('shell:'.length)))"
    )
    sphere = page.evaluate(
        """async (shells) => {
            const { shellLabel } = await import('/static/orbits.js');
            const v = window.fractalViewer;
            return shells.map((n) => shellLabel(n, v.sphereNodes()));
        }""",
        shells,
    )
    assert said == sphere and said[0] == "Shell 0 · built from nothing", (said, sphere)


@pytest.mark.e2e
def test_depth_two_lets_a_click_select_a_piece_of_a_piece(page: Page, url: str):
    """At depth 1 a piece that holds pieces is drawn as one; at depth 2 its own
    pieces are drawn inside it and a click on one selects it, from the Layers window's
    stepper and from the ring's View › Depth."""
    open_garage(page, url)
    nested = page.evaluate(NESTED)
    assert nested, "no piece of the level holds pieces of its own"
    assert page.evaluate("(k) => !!window.fractalViewer.meshByName[k]", nested["inner"]) is False

    windows.from_the_windows_menu(page, "layers")
    less = page.locator(".panel[data-panel='layers'] button[data-act='depth-less']")
    more = page.locator(".panel[data-panel='layers'] button[data-act='depth-more']")
    # At depth 1 the stepper's − is greyed as every control of the page is, saying why;
    # the window's buttons wear the page's controls, not the browser's own.
    expect(less).to_be_disabled()
    expect(less).to_have_attribute("aria-disabled", "true")
    expect(less).to_have_attribute("title", re.compile(r"^Disabled: the depth is 1, .*One level less"))
    expect(less).to_have_css("opacity", "0.45")
    for button in (more, page.locator(".panel[data-panel='layers'] button[data-act='reset']")):
        expect(button).to_have_css("background-color", "rgb(35, 40, 35)")
        expect(button).to_have_css("border-radius", "4px")
        expect(button).to_have_css("cursor", "pointer")
    more.click()
    said(page, "Depth: 2 levels")
    expect(less).to_be_enabled()
    expect(less).not_to_have_attribute("aria-disabled", "true")
    expect(less).to_have_attribute("title", re.compile(r"^One level less"))
    settled(page)
    assert page.evaluate("(k) => !!window.fractalViewer.meshByName[k]", nested["inner"]) is True
    spot = page.evaluate(PICKING, nested["inner"])
    assert spot, "no point of the canvas where a click picks the inner piece"
    page.mouse.click(spot["x"], spot["y"])
    assert page.evaluate("() => window.fractalViewer.selectedName") == nested["inner"]

    # Back to one level: the inner piece is gone from the world, and the choice is kept.
    page.locator(".panel[data-panel='layers'] button[data-act='depth-less']").click()
    said(page, "Depth: 1 level")
    settled(page)
    assert page.evaluate("(k) => !!window.fractalViewer.meshByName[k]", nested["inner"]) is False
    assert page.evaluate(STATE)["scope"]["depth"] == 1


@pytest.mark.e2e
def test_select_walls_is_the_wall_layers_selectable_tick_and_a_click_still_passes_a_wall(
    page: Page, url: str
):
    """A click passes through the garage's faded walls to what is behind; the
    View menu's Select walls and the Layers window's wall row are one tick, and ticked,
    a click picks the wall. The wall tick is the session's: a reload puts it back."""
    open_garage(page, url)
    windows.from_the_windows_menu(page, "layers")
    settled(page)
    spot = page.evaluate(FIND, "wall")
    assert spot, "no point of the world where a wall stands in front of a piece"
    wall = "category:wall"
    expect(_tick(page, wall, "selectable")).not_to_be_checked()
    page.mouse.click(spot["x"], spot["y"])
    assert page.evaluate("() => window.fractalViewer.selectedName") == spot["behind"]

    _tick(page, wall, "selectable").check()
    said(page, "Select walls: on")
    assert page.evaluate(STATE)["walls"] is True
    page.mouse.click(spot["x"], spot["y"])
    assert page.evaluate("() => window.fractalViewer.selectedName") == spot["first"]

    # The View menu's tick unticks the layer's.
    page.locator("#view-menu > summary").click()
    page.locator("#walls-toggle").uncheck()
    said(page, "Select walls: off")
    expect(_tick(page, wall, "selectable")).not_to_be_checked()

    _tick(page, wall, "selectable").check()
    page.reload()
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=20000)
    settled(page)
    assert page.evaluate(STATE)["walls"] is False


@pytest.mark.e2e
def test_the_alignment_grid_hidden_is_no_grid_on_a_machines_bed_either(page: Page, url: str):
    """The Alignment grid's Shown ticked off: the floor grid and the build volumes are not
    drawn, and a machine stepped into lays its bed's grid by the same tick, so none is
    drawn there either until the tick is on again."""
    open_garage(page, url)
    windows.from_the_windows_menu(page, "layers")
    assert page.evaluate(GRID)["drawn"] is True
    _tick(page, "grid", "shown").uncheck()
    said(page, "Alignment grid: hidden")
    seen = page.evaluate(GRID)
    assert seen["drawn"] is False and seen["volumes"] == 0, seen

    row(page, "printer_1").dblclick()
    said(page, "Stepped into printer_1")
    settled(page)
    seen = page.evaluate(GRID)
    assert seen["bed"] is True, seen
    assert seen["drawn"] is False, f"the bed's grid is drawn with the grid layer hidden: {seen}"

    _tick(page, "grid", "shown").check()
    seen = page.evaluate(GRID)
    assert seen["bed"] is True and seen["drawn"] is True, seen
