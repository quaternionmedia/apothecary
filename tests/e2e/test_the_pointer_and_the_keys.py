"""The pointer, the keys and the ring, made one (docs/plans/input-2026-10-12.md).

The right button is the camera's: a drag pans and a still click re-centres the view on
the surface under the pointer, and neither opens the ring. Ctrl + right-click opens the
ring, the modifier Settings' to change; the ring's key is too (m). Page Down and Page Up
step a level in and out, rebound in Settings; automatic zoom -- the wheel pushed on past
the dolly's limit -- is on or off, each way on its own, with its resistance and where its
limits sit. Every one of them is a row of the Settings panel, kept by this browser.

On the session's server: nothing here changes a site, and the settings are the
browser's, which each test starts without.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect
from viewer_ready import FREE_SPOT, settled

ROW = "#contents-list .contents-item[data-path='{}']"
RING = "#ring-overlay"
NOTCH = 120  # one notch of a mouse wheel, as Chromium reports it

# A spot on the world, clear of what stands over it, where the nearest thing drawn
# is a piece (`key`, or any) -- or, with `empty`, where nothing is drawn at all --
# and the point of the surface there.
SPOT = """([key, empty]) => {
    const v = window.fractalViewer, r = v.canvas.getBoundingClientRect();
    for (let y = r.top + 40; y < r.bottom - 40; y += 8) {
        for (let x = r.left + 40; x < r.right - 40; x += 8) {
            if (document.elementFromPoint(x, y) !== v.canvas) continue;
            const hit = v.raycastHits({ clientX: x, clientY: y })[0];
            if (empty ? !hit : hit && (!key || hit.object.userData.key === key)) {
                return { x, y, point: hit ? hit.point.toArray() : null };
            }
        }
    }
    return null;
}"""

ORBIT = """() => {
    const v = window.fractalViewer, o = v.orbitControls;
    return { target: o.target.toArray(), distance: o.getDistance(), nearest: o.minDistance,
             farthest: o.maxDistance, focus: v.focusPath.slice(), selected: v.selectedName,
             reach: v.reach && { ...v.reach } };
}"""

# The surface at the middle of the world, as a ray from the camera finds it.
AT_THE_MIDDLE = """() => {
    const v = window.fractalViewer, r = v.canvas.getBoundingClientRect();
    const hit = v.raycastHits({ clientX: r.left + r.width / 2, clientY: r.top + r.height / 2 })[0];
    return hit ? hit.point.toArray() : null;
}"""

# The camera put at the dolly's limit, nearest or farthest, looking as it looked.
TO_THE_LIMIT = """(which) => {
    const v = window.fractalViewer, o = v.orbitControls;
    const away = v.camera.position.clone().sub(o.target);
    away.setLength(which === 'in' ? o.minDistance : o.maxDistance);
    v.camera.position.copy(o.target).add(away);
    o.update();
    v.invalidate();
    return o.getDistance();
}"""

# The camera this far from the orbit's target, looking as it looked.
AT_DISTANCE = """(d) => {
    const v = window.fractalViewer, o = v.orbitControls;
    const away = v.camera.position.clone().sub(o.target).setLength(d);
    v.camera.position.copy(o.target).add(away);
    o.update();
    v.invalidate();
    return o.getDistance();
}"""


def _open(page: Page, url: str) -> None:
    page.goto(f"{url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
    settled(page)


def _orbit(page: Page) -> dict:
    return page.evaluate(ORBIT)


def _near(a, b, within: float = 1.0) -> bool:
    return all(abs(x - y) <= within for x, y in zip(a, b, strict=True))


def _no_ring_after_a_moment(page: Page) -> None:
    """The ring opens after a fetch: a moment is given for one to come, and none does."""
    page.wait_for_timeout(600)
    expect(page.locator(RING)).to_have_count(0)


def _settings(page: Page):
    """The Settings panel, opened from ⚙ View › Settings."""
    page.locator("#view-menu summary").click()
    page.locator("#settings-open").click()
    panel = page.locator(".panel[data-panel='settings']")
    expect(panel.locator(".settings-ui")).to_be_visible(timeout=5000)
    return panel


def _capture(page: Page, setting: str, key: str) -> None:
    field = page.locator(f".setting-key[data-setting='{setting}']")
    field.click()
    expect(field).to_have_attribute("aria-pressed", "true")
    page.keyboard.press(key)


def _unfocus(page: Page) -> None:
    """Nothing has the focus: a key pressed is the page's."""
    page.evaluate("() => document.activeElement && document.activeElement.blur()")


