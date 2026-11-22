"""A printed piece checked against its design: the Measure layer and Part › Feedback as one
act. The footpedal sliced for printer_1, Measure shown, its box's x is a dimension marked
in the world; its label clicked brings Part › Feedback on its piece with x's row given the
caret, what calipers read is typed and kept with Enter, and the reading is checked against
the design -- in Feedback's row, in its filed check, and on x in the world, coloured by
whether it is within the piece's tolerance. The footpedal is drawn as it rests and prints
on its button face, so its y and z are read in Feedback alone, which the reading says; y
read there is a check alone. A reload finds both kept.
Walkthrough page 55 is what it writes.

Runs against a server of its own, the scripted OrcaSlicer its slicer (tests/slicer_helpers.py).
Nothing is armed, started or sent to a machine.
"""

from __future__ import annotations

import re

import pytest
import windows
from doc_capture import moments
from garage import open_garage, said, select
from playwright.sync_api import Page, expect
from slicer_helpers import write_fake_orcaslicer
from viewer_ready import settled

SLICED_MS = 30000
PART = "footpedal"
CHANGING = tuple(moments(".panel", "#status"))

# Where a dimension's label stands, in the page's pixels, once the layer has laid it; null
# while it is not laid, or not a pick.
LABEL = """(name) => {
    const v = window.fractalViewer, r = v.canvas.getBoundingClientRect();
    const p = v.measure.picks.find((x) => x.name === name);
    if (!p) return null;
    const at = { x: r.left + (p.box.l + p.box.r) / 2, y: r.top + (p.box.t + p.box.b) / 2 };
    return document.elementFromPoint(at.x, at.y) === v.canvas ? at : null;
}"""

# A dimension's label as the world draws it: its words and its ink.
DRAWN = """(name) => {
    const s = window.fractalViewer.measure.labels.find((l) => l.userData.pick && l.userData.pick.name === name);
    return s ? { text: s.userData.text, ink: s.userData.ink } : null;
}"""


def _mm(v: float) -> str:
    """A size as the page's fields and status lines write it (static/format.js ``mm``): to
    three places at the most, no trailing zeros."""
    return f"{f'{v:.3f}'.rstrip('0').rstrip('.')} mm"


TOKENS = """() => {
    const css = getComputedStyle(document.documentElement);
    return { ok: css.getPropertyValue('--ok').trim(), bad: css.getPropertyValue('--bad').trim() };
}"""


@pytest.fixture(scope="module")
def url(base_url, start_server, tmp_path_factory):
    """This module's own server, the scripted OrcaSlicer its slicer."""
    orca = write_fake_orcaslicer(tmp_path_factory.mktemp("orca"))
    return start_server({"APOTHECARY_ORCASLICER": str(orca)})


def _measuring(page: Page) -> None:
    """Measure shown in the Layers window, the footpedal selected and framed."""
    windows.from_the_windows_menu(page, "layers")
    page.locator(
        ".panel[data-panel='layers'] input[data-layer='measure'][data-kind='shown']"
    ).check()
    said(page, "Measure: on")
    select(page, PART)
    page.locator("#viewer-canvas").focus()
    page.keyboard.press("f")
    settled(page)


def _pick(page: Page, name: str) -> None:
    """The dimension's label, once laid, clicked."""
    page.wait_for_function(f"(n) => ({LABEL})(n) !== null", arg=name, timeout=15000)
    at = page.evaluate(LABEL, name)
    page.mouse.click(at["x"], at["y"])


