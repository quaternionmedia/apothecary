"""The Models window, as a person goes through it against the simulated qmcp.

⊞ Windows › Models opens it beside the world: qmcp answering with its one model,
and each origin with its switch. A shape clicked on the bench's mat is named
there; Ask reads its colour off its pixels and asks the model, each guess not
checked; a person's word strikes the model's guess through; and the model
switched off leaves the view, its switch kept across a reload.
docs/models-checklist.md walks the same paths by hand.

Its server is the module's own, with the simulated qmcp and the stated picture
(tests/views_helpers.py's) pinned at the workbench, its shapes found.
"""

from __future__ import annotations

import json

import httpx
import pytest
import windows
from garage import NAME, drawn, open_garage, said
from garage import picture as stated_picture
from playwright.sync_api import expect
from viewer_ready import OCCLUSION_TESTED, settled
from views_helpers import HIGH, SHAPES, WIDE

MODEL = "qmcp/simulated-vlm@0"
COIN = 1  # tests/views_helpers.py's coin, in front of everything on the mat
ASKED = ("colour", "material", "label")

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


@pytest.fixture(scope="module")
def url(base_url, start_server, tmp_path_factory):
    """This module's own server: the simulated qmcp, and the stated picture pinned at
    the workbench, its shapes found. ``base_url`` is asked for only so that with no
    server to run against this is skipped, as every browser test is."""
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


def _switch(models, origin: str):
    return models.locator(f".models-switch[data-origin='{origin}']")


@pytest.mark.e2e
def test_the_models_window_asks_about_a_shape_and_a_person_overrules_it(page, url):
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
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

    # The model switched off: its guesses leave every row, what was read and said stays.
    _switch(models, MODEL).uncheck()
    said(page, f"{MODEL} is switched off")
    expect(colour).to_contain_text("1 guess not shown: switched off")
    expect(colour.locator("td").nth(0).locator(".swatch")).to_have_count(1)
    expect(label.locator("td").nth(2)).to_contain_text("lens cap")

    # The switch is kept: after a reload Models shows the model still switched off.
    open_garage(page, url, settle=False)
    windows.open_window(page, "models")
    models = windows.panel(page, "models")
    expect(models.locator(".models-state")).to_contain_text("the simulated qmcp is answering")
    expect(_switch(models, MODEL)).not_to_be_checked()
    expect(_switch(models, "plain/colour")).to_be_checked()
    _switch(models, MODEL).check()
    said(page, f"{MODEL} is switched on")
    assert errors == []