def _wheel(page: Page, notches: int) -> None:
    """Turned over the world, clear of what stands on it: negative is in."""
    middle = page.evaluate(
        "() => { const r = window.fractalViewer.canvas.getBoundingClientRect(); "
        "return [r.left + r.width / 2, r.top + r.height / 2]; }"
    )
    spot = page.evaluate(FREE_SPOT, middle)
    assert spot, "nowhere over the world to turn the wheel"
    page.mouse.move(*spot)
    for _ in range(abs(notches)):
        page.mouse.wheel(0, NOTCH if notches > 0 else -NOTCH)
    settled(page)


# --------------------------------------------------------------------------
# The right button is the camera's
# --------------------------------------------------------------------------


@pytest.mark.e2e
def test_a_right_drag_pans_and_opens_no_ring(page: Page, base_url: str):
    _open(page, base_url)
    before = _orbit(page)
    spot = page.evaluate(SPOT, [None, True])
    assert spot, "no empty space on the world to drag from"
    page.mouse.move(spot["x"], spot["y"])
    page.mouse.down(button="right")
    page.mouse.move(spot["x"] + 120, spot["y"] + 60, steps=12)
    page.mouse.up(button="right")
    settled(page)
    after = _orbit(page)
    assert not _near(after["target"], before["target"]), "a right-drag did not pan"
    assert abs(after["distance"] - before["distance"]) < 1, "a pan keeps its distance"
    assert after["selected"] == before["selected"]
    _no_ring_after_a_moment(page)


@pytest.mark.e2e
def test_a_still_right_click_recentres_on_the_surface_and_on_empty_space_does_nothing(
    page: Page, base_url: str
):
    """The orbit's pivot moves to the surface point under the pointer, the camera with
    it, so the distance stays and that point is the middle of the world; nothing is
    selected and no ring opens. On empty space nothing moves."""
    _open(page, base_url)
    before = _orbit(page)
    spot = page.evaluate(SPOT, ["workbench", False])
    assert spot, "the workbench is nowhere on screen"
    page.mouse.click(spot["x"], spot["y"], button="right")
    page.wait_for_function("() => !window.fractalViewer.glide")
    settled(page)
    after = _orbit(page)
    assert _near(after["target"], spot["point"]), (after["target"], spot["point"])
    assert abs(after["distance"] - before["distance"]) < 1
    assert _near(page.evaluate(AT_THE_MIDDLE), spot["point"], 2.0)
    assert after["selected"] is None and after["focus"] == []
    _no_ring_after_a_moment(page)

    empty = page.evaluate(SPOT, [None, True])
    assert empty, "no empty space on the world"
    page.mouse.click(empty["x"], empty["y"], button="right")
    settled(page)
    assert _near(_orbit(page)["target"], after["target"], 0.01)
    _no_ring_after_a_moment(page)


# --------------------------------------------------------------------------
# Ctrl + right-click, and the key
# --------------------------------------------------------------------------


