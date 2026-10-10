"""Loop 1, designing a part (docs/plans/ui-flows-2026-10-08.md), gone round in
the page: the part chosen from its ring (Part › Edit), a parameter moved and
checked once the slider rests, Apply drawing the variant with the bounds it
measured beside the declared ones, a reload drawing what the tab had applied
(its address keeps the variant), OpenSCAD's error shown by line, the defaults
again for nothing, and round once more; and two tabs applying different values
at once, each drawing its own.

The server is this module's own, with an OpenSCAD that is this machine's except
that it refuses a cube of ``TOO_BIG`` mm or more, saying so as an assertion at
the SCAD's ``size`` line would: the error a person meets is OpenSCAD's own
shape. Its variant cache is a temp folder. Opening the part draws its own STL,
which a fresh clone does not have, so ``parts/calibration_cube/`` is put back
as it was found.

A part drawn from a variant the tab applied wears a quiet amber edge, in the
world and in its editor; the saved part does not. The pictures of that are
written under pytest's temp folder (``part-loop-shots``).
"""

from __future__ import annotations

import re
import stat
import sys

import pytest
from playwright.sync_api import Page, expect
from viewer_ready import settled

from apothecary.projects.parts.calibration_cube import DEFAULT as CUBE
from apothecary.projects.parts.stl_renderer import get_renderer, params_sidecar_path

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
as an assertion at the SCAD's size line would refuse it."""
import os, sys
args = sys.argv[1:]
for i, arg in enumerate(args[:-1]):
    if arg == "-D" and args[i + 1].startswith("size=") and float(args[i + 1][5:]) >= {too_big}:
        sys.stderr.write(
            "ERROR: Assertion '(size < {too_big})' failed: \\"it fits the bed\\" "
            "in file {scad}, line {line}\\n"
            "TRACE: called by 'assert' in file {scad}, line {line}\\n"
            "Current top level object is empty.\\n"
        )
        sys.exit(1)
