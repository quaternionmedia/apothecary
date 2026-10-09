"""A piece made from a picture is edited in the one editor, from its ring: Part › Edit
opens it in Selected with the cursor in its first control, a slider stages a change
the stage bar validates, Apply rebuilds the piece where it stands -- its outline and
its thread stay -- and the found candidate returns it. A part in the parts library
gets the same editor from the same cell.

The picture is tests/e2e/test_picture_in_the_world.py's stated fixture, pinned at the
bench at 1800 mm through the API, and shape 1 (the coin, 54 by 54 mm, its thickness
guessed at 8.1) made through the API too, so no camera is opened. Everything a test
adds is taken back after it, and garage is reset.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect
from test_picture_in_the_world import (  # noqa: F401 - a fixture
    _open_garage,
    _pin,
    fixture_picture,
    leaves_garage_as_found,  # noqa: F401 - a fixture
)
from test_the_loop import _labels, _press, _ring_on, _said

MESH = """(key) => {
    const mesh = window.fractalViewer.meshByName[key];
    if (!mesh) return null;
    const g = mesh.geometry;
    g.computeBoundingBox();
    const s = g.boundingBox.max.clone().sub(g.boundingBox.min);
    return { size: [s.x, s.y, s.z], placeholder: !!mesh.userData.isPlaceholder };
}"""


def _footprint_size(page, piece: str) -> list:
    return page.evaluate(
        "(name) => { const n = window.fractalViewer.nodeByPath(name);"
        " return n.footprint.max.map((v, i) => v - n.footprint.min[i]); }",
        piece,
    )


def _centre(page, piece: str) -> list:
    return page.evaluate(
        "(name) => { const b = window.fractalViewer.nodeByPath(name).world_bounds;"
        " return [(b.min[0] + b.max[0]) / 2, (b.min[1] + b.max[1]) / 2, b.min[2]]; }",
        piece,
    )


def _slide(page, field: str, value: float) -> float:
    """Drag a slider to ``value``; the value it settles on, since a slider snaps to its step."""
    return page.locator(f"#part-params .param[data-field='{field}'] input[type=range]").evaluate(
        "(el, v) => { el.value = v; el.dispatchEvent(new Event('input')); return Number(el.value); }",
        value,
    )


def _mm(value: float) -> str:
    """A number as the page's status and facts write it: to a tenth, no trailing zero."""
    return f"{round(value, 1):g}"


def _made_piece(page, base_url: str, picture: str) -> str:
    view = _pin(page, base_url, "workbench", picture, mm_across=1800)
    answer = page.request.post(
        f"{base_url}/sites/garage/views/{view['id']}/make", data={"shape": 1}
    )
    assert answer.status == 200, answer.text()
    return answer.json()["made"][0]


