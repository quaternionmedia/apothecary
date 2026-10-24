"""Nothing covers a control: in Selected with a part's editor open -- in its window,
maximised, and with its SCAD editor popped out or over the whole page -- at the
widths the page is laid out for, scrolled from top to bottom, every control in view is
the thing under its own middle; and so is every control of the windows beside the
world, Pictures in front with its folds open. The part editor's stage bar stands pinned above
Selected's body, in its own space, not over the parameters it heads; squeezed, it
scrolls in itself.
"""

from __future__ import annotations

import pytest
import windows
from playwright.sync_api import Page, expect
from rings import on_row
from viewer_ready import settled


def _ring(page: Page, *labels: str) -> None:
    """The part's ring, from its row in Site, and the cells ``labels`` name."""
    on_row(page, PART, *labels)


PART = "calibration_cube"
SIZES = ((1280, 800), (1024, 700))

# Every control of `root` in view -- inside the window and inside each scrolling box it
# is in -- with what stands at the middle of the part of it in view, when that is
# neither it, nor inside it, nor its label.
COVERED = """(selector) => {
    const root = document.querySelector(selector);
    if (!root) return { missing: selector };
    const controls = [...root.querySelectorAll('input, select, button, textarea, summary, .cm-content')];
    const covered = [];
    let seen = 0;
    for (const el of controls) {
        if (!el.offsetParent && el.tagName !== 'SUMMARY') continue;
        // Folded away in a closed fold: not shown, whatever box it is still given.
        const fold = el.closest('details:not([open])');
        if (fold && !(el.tagName === 'SUMMARY' && el.parentElement === fold)) continue;
        const style = getComputedStyle(el);
        if (style.visibility === 'hidden' || style.display === 'none') continue;
        let r = el.getBoundingClientRect();
        if (!r.width || !r.height) continue;
        let view = { l: 0, t: 0, r: innerWidth, b: innerHeight };
        for (let a = el.parentElement; a; a = a.parentElement) {
            const s = getComputedStyle(a);
            if (/(auto|scroll|hidden)/.test(s.overflow + s.overflowX + s.overflowY)) {
                const ar = a.getBoundingClientRect();
                view = { l: Math.max(view.l, ar.left), t: Math.max(view.t, ar.top), r: Math.min(view.r, ar.right), b: Math.min(view.b, ar.bottom) };
            }
        }
        const l = Math.max(r.left, view.l), t = Math.max(r.top, view.t), rr = Math.min(r.right, view.r), b = Math.min(r.bottom, view.b);
        if (rr - l < 4 || b - t < 4) continue;  // out of view, or all but clipped
        seen += 1;
        const x = (l + rr) / 2, y = (t + b) / 2;
        const hit = document.elementFromPoint(x, y);
        const ok = hit && (hit === el || el.contains(hit) || (hit.closest('label') && hit.closest('label').contains(el)));
        if (!ok) covered.push({
            control: `${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''}.${[...el.classList].join('.')}`,
            under: hit ? `${hit.tagName.toLowerCase()}${hit.id ? '#' + hit.id : ''}.${[...hit.classList].join('.')}` : null,
            at: [Math.round(x), Math.round(y)],
        });
    }
    return { seen, covered };
}"""

# The scrolling body a control of `selector` is in, scrolled to `fraction` of its reach.
SCROLLED = """([selector, fraction]) => {
    const root = document.querySelector(selector);
    let slot = root && root.querySelector('.panel-body-slot, .cm-scroller');
    if (root && root.classList.contains('panel-body-slot')) slot = root;
    for (const s of [slot, ...(root ? root.querySelectorAll('.panel-body-slot, .scad-saved') : [])]) {
        if (s && s.scrollHeight > s.clientHeight) s.scrollTop = fraction * (s.scrollHeight - s.clientHeight);
    }
}"""


def _nothing_covered(page: Page, selector: str, how: str) -> int:
    """At each scroll of `selector`'s bodies, top to bottom, no control in view covered."""
    seen = 0
    for fraction in (0, 0.25, 0.5, 0.75, 1):
        page.evaluate(SCROLLED, [selector, fraction])
        settled(page)
        found = page.evaluate(COVERED, selector)
        assert "missing" not in found, (how, found)
        assert found["covered"] == [], (how, fraction, found["covered"])
        seen += found["seen"]
    return seen


@pytest.mark.e2e
@pytest.mark.parametrize("width, height", SIZES, ids=[f"{w}x{h}" for w, h in SIZES])
def test_nothing_covers_a_control_of_the_part_editor(
    page: Page, base_url: str, width: int, height: int
):
    page.set_viewport_size({"width": width, "height": height})
    page.goto(f"{base_url}/viewer/sites/parts_library")
    expect(page.locator("#status")).to_contain_text("Loaded", timeout=20000)
    page.evaluate("() => localStorage.removeItem('apothecary.layout')")
    settled(page)
    _ring(page, "Part", "Edit")
    windows.part_view(page)  # the Part laid out: Selected, Parameters, the SCAD window
    expect(page.locator(".scad-editor .cm-content")).to_be_visible(timeout=20000)
    # Something staged, so the bar says so and Apply is live.
    page.locator("#part-params .param[data-field='size'] .param-number").fill("20")
    expect(page.locator("#stage-summary")).to_contain_text("valid", timeout=10000)
    # The bar takes its own space above Selected's body, not over it.
    pinned = page.locator(".panel[data-panel='selected'] > .panel-pinned #stage-bar")
    expect(pinned).to_be_visible()
    selected = ".panel[data-panel='selected']"
    assert _nothing_covered(page, selected, f"Selected at {width}") > 5
    parameters = ".panel[data-panel='part-parameters']"
    assert _nothing_covered(page, parameters, f"Parameters at {width}") > 5
    # Every window beside the world, Site and the tabs with it; then Pictures,
    # which the Part view leaves out, opened with its folds open: nothing of one
    # window spills over another.
    assert _nothing_covered(page, ".lm_goldenlayout", f"the windows at {width}") > 15
    windows.open_window(page, "pictures")
    page.evaluate(
        "() => document.querySelectorAll(\".panel[data-panel='pictures'] details\")"
        ".forEach((d) => { d.open = true; })"
    )
    assert _nothing_covered(page, ".lm_goldenlayout", f"Pictures open at {width}") > 15

    # Selected maximised: its window the whole of the layout; again, restored.
    maximise = page.locator(".lm_stack", has=page.locator(selected)).locator(".lm_maximise")
    maximise.click()
    expect(page.locator(".lm_maximised", has=page.locator(selected))).to_be_visible()
    assert _nothing_covered(page, selected, f"maximised at {width}") > 5
    maximise.click()
    expect(page.locator(".lm_maximised")).to_have_count(0)

    # The SCAD window (Part › View › SCAD), then the editor over the whole page.
    _ring(page, "Part", "View", "SCAD")
    scad = ".panel[data-panel='part-scad']"
    expect(page.locator(scad)).to_be_visible()
    assert _nothing_covered(page, scad, f"the SCAD window at {width}") > 3
    page.locator("#scad-fullscreen").click()
    expect(page.locator(".scad-editor.fullscreen")).to_be_visible()
    assert _nothing_covered(page, ".scad-editor.fullscreen", f"fullscreen at {width}") > 3
    page.keyboard.press("Escape")
    expect(page.locator(".scad-editor.fullscreen")).to_have_count(0)
