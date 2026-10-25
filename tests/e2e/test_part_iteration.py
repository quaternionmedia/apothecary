"""Iterating on a part in the page, each piece through the page's own controls and keys:
the parameter controls (a number box beside each slider, round steps, choices, groups,
captions, captioned vectors, units where a field declares one), the focus kept after
Apply, OpenSCAD's keys in the SCAD editor and the browser's outside it, the staged
numbers' undo and redo by key, button and ring, a variant drawn where it stands, the
ghost of what was drawn before, framing the part being edited, and a render of older
SCAD saying so.

What the test part does not declare -- an integer, a field's own step, a choice or a
vector, and a field with no unit -- is said to the page here by answering its read of
the part's parameters with those fields as the server's ParamField carries them
(Playwright's route): the page draws what it is told, and nothing where it is told
nothing. The server is this module's own,
rendering with the OpenSCAD every server runs, its variant cache a temp folder.
"""

from __future__ import annotations

import json
import re

import pytest
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
    folder = tmp_path_factory.mktemp("part-iteration")
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
            timeout=RING_MS,
        )
        page.keyboard.press(page.evaluate(WEDGES)[label])


def _ring(page: Page, *labels: str, part: str = PART) -> None:
    page.locator(f"#contents-list .contents-item[data-path='{part}']").click(
        button="right", modifiers=["Control"]
    )
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=RING_MS)
    _press(page, *labels)


def _edit(page: Page, part: str = PART) -> None:
    _ring(page, "Part", "Edit", part=part)
    expect(
        page.locator(f".part-editor[data-target='part:{part}'] #part-params .param")
    ).not_to_have_count(0, timeout=15000)


def _param(page: Page, field: str):
    return page.locator(f"#part-params > .param[data-field='{field}']")


def _status(page: Page):
    return page.locator("#status")


def _summary(page: Page):
    return page.locator("#stage-summary")


def _told(page: Page, part: str, change) -> None:
    """The page's read of ``part``'s parameters answered with ``change`` made to it."""

    def answer(route):
        response = route.fetch()
        spec = response.json()
        change(spec)
        route.fulfill(response=response, body=json.dumps(spec))

    page.route(f"**/parts/{part}/params", answer)


def _applied(page: Page, said: str = "an applied variant, not saved") -> None:
    apply = page.locator("#apply-btn")
    expect(apply).to_be_enabled(timeout=10000)
    apply.click()
    expect(_status(page)).to_contain_text(said, timeout=60000)
    settled(page)


MESH_BOX = """(key) => {
    const v = window.fractalViewer, mesh = v.meshByName[key];
    const box = new mesh.position.constructor(), top = new mesh.position.constructor();
    const g = mesh.geometry;
    g.computeBoundingBox();
    mesh.localToWorld(box.copy(g.boundingBox.min));
    mesh.localToWorld(top.copy(g.boundingBox.max));
    return { min: [box.x, box.y, box.z], max: [top.x, top.y, top.z] };
}"""


# --- the controls -------------------------------------------------------------------


@pytest.mark.e2e
def test_a_number_is_a_slider_and_a_box_in_step_on_round_steps(page: Page, url, cube_as_it_was):
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    _open(page, url)
    _edit(page)
    size = _param(page, "size")
    slider, box = size.locator(".param-slider"), size.locator(".param-number")
    # The model's size is over 5 and at most 100: the slider stops on tenths, from the
    # first tenth over 5; its box beside it says the same number.
    assert slider.get_attribute("step") == "0.1"
    assert slider.get_attribute("min") == "5.5" and slider.get_attribute("max") == "100"
    expect(box).to_have_value("10")
    # The description is its caption, and the unit its model declares stands beside it.
    expect(size.locator(".caption")).to_have_text("Cube size")
    expect(size.locator(".unit")).to_have_text("mm")
    # The slider moved: the box follows.
    slider.evaluate("(el) => { el.value = 31.4; el.dispatchEvent(new Event('input')); }")
    expect(box).to_have_value("31.4")
    # A number typed: the slider follows, and it is staged as typed.
    box.fill("27.25")
    expect(_summary(page)).to_contain_text(
        "1 change staged, valid → 27.25 × 27.25 × 27.25 mm", timeout=10000
    )
    assert float(slider.input_value()) == pytest.approx(27.25, abs=0.06)
    # A yes or no is a tick-box, its caption its description.
    axes = _param(page, "show_axes")
    expect(axes.locator(".param-tick")).to_be_checked()
    expect(axes.locator(".caption")).to_contain_text("axis indicators")
    assert errors == []