@pytest.mark.e2e
def test_ctrl_right_click_opens_the_ring_and_so_does_the_key(page: Page, base_url: str):
    """A plain right-click on a Contents row opens nothing and selects nothing; Ctrl +
    right-click opens the row's ring and selects it; on a piece in the world, its
    ring; and m opens the selection's. The hint bar and ⌗ Ring say so."""
    _open(page, base_url)
    expect(page.locator("#viewer-hint")).to_contain_text("Ctrl+right-click: ring")
    expect(page.locator("#ring-open")).to_have_attribute(
        "title", re.compile(r"\(m, or Ctrl\+right-click a piece\)")
    )
    row = page.locator(ROW.format("cnc_router"))
    row.click(button="right")
    _no_ring_after_a_moment(page)
    assert _orbit(page)["selected"] is None
    row.click(button="right", modifiers=["Control"])
    expect(page.locator(RING)).to_be_visible(timeout=5000)
    expect(page.locator(f"{RING} .title")).to_have_text("cnc_router")
    expect(row).to_have_class(re.compile(r"\bselected\b"))
    page.keyboard.press("Escape")
    expect(page.locator(RING)).to_have_count(0)

    spot = page.evaluate(SPOT, ["workbench", False])
    page.keyboard.down("Control")
    page.mouse.click(spot["x"], spot["y"], button="right")
    page.keyboard.up("Control")
    expect(page.locator(RING)).to_be_visible(timeout=5000)
    expect(page.locator(f"{RING} .title")).to_have_text("workbench")
    page.keyboard.press("Escape")
    expect(page.locator(RING)).to_have_count(0)

    page.keyboard.press("m")
    expect(page.locator(RING)).to_be_visible(timeout=5000)
    expect(page.locator(f"{RING} .title")).to_have_text("workbench")
    page.keyboard.press("Escape")


@pytest.mark.e2e
def test_the_modifier_and_the_key_changed_in_settings_open_it_and_the_old_ones_do_not(
    page: Page, base_url: str
):
    """Alt chosen for the modifier: Alt + right-click opens the ring and Ctrl +
    right-click no longer does, at once and with the words following. k given to the
    ring: k opens it and m does not."""
    _open(page, base_url)
    panel = _settings(page)
    panel.locator(".setting-choice[data-setting='ringModifier']").select_option("alt")
    expect(page.locator("#viewer-hint")).to_contain_text("Alt+right-click: ring")
    expect(page.locator("#ring-open")).to_have_attribute(
        "title", re.compile(r"\(m, or Alt\+right-click a piece\)")
    )
    row = page.locator(ROW.format("printer_1"))
    row.click(button="right", modifiers=["Control"])
    _no_ring_after_a_moment(page)
    row.click(button="right", modifiers=["Alt"])
    expect(page.locator(RING)).to_be_visible(timeout=5000)
    expect(page.locator(f"{RING} .title")).to_have_text("printer_1")
    page.keyboard.press("Escape")
    expect(page.locator(RING)).to_have_count(0)

    _capture(page, "ringKey", "k")
    expect(panel.locator(".setting-key[data-setting='ringKey']")).to_have_text("k")
    _unfocus(page)
    page.keyboard.press("m")
    _no_ring_after_a_moment(page)
    page.keyboard.press("k")
    expect(page.locator(RING)).to_be_visible(timeout=5000)
    expect(page.locator(f"{RING} .title")).to_have_text("printer_1")
    page.keyboard.press("Escape")


# --------------------------------------------------------------------------
# Page Down and Page Up
# --------------------------------------------------------------------------


@pytest.mark.e2e
def test_page_down_and_page_up_step_in_and_out_and_a_rebound_key_works(page: Page, base_url: str):
    """Page Down steps into the selected piece and Page Up out to the level above,
    landing on it; a key another shortcut holds is refused, naming it; a key given to
    Step in steps in and Page Down then does not; typing in a box, neither does."""
    _open(page, base_url)
    page.locator(ROW.format("printer_1")).click()
    page.keyboard.press("PageDown")
    page.wait_for_function("() => window.fractalViewer.focusPath.join('.') === 'printer_1'")
    page.keyboard.press("PageUp")
    page.wait_for_function("() => window.fractalViewer.focusPath.length === 0")
    assert _orbit(page)["selected"] == "printer_1"

    panel = _settings(page)
    field = panel.locator(".setting-key[data-setting='zoomInKey']")
    _capture(page, "zoomInKey", "PageUp")
    expect(panel.locator(".setting-said")).to_have_text(
        "Page Up is taken: Step out. Press another key"
    )
    expect(field).to_have_attribute("aria-pressed", "true")  # still waiting for a key
    page.keyboard.press("f")
    expect(panel.locator(".setting-said")).to_have_text("f is taken: Fit. Press another key")
    page.keyboard.press("j")
    expect(field).to_have_text("j")
    expect(field).to_have_attribute("aria-pressed", "false")
    expect(page.locator("#viewer-hint")).to_contain_text("Double-click or j: go in")

    page.locator(".setting-number[data-setting='wheelResistance']").focus()
    page.keyboard.press("j")
    page.wait_for_timeout(300)
    assert _orbit(page)["focus"] == []
    _unfocus(page)
    page.keyboard.press("PageDown")
    page.wait_for_timeout(300)
    assert _orbit(page)["focus"] == []
    page.keyboard.press("j")
    page.wait_for_function("() => window.fractalViewer.focusPath.join('.') === 'printer_1'")


