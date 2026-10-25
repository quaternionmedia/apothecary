"""Loop 1, designing a part, gone round in the page: the part chosen from its ring
(Part › Edit), a parameter moved -- its line in the part's SCAD rewritten as it moves,
the text the one draft -- and checked once the slider rests, its box beside it in step,
Apply drawing the variant where it stands with the bounds it measured beside the
declared ones, a reload drawing what the tab had applied (its address keeps the
variant), OpenSCAD's error shown by line and the refused size put back (Part › Revert),
then undone and redone (Ctrl+Z, the editor's Redo), the defaults again for nothing
(Part › Defaults and Part › Apply), and round once more, the size typed in its box
(Part › Apply, then the editor's Defaults and Apply); an earlier apply drawn again from
Recent applies; a size staged and not applied kept over a reload, in its text, and
restored; then two tabs applying different values at once, each drawing its own. It
writes walkthrough/14-designing-a-part.md and its pictures as it goes.

The server is this module's own, with an OpenSCAD that is this machine's except
that it refuses a cube of ``TOO_BIG`` mm or more, saying so as an assertion at
the SCAD's ``size`` line would: the error a person meets is OpenSCAD's own
shape, and, as a snapshot does, it still writes the geometry and exits 0, which
the server answers as a failed render with that geometry as its ``partial``.
Its variant cache is a temp folder. Opening the part draws its own STL,
which a fresh clone does not have, so ``parts/calibration_cube/`` is put back
as it was found.

A part drawn from a variant the tab applied wears a quiet amber mark -- a dot
over it from the badge layer, an amber edge and a faint glow, an amber edge on
its editor -- and the saved part does not. Pictures of the library at its own
framing, at both widths, and of the part beside its saved neighbours, are
written under pytest's temp folder (``part-loop-shots``) too.
"""

from __future__ import annotations

import re
import stat
import sys

import pytest
from playwright.sync_api import Page, expect
from viewer_ready import (
    MARKED_LINE_FIRST,
    STAGE_BAR_AT_THE_TOP,
    by_hand,
    settled,
    site_folded,
)

from apothecary.projects.parts.calibration_cube import DEFAULT as CUBE
from apothecary.projects.parts.stl_renderer import params_sidecar_path

PART = "calibration_cube"
TOO_BIG = 60.0
SIZE_LINE = next(
    number
    for number, line in enumerate(CUBE.source_file.read_text().splitlines(), 1)
    if line.startswith("size =")
)
# templates/fractal_viewer.html.j2's VARIANT_EDGE_COLOR and VARIANT_GLOW: the edges of
# a part drawn from a variant, while it is not selected (a selection's are white), and
# its faint glow, selected or not.
VARIANT_EDGE = 0xD9A650
VARIANT_GLOW = 0x261B08

REFUSING_OPENSCAD = '''#!{python}
"""This machine's OpenSCAD, except that a cube of {too_big} mm or more is refused
as an assertion at the SCAD's size line would refuse it -- the way a snapshot
refuses one: it says the error, writes the geometry it built, and exits 0. The
size is the SCAD's own (the text is the truth: Apply writes it there), or -D's."""
import os, re, subprocess, sys
args = sys.argv[1:]
sizes = [float(args[i + 1][5:]) for i, a in enumerate(args[:-1])
         if a == "-D" and args[i + 1].startswith("size=")]
if not sizes and args and os.path.isfile(args[-1]):
    with open(args[-1], encoding="utf-8") as f:
        sizes = [float(m) for m in re.findall(r"^size\\s*=\\s*([-\\d.]+)\\s*;", f.read(), re.M)]
if sizes and sizes[-1] >= {too_big}:
    done = subprocess.run([{real!r}, *args])
    sys.stderr.write(
        "ERROR: Assertion '(size < {too_big})' failed: \\"it fits the bed\\" "
        "in file {scad}, line {line}\\n"
        "TRACE: called by 'assert' in file {scad}, line {line}\\n"
    )
    sys.exit(done.returncode)
os.execv({real!r}, [{real!r}, *args])
'''

MESH = """(key) => {
    const mesh = window.fractalViewer.meshByName[key];
    const g = mesh.geometry;
    g.computeBoundingBox();
    const s = g.boundingBox.max.clone().sub(g.boundingBox.min);
    const edges = mesh.getObjectByName('edges');
    const world = new mesh.position.constructor();
    mesh.localToWorld(world.copy(g.boundingBox.min));
    return { size: [s.x, s.y, s.z], bottom: world.y, placeholder: !!mesh.userData.isPlaceholder,
             variant: !!mesh.userData.drawnFromVariant,
             glow: mesh.material.emissive.getHex(),
             edge: edges ? edges.material.color.getHex() : null };
}"""

# Nothing selected, as test_the_loop's canvas ring has it, every piece coloured again.
NOTHING_SELECTED = """() => {
    const v = window.fractalViewer;
    v.selectedName = null;
    v.hideHandles();
    v.renderSelectedPanel();
    for (const k of Object.keys(v.meshByName)) v.colorMesh(k, v.renderNodeByKey[k]);
}"""