@pytest.mark.e2e
def test_what_a_field_declares_is_drawn_and_nothing_where_it_declares_nothing(
    page: Page, url, cube_as_it_was
):
    """A unit, an integer, a stated step, a choice and a vector, told to the page as the
    server tells them (params.py's ParamField), and a field with its unit taken away."""

    def change(spec):
        fields = {f["name"]: f for f in spec["fields"]}
        fields["size"]["unit"] = "mm"
        fields["wall_thickness"]["step"] = 0.25
        fields["wall_thickness"]["unit"] = None
        spec["fields"] += [
            {
                "name": "copies",
                "type": "number",
                "integer": True,
                "default": 2,
                "min": 1,
                "max": 12,
                "description": "How many",
                "contested": [],
            },
            {
                "name": "finish",
                "type": "enum",
                "default": "matte",
                "options": [
                    {"value": "matte", "label": "Matte"},
                    {"value": "gloss", "label": "Gloss"},
                ],
                "contested": [],
            },
            {
                "name": "offset",
                "type": "vector",
                "default": [1, 2, 3],
                "unit": "mm",
                "contested": [],
            },
        ]

    _told(page, PART, change)
    _open(page, url)
    _edit(page)
    expect(_param(page, "size").locator(".unit")).to_have_text("mm")
    expect(_param(page, "wall_thickness").locator(".unit")).to_have_count(0)
    # The field's own step, where it states one; one, for an integer.
    assert _param(page, "wall_thickness").locator(".param-slider").get_attribute("step") == "0.25"
    copies = _param(page, "copies")
    assert copies.locator(".param-slider").get_attribute("step") == "1"
    expect(copies.locator(".param-number")).to_have_value("2")
    # A choice is a drop-down of its options, by their labels.
    finish = _param(page, "finish")
    expect(finish.locator("select.param-choice option")).to_have_text(["Matte", "Gloss"])
    expect(finish.locator(".val")).to_have_text("Matte")
    # A vector: a box for each number, each captioned; its unit after them.
    offset = _param(page, "offset")
    expect(offset.locator(".coord .axis")).to_have_text(["x", "y", "z"])
    expect(offset.locator(".param-coord")).to_have_count(3)
    expect(offset.locator(".unit")).to_have_text("mm")
    # Moving one stages the field's whole value.
    finish.locator("select").select_option(label="Gloss")
    expect(finish.locator(".val")).to_have_text("Gloss")
    assert page.evaluate("() => window.fractalViewer.partParams.finish") == "gloss"
    offset.locator(".param-coord").nth(1).fill("5")
    assert page.evaluate("() => window.fractalViewer.partParams.offset") == [1, 5, 3]


@pytest.mark.e2e
def test_a_nested_model_is_a_group_of_its_own_fields(page: Page, url):
    """gridfinity's hole options are a model inside its model: a group, a tick-box for
    each of its fields, and moving one stages the group, checked by the part's model."""
    _open(page, url)
    _edit(page, part="gridfinity")
    group = _param(page, "hole_options")
    expect(group.locator("fieldset.param-group legend .name")).to_have_text("hole_options")
    expect(group.locator(".param.sub")).to_have_count(6)
    magnets = group.locator(".param.sub[data-field='magnet_holes'] .param-tick")
    expect(magnets).not_to_be_checked()
    magnets.check()
    expect(_summary(page)).to_contain_text("1 change staged, valid", timeout=10000)
    expect(group.locator(".was")).to_have_text(" was magnet_holes false")
    assert page.evaluate("() => window.fractalViewer.partParams.hole_options.magnet_holes") is True
    # A number of its model's, its description its caption.
    expect(_param(page, "gridx").locator(".caption")).to_have_text("Number of bases along X-axis")


# --- the loop's keys, focus and undo ------------------------------------------------


@pytest.mark.e2e
def test_focus_stays_and_the_staged_numbers_undo_by_key_button_and_ring(
    page: Page, url, cube_as_it_was
):
    _open(page, url)
    _edit(page)
    box = _param(page, "size").locator(".param-number")
    box.fill("20")
    expect(_summary(page)).to_contain_text("1 change staged, valid", timeout=10000)
    _applied(page)
    # Apply's button is disabled once nothing is staged: the focus goes back to the box.
    expect(box).to_be_focused()
    # A step staged, then undone by Ctrl+Z (the slider holding the focus), redone by the
    # editor's Redo, undone again by the ring's Part › History › Undo.
    _param(page, "size").locator(".param-slider").evaluate(
        "(el) => { for (const v of [21, 22, 23]) { el.value = v; el.dispatchEvent(new Event('input')); } }"
    )
    expect(_summary(page)).to_contain_text("1 change staged", timeout=10000)
    _param(page, "size").locator(".param-slider").focus()
    page.keyboard.press("Control+z")
    expect(box).to_have_value("20")  # the drag was one step
    expect(_summary(page)).to_have_text("No staged changes")
    page.locator("#redo-btn").click()
    expect(box).to_have_value("23")
    _ring(page, "Part", "History", "Undo")
    expect(box).to_have_value("20")
    expect(_status(page)).to_contain_text("one step back")
    _ring(page, "Part", "History", "Redo")
    expect(box).to_have_value("23")
    # In a box being typed in, Ctrl+Z is the box's own: the staged set is not stepped.
    page.evaluate("() => window.fractalViewer.setStatus('-')")
    box.click()
    page.keyboard.press("Control+z")
    expect(_status(page)).to_have_text("-")
    page.locator("#revert-btn").click()
    expect(_summary(page)).to_have_text("No staged changes", timeout=10000)


