"""The Models window, as a person goes through it against the simulated qmcp.

⊞ Windows › Models opens it beside the world: qmcp answering with its one model,
and each origin with its switch. A shape clicked on the bench's mat is named
there; Ask reads its colour off its pixels and asks the model, each guess not
checked; a person's word strikes the model's guess through; and the model
switched off leaves the view, its switch kept across a reload. A narrow window reads
its table down, a wide one across. docs/models-checklist.md walks the same paths by
hand; walkthrough pages 35 and 36 are what the two tests write.

Its server is the module's own, with the simulated qmcp and the stated picture
(tests/views_helpers.py's) pinned at the workbench, its shapes found.
"""

from __future__ import annotations

import json

import httpx
import pytest
import windows
from doc_capture import moments
from garage import NAME, drawn, open_garage, said
from garage import picture as stated_picture
from playwright.sync_api import expect
from viewer_ready import OCCLUSION_TESTED, settled
from views_helpers import HIGH, SHAPES, WIDE

MODEL = "qmcp/simulated-vlm@0"
COIN = 1  # tests/views_helpers.py's coin, in front of everything on the mat
ASKED = ("colour", "material", "label")
MODELS = ".panel[data-panel='models']"
# What changes on every run whatever the page does: the moments.
CHANGING = moments(MODELS, "#status")

# Straight down on the bench's mat from 1400 mm over its middle, a little in front.
LOOK_DOWN = """([x, y, z]) => {
    const v = window.fractalViewer;
    v.orbitControls.target.copy(v.sceneAt(x, y, z));
    v.camera.position.copy(v.sceneAt(x, y - 70, z + 1400));
    v.orbitControls.update();
}"""

# A point of a shape on the page where a click chooses it, as the page's own pick
# says, with nothing standing over the canvas there; null where none does.
ON_THE_SHAPE = """([index, min, max]) => {
    const v = window.fractalViewer, r = v.canvas.getBoundingClientRect();
    const view = window.apothecaryPictures.drawnAt('workbench');
    for (let i = 1; i < 6; i++) for (let j = 1; j < 6; j++) {
        const fx = min[0] + (max[0] - min[0]) * i / 6, fy = min[1] + (max[1] - min[1]) * j / 6;
        const p = window.apothecaryPictures.scenePoint(view.id, fx, fy).project(v.camera);
        const at = { clientX: r.left + (p.x + 1) / 2 * r.width, clientY: r.top + (1 - p.y) / 2 * r.height };
        const hit = v.raycastPick(at);
        if (hit && hit.pick && hit.pick.index === index
            && document.elementFromPoint(at.clientX, at.clientY) === v.canvas) return [at.clientX, at.clientY];
    }
    return null;
}"""


def _serve(start_server, tmp_path_factory) -> str:
    """A server of its own: the simulated qmcp, and the stated picture pinned at the
    workbench, its shapes found."""
    folder = tmp_path_factory.mktemp("models_pictures")
    (folder / f"{NAME}.png").write_bytes(stated_picture())
    (folder / f"{NAME}.shapes.json").write_text(
        json.dumps({"name": NAME, "pixel_width": WIDE, "pixel_height": HIGH, "shapes": SHAPES}),
        encoding="utf-8",
    )
    url = start_server({"APOTHECARY_QMCP": "simulated", "APOTHECARY_PICTURE_ROOT": str(folder)})
    with httpx.Client(base_url=url, timeout=15.0) as http:
        view = http.post(
            "/sites/garage/views",
            json={"host": "workbench", "picture": f"{NAME}.png", "mm_across": 1800},
        )
        view.raise_for_status()
        http.post(
            f"/sites/garage/views/{view.json()['id']}/find", json={"finder": "stated"}
        ).raise_for_status()
    return url


@pytest.fixture(scope="module")
def url(base_url, start_server, tmp_path_factory):
    """The story's server. ``base_url`` is asked for only so that with no server to run
    against this is skipped, as every browser test is."""
    return _serve(start_server, tmp_path_factory)