os.execv({real!r}, [{real!r}, *args])
'''

MESH = """(key) => {
    const mesh = window.fractalViewer.meshByName[key];
    const g = mesh.geometry;
    g.computeBoundingBox();
    const s = g.boundingBox.max.clone().sub(g.boundingBox.min);
    const edges = mesh.getObjectByName('edges');
    return { size: [s.x, s.y, s.z], placeholder: !!mesh.userData.isPlaceholder,
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
def loop_url(base_url, start_server, tmp_path_factory):
    """A server of this module's own, whose OpenSCAD refuses a cube too big."""
    renderer = get_renderer()
    if not renderer.is_available:
        pytest.skip("OpenSCAD not installed")
    folder = tmp_path_factory.mktemp("part-loop")
    openscad = folder / "openscad"
    openscad.write_text(
        REFUSING_OPENSCAD.format(
            python=sys.executable,
            too_big=TOO_BIG,
            scad=CUBE.source_file.name,
            line=SIZE_LINE,
            real=str(renderer.openscad_path),
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


def _press(page: Page, *labels: str) -> None:
    for label in labels:
        page.wait_for_function(
            f"() => [...document.querySelectorAll('#ring-overlay .wedge')]"
            f".some((w) => w.getAttribute('aria-label') === {label!r})",
            timeout=5000,
        )
        cell = next(c for c, got in page.evaluate(WEDGES).items() if got == label)
        page.keyboard.press(cell)


def _edit(page: Page) -> None:
    """The part's ring, from its row in Contents: Part › Edit."""
    page.locator(f"#contents-list .contents-item[data-path='{PART}']").click(button="right")
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
    _press(page, "Part", "Edit")
    expect(page.locator("#part-params .param[data-field='size'] input")).to_be_visible(
        timeout=10000
    )


# A drag: the slider's value through each of ``values``, an input event a frame apart.
DRAG = """async (el, values) => {
    for (const v of values) {
        el.value = v;
        el.dispatchEvent(new Event('input'));
        await new Promise((next) => requestAnimationFrame(next));
    }
}"""


def _slide(page: Page, *values: float) -> float:
    """The size slider dragged through ``values``; the value it rests at, as the
    slider snapped it."""
    slider = page.locator("#part-params .param[data-field='size'] input[type=range]")
    slider.evaluate(DRAG, list(values))
    return float(slider.input_value())


def _mesh(page: Page) -> dict:
    return page.evaluate(MESH, PART)


def _side(page: Page) -> float:
    return max(_mesh(page)["size"])


def _status(page: Page):
    return page.locator("#status")


def _apply(page: Page):
    apply = page.locator("#apply-btn")
    expect(apply).to_be_enabled(timeout=10000)
    with page.expect_response(lambda r: "/stl/generate" in r.url) as answer:
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


def _shows_variant(page: Page) -> None:
    """Its editor edged and saying so; in the world, its glow (it is selected)."""
    expect(page.locator(".part-editor")).to_have_class(re.compile(r"\bdrawn-from-variant\b"))
    expect(page.locator("#part-drawn")).to_have_text("an applied variant, not saved")
    mesh = _mesh(page)
    assert mesh["variant"] and mesh["glow"] == VARIANT_GLOW, mesh


def _shows_saved(page: Page) -> None:
    expect(page.locator(".part-editor")).not_to_have_class(re.compile(r"\bdrawn-from-variant\b"))
    expect(page.locator("#part-drawn")).to_be_hidden()
    mesh = _mesh(page)
    assert not mesh["variant"] and mesh["glow"] == 0 and mesh["edge"] != VARIANT_EDGE, mesh


def _a_round(page: Page, values: tuple[float, ...]) -> float:
    """Move the size, see the check, Apply, see the variant drawn and measured."""
    validations = []
    listen = lambda r: validations.append(r.url) if r.url.endswith("/validate") else None  # noqa: E731
    page.on("request", listen)
    side = _slide(page, *values)
    summary = page.locator("#stage-summary")
    expect(summary).to_contain_text("1 change staged, valid", timeout=10000)
    expect(summary).to_contain_text(f"{side:.2f} × {side:.2f} × {side:.2f} mm")
    page.remove_listener("request", listen)
    # The slider was dragged through every value; it was checked once, at rest.
    assert len(validations) == 1, validations

    answer = _apply(page)
    assert answer.ok, answer.text()
    expect(_status(page)).to_contain_text(
        f"{PART} regenerated: an applied variant, not saved", timeout=60000
    )
    settled(page)
    assert _side(page) == pytest.approx(side, abs=0.05)
    assert _measured(page) == pytest.approx(side, abs=0.05)
    assert _declared(page) == pytest.approx(side, abs=0.05)
    expect(page.locator("#stage-summary")).to_have_text("No staged changes")
    assert _variant_in_address(page) == answer.json()["variant"]
    _shows_variant(page)
    return side


def _back_to_the_defaults(page: Page, from_the_ring: bool = False) -> None:
    """Defaults -- Part › Defaults on the part's ring, or the editor's button --
    then Apply: the saved part again, and nothing rendered."""
    if from_the_ring:
        page.locator(f"#contents-list .contents-item[data-path='{PART}']").click(button="right")
        expect(page.locator("#ring-overlay")).to_be_visible(timeout=5000)
        _press(page, "Part", "Defaults")
        expect(_status(page)).to_contain_text("the part's own numbers are staged", timeout=10000)
    else:
        page.locator("#defaults-btn").click()
    expect(page.locator("#stage-summary")).to_contain_text("valid", timeout=10000)
    answer = _apply(page)
    assert answer.ok and answer.json()["regenerated"] is False, answer.text()
    expect(_status(page)).to_contain_text(
        f"{PART} from the cache, nothing rendered: drawn as saved", timeout=30000
    )
    settled(page)
    assert _side(page) == pytest.approx(10, abs=0.05)
    assert _variant_in_address(page) is None
    _shows_saved(page)


def _refused_by_openscad(page: Page, side_before: float) -> None:
    """A size OpenSCAD refuses: its error, by line, in the editor and on the status line."""
    _slide(page, 70)
    expect(page.locator("#stage-summary")).to_contain_text("valid", timeout=10000)
    answer = _apply(page)
    assert answer.status == 422, answer.text()
    error = page.locator("#part-messages li.error").first
    expect(error).to_contain_text(f"{CUBE.source_file.name}, line {SIZE_LINE}")
    expect(error).to_contain_text("it fits the bed")
    expect(_status(page)).to_have_class(re.compile(r"\berror\b"))
    expect(_status(page)).to_contain_text(f"line {SIZE_LINE}")
    marked = page.locator("#part-scad-content .scad-line.error-line")
    expect(marked).to_have_count(1)
    expect(marked).to_have_attribute("data-line", str(SIZE_LINE))
    expect(marked).to_contain_text("size =")
    # Nothing drawn changed.
    assert _side(page) == pytest.approx(side_before, abs=0.05)


# --- the loop ---------------------------------------------------------------------


@pytest.mark.e2e
def test_designing_a_part_twice_round(page: Page, loop_url: str, cube_as_it_was, shots):
    site = f"{loop_url}/viewer/sites/parts_library"
    # The part's own STL is current, as the server keeps it: the defaults are saved.
    assert page.request.post(f"{loop_url}/parts/{PART}/stl/generate").ok
    _open(page, site)
    _edit(page)
    # It starts from what is drawn: the saved part, measured.
    _shows_saved(page)
    assert _measured(page) == pytest.approx(10, abs=0.05)
    assert _variant_in_address(page) is None

    # Round one: a size, checked, applied, drawn.
    first = _a_round(page, (14, 22, 31, 26, 30))
    page.locator(".part-editor").evaluate("(el) => el.scrollIntoView({ block: 'start' })")
    page.locator(".panel[data-panel='selected']").screenshot(path=str(shots / "variant-editor.png"))

    # Beside the saved parts nearest it, not selected: the amber edges and glow are its alone.
    page.evaluate(NOTHING_SELECTED)
    neighbours = page.evaluate(BESIDE, PART)
    settled(page, 4)
    mesh = _mesh(page)
    assert mesh["variant"] and mesh["edge"] == VARIANT_EDGE and mesh["glow"] == VARIANT_GLOW
    for name in neighbours:
        assert page.evaluate(MESH, name)["edge"] != VARIANT_EDGE
        assert page.evaluate(MESH, name)["glow"] == 0
    page.screenshot(path=str(shots / "variant-beside-saved.png"))

    # A reload draws what the tab had applied, and its editor starts there.
    variant = _variant_in_address(page)
    page.reload()
    expect(page.locator("#status")).to_contain_text("Loaded", timeout=20000)
    _drawn(page)
    assert _variant_in_address(page) == variant
    assert _side(page) == pytest.approx(first, abs=0.05)
    _edit(page)
    _shows_variant(page)
    slider = page.locator("#part-params .param[data-field='size'] input[type=range]")
    assert float(slider.input_value()) == pytest.approx(first, abs=0.5)
    expect(page.locator("#stage-summary")).to_have_text("No staged changes")
    assert _measured(page) == pytest.approx(first, abs=0.05)

    # OpenSCAD refuses a size: its error by line; what is drawn stays.
    _refused_by_openscad(page, first)

    # The defaults again, for nothing: from the part's ring.
    _back_to_the_defaults(page, from_the_ring=True)
    page.screenshot(path=str(shots / "saved-again.png"))

    # Round two, back with the editor's Defaults.
    _a_round(page, (40, 45, 47))
    _back_to_the_defaults(page)


@pytest.mark.e2e
def test_two_tabs_applying_at_once_each_draw_their_own(page: Page, loop_url: str, cube_as_it_was):
    site = f"{loop_url}/viewer/sites/parts_library"
    other = page.context.new_page()
    try:
        # A person works in the tab in front: a tab behind draws no frames.
        sides = []
        for tab, value in ((page, 24), (other, 36)):
            tab.bring_to_front()
            _open(tab, site)
            _edit(tab)
            sides.append(_slide(tab, value))
            expect(tab.locator("#stage-summary")).to_contain_text("valid", timeout=10000)
        # Both Apply, neither waiting for the other.
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
        # Each tab, reloaded, still draws its own.
        for tab, side in zip((page, other), sides, strict=True):
            tab.bring_to_front()
            tab.reload()
            expect(tab.locator("#status")).to_contain_text("Loaded", timeout=20000)
            _drawn(tab)
            assert _side(tab) == pytest.approx(side, abs=0.05)
    finally:
        other.close()
