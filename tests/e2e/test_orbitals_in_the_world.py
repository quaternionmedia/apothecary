"""The universe's orbitals in the world (apothecary/static/orbits.js, docs/viewer.md's
"Apothecary is the universe" and "Layers"): each shell's rings drawn in its layer's
colour and never picked as a piece, an outline round each category's cluster on its
shell, a line from a part to each part it is built from, a drawn ring that opens its
layer's ring where it is clicked, and the ring's cells, the Layers window's ticks and the
world reading one choice whichever of the three is used.

Runs against a server of its own, so the universe it draws is the code's.
"""

from __future__ import annotations

import httpx
import pytest
import rings
import windows
from garage import said
from playwright.sync_api import Page, expect
from viewer_ready import settled

UNIVERSE = "apothecary"

# What the world draws of the orbitals: each loop's layer, the layers it is drawn for,
# whether it is drawn and in what colour, and whether it is a piece; each link's ends and
# whether it is drawn.
ORBITS = """() => {
    const v = window.fractalViewer, o = v.orbits;
    if (!o) return null;
    const pieces = new Set(Object.values(v.meshByName));
    return {
        loops: o.loops.map((l) => ({ layer: l.layer, layers: l.layers, drawn: l.object.visible,
            colour: '#' + l.object.material.color.getHexString(), piece: pieces.has(l.object) })),
        links: o.links.map((l) => ({ from: l.from, to: l.to, drawn: l.object.visible })),
    };
}"""

# A point of the canvas, on the page, on a drawn loop of `layer` where no piece is under
# it and a click finds that loop and no other: the loop's own points, projected, walked
# until one is clear.
ON_A_LOOP = """(layer) => {
    const v = window.fractalViewer, r = v.canvas.getBoundingClientRect();
    for (const loop of v.orbits.loops.filter((l) => l.layer === layer && l.object.visible)) {
        for (const p of loop.points) {
            const s = v.sceneAt(...p).project(v.camera);
            if (s.z > 1 || s.z < -1) continue;
            const at = { clientX: r.left + (s.x + 1) / 2 * r.width, clientY: r.top + (1 - s.y) / 2 * r.height };
            if (at.clientX < r.left + 30 || at.clientX > r.right - 30 || at.clientY < r.top + 30 || at.clientY > r.bottom - 30) continue;
            if (document.elementFromPoint(at.clientX, at.clientY) !== v.canvas) continue;
            if (v.raycastHits(at).length) continue;
            if (v.orbitAt(at) !== layer) continue;
            return { x: at.clientX, y: at.clientY };
        }
    }
    return null;
}"""

# What a ray through a point meets, as a click asks: nothing that is not a piece or a mark.
HITS = """([x, y]) => window.fractalViewer.raycastHits({ clientX: x, clientY: y })
    .map((h) => h.object.userData.key || null)"""

# The one choice, as the pick scope holds it.
SCOPE = "() => window.fractalViewer.pickScope.toJSON()"

# Whether the world draws every piece on a shell, and every loop drawn for it.
SHELL_DRAWN = """(shell) => {
    const v = window.fractalViewer;
    const keys = Object.keys(v.renderNodeByKey).filter((k) => v.renderNodeByKey[k].shell === shell && v.meshByName[k]);
    const loops = v.orbits.loops.filter((l) => l.layers.includes(`shell:${shell}`));
    return { pieces: keys.map((k) => v.meshByName[k].visible), loops: loops.map((l) => l.object.visible) };
}"""


@pytest.fixture(scope="module")
def url(start_server):
    return start_server()


def _universe(page: Page, url: str) -> None:
    page.goto(f"{url}/viewer/sites/{UNIVERSE}")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=20000)
    page.wait_for_function("() => !!window.fractalViewer.orbits", timeout=20000)
    settled(page)


def _tick(page: Page, layer: str, kind: str):
    return page.locator(
        f".panel[data-panel='layers'] input[data-layer='{layer}'][data-kind='{kind}']"
    )