@pytest.mark.e2e
@pytest.mark.usefixtures("leaves_garage_as_found")
def test_a_made_piece_is_edited_from_its_ring_and_the_found_candidate_returns_it(
    page,
    base_url: str,
    fixture_picture,  # noqa: F811 - the fixture's value, the picture's name
):
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    piece = _made_piece(page, base_url, fixture_picture)
    _open_garage(page, base_url)
    page.wait_for_function(
        "() => window.apothecaryPictures.state().some((e) => e.host === 'workbench' && e.outlines.length)",
        timeout=10000,
    )
    stood = _centre(page, piece)

    # Why this first, so there is a thread to keep.
    _ring_on(page, piece)
    _press(page, "Why this")
    _said(page, "made from shape 1")
    assert page.evaluate("() => window.apothecaryPictures.traced()")["piece"] == piece

    # Part › Edit: the editor in Selected, under the piece's provenance, its first
    # control focused. Height is contested (a guess), so it comes first; width has
    # a slider and, as found, no candidate yet.
    _ring_on(page, piece)
    assert _labels(page)[-2:] == ["Picture", "Part"]
    _press(page, "Part", "Edit")
    _said(page, f"Editing {piece}")
    params = page.locator("#part-params")
    width = params.locator(".param[data-field='width']")
    expect(width.locator("input[type=range]")).to_be_visible(timeout=10000)
    expect(width.locator(".cand")).to_have_count(0)
    height = params.locator(".param[data-field='height']")
    expect(height).to_have_class(re.compile(r"\bis-contested\b"))
    expect(height.locator(".cand")).to_have_count(1)
    expect(height.locator(".cand .note")).to_contain_text("cannot see thickness")
    expect(params.locator("input, select").first).to_be_focused(timeout=5000)
    facts = page.locator("#selected-body .picture-facts[data-facts='made']")
    expect(facts).to_contain_text("Size: 54 × 54 × 8.1 mm, as found; thickness a guess")
    assert (
        facts.evaluate("(el) => el.compareDocumentPosition(document.getElementById('part-params'))")
        & 4
    )
    # A made piece has no checklist and no Regenerate STL: Apply is its rebuild.
    expect(page.locator("#part-checklist")).to_have_count(0)
    expect(page.locator("#part-regenerate-btn")).to_have_count(0)
    expect(page.locator("#part-scad-content")).to_contain_text("cylinder", timeout=10000)

    # Two sliders staged: validated, the envelope said, nothing built yet.
    w = _slide(page, "width", 40)
    d = _slide(page, "depth", 40)
    assert 39 < w < 41 and 39 < d < 41, (w, d)
    summary = page.locator("#stage-summary")
    expect(summary).to_contain_text("2 changes staged, valid", timeout=10000)
    expect(summary).to_contain_text(f"{w:.2f} × {d:.2f} × 8.10 mm")
    assert _footprint_size(page, piece) == pytest.approx([54, 54, 8.1])
    apply = page.locator("#apply-btn")
    expect(apply).to_have_text("Apply 2 changes")

    # Apply: rebuilt where it stands, and the status says what was built and found.
    apply.click()
    _said(page, f"{piece} rebuilt {_mm(w)} × {_mm(d)} × 8.1 mm; found 54 × 54, thickness a guess")
    assert _footprint_size(page, piece) == pytest.approx([w, d, 8.1])
    assert _centre(page, piece) == pytest.approx(stood, abs=0.01)
    expect(summary).to_have_text("No staged changes")
    # The mesh on screen follows: its real geometry, as wide as the slider said.
    page.wait_for_function(
        "(key) => { const m = window.fractalViewer.meshByName[key]; return m && !m.userData.isPlaceholder; }",
        arg=piece,
        timeout=30000,
    )
    mesh = page.evaluate(MESH, piece)
    assert max(mesh["size"]) == pytest.approx(max(w, d), abs=0.5), mesh
    # Its outline and its thread stay, and so does the selection.
    drawn = next(
        e
        for e in page.evaluate("() => window.apothecaryPictures.state()")
        if e["host"] == "workbench"
    )
    assert any(o["index"] == 1 and o["status"] == "made" for o in drawn["outlines"])
    traced = page.evaluate("() => window.apothecaryPictures.traced()")
    assert traced and traced["piece"] == piece and traced["visible"]
    assert page.evaluate("() => window.fractalViewer.selectedName") == piece
    expect(facts).to_contain_text(
        f"Size: {_mm(w)} × {_mm(d)} × 8.1 mm, a person's (found 54 × 54); thickness a guess"
    )

    # The found sides are candidates now, one click away; taking them returns the piece.
    expect(width.locator(".cand")).to_have_count(1, timeout=10000)
    expect(width.locator(".cand b")).to_have_text("54")
    width.locator(".cand").click()
    params.locator(".param[data-field='depth'] .cand").click()
    expect(apply).to_have_text("Apply 2 changes", timeout=10000)
    expect(apply).to_be_enabled()
    apply.click()
    _said(page, f"{piece} rebuilt 54 × 54 × 8.1 mm; found 54 × 54, thickness a guess")
    record = page.request.get(f"{base_url}/sites/garage/attached").json()["made"][piece]
    assert record["parameters_stated"] is False
    expect(facts).to_contain_text("Size: 54 × 54 × 8.1 mm, as found")
    assert errors == []


@pytest.mark.e2e
def test_a_part_in_the_library_gets_the_same_editor_from_the_same_cell(page, base_url: str):
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"{base_url}/viewer/sites/parts_library")
    expect(page.locator("#status")).to_contain_text("Loaded", timeout=20000)
    _ring_on(page, "v_slot")
    assert _labels(page)[-1] == "Part"
    _press(page, "Part", "Edit")
    _said(page, "Editing v_slot")
    expect(page.locator("#part-params input[type=range]").first).to_be_focused(timeout=10000)
    # A part has what a made piece lacks: its checklist and Regenerate STL.
    expect(page.locator("#part-checklist")).to_be_visible()
    expect(page.locator("#part-regenerate-btn")).to_be_visible()
    expect(page.locator("#stage-summary")).to_have_text("No staged changes")
    assert errors == []