# The part framed with the part nearest it, close in, for a picture of the two.
BESIDE = """(part) => {
    const v = window.fractalViewer;
    const at = (n) => { const b = v.boundsFor(n, 0); return b.min.map((m, i) => (m + b.max[i]) / 2); };
    const here = v.renderNodeByKey[part], c = at(here);
    const others = Object.entries(v.renderNodeByKey)
        .filter(([k, n]) => k !== part && n.part_ref && v.meshByName[k]).map(([, n]) => n);
    const away = (n) => Math.hypot(...at(n).map((x, i) => x - c[i]));
    others.sort((a, b) => away(a) - away(b));
    v.frameCameraForChildren([here, others[0]]);
    v.camera.position.lerp(v.orbitControls.target, 0.35);
    v.orbitControls.update();
    return [others[0].name];
}"""

WEDGES = (
    "() => Object.fromEntries([...document.querySelectorAll('#ring-overlay .wedge')]"
    ".filter((w) => !w.classList.contains('empty'))"
    ".map((w) => [w.dataset.cell, w.getAttribute('aria-label')]))"
)


@pytest.fixture(scope="module")
def loop_url(base_url, start_server, every_stl_built, tmp_path_factory):
    """A server of this module's own, whose OpenSCAD -- the one every server runs, not a
    snapshot of the person's -- refuses a cube too big."""
    real = every_stl_built()["path"]
    if not real:
        pytest.skip("OpenSCAD not installed")
    folder = tmp_path_factory.mktemp("part-loop")
    openscad = folder / "openscad"
    openscad.write_text(
        REFUSING_OPENSCAD.format(
            python=sys.executable,
            too_big=TOO_BIG,
            scad=CUBE.source_file.name,
            line=SIZE_LINE,
            real=real,
        )
    )
    openscad.chmod(openscad.stat().st_mode | stat.S_IEXEC)
    return start_server(
        {"APOTHECARY_OPENSCAD": str(openscad), "APOTHECARY_CACHE_DIR": str(folder / "cache")}
    )


@pytest.fixture(scope="module")
def shots(tmp_path_factory):
    folder = tmp_path_factory.getbasetemp() / "part-loop-shots"
    folder.mkdir(exist_ok=True)
    return folder


@pytest.fixture
def cube_as_it_was():
    """Opening the part draws its own STL, built if a fresh clone lacks it; put back."""
    stl = CUBE.get_stl_output_path()
    files = (stl, params_sidecar_path(stl))
    kept = {path: path.read_bytes() for path in files if path.exists()}
    yield
    for path in files:
        if path in kept:
            path.write_bytes(kept[path])
        else:
            path.unlink(missing_ok=True)


# --- what a person does ---------------------------------------------------------


def _open(page: Page, url: str) -> None:
    page.goto(url)
    expect(page.locator("#status")).to_contain_text("Loaded", timeout=20000)
    page.evaluate("() => localStorage.removeItem('apothecary.panels')")
    settled(page)
    _drawn(page)


def _drawn(page: Page) -> None:
    """The part's real geometry is on screen, not the box standing in for it."""
    page.wait_for_function(
        f"() => {{ const m = window.fractalViewer.meshByName['{PART}'];"
        " return m && !m.userData.isPlaceholder; }",
        timeout=60000,
    )
    settled(page)


# How long a ring may take to open: it asks the server what to offer, and on a
# machine loaded with OpenSCAD runs that answer can take over 5 s.
RING_MS = 15000

# The widths the page is laid out for (the rail beside the world, and the narrower).
WIDTHS = ((1024, 768), (1280, 800))


def _reloaded(page: Page) -> None:
    page.reload()
    expect(page.locator("#status")).to_contain_text("Loaded", timeout=20000)
    _drawn(page)
    settled(page, 4)


def _press(page: Page, *labels: str) -> None:
    for label in labels:
        page.wait_for_function(
            f"() => [...document.querySelectorAll('#ring-overlay .wedge')]"
            f".some((w) => w.getAttribute('aria-label') === {label!r})",
            timeout=RING_MS,
        )
        cell = next(c for c, got in page.evaluate(WEDGES).items() if got == label)
        page.keyboard.press(cell)


def _edit(page: Page) -> None:
    """The part's ring, from its row in Contents: Part › Edit."""
    page.locator(f"#contents-list .contents-item[data-path='{PART}']").click(
        button="right", modifiers=["Control"]
    )
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=RING_MS)
    _press(page, "Part", "Edit")
    expect(page.locator("#part-params .param[data-field='size'] input[type=range]")).to_be_visible(
        timeout=10000
    )


# A drag: the slider's value through each of ``values``, an input event for each,
# with no pause between them that the page could take for the slider resting (a
# frame, on a loaded machine, can be longer than the quiet the check waits for).
DRAG = """(el, values) => {
    for (const v of values) {
        el.value = v;
        el.dispatchEvent(new Event('input'));
    }
}"""


def _slide(page: Page, *values: float) -> float:
    """The size slider dragged through ``values``; the value it rests at, as the
    slider snapped it. Its box beside it says the same."""
    slider = page.locator("#part-params .param[data-field='size'] input[type=range]")
    slider.evaluate(DRAG, list(values))
    rest = float(slider.input_value())
    expect(_size_box(page)).to_have_value(f"{rest:g}")
    return rest