@pytest.mark.e2e
def test_openscad_s_keys_work_in_the_editor_and_the_browser_s_outside(
    page: Page, url, cube_as_it_was
):
    _open(page, url)
    _edit(page)
    code = page.locator(".scad-editor .cm-content")
    expect(code).to_be_visible(timeout=20000)
    # Outside the editor the page takes none of F5, F6 and Ctrl+Enter: what the browser
    # would do stands. Ctrl+S, while the editor is open, is the page's anywhere
    # (test_the_pointer_and_the_keys.py), and is pressed here only inside it.
    taken = page.evaluate(
        """() => ['F5', 'F6', 'Enter'].map((key) => {
            const e = new KeyboardEvent('keydown', { key, ctrlKey: key === 'Enter', bubbles: true, cancelable: true });
            document.body.dispatchEvent(e);
            return e.defaultPrevented;
        })"""
    )
    assert taken == [False, False, False]
    # Inside it: F6 applies what is staged -- the text, the size written into it -- and
    # the page stays.
    _param(page, "size").locator(".param-number").fill("12")
    expect(_summary(page)).to_contain_text("1 change staged, valid", timeout=10000)
    code.click(position={"x": 24, "y": 8})  # its first line: in view in Selected's window
    with page.expect_response(lambda r: "/draft/render" in r.url, timeout=60000):
        page.keyboard.press("F6")
    expect(_status(page)).to_contain_text("an applied variant, not saved", timeout=60000)
    # Ctrl+Enter, with an edit: the edit is rendered, and the focus stays in the code.
    page.keyboard.press("Control+End")
    page.keyboard.insert_text("\ntranslate([0, 0, size]) cube(1);")
    with page.expect_response(lambda r: "/draft/render" in r.url, timeout=60000):
        page.keyboard.press("Control+Enter")
    expect(_status(page)).to_contain_text("from its edited SCAD", timeout=60000)
    assert page.evaluate("() => document.activeElement.classList.contains('cm-content')")
    # Ctrl+S saves it, under the name greyed in the box.
    page.keyboard.press("Control+s")
    expect(_status(page)).to_contain_text("saved as the variant variant-1", timeout=20000)
    assert "/viewer/sites/parts_library" in page.url


# --- where a variant stands, what was before, and framing ------------------------------


@pytest.mark.e2e
def test_a_variant_stands_where_it_grew_beside_a_ghost_of_what_was_before(
    page: Page, url, cube_as_it_was
):
    _open(page, url)
    _edit(page)
    _param(page, "size").locator(".param-number").fill("30")
    expect(_summary(page)).to_contain_text("1 change staged, valid", timeout=10000)
    _applied(page)
    # Grown from where it stood, on the floor: not centred on the envelope it had.
    box = page.evaluate(MESH_BOX, PART)
    assert box["min"][1] == pytest.approx(0, abs=0.05)
    assert box["max"][1] == pytest.approx(30, abs=0.05)
    expect(page.locator("[data-facts='footprint']")).to_have_text(
        "30 × 30 × 30 mm, as the variant drawn measures (declared 10 × 10 × 10 mm)"
    )
    # The ghost: the saved part, faint, and how much the size changed.
    page.locator("#ghost-toggle").check()
    ghost = page.locator("#part-ghost")
    expect(ghost).to_have_text(
        "Ghost of the saved part, 10.00 × 10.00 × 10.00 mm; drawn now 30.00 × 30.00 × 30.00 mm,"
        " +20.00 × +20.00 × +20.00 mm"
    )
    assert page.evaluate(
        "() => window.fractalViewer.scene.children.some((o) => o.userData.ghost === 'calibration_cube')"
    )
    # Round again: the ghost is the variant before.
    _param(page, "size").locator(".param-number").fill("25")
    expect(_summary(page)).to_contain_text("1 change staged, valid", timeout=10000)
    _applied(page)
    expect(ghost).to_contain_text("Ghost of the variant before, 30.00 × 30.00 × 30.00 mm")
    expect(ghost).to_contain_text("−5.00 × −5.00 × −5.00 mm")
    # Part › View › Ghost hides it, as the tick-box does.
    _ring(page, "Part", "View", "Ghost")
    expect(page.locator("#ghost-toggle")).not_to_be_checked()
    expect(ghost).to_be_hidden()
    assert not page.evaluate(
        "() => window.fractalViewer.scene.children.some((o) => o.userData.ghost)"
    )

    # f frames it as drawn, Selected and its editor kept open; the ring's Part › View ›
    # Fit does the same.
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    page.keyboard.press("f")
    expect(_status(page)).to_contain_text(f"Framed {PART}; Selected and its editor stay open")
    settled(page)
    drawn = page.evaluate(MESH_BOX, PART)
    middle = [(a + b) / 2 for a, b in zip(drawn["min"], drawn["max"], strict=True)]
    target = page.evaluate("() => window.fractalViewer.orbitControls.target.toArray()")
    assert target == pytest.approx(middle, abs=0.1)
    assert page.evaluate("() => window.fractalViewer.selectedName") == PART
    expect(page.locator(".part-editor[data-target='part:calibration_cube']")).to_be_visible()
    page.evaluate(
        "() => window.fractalViewer.frameCameraForChildren(window.fractalViewer.currentRenderNodes(window.fractalViewer.currentFocusNode()))"
    )
    settled(page)
    _ring(page, "Part", "View", "Fit")
    expect(_status(page)).to_contain_text(f"Framed {PART}")
    settled(page)
    target = page.evaluate("() => window.fractalViewer.orbitControls.target.toArray()")
    assert target == pytest.approx(middle, abs=0.1)