@pytest.fixture(scope="module")
def narrow_url(base_url, start_server, tmp_path_factory):
    """The narrow window's server, apart from the story's, so neither page shows a
    word the other said."""
    return _serve(start_server, tmp_path_factory)


def _switch(models, origin: str):
    return models.locator(f".models-switch[data-origin='{origin}']")


@pytest.mark.e2e
def test_the_models_window_asks_about_a_shape_and_a_person_overrules_it(page, url, walkthrough):
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    story = walkthrough(
        ordinal="35",
        slug="the-models-window",
        title="The Models window",
        intro=(
            "Image models through qmcp, asked only when a person asks: a shape chosen on a "
            "picture's mat, its colour read off its pixels by the plain reader beside each "
            "model's guess at its colour, material and label, every guess shown and used "
            "for nothing, and a person's word ahead of any guess. "
            "[docs/models-checklist.md](../docs/models-checklist.md) walks the same paths "
            "by hand."
        ),
        runtime=(
            "It drives a real browser against a real server of its own, with the simulated "
            "qmcp and its one model, and the stated picture pinned at the workbench, its "
            "shapes found. No model runs; nothing reaches a network."
        ),
        does_not_show=[
            "**A real model.** The simulated qmcp answers the same each time; a model "
            "through a real qmcp is the checklist's.",
            "**Checking a model.** It is not built "
            "([the plan](../docs/plans/image-models-through-qmcp-2026-10-30.md)), so no "
            "guess is trusted, and the window says so.",
            "**What changes on every run.** Moments are blanked in the pictures.",
        ],
        browser_suite_only=True,
    )
    open_garage(page, url)
    page.wait_for_function(
        "() => window.apothecaryPictures.state().some((e) => e.host === 'workbench' && e.mat)"
    )

    # Opened from ⊞ Windows: qmcp answering, both origins switched on, nothing chosen.
    windows.from_the_windows_menu(page, "models")
    models = windows.panel(page, "models")
    expect(models.locator(".models-state")).to_contain_text("the simulated qmcp is answering")
    for origin in ("plain/colour", MODEL):
        expect(_switch(models, origin)).to_be_checked()
    expect(models.locator(".models-chosen")).to_contain_text(
        "Choose a shape on a picture's mat to ask about it"
    )
    expect(models.locator(".models-ask")).to_have_count(0)
    expect(models.locator(".models-note")).to_contain_text(
        "every guess is a guess: checking a model is not built, so none is trusted"
    )
    story.shows(
        "⊞ Windows › Models: qmcp answering, and no guess trusted",
        "The header's ⊞ Windows, Models under Pictures: beside the world, qmcp answering "
        "with its one model, the plain reader and the model each with its switch, on. "
        "Checking a model is not built, so the window says none of its guesses is trusted. "
        "Nothing is chosen yet.",
        blank=CHANGING,
    )

    # The coin clicked on the bench's mat is the shape Models asks about.
    page.evaluate(LOOK_DOWN, drawn(page, "workbench")["mat"]["centre"])
    settled(page, frames=OCCLUSION_TESTED)
    shape = SHAPES[COIN]
    at = page.evaluate(ON_THE_SHAPE, [COIN, shape["min"], shape["max"]])
    assert at, "no point of the coin is picked as the coin"
    page.mouse.click(*at)
    expect(models.locator(".models-chosen")).to_contain_text(
        f"Shape {COIN}, a {shape['kind']}, in {NAME}.png at workbench"
    )
    story.shows(
        "A shape clicked on the bench's mat is the one Models asks about",
        "Looking straight down on the workbench's mat, the coin clicked: Models names it, "
        "its shape and the picture it is in, and offers Ask.",
        shown=models.locator(".models-chosen").inner_text(),
        blank=CHANGING,
    )

    # Ask: a row for each property asked, the colour read off its pixels and each
    # guess not checked.
    models.locator(".models-ask").click()
    expect(models.locator(".models-said")).to_contain_text("the simulated qmcp answered")
    rows = models.locator(".models-table tbody tr")
    expect(rows).to_have_count(len(ASKED))
    for i, prop in enumerate(ASKED):
        expect(rows.nth(i)).to_have_attribute("data-property", prop)
    colour = models.locator("tr[data-property='colour']")
    expect(colour.locator("td").nth(0).locator(".swatch")).to_have_count(1)
    expect(colour.locator("td").nth(1)).to_contain_text("not checked")
    story.shows(
        "Ask: the colour read off its pixels, and each guess not checked",
        "Ask: a row for each property asked -- colour, material, label -- the colour the "
        "plain reader read off the coin's pixels with its swatch, and the model's guess at "
        "each, marked not checked.",
        blank=CHANGING,
    )

    # A person's word on the label comes first, and the model's guess is struck through.
    label = models.locator("tr[data-property='label']")
    word = label.locator("input.models-word")
    word.fill("lens cap")
    word.press("Enter")
    said(page, "lens cap")
    expect(label.locator("td").nth(2)).to_contain_text("lens cap")
    guess = label.locator("td").nth(1)
    expect(guess).to_contain_text("overruled by a person")
    struck = guess.locator(".overruled").first
    expect(struck).to_have_css("text-decoration-line", "line-through")
    story.shows(
        "A person's word comes first, the model's guess struck through",
        "lens cap typed in the label's row and Enter: a person's word is the label now, "
        "and the model's guess is struck through, overruled by a person.",
        blank=CHANGING,
    )

    # The model switched off: its guesses leave every row, what was read and said stays.
    _switch(models, MODEL).uncheck()
    said(page, f"{MODEL} is switched off")
    expect(colour).to_contain_text("1 guess not shown: switched off")
    expect(colour.locator("td").nth(0).locator(".swatch")).to_have_count(1)
    expect(label.locator("td").nth(2)).to_contain_text("lens cap")
    story.shows(
        "The model switched off: its guesses leave every row",
        "The model's switch, off: its guesses leave every row, each saying a guess is "
        "not shown, while what the plain reader read and what a person said stay.",
        blank=CHANGING,
    )

    # The switch is kept: after a reload Models shows the model still switched off.
    open_garage(page, url, settle=False)
    windows.open_window(page, "models")
    models = windows.panel(page, "models")
    expect(models.locator(".models-state")).to_contain_text("the simulated qmcp is answering")
    expect(_switch(models, MODEL)).not_to_be_checked()
    expect(_switch(models, "plain/colour")).to_be_checked()
    story.says(
        "Reloaded, the model is still switched off",
        "The page opened again and Models with it: qmcp answering, the plain reader on, "
        "and the model still off, as it was left; switched on again after.",
        shown=models.locator(".models-state").inner_text(),
    )
    _switch(models, MODEL).check()
    said(page, f"{MODEL} is switched on")
    assert errors == []


