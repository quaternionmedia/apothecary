"""The Badge window: parts/badge composed in the page, a face or the word picked, the
word typed, and the badge drawn made on a machine (apothecary/static/widgets/badge.js).

In the universe, where every part stands, the badge selected and ⊞ Windows › Badge
opened: its six faces and the word, each a cell of its ring's Part › View › Badge,
staged in its editor and drawn at once; the word's text, font and size the Parameters
window's own controls, staged there too and drawn once they rest; ⚒ Cut greyed for a
word, in the part's own words; ⚒ Print and ⚒ Cut taking the badge drawn to the garage,
its printer's or router's window, as ⚒ Make does.

Runs against a server of its own, the scripted OrcaSlicer its slicer, nothing pinned:
the garage's printer and router open as the garage plans them. No real port is opened.
"""

from __future__ import annotations

import pytest
import windows
from garage import row, select, to_site
from playwright.sync_api import Page, expect
from slicer_helpers import write_fake_orcaslicer

DRAWN_MS = 60000
BADGE = "badge"
STATE = "() => window.apothecaryBadge && window.apothecaryBadge.state()"
VARIANT = "() => window.fractalViewer.variantByPart.badge || null"


@pytest.fixture(scope="module")
def url(base_url, start_server, tmp_path_factory):
    """This module's own server, the scripted OrcaSlicer its slicer. ``base_url`` is
    asked for only so that with no server to run against this is skipped, as every
    browser test is."""
    orca = write_fake_orcaslicer(tmp_path_factory.mktemp("orca"))
    return start_server({"APOTHECARY_ORCASLICER": str(orca)})