@pytest.mark.e2e
def test_a_render_of_older_scad_says_so_and_leaves_the_newer_check_marked(
    page: Page, url, cube_as_it_was
):
    """A render that lands after the text has moved on is drawn, said to be of older
    SCAD than the editor holds, and does not clear what the newer check marked."""
    _open(page, url)
    _edit(page)
    code = page.locator(".scad-editor .cm-content")
    expect(code).to_be_visible(timeout=20000)
    # Renders answer late, so the text can move on while one is under way.
    page.evaluate(
        """() => { const real = window.fetch;
            window.fetch = async (url, init) => {
                const r = await real(url, init);
                if (String(url).includes('/draft/render')) await new Promise((ok) => setTimeout(ok, 2500));
                return r;
            }; }"""
    )
    code.click(position={"x": 24, "y": 8})  # its first line: in view in Selected's window
    page.keyboard.press("Control+End")
    with page.expect_request(lambda r: "/draft/render" in r.url, timeout=30000):
        page.keyboard.insert_text("\ntranslate([0, 0, size]) cube(2);")
    page.keyboard.insert_text('\nassert(false, "not this either");')
    page.wait_for_function(
        "() => (window.fractalViewer.scadEditor?.marked ?? []).some((m) => m.severity === 'error')",
        timeout=15000,
    )
    expect(_status(page)).to_contain_text(
        f"{PART} drawn from older SCAD than the editor holds now", timeout=60000
    )
    expect(_status(page)).not_to_contain_text("regenerated")
    assert page.evaluate(
        "() => window.fractalViewer.scadEditor.marked.some((m) => m.severity === 'error')"
    )
    expect(page.locator(".scad-said")).to_contain_text("Not rendered until it reads")
    expect(page.locator(".cm-lintRange-error")).to_have_count(1)
    assert re.search(rf"[?&]variant={PART}", page.url)


# --- what a section reads while Selected is drawn without it ----------------------------


@pytest.mark.e2e
def test_a_part_selected_again_after_a_double_click_shows_what_its_section_read(
    page: Page, url, cube_as_it_was
):
    """A double-click on a part's row selects it, steps in and draws Selected with nothing
    selected; a click selects it again, and its section is put in Selected as it was.
    What the server answered between -- the part's readiness, its size, its controls --
    is in the section then. The server's answers are held here until the double-click
    has drawn Selected empty, so they land while the section is out of the page."""
    _open(page, url)
    held, holding = [], [True]

    def hold(route):
        if holding[0]:
            held.append(route)
        else:
            route.continue_()

    page.route(f"**/parts/{PART}/**", hold)
    row = page.locator(f"#contents-list .contents-item[data-path='{PART}']")
    with page.expect_request(lambda r: f"/parts/{PART}/checklist" in r.url):
        row.dblclick()
    expect(page.locator("#selected-body .no-selection")).to_be_visible()
    holding[0] = False
    with page.expect_response(lambda r: f"/parts/{PART}/checklist" in r.url):
        for route in held:
            route.continue_()
    page.evaluate("() => window.fractalViewer.scadLoading")
    page.evaluate("() => window.fractalViewer.editorLoading")
    row.click()
    section = page.locator(f".part-editor[data-target='part:{PART}']")
    expect(section.locator("#part-checklist .verdict")).to_be_visible()
    expect(section.locator("#part-envelope .measured")).to_contain_text("measured")
    expect(section.locator("#part-params .param")).not_to_have_count(0)