def _size_box(page: Page):
    return page.locator("#part-params .param[data-field='size'] .param-number")


def _type_size(page: Page, value: float) -> float:
    """The size typed in its box, a key at a time; the slider follows."""
    box = _size_box(page)
    box.click()
    box.press("Control+a")
    box.press_sequentially(f"{value:g}", delay=30)
    slider = page.locator("#part-params .param[data-field='size'] input[type=range]")
    expect(slider).to_have_value(f"{value:g}")
    return value


def _mesh(page: Page) -> dict:
    return page.evaluate(MESH, PART)


# What the cube's pictures are framed by: the view brought to it by hand, Shift+drag and
# the wheel, to about this far from its middle (mm).
NEAR = 110


def _framed_on_the_cube(page: Page) -> None:
    by_hand(page, PART, distance=NEAR)


def _envelope(page: Page) -> str:
    """What the editor says of the part's size: the envelope it declares, and what is
    drawn measures. It stands below the SCAD, out of a picture of the sizes, so a step
    that names it carries its words -- all but which OpenSCAD measured, which is the
    machine's (the page's "does not show")."""
    said = " ".join(page.locator("#part-envelope").inner_text().split())
    return re.sub(r" \((OpenSCAD's summary|read from the STL)\)", "", said)


def _shown_whole(page: Page, show) -> None:
    """``show()``, the picture taken with Site folded to its title by its ▾, so Selected
    has the rail: the editor from its stage bar down, its sizes and, under them, what
    the STL measures beside what the part declares."""
    with site_folded(page):
        page.evaluate(STAGE_BAR_AT_THE_TOP)
        show()


def _side(page: Page) -> float:
    return max(_mesh(page)["size"])


def _size_line(page: Page) -> str:
    """The SCAD's size assignment, as the editor below the parameters has it."""
    text = page.evaluate("() => window.fractalViewer.scadEditor.text()")
    return next(line for line in text.splitlines() if line.startswith("size ="))


def _status(page: Page):
    return page.locator("#status")


def _ring_on_the_part(page: Page, *labels: str) -> None:
    """The part's ring, from its row in Site, and the cells ``labels`` name."""
    page.locator(f"#contents-list .contents-item[data-path='{PART}']").click(
        button="right", modifiers=["Control"]
    )
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=RING_MS)
    _press(page, *labels)


def _apply(page: Page, from_the_ring: bool = False):
    """Apply -- the editor's button, or Part › Apply on the part's ring -- and the
    answer the page got: the text rendered, its values in it."""
    apply = page.locator("#apply-btn")
    expect(apply).to_be_enabled(timeout=10000)
    with page.expect_response(lambda r: "/draft/render" in r.url) as answer:
        if from_the_ring:
            _ring_on_the_part(page, "Part", "Apply")
        else:
            apply.click()
    return answer.value


def _variant_in_address(page: Page) -> str | None:
    found = re.search(rf"[?&]variant={PART}(?:%3A|:)([0-9a-f]+)", page.url)
    return found.group(1) if found else None


def _measured(page: Page) -> float:
    text = page.locator("#part-envelope .measured").inner_text()
    found = re.search(r"measured ([\d.]+) × ([\d.]+) × ([\d.]+) mm", text)
    assert found, text
    assert "(OpenSCAD's summary)" in text or "(read from the STL)" in text, text
    return max(float(v) for v in found.groups())


def _declared(page: Page) -> float:
    text = page.locator("#part-envelope .declared").inner_text()
    found = re.search(r"envelope ([\d.]+) × ([\d.]+) × ([\d.]+) mm", text)
    assert found, text
    return max(float(v) for v in found.groups())


def _mark(page: Page):
    """The amber dot the badge layer stands over a part drawn from a variant."""
    return page.locator(f".world-badge.variant-mark[data-part='{PART}']")


def _marked_at_a_glance(page: Page) -> None:
    """The dot is drawn, inside the world's canvas, with nothing selected needed."""
    mark = _mark(page)
    expect(mark).to_be_visible(timeout=10000)
    box, canvas = mark.bounding_box(), page.locator("#viewer-canvas").bounding_box()
    assert canvas["x"] <= box["x"] and box["x"] + box["width"] <= canvas["x"] + canvas["width"]
    assert canvas["y"] <= box["y"] and box["y"] + box["height"] <= canvas["y"] + canvas["height"]


def _shows_variant(page: Page) -> None:
    """Its editor edged and saying so; in the world, its dot and its glow."""
    expect(page.locator(".part-editor")).to_have_class(re.compile(r"\bdrawn-from-variant\b"))
    expect(page.locator("#part-drawn")).to_have_text("an applied variant, not saved")
    _marked_at_a_glance(page)
    mesh = _mesh(page)
    assert mesh["variant"] and mesh["glow"] == VARIANT_GLOW, mesh


def _shows_saved(page: Page) -> None:
    expect(page.locator(".part-editor")).not_to_have_class(re.compile(r"\bdrawn-from-variant\b"))
    expect(page.locator("#part-drawn")).to_be_hidden()
    expect(_mark(page)).to_have_count(0)
    mesh = _mesh(page)
    assert not mesh["variant"] and mesh["glow"] == 0 and mesh["edge"] != VARIANT_EDGE, mesh