@pytest.mark.e2e
def test_a_dimension_clicked_in_the_world_is_read_into_the_piece_s_feedback(
    page: Page, url: str, walkthrough
):
    """x clicked on the footpedal opens its cabinet on its kept slice with x's row given the
    caret and its designed size said; a reading outside the default tolerance kept with
    Enter is the first turn of printer_1's tuning, shown in Feedback's row and filed check,
    and on x in the world in the page's colour for outside. y, not drawn as sliced, read
    within in Feedback is a check alone. A reload finds both, in the world and in Feedback."""
    story = walkthrough(
        ordinal="55",
        slug="a-printed-piece-checked-against-its-design",
        title="A printed piece checked against its design",
        intro=(
            "A part's dimensions are what a person reads of a piece of it with calipers. With "
            "the Measure layer shown, a part's piece selected wears them in the world; a "
            "dimension's label clicked brings Part › Feedback on the piece, its row ready for "
            "what calipers read; and the reading, kept in the piece's drawer, is checked "
            "against the design, there and on the dimension in the world. "
            "[docs/cabinet.md](../docs/cabinet.md#dimensions) is the reference."
        ),
        runtime=(
            "It drives a real browser against a real server of its own, the slicer a scripted "
            "OrcaSlicer: the footpedal is sliced for printer_1, and nothing is printed, armed "
            "or sent. The readings are typed as a person types them."
        ),
        does_not_show=[
            "**A part that names a plan.** The print coupon's dimensions are its plan's "
            "features, each drawn along the line its jaws close on; this page reads a box's "
            "(`tests/test_cabinet.py`, `tests/test_measure_world.py`).",
            "**A tolerance from the part or the printer.** The footpedal's print settings and "
            "printer_1's profile state none, so the default is used and said "
            "(`test_the_tolerance_is_the_part_s_else_the_printer_s_profile_s_else_a_default`).",
            "**What changes on every run.** Moments are blanked in the pictures.",
        ],
        browser_suite_only=True,
    )
    errors: list = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    open_garage(page, url, settle=False)
    page.wait_for_function(
        "() => window.fractalViewer.machinesHere.some((m) => m.path === 'printer_1')",
        timeout=15000,
    )
    select(page, PART)
    expect(page.locator("#make-here")).to_have_text(re.compile("on printer_1"), timeout=15000)
    page.locator("#make-here").click()
    expect(page.locator("#status")).to_contain_text("kept and chosen", timeout=SLICED_MS)
    record = next(
        r for r in page.request.get(f"{url}/slicer/slices").json() if r["made"]["name"] == PART
    )
    x, y, _ = record["size"]
    # What calipers read, as typed, and how far each is from its design: x past the default
    # tolerance, y inside it.
    read_x, read_y = f"{x + 0.31:.2f}", f"{y + 0.05:.2f}"
    off_x, off_y = f"{float(read_x) - x:+.2f}", f"{float(read_y) - y:+.2f}"
    tokens = page.evaluate(TOKENS)

    _measuring(page)
    # The footpedal is drawn as it rests, its wedge on its base; it prints on its button
    # face. Its x is the same side either way and is marked; y and z, the box it was
    # sliced in, are read in Feedback, and the reading says so.
    page.wait_for_function(f"(n) => ({LABEL})(n) !== null", arg="x", timeout=15000)
    assert re.fullmatch(r"x \d+\.\d\d mm · mesh", page.evaluate(DRAWN, "x")["text"])
    assert page.evaluate("() => window.fractalViewer.measure.picks.map((p) => p.name)") == ["x"]
    reading = page.locator(".panel[data-panel='layers'] .layers-reading")
    expect(reading).to_contain_text(
        f"{PART}'s dimensions, as printed on printer_1: its kept file {record['file_id']}, no "
        "drawer yet, each checked within ± 0.20 mm (a default, 0.2 mm: neither footpedal's "
        "print settings nor printer_1's profile states one); a dimension's label clicked "
        "takes its reading in Part › Feedback"
    )
    expect(reading).to_contain_text(
        f"{PART}'s y, z: not drawn here, the part drawn not being as it was sliced (as it "
        "rests, or another variant); read in Part › Feedback"
    )

    # x clicked: Feedback on the piece, x's row marked and given the caret; no point dropped.
    _pick(page, "x")
    feedback = windows.panel(page, "part-feedback")
    expect(feedback.locator("#feedback-title")).to_have_text(f"Feedback · {PART}", timeout=10000)
    expect(page.locator("#status")).to_contain_text(
        f"x, the part across X, at its widest: designed {_mm(x)}. Type what calipers read of "
        f"{PART}'s piece in its row under measured, then Enter"
    )
    expect(feedback.locator(".measure-row.picked")).to_have_attribute("data-feature", "x")
    page.wait_for_function("() => document.activeElement?.dataset?.feature === 'x'")
    assert page.evaluate("() => window.fractalViewer.measure.points.length") == 0
    expect(feedback.locator("#feedback-measure-said")).to_contain_text(
        "of 3 features of its box · tolerance ± 0.20 mm, a default"
    )

    # Typed and kept with Enter: printer_1's first turn, x outside ± 0.20 mm.
    page.keyboard.type(read_x)
    page.keyboard.press("Enter")
    expect(page.locator("#status")).to_contain_text(
        f"turn-1 filed in {PART}'s drawer, for printer_1", timeout=10000
    )
    check = feedback.locator('.measure-row[data-feature="x"] .measure-check')
    expect(check).to_have_text(f"{read_x} {off_x} ✗")
    expect(check).to_have_class(re.compile("outside"))
    expect(feedback.locator("#feedback-filed .feedback-checks .outside")).to_have_text(
        f"x {read_x} mm against {x:.2f} designed, {off_x}: outside ± 0.20 (a default)"
    )
    page.wait_for_function(f"() => ({DRAWN})('x')?.text.includes('read')", timeout=10000)
    drawn = page.evaluate(DRAWN, "x")
    assert drawn["text"].endswith(f" mm · mesh · read {read_x} {off_x}"), drawn
    assert drawn["ink"] == tokens["bad"]
    expect(reading).to_contain_text(
        f"{PART}'s x, the part across X, at its widest: designed {x:.2f} mm, read "
        f"{read_x} mm (filed-1, turn-1), {off_x} mm: outside ± 0.20, a default"
    )
    # The reading in view, under the Layers window's rows, as the caption reads it.
    reading.first.scroll_into_view_if_needed()
    settled(page)
    story.shows(
        "A dimension clicked, read, and checked against its design",
        "Measure shown and the footpedal selected and framed. Its x is a dimension of the "
        "piece as sliced, marked on the part; its label clicked brought Part › Feedback on "
        "its kept slice with x's row given the caret, and what calipers read was typed and "
        "kept with Enter. Feedback's row and the filed check say how far it is from the "
        "design, outside the default ± 0.20 mm, and x's line and label in the world wear the "
        "page's colour for outside. The part is drawn as it rests, so its y and z are read "
        "in Feedback alone, as the reading under Layers says.",
        blank=CHANGING,
    )

    # y read within, in its row in Feedback: the piece's last turn already reads it, so a
    # check alone, and said under Layers too.
    field = feedback.locator('input.measure-read[data-feature="y"]')
    field.fill(read_y)
    field.press("Enter")
    expect(page.locator("#status")).to_contain_text(
        f"a check filed in {PART}'s drawer, for printer_1: "
        f"y {read_y} mm against {y:.2f} designed, {off_y}: within ± 0.20 (a default): "
        "kept as a check of the piece, and no turn: turn-1 already reads it for printer_1's "
        "tuning",
        timeout=10000,
    )
    expect(feedback.locator('.measure-row[data-feature="y"] .measure-check')).to_have_class(
        re.compile("within")
    )
    expect(reading).to_contain_text(
        f"{PART}'s y, the part across Y, at its widest: designed {y:.2f} mm, read {read_y} mm "
        f"(filed-2), {off_y} mm: within ± 0.20, a default"
    )

    # Kept: a reload, Measure shown again (it is the session's), finds them.
    page.reload()
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=20000)
    settled(page)
    _measuring(page)
    page.wait_for_function(f"() => ({DRAWN})('x')?.text.includes('read')", timeout=15000)
    drawn = page.evaluate(DRAWN, "x")
    assert drawn["text"].endswith(f" mm · mesh · read {read_x} {off_x}"), drawn
    assert drawn["ink"] == tokens["bad"]
    _pick(page, "x")
    expect(page.locator("#status")).to_contain_text(
        f"x, the part across X, at its widest: designed {_mm(x)}; last read {read_x} mm, "
        f"{off_x}, outside ± 0.20",
        timeout=10000,
    )
    expect(feedback.locator('.measure-row[data-feature="y"] .measure-check')).to_have_text(
        f"{read_y} {off_y} ✓"
    )
    (drawer,) = page.request.get(f"{url}/cabinet/{PART}").json()["drawers"]
    assert [(f["made"], [c["name"] for c in f["checked"]]) for f in drawer["filed"]] == [
        ("turn-1", ["x"]),
        (None, ["y"]),
    ]
    settled(page)
    story.shows(
        "Kept: the readings on the part after a reload",
        "The page reloaded, Measure shown again and the footpedal selected: x wears its "
        "reading from the piece's drawer, outside its tolerance, and its label clicked again "
        "says its designed size and its last reading. Feedback's rows say the same of the "
        "same drawer, y read within.",
        blank=CHANGING,
    )
    assert errors == []