# Each row's cells, as laid out: where each starts and how wide it is, and the name
# its column gives it in front of it, if any.
LAID_OUT = """(row) => [...row.querySelectorAll('td')].map((td) => {
    const b = td.getBoundingClientRect(), named = getComputedStyle(td, '::before').content;
    return { left: Math.round(b.left), top: Math.round(b.top), bottom: Math.round(b.bottom),
             width: Math.round(b.width), named: named === 'none' ? null : named.replace(/"/g, '') };
})"""

# Anything from the table up to the window's body that is wider than it shows.
ACROSS = """(table) => {
    const panel = table.closest('.panel'), wide = [];
    for (let el = table; el && el !== panel.parentElement; el = el.parentElement)
        if (el.scrollWidth > el.clientWidth + 1) wide.push(el.className || el.tagName);
    return wide;
}"""


@pytest.mark.e2e
def test_a_narrow_models_window_reads_down_and_a_wide_one_is_a_table(page, narrow_url, walkthrough):
    """Beside the world on a page 1024 px wide, the table reads down: each property,
    then Read, Guessed and A person each on a line of its own, named, and nothing is
    reached by a scroll across. Widened, it is a table again."""
    story = walkthrough(
        ordinal="36",
        slug="the-models-window-narrow-and-wide",
        title="The Models window, narrow and wide",
        intro=(
            "The Models window's table as wide as the window it is in: beside the world on "
            "a narrow page, each property reads down, Read, Guessed and A person each on a "
            "line of its own and named; on a wide one, it is a table. "
            "[Page 35](35-the-models-window.md) is the window from the start."
        ),
        runtime=(
            "It drives a real browser against a real server of its own, as page 35's is: "
            "the simulated qmcp, and the stated picture pinned at the workbench. The page "
            "is 1024 px wide, then 1920."
        ),
        does_not_show=[
            "**What changes on every run.** Moments are blanked in the pictures.",
        ],
        browser_suite_only=True,
    )
    page.set_viewport_size({"width": 1024, "height": 768})
    open_garage(page, narrow_url)
    page.wait_for_function(
        "() => window.apothecaryPictures.state().some((e) => e.host === 'workbench' && e.mat)"
    )
    windows.from_the_windows_menu(page, "models")
    models = windows.panel(page, "models")
    page.evaluate(LOOK_DOWN, drawn(page, "workbench")["mat"]["centre"])
    settled(page, frames=OCCLUSION_TESTED)
    shape = SHAPES[COIN]
    page.mouse.click(*page.evaluate(ON_THE_SHAPE, [COIN, shape["min"], shape["max"]]))
    models.locator(".models-ask").click()
    # Answered, so the rows measured are the ones Ask drew last.
    expect(models.locator(".models-said")).to_contain_text("the simulated qmcp answered")
    expect(models.locator(".models-table tbody tr")).to_have_count(len(ASKED))
    table = models.locator(".models-table")

    expect(table.locator("thead")).to_be_hidden()
    for prop in ASKED:
        row = models.locator(f"tr[data-property='{prop}']")
        cells = row.evaluate(LAID_OUT)
        assert [c["named"] for c in cells] == ["Read", "Guessed", "A person"], prop
        for above, below in zip(cells, cells[1:], strict=False):
            assert below["top"] >= above["bottom"] - 1, (prop, cells)
        width = table.evaluate("(t) => t.getBoundingClientRect().width")
        assert all(c["width"] >= width * 0.9 for c in cells), (prop, width, cells)
    assert table.evaluate(ACROSS) == []
    word = models.locator("tr[data-property='label'] input.models-word").bounding_box()
    right = models.evaluate("(p) => p.getBoundingClientRect().right")
    assert word and word["x"] + word["width"] <= right, (word, right)
    models.locator("tr[data-property='label']").scroll_into_view_if_needed()
    story.shows(
        "Narrow, each property reads down",
        "On a page 1024 px wide, Models beside the world, a shape asked about: each "
        "property's row reads down, Read, Guessed and A person each on a line of its own "
        "and named, and the box for a person's word inside the window, nothing reached by "
        "a scroll across.",
        blank=CHANGING,
    )

    # Wide, the table is a table: its head shown, a row's cells side by side, unnamed.
    page.set_viewport_size({"width": 1920, "height": 1080})
    expect(table.locator("thead")).to_be_visible()
    cells = models.locator("tr[data-property='label']").evaluate(LAID_OUT)
    assert len({c["top"] for c in cells}) == 1, cells
    assert [c["named"] for c in cells] == [None, None, None]
    story.shows(
        "Wide, it is a table",
        "The page widened to 1920 px: the table's head shown, and each property's cells "
        "side by side under it, unnamed.",
        blank=CHANGING,
    )