def _a_round(
    page: Page,
    values: tuple[float, ...],
    story=None,
    from_the_ring: bool = False,
    typed: bool = False,
) -> float:
    """Move the size -- the slider dragged, or ``typed`` in its box -- see the check,
    Apply -- the editor's, or Part › Apply -- and see the variant drawn and measured,
    standing on the floor where it grew. With ``story``, the page's steps for them,
    each said after what it says is asserted."""
    validations = []
    listen = lambda r: validations.append(r.url) if r.url.endswith("/validate") else None  # noqa: E731
    page.on("request", listen)
    side = _type_size(page, values[-1]) if typed else _slide(page, *values)
    summary = page.locator("#stage-summary")
    expect(summary).to_contain_text("1 change staged, valid", timeout=10000)
    expect(summary).to_contain_text(f"{side:.2f} × {side:.2f} × {side:.2f} mm")
    page.remove_listener("request", listen)
    # The slider was dragged through every value, or the box typed in a key at a
    # time; it was checked once, at rest.
    assert len(validations) == 1, validations
    # Its line in the part's SCAD says it, the line's own range and caption kept.
    line = _size_line(page)
    assert re.match(rf"size = {side:g};\s+// \[", line), line
    if story:
        said = f"{summary.inner_text()}\n{line}"
        _shown_whole(
            page,
            lambda: story.shows(
                "A size dragged is checked once the slider rests",
                f"The size slider dragged through {len(values)} values without a pause: its "
                "line in the part's SCAD, in the editor below, rewritten as it moved, its "
                "comment kept -- the text and the controls are one draft. One check, once "
                "it rests, against the part's own model, and the envelope it would produce. "
                "Nothing is rendered yet; Apply is the next step.",
                shown=said,
            ),
        )

    answer = _apply(page, from_the_ring)
    assert answer.ok, answer.text()
    # Its own text with another size in it: its numbers applied, said so.
    said = f"{PART} regenerated: an applied variant, not saved"
    expect(_status(page)).to_contain_text(said, timeout=60000)
    settled(page)
    assert _side(page) == pytest.approx(side, abs=0.05)
    assert _measured(page) == pytest.approx(side, abs=0.05)
    assert _declared(page) == pytest.approx(side, abs=0.05)
    # Drawn where it stands: grown from the floor, not centred on the envelope it had.
    assert _mesh(page)["bottom"] == pytest.approx(0, abs=0.05)
    # Measured as declared: the envelope's line stays green, and Selected's Footprint
    # is what the variant drawn measures.
    expect(page.locator("#part-envelope")).not_to_have_class(re.compile(r"\bdiffers\b"))
    expect(page.locator("[data-facts='footprint']")).to_contain_text(
        f"{side:.0f} × {side:.0f} × {side:.0f} mm, as the variant drawn measures"
    )
    expect(page.locator("#stage-summary")).to_have_text("No staged changes")
    assert _variant_in_address(page) == answer.json()["variant"]
    _shows_variant(page)
    if story:
        said = f"{_status(page).inner_text()}\n{_envelope(page)}"
        _shown_whole(
            page,
            lambda: story.shows(
                "Apply draws the variant, marked as not saved",
                "Apply: the text rendered, its size in it and nothing passed beside it, into "
                "the cache of variants, and drawn in this tab at that "
                "size, grown from where the part stood on the floor rather than "
                "centred on the envelope it had, and measured beside the envelope the part "
                "declares, Selected's Footprint following it. The editor's amber edge and "
                "its words, and an amber dot over the part in the world, say it is an "
                "applied variant and not the saved part; the status line says so too.",
                shown=said,
            ),
        )
    return side


def _back_to_the_defaults(page: Page, from_the_ring: bool = False) -> str:
    """Defaults then Apply -- Part › Defaults and Part › Apply on the part's ring, or
    the editor's buttons: the saved part again, and nothing rendered. The status line."""
    if from_the_ring:
        _ring_on_the_part(page, "Part", "Defaults")
        expect(_status(page)).to_contain_text(
            "the part's own SCAD is back in its editor", timeout=10000
        )
    else:
        page.locator("#defaults-btn").click()
    expect(page.locator("#stage-summary")).to_contain_text("valid", timeout=10000)
    answer = _apply(page, from_the_ring)
    assert answer.ok and answer.json()["regenerated"] is False, answer.text()
    said = f"{PART} from the cache, nothing rendered: drawn as saved"
    expect(_status(page)).to_contain_text(said, timeout=30000)
    settled(page)
    assert _side(page) == pytest.approx(10, abs=0.05)
    assert _variant_in_address(page) is None
    _shows_saved(page)
    return _status(page).inner_text()


FAILED = """(part) => {
    const v = window.fractalViewer, f = v.failures[part];
    if (!f) return null;
    const g = f.mesh.geometry; g.computeBoundingBox();
    const s = g.boundingBox.max.clone().sub(g.boundingBox.min);
    return { size: [s.x, s.y, s.z], color: f.mesh.material.color.getHex(),
             drawnShown: v.meshByName[part].visible, inScene: !!f.mesh.parent };
}"""


