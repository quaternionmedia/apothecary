"""A part's parameters and its SCAD, tied together (docs/viewer.md, "The part editor"):
the text is the one draft. A control moved rewrites its value in its line, the line's
comment kept; a value typed in the text moves its control; the SCAD editor's undo takes
back each, whichever made it, and Apply sends the text alone. A computed assignment
shows the value its check gave it, under its expression, and moving it asks before the
expression gives way. A part in a submodule (gridfinity) is edited as its overlay: the
upstream's parameters it does not set are listed with upstream's values, moving one
appends its line, and its upstream SCAD is one link away, read only; a saved variant of
it is its overlay, put in the editor. A part whose SCAD its Python generates (the
snowplow) stays one way: its controls drive its model, its SCAD following, read only.
Walkthrough 04 goes round the loop with the text tied, and keeps a size staged over a
reload in its text."""

from __future__ import annotations

import json
import re

import part_editing
import pytest
import rings
from playwright.sync_api import Page, expect
from viewer_ready import settled

from apothecary.projects.parts.calibration_cube import DEFAULT as CUBE
from apothecary.projects.parts.stl_renderer import params_sidecar_path

PART = "calibration_cube"
RING_MS = 15000
WEDGES = (
    "() => Object.fromEntries([...document.querySelectorAll('#ring-overlay .wedge')]"
    ".filter((w) => !w.classList.contains('empty'))"
    ".map((w) => [w.getAttribute('aria-label'), w.dataset.cell]))"
)


@pytest.fixture(scope="module")
def url(start_server, every_stl_built, tmp_path_factory):
    real = every_stl_built()["path"]
    if not real:
        pytest.skip("OpenSCAD not installed")
    folder = tmp_path_factory.mktemp("text-tied")
    return start_server(
        {"APOTHECARY_OPENSCAD": real, "APOTHECARY_CACHE_DIR": str(folder / "cache")}
    )


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
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(f"{url}/viewer/sites/parts_library")
    expect(page.locator("#status")).to_contain_text("Loaded", timeout=20000)
    page.evaluate("() => localStorage.removeItem('apothecary.panels')")
    settled(page)


def _ring(page: Page, part: str, *labels: str) -> None:
    rings.on_row(page, part, *labels)


def _edit(page: Page, part: str = PART) -> None:
    part_editing.edit(page, part)


def _param(page: Page, field: str):
    return part_editing.param(page, field)


def _text(page: Page) -> str:
    return page.evaluate("() => window.fractalViewer.scadEditor.text()")


def _line(page: Page, name: str) -> str | None:
    """The last line assigning ``name`` in the editor's text, as OpenSCAD uses the last."""
    found = [line for line in _text(page).splitlines() if re.match(rf"\s*{name}\s*=", line)]
    return found[-1] if found else None


def _type_over(page: Page, old: str, new: str) -> None:
    """``old`` selected in the editor's text, and ``new`` typed over it, as a person types."""
    page.evaluate(
        """(old) => {
            const view = window.fractalViewer.scadEditor.view;
            const at = view.state.doc.toString().indexOf(old);
            if (at < 0) throw new Error(`not in the text: ${old}`);
            view.focus();
            view.dispatch({ selection: { anchor: at, head: at + old.length }, scrollIntoView: true });
        }""",
        old,
    )
    if new:
        page.keyboard.insert_text(new)
    else:
        page.keyboard.press("Delete")


def _status(page: Page):
    return page.locator("#status")


def _summary(page: Page):
    return page.locator("#stage-summary")


# --- a control and its line ---------------------------------------------------------