@pytest.mark.e2e
def test_each_shell_is_drawn_as_rings_in_its_colour_and_a_click_passes_through_them(
    page: Page, url: str
):
    """Three rings for each shell, in the shell's colour from the table the site is sent
    with; none is a piece, and a ray through a ring meets no ring."""
    colours = httpx.get(f"{url}/sites/{UNIVERSE}").json()["layer_colours"]
    _universe(page, url)
    drawn = page.evaluate(ORBITS)
    shells = sorted({int(k.split(":")[1]) for k in colours if k.startswith("shell:")})
    assert len(shells) >= 3
    for n in shells:
        rings_of = [loop for loop in drawn["loops"] if loop["layers"] == [f"shell:{n}"]]
        assert len(rings_of) == 3, n
        assert all(loop["drawn"] and loop["colour"] == colours[f"shell:{n}"] for loop in rings_of)
    assert not any(loop["piece"] for loop in drawn["loops"])
    spot = page.evaluate(ON_A_LOOP, f"shell:{shells[-1]}")
    assert spot, "no point of the canvas on the outermost shell's ring clear of every piece"
    assert page.evaluate(HITS, [spot["x"], spot["y"]]) == []
    assert (
        page.evaluate(
            "(a) => window.fractalViewer.raycastPick(a)",
            {"clientX": spot["x"], "clientY": spot["y"]},
        )
        is None
    )


@pytest.mark.e2e
def test_a_categorys_cluster_is_outlined_on_its_shell_and_hidden_with_its_layer(
    page: Page, url: str
):
    """The two machines on the shell they share are outlined in the machine category's
    colour; the category's Shown ticked off hides the outline and the machines both."""
    colours = httpx.get(f"{url}/sites/{UNIVERSE}").json()["layer_colours"]
    _universe(page, url)
    windows.from_the_windows_menu(page, "layers")
    outline = [
        loop for loop in page.evaluate(ORBITS)["loops"] if loop["layer"] == "category:machine"
    ]
    assert len(outline) == 1
    (machine,) = outline
    assert machine["drawn"] and machine["colour"] == colours["category:machine"]
    assert machine["layers"][0].startswith("shell:")
    swatch = page.locator(
        ".panel[data-panel='layers'] tr[data-row='category:machine'] .layers-swatch"
    )
    expect(swatch).to_have_css("background-color", _rgb(colours["category:machine"]))

    _tick(page, "category:machine", "shown").uncheck()
    said(page, "machine: hidden")
    outline = [o for o in page.evaluate(ORBITS)["loops"] if o["layer"] == "category:machine"]
    assert outline[0]["drawn"] is False
    hidden = page.evaluate(
        """() => { const v = window.fractalViewer;
            return ['ender3', 'anolex_4060_evo_ultra_2'].map((k) => v.meshByName[k].visible); }"""
    )
    assert hidden == [False, False]


@pytest.mark.e2e
def test_a_part_is_joined_by_a_line_to_what_it_is_built_from_while_both_are_drawn(
    page: Page, url: str
):
    _universe(page, url)
    windows.from_the_windows_menu(page, "layers")
    links = {(k["from"], k["to"]): k["drawn"] for k in page.evaluate(ORBITS)["links"]}
    assert links[("ender3", "creality_v422")] is True
    assert links[("webcam_desk_stand", "webcam")] is True
    _tick(page, "shell:0", "shown").uncheck()
    said(page, "Shell 0: hidden")
    links = {(k["from"], k["to"]): k["drawn"] for k in page.evaluate(ORBITS)["links"]}
    assert links[("ender3", "creality_v422")] is False
    _tick(page, "shell:0", "shown").check()
    links = {(k["from"], k["to"]): k["drawn"] for k in page.evaluate(ORBITS)["links"]}
    assert links[("ender3", "creality_v422")] is True