def _badge_window(page: Page, url: str):
    """The universe, the badge selected and the Badge window opened from ⊞ Windows,
    showing the badge."""
    page.goto(f"{url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=20000)
    to_site(page, "apothecary")
    expect(row(page, BADGE)).to_be_visible(timeout=20000)
    select(page, BADGE)
    windows.from_the_windows_menu(page, "badge")
    window = windows.panel(page, "badge")
    try:
        expect(window.locator(".badge-head")).to_contain_text(BADGE, timeout=20000)
    except AssertionError:
        said = page.evaluate(
            "() => ({ html: document.querySelector(\".panel[data-panel='badge']\")?.innerHTML,"
            " selected: window.fractalViewer.selectedName, status: document.getElementById('status').textContent,"
            " shown: window.apothecaryPanels.state('badge') })"
        )
        pytest.fail(f"the Badge window did not show the badge: {said}")
    return window


def _in_the_garage(page: Page) -> None:
    """The garage opened by ⚒ Print or ⚒ Cut, or the status line's words saying why not."""
    try:
        page.wait_for_function("() => window.fractalViewer.siteName === 'garage'", timeout=20000)
    except Exception:
        said = page.locator("#status").inner_text()
        pytest.fail(f"the garage did not open; the status line says: {said}")


@pytest.mark.e2e
def test_a_face_picked_is_staged_and_drawn_and_its_button_says_its_ring_cell(page: Page, url: str):
    """😉 pressed stages the face wink in the badge's editor and draws it, a variant of the
    badge in the world, the button pressed marked; each face's button wears the address
    of its cell, Part › View › Badge › it."""
    errors: list = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    window = _badge_window(page, url)
    faces = window.locator(".badge-face")
    expect(faces).to_have_count(7)
    assert faces.evaluate_all("(b) => b.map((x) => x.dataset.face)") == [
        "open",
        "smile",
        "neutral",
        "wink",
        "frown",
        "grin",
        "word",
    ]
    expect(window.locator(".badge-face[data-face='smile']")).to_have_attribute(
        "aria-pressed", "true"
    )
    window.locator(".badge-face[data-face='wink']").click()
    expect(page.locator("#status")).to_contain_text("badge: 😉 wink drawn", timeout=DRAWN_MS)
    page.wait_for_function(VARIANT, timeout=DRAWN_MS)
    assert page.evaluate(STATE)["staged"]["face"] == "wink"
    expect(window.locator(".badge-face[data-face='wink']")).to_have_attribute(
        "aria-pressed", "true"
    )
    # The face's own number is the Parameters window's control, here too.
    expect(window.locator(".badge-fields .param[data-field='diameter']")).to_be_visible()
    # Each face's button says its cell of the ring, once the ring is resolved.
    page.wait_for_function(
        "() => /⌗\\d+/.test(document.querySelector(\".badge-face[data-face='grin']\").title)",
        timeout=20000,
    )
    assert errors == [], errors


@pytest.mark.e2e
def test_the_word_is_typed_drawn_and_greyed_for_the_router_in_the_part_s_words(
    page: Page, url: str
):
    """✎ Word: the word's text, font and size shown, the text typed key by key staged in
    Parameters too, every key kept in the Badge window's field, and drawn once the controls
    rest; ⚒ Cut greyed, its tip the part's refusal."""
    errors: list = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    window = _badge_window(page, url)
    window.locator(".badge-face[data-face='word']").click()
    expect(page.locator("#status")).to_contain_text("badge: the word drawn", timeout=DRAWN_MS)
    for field in ("text", "font", "text_size"):
        expect(window.locator(f".badge-fields .param[data-field='{field}']")).to_be_visible()
    cut = window.locator(".badge-make[data-make='router']")
    expect(cut).to_be_disabled()
    expect(cut).to_have_attribute(
        "title",
        "Disabled: a word is printed, not cut: its letters are a font's outlines, which the router's one end mill cannot follow -- choose a face to cut, or make the word on a printer",
    )
    expect(window.locator(".badge-make[data-make='printer']")).to_be_enabled()
    before = page.evaluate(VARIANT)
    text = window.locator(".badge-fields .param[data-field='text'] input")
    text.click()
    text.press("Control+a")
    text.press_sequentially("HI MOM", delay=60)
    expect(text).to_have_value("HI MOM")
    assert page.evaluate(
        "() => document.activeElement?.closest(\".panel[data-panel='badge']\") !== null"
    ), "a key typed in the Badge window moved the cursor out of it"
    expect(window.locator(".badge-what")).to_contain_text("the word HI MOM")
    page.wait_for_function(f"() => ({VARIANT})() && ({VARIANT})() !== {before!r}", timeout=DRAWN_MS)
    assert page.evaluate(STATE)["staged"]["text"] == "HI MOM"
    # Staged in the part's editor, so Parameters says the same.
    staged = page.evaluate(
        "() => window.fractalViewer.partStages[window.fractalViewer.editorTarget.key].staged.text"
    )
    assert staged == "HI MOM"
    assert errors == [], errors


@pytest.mark.e2e
def test_another_piece_selected_before_the_controls_rest_stays_selected(page: Page, url: str):
    """A diameter typed, then another piece selected before the controls rest: what
    waited to be drawn is let go, so the selection stays where the person put it and the
    window says what that piece is built from."""
    errors: list = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    window = _badge_window(page, url)
    diameter = window.locator(".badge-fields .param[data-field='diameter'] input.param-number")
    diameter.click()
    diameter.press("Control+a")
    diameter.press_sequentially("41")
    select(page, "dust_port")
    page.wait_for_timeout(1500)  # past the window's rest, 700 ms
    assert page.evaluate("() => window.fractalViewer.selectedName") == "dust_port"
    expect(window.locator(".badge-none")).to_contain_text("dust_port is built from")
    assert errors == [], errors


@pytest.mark.e2e
def test_cut_takes_a_face_drawn_to_the_garage_s_router_and_writes_its_toolpath(
    page: Page, url: str
):
    """A face drawn, ⚒ Cut: the garage opened with the variant drawn, cnc_router's Cut
    window in front, badge under makes, its toolpath written as the variant drawn -- a
    groove for its smile -- and nothing armed or started."""
    errors: list = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    window = _badge_window(page, url)
    window.locator(".badge-face[data-face='frown']").click()
    expect(page.locator("#status")).to_contain_text("badge: 🙁 frown drawn", timeout=DRAWN_MS)
    page.wait_for_function(VARIANT, timeout=DRAWN_MS)
    variant = page.evaluate(VARIANT)
    window.locator(".badge-make[data-make='router']").click()
    _in_the_garage(page)
    try:
        expect(page.locator("#status")).to_contain_text("kept and chosen", timeout=DRAWN_MS)
    except AssertionError:
        card = page.evaluate(
            "() => ({ part: document.querySelector('#print-part')?.value,"
            " said: document.querySelector('#print-slice-said')?.innerText,"
            " machine: window.fractalViewer.machine && { path: window.fractalViewer.machine.path,"
            " kind: window.fractalViewer.machine.handle?.kind?.() } })"
        )
        pytest.fail(f"no toolpath was kept: the page's errors {errors}, the Cut card {card}")
    machine = windows.machine(page)
    expect(machine.locator("#print-title")).to_have_text("Cut from here")
    expect(machine.locator("#print-part")).to_have_value(BADGE)
    said = machine.locator("#print-slice-said")
    expect(said).to_contain_text(f"badge (the variant {variant[:8]}) toolpath for cnc_router")
    expect(said).to_contain_text("groove of 12 strokes")
    assert page.evaluate("() => window.fractalViewer.machine.armed") in (False, None)
    assert errors == [], errors


@pytest.mark.e2e
def test_print_takes_the_word_drawn_to_the_garage_s_printer_and_slices_it(page: Page, url: str):
    """The word drawn, ⚒ Print: the garage opened with the variant drawn, printer_1's
    Print window in front, badge under makes and sliced as the variant drawn."""
    errors: list = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    window = _badge_window(page, url)
    window.locator(".badge-face[data-face='word']").click()
    expect(page.locator("#status")).to_contain_text("badge: the word drawn", timeout=DRAWN_MS)
    page.wait_for_function(VARIANT, timeout=DRAWN_MS)
    variant = page.evaluate(VARIANT)
    window.locator(".badge-make[data-make='printer']").click()
    _in_the_garage(page)
    expect(page.locator("#status")).to_contain_text("kept and chosen", timeout=DRAWN_MS)
    machine = windows.machine(page)
    expect(machine.locator("#print-title")).to_have_text("Print from here")
    expect(machine.locator("#print-part")).to_have_value(BADGE)
    expect(machine.locator("#print-slice-said")).to_contain_text(
        f"badge (the variant {variant[:8]}) sliced"
    )
    assert errors == [], errors
