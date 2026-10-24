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
from viewer_ready import settled

PART = "calibration_cube"
SIZES = ((1280, 800), (1024, 700))
WEDGES = (
    "() => Object.fromEntries([...document.querySelectorAll('#ring-overlay .wedge')]"
    ".filter((w) => !w.classList.contains('empty'))"
    ".map((w) => [w.getAttribute('aria-label'), w.dataset.cell]))"
)

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


def _press(page: Page, *labels: str) -> None:
    for label in labels:
        page.wait_for_function(
            f"() => [...document.querySelectorAll('#ring-overlay .wedge')]"
            f".some((w) => w.getAttribute('aria-label') === {label!r})",
            timeout=15000,
        )
        page.keyboard.press(page.evaluate(WEDGES)[label])


def _ring(page: Page, *labels: str) -> None:
    page.locator(f"#contents-list .contents-item[data-path='{PART}']").click(
        button="right", modifiers=["Control"]
    )
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=15000)
    _press(page, *labels)


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
def test_nothing_covers_a_control_of_the_part_editor(page: Page, base_url: str):
    for width, height in SIZES:
        page.set_viewport_size({"width": width, "height": height})
        page.goto(f"{base_url}/viewer/sites/parts_library")
        expect(page.locator("#status")).to_contain_text("Loaded", timeout=20000)
        page.evaluate("() => localStorage.removeItem('apothecary.layout')")
        settled(page)
        _ring(page, "Part", "Edit")
        expect(page.locator(".scad-editor .cm-content")).to_be_visible(timeout=20000)
        # Something staged, so the bar says so and Apply is live.
        page.locator("#part-params .param[data-field='size'] .param-number").fill("20")
        expect(page.locator("#stage-summary")).to_contain_text("valid", timeout=10000)
        # The bar takes its own space above Selected's body, not over it.
        pinned = page.locator(".panel[data-panel='selected'] > .panel-pinned #stage-bar")
        expect(pinned).to_be_visible()
        selected = ".panel[data-panel='selected']"
        assert _nothing_covered(page, selected, f"docked at {width}") > 10
        # Every window beside the world, Site and the tabs with it; then Pictures in
        # front with its folds open: nothing of one window spills over another.
        assert _nothing_covered(page, ".lm_goldenlayout", f"the windows at {width}") > 15
        windows.show(page, "pictures")
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

        # The SCAD editor popped out, then over the whole page.
        _ring(page, "Part", "View", "Pop out")
        popped = ".panel[data-panel='scad-editor']"
        expect(page.locator(popped)).to_be_visible()
        assert _nothing_covered(page, popped, f"SCAD popped out at {width}") > 3
        assert _nothing_covered(page, selected, f"beside the SCAD popped out at {width}") > 5
        page.locator("#scad-fullscreen").click()
        expect(page.locator(".scad-editor.fullscreen")).to_be_visible()
        assert _nothing_covered(page, ".scad-editor.fullscreen", f"fullscreen at {width}") > 3
        page.keyboard.press("Escape")
        _ring(page, "Part", "View", "Pop out")
        expect(page.locator(popped)).to_have_count(0)