@pytest.mark.e2e
def test_a_click_on_a_shells_ring_opens_that_shells_ring_and_only_this_hides_the_rest(
    page: Page, url: str
):
    """A still click on a drawn ring, where no piece is under it, opens the ring of that
    shell's acts at View › Layers › Shells › its shell, in its colour, and selects
    nothing; its Only this leaves that shell alone drawn, the window's ticks with it."""
    _universe(page, url)
    windows.from_the_windows_menu(page, "layers")
    outer = max(
        int(o["layer"].split(":")[1])
        for o in page.evaluate(ORBITS)["loops"]
        if o["layer"].startswith("shell:")
    )
    spot = page.evaluate(ON_A_LOOP, f"shell:{outer}")
    assert spot, "no point of the canvas on the outermost shell's ring clear of every piece"
    page.mouse.click(spot["x"], spot["y"])
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=rings.RING_MS)
    assert rings.labels(page) == ["Shown", "Selectable", "Only this", "All"]
    expect(page.locator("#ring-overlay .title")).to_have_text(f"Shell {outer}")
    expect(page.locator("#ring-overlay .address")).to_have_text(f"⌗214{'8624'[outer]}")
    assert page.evaluate("() => window.fractalViewer.selectedName") is None
    colour = page.evaluate(
        "() => document.querySelector('#ring-overlay .wedge[data-colour]').dataset.colour"
    )
    assert colour == httpx.get(f"{url}/sites/{UNIVERSE}").json()["layer_colours"][f"shell:{outer}"]

    rings.press(page, "Only this")
    said(page, f"Shell {outer} alone of its kind shown")
    hidden = page.evaluate(SCOPE)["hidden"]
    assert sorted(hidden) == sorted(f"shell:{n}" for n in range(outer))
    for n in range(outer):
        expect(_tick(page, f"shell:{n}", "shown")).not_to_be_checked()
        seen = page.evaluate(SHELL_DRAWN, n)
        assert not any(seen["pieces"]) and not any(seen["loops"]), (n, seen)
    expect(_tick(page, f"shell:{outer}", "shown")).to_be_checked()


@pytest.mark.e2e
def test_the_rings_cell_the_windows_tick_and_the_world_read_one_choice(page: Page, url: str):
    """Shell 1 hidden from its ring's cell, shown again from the window's tick, made
    unselectable from the ring opened on its drawn ring in the world: after each, the
    scope, the tick and the world say the same."""
    _universe(page, url)
    windows.from_the_windows_menu(page, "layers")

    def agree(shown: bool, selectable: bool) -> None:
        scope = page.evaluate(SCOPE)
        assert ("shell:1" not in scope["hidden"]) is shown
        assert ("shell:1" not in scope["unselectable"]) is selectable
        for kind, on in (("shown", shown), ("selectable", shown and selectable)):
            if on:
                expect(_tick(page, "shell:1", kind)).to_be_checked()
            else:
                expect(_tick(page, "shell:1", kind)).not_to_be_checked()
        seen = page.evaluate(SHELL_DRAWN, 1)
        assert seen["pieces"] and all(d is shown for d in seen["pieces"]), seen
        assert seen["loops"] and all(d is shown for d in seen["loops"]), seen

    agree(True, True)
    # The ring's cell: View › Layers › Shells › Shell 1 › Shown.
    address = rings.on_world(page, "View", "Layers", "Shells", "Shell 1", "Shown")
    assert address == "21468"
    said(page, "Shell 1: hidden")
    agree(False, True)

    # The window's tick.
    _tick(page, "shell:1", "shown").check()
    said(page, "Shell 1: shown")
    agree(True, True)

    # The world: its drawn ring, clicked, opens its ring; Selectable.
    spot = page.evaluate(ON_A_LOOP, "shell:1")
    assert spot, "no point of the canvas on shell 1's ring clear of every piece"
    page.mouse.click(spot["x"], spot["y"])
    expect(page.locator("#ring-overlay .title")).to_have_text("Shell 1", timeout=rings.RING_MS)
    rings.press(page, "Selectable")
    said(page, "Shell 1: a click passes through it")
    agree(True, False)


def _rgb(colour: str) -> str:
    return "rgb({}, {}, {})".format(*(int(colour[i : i + 2], 16) for i in (1, 3, 5)))


# What the world labels the sphere with at the universe's level: each label's text,
# the layers it belongs to, whether it is drawn now, and whether it is a piece or a hit.
LABELS = """() => {
    const v = window.fractalViewer, o = v.orbits;
    if (!o) return null;
    const pieces = new Set(Object.values(v.meshByName));
    return o.labels.map((l) => ({ text: l.text, layers: l.layers, drawn: l.sprite.visible,
        piece: pieces.has(l.sprite), inScene: !!l.sprite.parent }));
}"""