@pytest.mark.e2e
def test_a_control_writes_its_line_a_typed_value_moves_it_and_undo_takes_back_each(
    page: Page, url, cube_as_it_was
):
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    _open(page, url)
    _edit(page)
    own = _line(page, "size")
    assert re.match(r"size = 10;\s+// ", own), own
    box = _param(page, "size").locator(".param-number")
    slider = _param(page, "size").locator(".param-slider")

    # Moved: its value rewritten in its line, its comment kept, staged and checked.
    box.fill("20")
    expect(_summary(page)).to_contain_text("1 change staged, valid", timeout=10000)
    assert _line(page, "size") == own.replace("size = 10;", "size = 20;", 1)

    # Typed in the text: the control follows, the slider with it.
    _type_over(page, "size = 20", "size = 25")
    expect(box).to_have_value("25", timeout=10000)
    assert float(slider.input_value()) == pytest.approx(25)

    # The SCAD editor's history is the one: the typing undone, then the move, each a step,
    # the text and the control going back together; and forward again.
    undo, redo = page.locator("#undo-btn"), page.locator("#redo-btn")
    undo.click()
    expect(box).to_have_value("20")
    assert _line(page, "size").startswith("size = 20;")
    undo.click()
    expect(box).to_have_value("10")
    assert _line(page, "size") == own
    expect(_summary(page)).to_have_text("No staged changes")
    redo.click()
    expect(box).to_have_value("20")
    assert _line(page, "size").startswith("size = 20;")

    expect(_summary(page)).to_contain_text("1 change staged, valid", timeout=10000)

    # Apply sends the text, its values in it, and nothing beside it.
    with page.expect_request(lambda r: "/draft/render" in r.url, timeout=60000) as asked:
        page.locator("#apply-btn").click()
    sent = json.loads(asked.value.post_data)
    assert "params" not in sent
    assert sent["scad"] == _text(page) and "\nsize = 20;" in sent["scad"]
    expect(_status(page)).to_contain_text("an applied variant, not saved", timeout=60000)
    expect(_summary(page)).to_have_text("No staged changes")
    assert errors == []


@pytest.mark.e2e
def test_a_computed_value_shows_its_expression_and_asks_before_it_gives_way(
    page: Page, url, cube_as_it_was
):
    _open(page, url)
    _edit(page)
    wall_line = _line(page, "wall_thickness")
    literal = re.match(r"wall_thickness = ([^;]+);", wall_line).group(1)
    _type_over(page, f"wall_thickness = {literal}", "wall_thickness = size * 0.3")
    wall = _param(page, "wall_thickness")
    # Its check gives its value: shown, under its expression.
    expect(wall.locator(".computed-said")).to_have_text("= size * 0.3 · computed", timeout=20000)
    expect(wall.locator(".param-number")).to_have_value("3")

    # Moved, it asks first; kept computed, nothing in the text changes.
    wall.locator(".param-number").fill("4")
    ask = wall.locator(".computed-ask")
    expect(ask).to_contain_text("wall_thickness is computed, = size * 0.3")
    expect(ask.locator(".computed-replace")).to_have_text("Replace it with 4")
    assert _line(page, "wall_thickness").startswith("wall_thickness = size * 0.3;")
    ask.locator(".computed-keep").click()
    expect(ask).to_have_count(0)
    expect(wall.locator(".param-number")).to_have_value("3")
    assert _line(page, "wall_thickness").startswith("wall_thickness = size * 0.3;")

    # Moved again and replaced: the plain value in place of the expression, one edit.
    wall.locator(".param-number").fill("4")
    wall.locator(".computed-ask .computed-replace").click()
    expect(_status(page)).to_contain_text("wall_thickness is 4 in its text now")
    assert _line(page, "wall_thickness").startswith("wall_thickness = 4;")
    expect(wall.locator(".computed-said")).to_have_count(0)
    expect(wall.locator(".param-number")).to_have_value("4")
    # Undo puts the expression back.
    page.locator("#undo-btn").click()
    assert _line(page, "wall_thickness").startswith("wall_thickness = size * 0.3;")
    expect(wall.locator(".computed-said")).to_be_visible()


# --- a part in a submodule, edited as its overlay -----------------------------------