def _refused_by_openscad(page: Page, side_before: float) -> str:
    """A size OpenSCAD refuses: its error, by line, in the editor and on the status
    line; what it wrote before the error drawn greyed where the part stands, flagged
    with the failing line, what was drawn hidden under it; and Save refused with the
    same words. The status line."""
    _slide(page, 70)
    expect(page.locator("#stage-summary")).to_contain_text("valid", timeout=10000)
    answer = _apply(page)
    assert answer.status == 422, answer.text()
    # A failed render, though OpenSCAD wrote geometry and exited 0: never a variant,
    # and the geometry it wrote named, flagged with the failing line.
    partial = answer.json()["detail"]["partial"]
    assert partial["line"] == SIZE_LINE and "/partials/" in partial["stl_url"]
    error = page.locator("#part-messages li.error").first
    expect(error).to_contain_text(f"{CUBE.source_file.name}, line {SIZE_LINE}")
    expect(error).to_contain_text("it fits the bed")
    expect(_status(page)).to_have_class(re.compile(r"\berror\b"))
    expect(_status(page)).to_contain_text(f"line {SIZE_LINE}")
    # Marked on its line in the SCAD editor below, as the editor's lint marks one.
    page.wait_for_function(
        "(line) => (window.fractalViewer.scadEditor?.marked ?? [])"
        ".some((m) => m.severity === 'error' && m.line === line)",
        arg=SIZE_LINE,
        timeout=10000,
    )
    page.locator(".scad-editor .scad-code").scroll_into_view_if_needed()
    marked = page.locator(".scad-editor .cm-line:has(.cm-lintRange-error)")
    expect(marked).to_have_count(1)
    expect(marked).to_contain_text("size =")
    # The variant drawn before is the part's mesh still, hidden under the failure.
    assert _side(page) == pytest.approx(side_before, abs=0.05)
    page.wait_for_function(f"() => !!window.fractalViewer.failures['{PART}']", timeout=20000)
    failed = page.evaluate(FAILED, PART)
    assert max(failed["size"]) == pytest.approx(70, abs=0.5), failed
    assert failed["inScene"] and not failed["drawnShown"], failed
    flag = page.locator(f".world-badge.failure-mark[data-part='{PART}']")
    expect(flag).to_be_visible(timeout=10000)
    expect(flag.locator(".badge-icon")).to_have_text(f"failed at line {SIZE_LINE}")
    expect(page.locator("#part-envelope")).to_have_class(re.compile(r"\bfailed\b"))
    said = _status(page).inner_text()
    assert f"drawn greyed, flagged at line {SIZE_LINE}" in said, said
    # Save refuses what would be a failed render, saying so.
    _ring_on_the_part(page, "Part", "Save")
    expect(_status(page)).to_contain_text(
        "Not saved: with these values OpenSCAD says an error", timeout=30000
    )
    expect(_status(page)).to_contain_text("A failed render is not saved as a variant")
    return said


def _reverted_from_the_ring(page: Page, side: float) -> str:
    """Part › Revert: what was staged put back to what is drawn. The status line."""
    _ring_on_the_part(page, "Part", "Revert")
    expect(_status(page)).to_contain_text("put back to what is drawn", timeout=10000)
    expect(page.locator("#stage-summary")).to_have_text("No staged changes", timeout=10000)
    slider = page.locator("#part-params .param[data-field='size'] input[type=range]")
    assert float(slider.input_value()) == pytest.approx(side, abs=0.5)
    _shows_variant(page)
    # The failure goes with what was staged: what is drawn shows again.
    assert page.evaluate(FAILED, PART) is None
    assert page.evaluate(f"() => window.fractalViewer.meshByName['{PART}'].visible")
    expect(page.locator(".world-badge.failure-mark")).to_have_count(0)
    return _status(page).inner_text()


def _undone_and_redone(page: Page, refused: float, side: float) -> str:
    """Ctrl+Z, the slider holding the focus: the Revert undone, the refused size staged
    again. The editor's Redo: the Revert again, nothing staged. The status line."""
    slider = page.locator("#part-params .param[data-field='size'] input[type=range]")
    slider.focus()
    page.keyboard.press("Control+z")
    expect(page.locator("#stage-summary")).to_contain_text("1 change staged", timeout=10000)
    expect(_size_box(page)).to_have_value(f"{refused:g}")
    expect(_status(page)).to_contain_text("one step back")
    redo = page.locator("#redo-btn")
    expect(redo).to_be_enabled()
    redo.click()
    expect(page.locator("#stage-summary")).to_have_text("No staged changes", timeout=10000)
    assert float(_size_box(page).input_value()) == pytest.approx(side, abs=0.05)
    expect(redo).to_be_disabled()
    return _status(page).inner_text()