# The piece, by key, whose middle shows on the canvas clear of the edges on the side the
# eye sees and which a pointer on its middle names; and where on the page that is.
A_NAMED_PIECE = """() => {
    const v = window.fractalViewer, r = v.canvas.getBoundingClientRect();
    for (const [key, node] of Object.entries(v.renderNodeByKey)) {
        if (key.includes('.') || !node.part_ref || !v.pickScope.drawn(node)) continue;
        const b = node.world_bounds;
        const m = [0, 1, 2].map((i) => (b.min[i] + b.max[i]) / 2);
        const at = v.sceneAt(...m);
        if (!v.facesEye(at)) continue;
        const s = at.clone().project(v.camera);
        if (s.z > 1 || s.z < -1) continue;
        const x = r.left + (s.x + 1) / 2 * r.width, y = r.top + (1 - s.y) / 2 * r.height;
        if (x < r.left + 40 || x > r.right - 40 || y < r.top + 40 || y > r.bottom - 40) continue;
        if (v.nameAt({ clientX: x, clientY: y }) !== key) continue;
        return { key, x, y, name: node.part_ref };
    }
    return null;
}"""


@pytest.mark.e2e
def test_each_shell_and_cluster_is_labelled_at_the_universes_level_and_hidden_with_its_layer(
    page: Page, url: str
):
    """A label for each shell, in the docs' words, and one for each cluster, naming its
    category; each is of its loop's layers, no piece and no hit, and gone where the
    orbitals are (a part stepped into)."""
    _universe(page, url)
    windows.from_the_windows_menu(page, "layers")
    page.wait_for_timeout(400)
    labels = page.evaluate(LABELS)
    shells = [lab for lab in labels if lab["text"].startswith("shell ")]
    assert [lab["text"].split(" · ")[1] for lab in shells][0] == "built from nothing"
    assert [lab["text"].split(" · ")[1] for lab in shells][-1] == "sites"
    categories = {lab["text"] for lab in labels} - {lab["text"] for lab in shells}
    assert {"machine", "camera"} <= categories
    assert not any(lab["piece"] for lab in labels) and all(lab["inScene"] for lab in labels)
    drawn = [lab for lab in labels if lab["drawn"]]
    assert drawn, "no label is drawn at the opening view"
    # Hiding shell 0 hides its label and the labels of the clusters on it, and no other shell's.
    _tick(page, "shell:0", "shown").uncheck()
    said(page, "Shell 0: hidden")
    page.wait_for_timeout(400)
    after = {(lab["text"], tuple(lab["layers"])): lab["drawn"] for lab in page.evaluate(LABELS)}
    for lab in labels:
        if lab["layers"][0] == "shell:0":
            assert after[(lab["text"], tuple(lab["layers"]))] is False, lab
    # The labels of the other shells are untouched by it: still drawn as before.
    others = [lab for lab in labels if lab["layers"][0] != "shell:0" and lab["drawn"]]
    assert all(after[(lab["text"], tuple(lab["layers"]))] for lab in others)
    _tick(page, "shell:0", "shown").check()
    # Never a hit: a ray through a label's middle meets no piece for it.
    where = page.evaluate(
        """() => { const v = window.fractalViewer, r = v.canvas.getBoundingClientRect();
            const l = v.orbits.labels.find((x) => x.sprite.visible);
            const s = l.sprite.position.clone().project(v.camera);
            return [r.left + (s.x + 1) / 2 * r.width, r.top + (1 - s.y) / 2 * r.height]; }"""
    )
    assert "label" not in " ".join(str(k) for k in page.evaluate(HITS, where))
    # Stepped into a part, the sphere's labels are gone with its orbitals.
    page.evaluate("() => window.fractalViewer.stepIn('datum_core', 'test')")
    page.wait_for_function("() => !window.fractalViewer.orbits", timeout=20000)
    assert page.evaluate(LABELS) is None