@pytest.mark.e2e
def test_an_overlay_sets_an_upstream_parameter_and_lets_it_go(page: Page, url):
    _open(page, url)
    _edit(page, "gridfinity")
    text = _text(page)
    assert re.search(r"^include <[^>]*gridfinity-rebuilt-bins\.scad>", text, re.M), text
    assert _line(page, "gridx") is None
    gridx = _param(page, "gridx")
    # Not set in the overlay: upstream's value, said so.
    expect(gridx).to_have_class(re.compile(r"\bunset\b"))
    expect(gridx.locator(".unset-said")).to_contain_text("upstream's value")
    upstream_value = gridx.locator(".param-number").input_value()

    # The upstream file, one step away and read only.
    link = page.locator(".part-actions .part-upstream")
    expect(link).to_have_text("Upstream SCAD, read only")
    href = link.get_attribute("href")
    assert href.endswith("/parts/gridfinity/upstream"), href
    upstream = page.request.get(href)
    assert upstream.ok and upstream.headers["x-part-scad"] == "upstream"
    assert re.search(r"^gridx\s*=", upstream.text(), re.M)

    # Moved: its line set in the overlay, appended after the include.
    gridx.locator(".param-number").fill("4")
    expect(gridx).not_to_have_class(re.compile(r"\bunset\b"), timeout=10000)
    assert _text(page) == text + "gridx = 4;\n"
    # Its line typed away: upstream's value again.
    _type_over(page, "gridx = 4;\n", "")
    expect(gridx).to_have_class(re.compile(r"\bunset\b"), timeout=10000)
    expect(gridx.locator(".param-number")).to_have_value(upstream_value)


@pytest.mark.e2e
def test_a_saved_variant_of_an_overlay_is_its_overlay_in_the_editor(page: Page, url):
    """A part in a submodule saves its overlay, its values in it: chosen, the overlay
    is put in the editor, and the controls stand on its values."""
    own = page.request.get(f"{url}/parts/gridfinity/scad").text()
    wide = {
        "part": "gridfinity",
        "name": "wide",
        "ref": "refs/apothecary/variants/gridfinity/wide",
        "commit": "0" * 40,
        "author": "A person",
        "author_email": "a@example.invalid",
        "date": "2026-10-12T10:00:00+00:00",
        "subject": "wide",
        "scad_path": "parts/gridfinity/gridfinity.overlay.scad",
        "kind": "overlay",
        "upstream": "parts/gridfinity/gridfinity-rebuilt-openscad/gridfinity-rebuilt-bins.scad",
        "params": {"gridx": 5},
        "merged": False,
        "repository": ".",
        "deleted": False,
        "merge": None,
        "diff": "",
    }

    def listed(route):
        route.fulfill(status=200, content_type="application/json", body=json.dumps([wide]))

    def one(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({**wide, "scad": own + "gridx = 5;\n"}),
        )

    page.route(re.compile(r".*/parts/gridfinity/saved(\?.*)?$"), listed)
    page.route("**/parts/gridfinity/saved/wide", one)
    _open(page, url)
    _edit(page, "gridfinity")
    row = page.locator(".scad-saved .saved-row[data-variant='wide']")
    expect(row.locator(".saved-kind")).to_have_text("overlay")
    row.locator(".saved-variant").click()
    expect(_status(page)).to_contain_text(
        "the variant wide is drawn, its overlay in the editor", timeout=20000
    )
    assert _text(page) == own + "gridx = 5;\n"
    gridx = _param(page, "gridx")
    expect(gridx.locator(".param-number")).to_have_value("5")
    expect(gridx).not_to_have_class(re.compile(r"\bunset\b"))
    expect(page.locator("#scad-name")).to_have_value("wide")


# --- a part whose SCAD its Python generates -------------------------------------------


@pytest.mark.e2e
def test_a_generated_part_stays_one_way_its_scad_following_its_controls(page: Page, url):
    """The snowplow's SCAD is what its Python generates: its controls drive its model,
    and the SCAD follows each check, read only -- no draft checked, no assignments read."""
    asked = []
    page.on(
        "request",
        lambda r: asked.append(r.url)
        if re.search(r"/parts/snowplow/(draft|assignments)", r.url)
        else None,
    )
    _open(page, url)
    _edit(page, "snowplow")
    text = _text(page)
    assert page.evaluate("() => window.fractalViewer.scadEditor.view.state.readOnly")
    _param(page, "blade_width").locator(".param-number").fill("150")
    expect(_summary(page)).to_contain_text("1 change staged, valid", timeout=10000)
    page.wait_for_function(
        "(was) => window.fractalViewer.scadEditor.text() !== was", arg=text, timeout=15000
    )
    page.locator("#revert-btn").click()
    expect(_summary(page)).to_have_text("No staged changes", timeout=10000)
    page.wait_for_function(
        "(was) => window.fractalViewer.scadEditor.text() === was", arg=text, timeout=15000
    )
    assert asked == [], asked