def _drawn_again_from_the_history(page: Page, side: float) -> str:
    """Recent applies, unfolded: the round's apply clicked, drawn again from the cache
    -- nothing rendered -- and marked as drawn. The status line."""
    fold = page.locator("#part-history")
    expect(fold).to_be_visible()
    fold.locator("summary").click()
    row = fold.locator("li[data-at]", has_text=f"size {side:g}")
    expect(row).to_have_count(1)
    rendered = []
    rendering = re.compile(r"/(stl/generate|draft/render)")

    def listen(request):
        if rendering.search(request.url):
            rendered.append(request.url)

    page.on("request", listen)
    row.click()
    expect(_status(page)).to_contain_text("drawn again from the cache", timeout=30000)
    settled(page)
    page.remove_listener("request", listen)
    assert rendered == [], rendered
    assert _side(page) == pytest.approx(side, abs=0.05)
    expect(row).to_have_class(re.compile(r"\bdrawn\b"))
    _shows_variant(page)
    # Its text, its size in it, is what is drawn, the envelope declared for it, measured
    # as declared.
    assert _size_line(page).startswith(f"size = {side:g};")
    expect(page.locator("#stage-summary")).to_have_text("No staged changes")
    expect(page.locator("#part-envelope .declared")).to_have_text(
        f"envelope {side:.2f} × {side:.2f} × {side:.2f} mm", timeout=10000
    )
    expect(page.locator("#part-envelope")).not_to_have_class(re.compile(r"\bdiffers\b"))
    return _status(page).inner_text()


def _kept_over_a_reload(page: Page, staged: float, drawn: float) -> str:
    """A size staged and not applied, and the page reloaded: leaving asks first (the
    browser's question, answered by leaving), the status line names the part with
    work kept -- its text, the size in it -- and its editor offers it back; Restore
    stages it again. The offer's words."""
    _type_size(page, staged)
    expect(page.locator("#stage-summary")).to_contain_text("1 change staged, valid", timeout=10000)
    asked = []

    def leave(dialog):
        asked.append(dialog.type)
        dialog.accept()

    page.on("dialog", leave)
    _reloaded(page)
    page.remove_listener("dialog", leave)
    assert asked == ["beforeunload"], asked
    expect(_status(page)).to_contain_text(f"{PART} has work kept from before the reload")
    _edit(page)
    offer = page.locator("#kept-offer")
    expect(offer).to_be_visible(timeout=10000)
    expect(offer).to_contain_text(f"its SCAD edited, size {staged:g}")
    words = offer.locator(".kept-said").inner_text()
    # Nothing is staged until it is restored: what is drawn is what the address names.
    assert float(_size_box(page).input_value()) == pytest.approx(drawn, abs=0.05)
    page.locator("#kept-restore").click()
    expect(offer).to_be_hidden()
    expect(page.locator("#stage-summary")).to_contain_text("1 change staged, valid", timeout=10000)
    expect(_size_box(page)).to_have_value(f"{staged:g}")
    assert _size_line(page).startswith(f"size = {staged:g};")
    expect(_status(page)).to_contain_text("restored from before the reload")
    return words


def _two_tabs(page: Page, site: str, story) -> None:
    """A second tab: each stages a size and Applies, neither waiting for the other,
    and each draws, and reloaded keeps, its own."""
    other = page.context.new_page()
    try:
        # A person works in the tab in front: a tab behind draws no frames.
        sides = []
        for tab, value in ((page, 24), (other, 36)):
            tab.bring_to_front()
            if tab is other:
                _open(tab, site)
                _edit(tab)
            sides.append(_slide(tab, value))
            expect(tab.locator("#stage-summary")).to_contain_text("valid", timeout=10000)
        for tab in (page, other):
            tab.bring_to_front()
            tab.locator("#apply-btn").click()
        for tab, side in zip((page, other), sides, strict=True):
            tab.bring_to_front()
            expect(_status(tab)).to_contain_text("an applied variant, not saved", timeout=60000)
            settled(tab)
            assert _side(tab) == pytest.approx(side, abs=0.05)
            _shows_variant(tab)
        assert _variant_in_address(page) != _variant_in_address(other)
        for tab, side in zip((other, page), reversed(sides), strict=True):
            tab.bring_to_front()
            _reloaded(tab)
            assert _side(tab) == pytest.approx(side, abs=0.05)
            _marked_at_a_glance(tab)
    finally:
        other.close()
    _edit(page)
    _framed_on_the_cube(page)
    _shown_whole(
        page,
        lambda: story.shows(
            "Two tabs apply at once, and each draws its own",
            f"A second tab of the same page: this one stages {sides[0]:.2f} mm and the other "
            f"{sides[1]:.2f} mm, and both Apply, neither waiting. Each renders into a file "
            "of its own and draws its own variant, its address naming it; each, reloaded, "
            "draws its own again. This is the first tab, reloaded, its editor open and the "
            "view brought to the cube by hand.",
        ),
    )


# --- the loop ---------------------------------------------------------------------