@pytest.mark.e2e
def test_the_piece_under_the_pointer_and_the_selected_piece_are_named_and_neither_is_a_hit(
    page: Page, url: str
):
    _universe(page, url)
    piece = page.evaluate(A_NAMED_PIECE)
    assert piece, "no piece stands clear on the side of the sphere the eye sees"
    pieces_before = sorted(page.evaluate("() => Object.keys(window.fractalViewer.meshByName)"))
    page.mouse.move(piece["x"], piece["y"])
    page.mouse.move(piece["x"] + 1, piece["y"])
    badge = page.locator("[data-anchor='piece-name:hover']")
    expect(badge).to_be_visible(timeout=5000)
    expect(badge).to_contain_text(piece["name"])
    assert badge.evaluate("(el) => getComputedStyle(el).pointerEvents") == "none"
    # Off the piece, it goes; selected, it is named and stays, whatever the pointer does.
    page.mouse.move(1, 1)
    expect(badge).to_have_count(0, timeout=5000)
    page.evaluate("(k) => window.fractalViewer.selectChild(k)", piece["key"])
    selected = page.locator("[data-anchor='piece-name:selected']")
    expect(selected).to_be_visible(timeout=5000)
    expect(selected).to_contain_text(piece["name"])
    # Over a part that already wears badges, the name is in no badge's way and is never
    # merged into their count: two others at the same place do not hide it.
    page.evaluate(
        """(k) => { const v = window.fractalViewer, n = v.renderNodeByKey[k], b = n.world_bounds;
            const at = () => v.sceneAt(...[0, 1, 2].map((i) => (b.min[i] + b.max[i]) / 2));
            for (const id of ['t1', 't2']) v.anchors.badge('test:' + id, at, { className: 'variant-mark' });
            v.invalidate(); }""",
        piece["key"],
    )
    page.wait_for_timeout(500)
    expect(selected).to_be_visible()
    assert "merged" not in (selected.get_attribute("class") or "")
    page.mouse.move(piece["x"], piece["y"])
    page.mouse.move(piece["x"] + 1, piece["y"])
    expect(page.locator("[data-anchor='piece-name:hover']")).to_have_count(0)
    assert sorted(page.evaluate("() => Object.keys(window.fractalViewer.meshByName)")) == pieces_before


@pytest.mark.e2e
def test_the_alignment_grids_row_says_what_it_draws_in_its_colour_and_what_it_does_not(
    page: Page, url: str
):
    _universe(page, url)
    windows.from_the_windows_menu(page, "layers")
    hint = page.locator(".panel[data-panel='layers'] tr[data-row='grid'] th").get_attribute("title")
    assert "build volumes, drawn in this colour" in hint and "faint greys" in hint


def _clear(a: dict, b: dict) -> bool:
    return a["r"] <= b["l"] or b["r"] <= a["l"] or a["b"] <= b["t"] or b["b"] <= a["t"]


@pytest.mark.e2e
def test_the_selected_pieces_name_stands_off_its_measurements_labels(page: Page, url: str):
    """Measured in the universe, the selected piece's name badge rises above any label of
    its sizes it would cover: both are read."""
    _universe(page, url)
    piece = page.evaluate(A_NAMED_PIECE)
    assert piece, "no piece stands clear on the side of the sphere the eye sees"
    page.evaluate("(k) => window.fractalViewer.selectChild(k)", piece["key"])
    page.evaluate("() => window.fractalViewer.fitSelected()")
    page.evaluate("() => window.fractalViewer.pickScope.setShown('measure', true)")
    page.wait_for_function("() => window.fractalViewer.measure.labelBoxes().length >= 3", timeout=10000)
    page.wait_for_timeout(500)
    badge = page.evaluate("() => window.fractalViewer.anchors.drawn('piece-name:selected')")
    labels = page.evaluate("() => window.fractalViewer.measure.labelBoxes()")
    assert badge, "the selected piece wears no name"
    for label in labels:
        assert _clear(badge, label), (badge, label)
    # A label laid just where the name stands: the name rises above it.
    page.evaluate(PUT_A_LABEL_UNDER_THE_NAME)
    page.wait_for_timeout(400)
    badge = page.evaluate("() => window.fractalViewer.anchors.drawn('piece-name:selected')")
    (label,) = page.evaluate("() => window.fractalViewer.measure.labelBoxes()")
    assert _clear(badge, label) and badge["b"] <= label["t"], (badge, label)


# The measurement's labels said to be one, laid across where the selected piece's name
# stands, as a size's label can fall.
PUT_A_LABEL_UNDER_THE_NAME = """() => {
    const v = window.fractalViewer, at = v.anchors.at('piece-name:selected');
    const box = { l: at.x - 60, r: at.x + 60, t: at.y - 44, b: at.y - 20 };
    v.measure.labelBoxes = () => [box];
    v.anchors.touch(); v.invalidate();
}"""