# --------------------------------------------------------------------------
# Automatic zoom
# --------------------------------------------------------------------------


@pytest.mark.e2e
def test_automatic_zoom_off_steps_neither_way_and_each_way_turns_off_alone(
    page: Page, base_url: str
):
    _open(page, base_url)
    panel = _settings(page)
    tick = lambda name: panel.locator(f".setting-tick[data-setting='{name}']")  # noqa: E731

    # On, as it starts: five notches past the nearest step in.
    page.evaluate(TO_THE_LIMIT, "in")
    _wheel(page, -5)
    assert len(_orbit(page)["focus"]) == 1, "the wheel past the limit did not step in"
    # And past the farthest, out again.
    page.evaluate(TO_THE_LIMIT, "out")
    _wheel(page, 5)
    assert _orbit(page)["focus"] == [], "the wheel past the limit did not step out"

    tick("autoZoom").uncheck()
    page.evaluate(TO_THE_LIMIT, "in")
    _wheel(page, -10)
    assert _orbit(page)["focus"] == [], "automatic zoom is off, and it stepped in"

    tick("autoZoom").check()
    tick("autoZoomIn").uncheck()
    page.evaluate(TO_THE_LIMIT, "in")
    _wheel(page, -10)
    assert _orbit(page)["focus"] == [], "stepping in is off, and it stepped in"
    page.evaluate("() => window.fractalViewer.zoomIn('workbench')")
    settled(page)
    page.evaluate(TO_THE_LIMIT, "out")
    _wheel(page, 5)
    assert _orbit(page)["focus"] == [], "stepping out is on, and it did not step out"

    tick("autoZoomIn").check()
    tick("autoZoomOut").uncheck()
    page.evaluate("() => window.fractalViewer.zoomIn('workbench')")
    settled(page)
    page.evaluate(TO_THE_LIMIT, "out")
    _wheel(page, 10)
    assert _orbit(page)["focus"] == ["workbench"], "stepping out is off, and it stepped out"


@pytest.mark.e2e
def test_the_resistance_and_the_limits_change_when_the_step_comes(page: Page, base_url: str):
    """Ten notches past the limit are not enough at a resistance of 2000, and one is at
    100. Nearest moved out to half the level's size: from where the wheel was nowhere
    near the limit, the limit is there, at once, and the wheel steps in from it.
    Farthest moved in: the limit stands where it says, on this level and the next."""
    _open(page, base_url)
    panel = _settings(page)
    number = lambda name: panel.locator(f".setting-number[data-setting='{name}']")  # noqa: E731

    number("wheelResistance").fill("2000")
    number("wheelResistance").press("Tab")
    page.evaluate(TO_THE_LIMIT, "in")
    _wheel(page, -10)
    assert _orbit(page)["focus"] == [], "a resistance of 2000 gave way to 1200"
    number("wheelResistance").fill("100")
    number("wheelResistance").press("Tab")
    page.evaluate(TO_THE_LIMIT, "in")
    _wheel(page, -1)
    assert len(_orbit(page)["focus"]) == 1, "a resistance of 100 held against a notch"
    _unfocus(page)
    page.keyboard.press("PageUp")
    settled(page)
    panel.locator(".setting-reset[data-setting='wheelResistance']").click()
    expect(number("wheelResistance")).to_have_value("500")

    orbit = _orbit(page)
    span = orbit["reach"]["span"]
    page.evaluate(AT_DISTANCE, span * 0.5)
    _wheel(page, -6)
    orbit = _orbit(page)
    assert orbit["focus"] == [] and orbit["distance"] > orbit["nearest"] * 1.05
    number("dollyIn").fill("0.5")
    number("dollyIn").press("Tab")
    orbit = _orbit(page)
    assert abs(orbit["nearest"] - max(10, span * 0.5)) < 0.01, orbit
    assert orbit["distance"] >= orbit["nearest"] - 0.01  # held at the new limit
    _wheel(page, -5)
    assert len(_orbit(page)["focus"]) == 1, "the wheel did not step in from the new limit"

    number("dollyOut").fill("2")
    number("dollyOut").press("Tab")
    orbit = _orbit(page)
    assert abs(orbit["farthest"] - max(2000, orbit["reach"]["distance"] * 2)) < 0.01, orbit
    page.evaluate(TO_THE_LIMIT, "out")
    _wheel(page, 5)
    orbit = _orbit(page)
    assert orbit["focus"] == [], "the wheel did not step out from the new limit"
    assert abs(orbit["farthest"] - max(2000, orbit["reach"]["distance"] * 2)) < 0.01, orbit