@pytest.mark.e2e
def test_designing_a_part_twice_round(
    page: Page, loop_url: str, cube_as_it_was, shots, walkthrough
):
    """The loop, twice round and in two tabs, and walkthrough page 14 written from it.
    Marked e2e and not walkthrough: a loop's page is written by the browser suite
    only, so `apothecary test run` stays quick."""
    story = walkthrough(
        ordinal="14",
        slug="designing-a-part",
        title="Designing a part",
        browser_suite_only=True,
        intro=(
            "A part chosen from its ring, a size moved and checked, its box beside the "
            "slider in step, Apply drawing it in this tab where it stands, with what it "
            "measures beside what it declares, a reload drawing it again, OpenSCAD's "
            "refusal shown by line, put back, undone and redone, the saved part again for "
            "nothing; then round again, the size typed, an earlier apply drawn again from "
            "the cache, a size staged kept over a reload, and two tabs applying at once. "
            "The parameters and the part's SCAD are one draft: a control rewrites its line, "
            "and Apply renders the text. "
            "Every step is the page's own: a cell of a ring, a slider, a box, a key or a "
            "button, and every step's words name the next one."
        ),
        runtime=(
            "It drives a real browser against a real server of its own, whose OpenSCAD is "
            "the one every test server runs, wrapped by the test so that it refuses a cube "
            f"of {TOO_BIG:.0f} mm or more, as an assertion at the SCAD's size line would, so "
            "that the error met is OpenSCAD's own shape. Its cache of variants is a "
            "temporary folder. It needs no network, and refuses one."
        ),
        does_not_show=[
            "**Editing the SCAD.** The part's source is in the editor below its parameters, "
            "its refused line marked there; editing it is walkthrough 16's.",
            "**A variant kept for good.** An applied variant lives in its tab's address and "
            "the cache, which keeps the most recently drawn of each part; saving one is a "
            "variant in git, walkthrough 16's too.",
            "**Which OpenSCAD measured.** The editor says whether the measured bounds are "
            "OpenSCAD's own summary of the render or were read off the STL; which it is "
            "depends on the machine's OpenSCAD, so the words here leave it out.",
            "**What changes from machine to machine.** A variant's key is a hash of what "
            "made it, its OpenSCAD among them; the address that carries it is not in the "
            "pictures, nor in the words.",
        ],
    )
    page.set_viewport_size({"width": 1280, "height": 800})
    site = f"{loop_url}/viewer/sites/parts_library"
    # The part's own STL is current, as the server keeps it: the defaults are saved.
    assert page.request.post(f"{loop_url}/parts/{PART}/stl/generate").ok
    _open(page, site)
    _edit(page)
    # It starts from what is drawn: the saved part, measured.
    _shows_saved(page)
    assert _measured(page) == pytest.approx(10, abs=0.05)
    assert _variant_in_address(page) is None
    _framed_on_the_cube(page)
    _shown_whole(
        page,
        lambda: story.shows(
            "Part › Edit opens the part's editor at what is drawn",
            "The parts library, /viewer/sites/parts_library (the site drop-down's "
            f"parts_library): {PART}'s row in Site, its ring, Part › Edit: its parameters in "
            "Selected. They "
            "start from what is drawn, the part's own STL as its params sidecar records it, "
            "and beside the envelope the part declares is what that STL measures. Nothing "
            "marks it: it is the saved part. The view is brought to it by hand, Shift+drag "
            "and the wheel, as the library frames a whole shelf of parts; in this page's "
            "pictures of the editor, Site is folded to its title by its ▾, so Selected has "
            "the rail. A slider is the next step.",
            shown=_envelope(page),
        ),
    )

    # Round one: a size, checked, applied, drawn.
    first = _a_round(page, (14, 22, 31, 26, 30), story)
    page.locator(".part-editor").evaluate("(el) => el.scrollIntoView({ block: 'start' })")
    page.locator(".panel[data-panel='selected']").screenshot(path=str(shots / "variant-editor.png"))

    # Beside the saved parts nearest it, not selected: the amber edges and glow are its alone.
    page.evaluate(NOTHING_SELECTED)
    neighbours = page.evaluate(BESIDE, PART)
    settled(page, 4)
    mesh = _mesh(page)
    assert mesh["variant"] and mesh["edge"] == VARIANT_EDGE and mesh["glow"] == VARIANT_GLOW
    _marked_at_a_glance(page)
    for name in neighbours:
        assert page.evaluate(MESH, name)["edge"] != VARIANT_EDGE
        assert page.evaluate(MESH, name)["glow"] == 0
    page.screenshot(path=str(shots / "variant-beside-saved.png"))

    # A reload draws what the tab had applied: at the library's own framing, nothing
    # selected, at either width the page is laid out for.
    variant = _variant_in_address(page)
    for width, height in WIDTHS:
        page.set_viewport_size({"width": width, "height": height})
        _reloaded(page)
        assert page.evaluate("() => window.fractalViewer.selectedName") is None
        _marked_at_a_glance(page)
        page.screenshot(path=str(shots / f"library-{width}.png"))
    assert _variant_in_address(page) == variant
    assert _side(page) == pytest.approx(first, abs=0.05)
    story.shows(
        "A reload draws what the tab applied, marked at a glance",
        "The tab's address keeps the variant, so a reload, a bookmark or a link draws it "
        "again, and no other tab is touched. At the library's own framing, with nothing "
        f"selected, the amber dot over {PART} says it is drawn from a variant and not the "
        "saved part; its words, on hover, say so.",
    )
    _edit(page)
    _shows_variant(page)
    slider = page.locator("#part-params .param[data-field='size'] input[type=range]")
    assert float(slider.input_value()) == pytest.approx(first, abs=0.5)
    expect(page.locator("#stage-summary")).to_have_text("No staged changes")
    assert _measured(page) == pytest.approx(first, abs=0.05)
    story.says(
        "Reopened, the editor starts from the variant",
        f"Part › Edit again: the size slider stands at {first:.2f} mm, the variant's, the "
        "measured bounds are the variant's, and nothing is staged.",
    )

    # OpenSCAD refuses a size: its error by line; what is drawn stays.
    refused = _refused_by_openscad(page, first)
    # The list in the stage bar, and the marked line first in the code below it.
    marked = page.locator(".scad-editor .cm-line:has(.cm-lintRange-error)")
    # f, the focus out of any box: the view brought to what is drawn, the greyed failure.
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    page.keyboard.press("f")
    expect(_status(page)).to_contain_text(f"Framed {PART}")
    settled(page)
    with site_folded(page):
        page.evaluate(STAGE_BAR_AT_THE_TOP)
        marked.evaluate(MARKED_LINE_FIRST)
        story.shows(
            "OpenSCAD's refusal, by line, drawn greyed",
            "A size of 70 mm, which this run's OpenSCAD refuses -- the test's stand-in, which "
            f"refuses a cube of {TOO_BIG:.0f} mm or more where a real OpenSCAD renders it; "
            "walkthrough 16 meets a refusal of the SCAD's own. Like a snapshot, it says the "
            "error and still writes the geometry it built: a failed render, never a variant. "
            "Apply answers with OpenSCAD's words, listed by file and line under the stage "
            "bar, the line marked in the part's source below, and carried on the status "
            "line; what it built is drawn greyed where the part stands, a red flag over it "
            "naming the line, the variant drawn before hidden under it -- f frames it. Part › "
            "Save refuses it in the same words. The refused size is still staged.",
            shown=refused,
        )

    # Revert, from the part's ring: what is staged put back to what is drawn.
    reverted = _reverted_from_the_ring(page, first)
    story.says(
        "Part › Revert puts back what was staged",
        f"{PART}'s ring, Part › Revert: the refused size is put back to what is drawn, "
        f"{first:.2f} mm, the greyed failure gone and the variant shown again, and nothing "
        "is staged. Part › Defaults is the way to the saved part.",
        shown=reverted,
    )

    # Undo and Redo: the draft a step back and forward again.
    redone = _undone_and_redone(page, 70, first)
    story.says(
        "Ctrl+Z and Redo step the draft back and forward",
        "Ctrl+Z, the slider holding the focus: the Revert undone, 70 mm staged again, "
        "its box and its line saying so -- the SCAD editor's own history, the text and "
        "the controls going back together. The editor's Redo, under Apply: the Revert "
        "again, and nothing staged. Part › History holds the same two.",
        shown=redone,
    )

    # The defaults again, for nothing: from the part's ring.
    back = _back_to_the_defaults(page, from_the_ring=True)
    page.screenshot(path=str(shots / "saved-again.png"))
    # Its parameters from the first, wherever the Apply left Selected scrolled.
    page.evaluate(STAGE_BAR_AT_THE_TOP)
    story.shows(
        "Part › Defaults, then Part › Apply: the saved part again, for nothing",
        f"{PART}'s ring, Part › Defaults: the part's own SCAD back in its editor -- its "
        "defaults are its SCAD as saved -- its numbers with it, and the status line names "
        "Apply. Part › Apply renders nothing, since the cache "
        "already holds the saved part, and draws it: the amber marks are gone, and the "
        "address names no variant.",
        shown=back,
    )

    # Round two: typed in the box, applied from the part's ring, back with the
    # editor's buttons.
    second = _a_round(page, (47.5,), from_the_ring=True, typed=True)
    back = _back_to_the_defaults(page)
    story.says(
        "Round two, the size typed in its box",
        f"A second size, {second:.2f} mm, typed a key at a time in the box beside the "
        "slider, which follows it; checked once, and applied from the part's ring, Part › "
        "Apply, as the editor's Apply applies it: rendered, drawn and marked. Then the "
        "editor's own Defaults and Apply: the saved part again, nothing rendered.",
        shown=back,
    )

    # An earlier apply, drawn again from the cache.
    again = f"{_drawn_again_from_the_history(page, first)}\n{_envelope(page)}"
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    page.keyboard.press("f")
    expect(_status(page)).to_contain_text(f"Framed {PART}")
    settled(page)
    _shown_whole(
        page,
        lambda: story.shows(
            "Recent applies draws an earlier one again, from the cache",
            f"Recent applies, under the parameters, lists this tab's applies of {PART}, "
            f"newest first. The first round's, {first:.2f} mm, clicked: drawn again from "
            "the cache of variants, nothing rendered, its text and its numbers what is "
            "drawn; f frames it.",
            shown=again,
        ),
    )

    # A size staged and not applied, kept over a reload in its text, and restored.
    kept = _kept_over_a_reload(page, 20, first)
    story.says(
        "A size staged and not applied is kept over a reload",
        "A size of 20 mm staged and not applied, and the page reloaded: the browser asks "
        "before leaving, the status line names the part with work kept -- its SCAD as "
        "edited, the size in it -- and Part › Edit offers it back. Restore stages it "
        "again, its line and its control both; Discard would let it go.",
        shown=kept,
    )
    page.locator("#revert-btn").click()
    expect(page.locator("#stage-summary")).to_have_text("No staged changes", timeout=10000)

    # Two tabs, at once.
    _two_tabs(page, site, story)