# --------------------------------------------------------------------------
# Kept per browser, and reset
# --------------------------------------------------------------------------


@pytest.mark.e2e
def test_settings_survive_a_reload_and_reset_puts_them_back(page: Page, base_url: str):
    _open(page, base_url)
    panel = _settings(page)
    panel.locator(".setting-choice[data-setting='ringModifier']").select_option("alt")
    _capture(page, "zoomOutKey", "u")
    panel.locator(".setting-tick[data-setting='autoZoom']").uncheck()
    panel.locator(".setting-number[data-setting='dollyOut']").fill("4")
    panel.locator(".setting-number[data-setting='dollyOut']").press("Tab")
    changed = {"ringModifier": "alt", "zoomOutKey": "u", "autoZoom": False, "dollyOut": 4}

    page.reload()
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
    values = page.evaluate("() => window.apothecarySettings.values()")
    assert {k: values[k] for k in changed} == changed
    panel = _settings(page)
    expect(panel.locator(".setting-key[data-setting='zoomOutKey']")).to_have_text("u")
    expect(panel.locator(".setting-tick[data-setting='autoZoom']")).not_to_be_checked()
    expect(page.locator("#viewer-hint")).to_contain_text("Alt+right-click: ring")
    # Each row shows its default, and its reset is there while it differs from it.
    expect(panel.locator("[data-row='zoomOutKey'] .setting-default")).to_have_text(
        "default: Page Up"
    )
    expect(panel.locator(".setting-reset[data-setting='ringKey']")).to_be_disabled()

    panel.locator(".setting-reset[data-setting='zoomOutKey']").click()
    expect(panel.locator(".setting-key[data-setting='zoomOutKey']")).to_have_text("Page Up")
    expect(panel.locator(".setting-reset[data-setting='zoomOutKey']")).to_be_disabled()
    panel.locator(".settings-reset-all").click()
    expect(panel.locator(".setting-choice[data-setting='ringModifier']")).to_have_value("ctrl")
    expect(panel.locator(".setting-tick[data-setting='autoZoom']")).to_be_checked()
    expect(page.locator("#viewer-hint")).to_contain_text("Ctrl+right-click: ring")
    assert page.evaluate("() => localStorage.getItem('apothecary.settings')") is None
    page.reload()
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
    assert page.evaluate("() => window.apothecarySettings.values().ringModifier") == "ctrl"


@pytest.mark.e2e
def test_settings_work_with_no_storage(page: Page, base_url: str):
    """A browser that keeps nothing has the defaults, and a setting changed still holds
    for the page's life."""
    page.add_init_script(
        "Object.defineProperty(window, 'localStorage', { get() { throw new Error('refused'); } });"
    )
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    _open(page, base_url)
    assert page.evaluate("() => window.apothecarySettings.values().zoomInKey") == "PageDown"
    panel = _settings(page)
    _capture(page, "zoomInKey", "j")
    expect(panel.locator(".setting-key[data-setting='zoomInKey']")).to_have_text("j")
    page.locator(ROW.format("printer_1")).click()
    _unfocus(page)
    page.keyboard.press("j")
    page.wait_for_function("() => window.fractalViewer.focusPath.join('.') === 'printer_1'")
    assert errors == []
