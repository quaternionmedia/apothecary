"""The pointer, the keys and the ring, made one (docs/plans/input-2026-10-12.md).

The right button is the camera's: a drag pans and a still click re-centres the view on
the surface under the pointer, and neither opens the ring. Ctrl + right-click opens the
ring, the modifier Settings' to change; the ring's key is too (m). Page Down and Page Up
step a level in and out, rebound in Settings; automatic zoom -- the wheel pushed on past
the dolly's limit -- is on or off, each way on its own, with its resistance and where its
limits sit. Every one of them is a row of the Settings panel, kept by this browser.

On a server of its own, the simulated printer pinned to printer_1 so a board's badge
stands in the world: Ctrl+S here saves a variant, which no other module should see. The
settings are the browser's, which each test starts without.
"""

from __future__ import annotations

import re

import httpx
import pytest
from playwright.sync_api import Page, expect
from viewer_ready import FREE_SPOT, settled

ROW = "#contents-list .contents-item[data-path='{}']"
PRINTER = "/dev/ttyFAKE1"


@pytest.fixture(scope="module")
def url(start_server):
    url = start_server()
    httpx.post(f"{url}/firmware/devices/identify", json={"port": PRINTER}, timeout=15.0)
    r = httpx.put(
        f"{url}/sites/garage/nodes/printer_1/device", json={"identity": PRINTER}, timeout=15.0
    )
    assert r.status_code == 200, r.text
    return url


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


def _world(page: Page) -> None:
    """The world has the keyboard's focus, as a press there gives it."""
    page.locator("#viewer-canvas").focus()


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
def test_a_right_drag_pans_and_opens_no_ring(page: Page, url: str):
    _open(page, url)
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
    page: Page, url: str
):
    """The orbit's pivot moves to the surface point under the pointer, the camera with
    it, so the distance stays and that point is the middle of the world; nothing is
    selected and no ring opens. On empty space nothing moves."""
    _open(page, url)
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
def test_ctrl_right_click_opens_the_ring_and_so_does_the_key(page: Page, url: str):
    """A plain right-click on a Contents row opens nothing and selects nothing; Ctrl +
    right-click opens the row's ring and selects it; on a piece in the world, its
    ring; and m opens the selection's. The hint bar and ⌗ Ring say so."""
    _open(page, url)
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
    page: Page, url: str
):
    """Alt chosen for the modifier: Alt + right-click opens the ring and Ctrl +
    right-click no longer does, at once and with the words following. k given to the
    ring: k opens it and m does not."""
    _open(page, url)
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
def test_page_down_and_page_up_step_in_and_out_and_a_rebound_key_works(page: Page, url: str):
    """Page Down steps into the selected piece and Page Up out to the level above,
    landing on it; a key another shortcut holds is refused, naming it; a key given to
    Step in steps in and Page Down then does not; typing in a box, neither does."""
    _open(page, url)
    page.locator(ROW.format("printer_1")).click()
    _world(page)
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
    expect(panel.locator(".setting-said")).to_have_text(
        "f is taken: Fit the selection. Press another key"
    )
    page.keyboard.press("j")
    expect(field).to_have_text("j")
    expect(field).to_have_attribute("aria-pressed", "false")
    expect(page.locator("#viewer-hint")).to_contain_text("Page Up: step out")

    page.locator(".setting-number[data-setting='wheelResistance']").focus()
    page.keyboard.press("j")
    page.wait_for_timeout(300)
    assert _orbit(page)["focus"] == []
    # Nothing focused, and the last press was not in the world: Page Down is the
    # browser's, and scrolls.
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
def test_automatic_zoom_off_steps_neither_way_and_each_way_turns_off_alone(page: Page, url: str):
    _open(page, url)
    panel = _settings(page)
    tick = lambda name: panel.locator(f".setting-tick[data-setting='{name}']")  # noqa: E731
    page.locator(ROW.format("workbench")).click()

    # On, as it starts: five notches past the nearest step into the selection.
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
def test_the_resistance_and_the_limits_change_when_the_step_comes(page: Page, url: str):
    """Ten notches past the limit are not enough at a resistance of 2000, and one is at
    100. Nearest moved out to half the level's size: from where the wheel was nowhere
    near the limit, the limit is there, at once, and the wheel steps in from it.
    Farthest moved in: the limit stands where it says, on this level and the next."""
    _open(page, url)
    panel = _settings(page)
    number = lambda name: panel.locator(f".setting-number[data-setting='{name}']")  # noqa: E731
    page.locator(ROW.format("workbench")).click()

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
    _world(page)
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
def test_settings_survive_a_reload_and_reset_puts_them_back(page: Page, url: str):
    _open(page, url)
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
def test_settings_work_with_no_storage(page: Page, url: str):
    """A browser that keeps nothing has the defaults, and a setting changed still holds
    for the page's life."""
    page.add_init_script(
        "Object.defineProperty(window, 'localStorage', { get() { throw new Error('refused'); } });"
    )
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    _open(page, url)
    assert page.evaluate("() => window.apothecarySettings.values().zoomInKey") == "PageDown"
    panel = _settings(page)
    _capture(page, "zoomInKey", "j")
    expect(panel.locator(".setting-key[data-setting='zoomInKey']")).to_have_text("j")
    page.locator(ROW.format("printer_1")).click()
    _unfocus(page)
    page.keyboard.press("j")
    page.wait_for_function("() => window.fractalViewer.focusPath.join('.') === 'printer_1'")
    assert errors == []


# --------------------------------------------------------------------------
# A click is a still left press and release; clearing the selection; Escape
# --------------------------------------------------------------------------

# A point on a move arrow of the selection, found as the arrows find the pointer.
ARROW_SPOT = """() => {
    const v = window.fractalViewer, tc = v.transformControls, r = v.canvas.getBoundingClientRect();
    for (let y = r.top + 20; y < r.bottom - 20; y += 3) {
        for (let x = r.left + 20; x < r.right - 20; x += 3) {
            if (document.elementFromPoint(x, y) !== v.canvas) continue;
            tc.pointerHover({ x: ((x - r.left) / r.width) * 2 - 1, y: -((y - r.top) / r.height) * 2 + 1, button: -1 });
            if (tc.axis === 'X') { tc.axis = null; return { x, y }; }
        }
    }
    tc.axis = null;
    return null;
}"""

PLACE = """(key) => { const p = window.fractalViewer.meshByName[key].position; return [p.x, p.y, p.z]; }"""


@pytest.mark.e2e
def test_a_still_left_click_selects_and_on_empty_space_lets_go_and_a_drag_selects_nothing(
    page: Page, url: str
):
    """A turn begun over a piece selects nothing; a middle click selects nothing; a still
    left click selects the piece it lands on; one on empty space lets the selection go."""
    _open(page, url)
    spot = page.evaluate(SPOT, ["workbench", False])
    page.mouse.move(spot["x"], spot["y"])
    page.mouse.down()
    page.mouse.move(spot["x"] + 80, spot["y"] + 20, steps=8)
    page.mouse.up()
    settled(page)
    assert _orbit(page)["selected"] is None, "a turn begun over the workbench selected it"
    spot = page.evaluate(SPOT, ["workbench", False])
    page.mouse.click(spot["x"], spot["y"], button="middle")
    page.wait_for_timeout(300)
    assert _orbit(page)["selected"] is None, "a middle click selected"
    page.mouse.click(spot["x"], spot["y"])
    expect(page.locator(ROW.format("workbench"))).to_have_class(re.compile(r"\bselected\b"))
    empty = page.evaluate(SPOT, [None, True])
    page.mouse.click(empty["x"], empty["y"])
    page.wait_for_function("() => window.fractalViewer.selectedName === null")
    expect(page.locator("#selected-body")).to_contain_text("Click a piece to select it")


@pytest.mark.e2e
def test_escape_folds_the_menu_puts_a_drag_back_unsaved_then_lets_go(page: Page, url: str):
    """One rung a press: ⚙ View folded, the selection kept; a move-arrow drag put back
    where it began, nothing sent, and the pointer's release keeps nothing; then the
    selection let go."""
    _open(page, url)
    page.locator(ROW.format("workbench")).click()
    page.locator("#view-menu summary").click()
    expect(page.locator("#view-menu")).to_have_attribute("open", "")
    _world(page)
    page.keyboard.press("Escape")
    expect(page.locator("#view-menu")).not_to_have_attribute("open", "")
    assert _orbit(page)["selected"] == "workbench"

    sent = []
    page.on("request", lambda r: sent.append(r.url) if "/layout" in r.url else None)
    settled(page)
    before = page.evaluate(PLACE, "workbench")
    arrow = page.evaluate(ARROW_SPOT)
    assert arrow, "no move arrow on screen"
    page.mouse.move(arrow["x"], arrow["y"])
    page.mouse.down()
    page.mouse.move(arrow["x"] + 160, arrow["y"], steps=10)
    moved = page.evaluate(PLACE, "workbench")
    assert not _near(moved, before), "the arrow did not move the workbench"
    page.keyboard.press("Escape")
    assert _near(page.evaluate(PLACE, "workbench"), before, 0.01)
    page.mouse.move(arrow["x"] + 260, arrow["y"], steps=6)
    page.mouse.up()
    page.wait_for_timeout(500)
    assert _near(page.evaluate(PLACE, "workbench"), before, 0.01)
    assert sent == [], sent
    expect(page.locator("#status")).to_contain_text("put back where it was; nothing saved")
    assert _orbit(page)["selected"] == "workbench"

    page.keyboard.press("Escape")
    page.wait_for_function("() => window.fractalViewer.selectedName === null")
    expect(page.locator("#status")).to_contain_text("Let go of workbench")


# --------------------------------------------------------------------------
# Shift+M, the one key check, f and Shift+F
# --------------------------------------------------------------------------


@pytest.mark.e2e
def test_shift_m_opens_the_canvas_ring_whatever_is_selected(page: Page, url: str):
    _open(page, url)
    page.locator(ROW.format("cnc_router")).click()
    _world(page)
    page.keyboard.press("Shift+M")
    expect(page.locator(RING)).to_be_visible(timeout=5000)
    expect(page.locator(f"{RING} .wedge[aria-label='Pieces']")).to_have_count(1)
    expect(page.locator(f"{RING} .title")).not_to_have_text("cnc_router")
    page.keyboard.press("Escape")
    page.keyboard.press("m")
    expect(page.locator(f"{RING} .title")).to_have_text("cnc_router", timeout=5000)
    page.keyboard.press("Escape")


@pytest.mark.e2e
def test_one_key_check_for_every_shortcut(page: Page, url: str):
    """A slider focused takes Page Down -- it moves, and nothing steps -- and lets m open
    the ring; Ctrl+Backspace steps out of nothing, Backspace does; the ring's key is
    matched by where it is (Cyrillic ь on the M key) and with Caps Lock on; the rail's
    tilde by where it is, a dead key there included."""
    page.goto(f"{url}/viewer/sites/parts_library")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
    page.locator(ROW.format("calibration_cube")).click()
    slider = page.locator("#part-params .param-slider").first
    expect(slider).to_be_visible(timeout=20000)
    slider.focus()
    was = slider.input_value()
    page.keyboard.press("PageDown")
    page.wait_for_timeout(300)
    assert slider.input_value() != was, "the focused slider did not take Page Down"
    assert _orbit(page)["focus"] == [], "Page Down stepped in from a focused slider"
    page.keyboard.press("m")
    expect(page.locator(RING)).to_be_visible(timeout=5000)
    page.keyboard.press("Escape")
    expect(page.locator(RING)).to_have_count(0)

    _world(page)
    page.keyboard.press("PageDown")
    page.wait_for_function("() => window.fractalViewer.focusPath.join('.') === 'calibration_cube'")
    _unfocus(page)
    page.keyboard.press("Control+Backspace")
    page.wait_for_timeout(300)
    assert _orbit(page)["focus"] == ["calibration_cube"], "Ctrl+Backspace stepped out"
    page.keyboard.press("Backspace")
    page.wait_for_function("() => window.fractalViewer.focusPath.length === 0")

    press = """([key, code, shift]) => window.dispatchEvent(new KeyboardEvent('keydown',
        { key, code, shiftKey: shift, bubbles: true, cancelable: true }))"""
    page.evaluate(press, ["ь", "KeyM", False])
    expect(page.locator(f"{RING} .title")).to_have_text(re.compile("^calibr"), timeout=5000)
    page.keyboard.press("Escape")
    page.evaluate(press, ["M", "KeyM", False])  # Caps Lock on: still m, not Shift+M
    expect(page.locator(f"{RING} .title")).to_have_text(re.compile("^calibr"), timeout=5000)
    page.keyboard.press("Escape")
    page.evaluate(press, ["Dead", "Backquote", False])
    assert page.evaluate("() => window.apothecaryPanels.railHidden()") is True
    page.evaluate(press, ["§", "Backquote", False])
    assert page.evaluate("() => window.apothecaryPanels.railHidden()") is False


@pytest.mark.e2e
def test_f_frames_the_selection_else_the_level_and_shift_f_the_level(page: Page, url: str):
    _open(page, url)
    page.locator(ROW.format("workbench")).click()
    _world(page)
    page.keyboard.press("f")
    expect(page.locator("#status")).to_contain_text("Framed workbench")
    page.keyboard.press("Shift+F")
    expect(page.locator("#status")).to_contain_text("Framed the level")
    page.keyboard.press("Escape")
    page.wait_for_function("() => window.fractalViewer.selectedName === null")
    page.locator("#status").evaluate("(el) => { el.textContent = ''; }")
    page.keyboard.press("f")
    expect(page.locator("#status")).to_contain_text("Framed the level")


# --------------------------------------------------------------------------
# One way in, saying what it did; the wheel's momentum
# --------------------------------------------------------------------------


@pytest.mark.e2e
def test_page_down_steps_into_the_middle_of_the_view_and_says_so(page: Page, url: str):
    """With nothing selected, Page Down steps into what the middle of the view shows: a
    still right-click on the workbench brings it there. With nothing there, it says so."""
    _open(page, url)
    spot = page.evaluate(SPOT, ["workbench", False])
    page.mouse.click(spot["x"], spot["y"], button="right")
    page.wait_for_function("() => !window.fractalViewer.glide")
    settled(page)
    _world(page)
    page.keyboard.press("PageDown")
    page.wait_for_function("() => window.fractalViewer.focusPath.join('.') === 'workbench'")
    expect(page.locator("#status")).to_have_text(
        "Stepped into workbench (Page Down, the middle of the view)"
    )
    page.keyboard.press("PageUp")
    page.wait_for_function("() => window.fractalViewer.focusPath.length === 0")
    expect(page.locator("#status")).to_contain_text("Stepped out of workbench")


@pytest.mark.e2e
def test_the_wheels_momentum_takes_no_step(page: Page, url: str):
    """At the limit, notches a quarter of a second apart never add up to a step; and
    the notches right after a step take no second one."""
    _open(page, url)
    page.locator(ROW.format("workbench")).click()
    page.evaluate(TO_THE_LIMIT, "in")
    middle = page.evaluate(
        "() => { const r = window.fractalViewer.canvas.getBoundingClientRect(); "
        "return [r.left + r.width / 2, r.top + r.height / 2]; }"
    )
    page.mouse.move(*page.evaluate(FREE_SPOT, middle))
    for _ in range(8):
        page.mouse.wheel(0, -NOTCH)
        page.wait_for_timeout(300)
    assert _orbit(page)["focus"] == [], "spaced notches stepped in"
    page.evaluate(TO_THE_LIMIT, "in")
    for _ in range(12):  # five step in; the seven right after are momentum
        page.mouse.wheel(0, -NOTCH)
    settled(page)
    assert _orbit(page)["focus"] == ["workbench"], _orbit(page)["focus"]


# --------------------------------------------------------------------------
# Badges, a Machine, a long press, Ctrl+S
# --------------------------------------------------------------------------

BADGE = ".world-badge[data-path='printer_1']"


@pytest.mark.e2e
def test_a_badge_passes_the_right_button_to_its_piece(page: Page, url: str):
    """A still right-click on printer_1's board badge re-centres the view on the board;
    Ctrl+right-click on it opens printer_1's ring."""
    _open(page, url)
    badge = page.locator(BADGE)
    expect(badge).to_be_visible(timeout=15000)
    before = _orbit(page)
    badge.click(button="right")
    page.wait_for_function("() => !window.fractalViewer.glide")
    after = _orbit(page)
    assert not _near(after["target"], before["target"]), (
        "the badge's right-click re-centred nothing"
    )
    assert abs(after["distance"] - before["distance"]) < 1
    _no_ring_after_a_moment(page)
    badge.click(button="right", modifiers=["Control"])
    expect(page.locator(f"{RING} .title")).to_have_text("printer_1", timeout=5000)
    page.keyboard.press("Escape")


@pytest.mark.e2e
def test_a_plain_right_click_in_a_machine_is_the_browsers(page: Page, url: str):
    _open(page, url)
    badge = page.locator(BADGE)
    expect(badge).to_be_visible(timeout=15000)
    badge.click()
    machine = page.locator(".panel[data-panel='machine']")
    expect(machine).to_be_visible(timeout=10000)
    prevented = page.evaluate(
        """() => { const el = document.querySelector(".panel[data-panel='machine'] .kv")
            || document.querySelector(".panel[data-panel='machine']");
            const ev = new MouseEvent('contextmenu', { bubbles: true, cancelable: true, button: 2 });
            el.dispatchEvent(ev); return ev.defaultPrevented; }"""
    )
    assert prevented is False, "a plain right-click in a Machine kept the browser's menu away"
    _no_ring_after_a_moment(page)
    machine.locator(".kv").first.click(button="right", modifiers=["Control"])
    expect(page.locator(RING)).to_be_visible(timeout=5000)
    page.keyboard.press("Escape")


@pytest.mark.e2e
def test_a_still_long_press_by_touch_opens_the_ring(page: Page, url: str):
    """A finger held still on the workbench for half a second opens its ring; a short tap
    selects, as a click does, and opens nothing."""
    _open(page, url)
    spot = page.evaluate(SPOT, ["workbench", False])
    cdp = page.context.new_cdp_session(page)
    point = [{"x": spot["x"], "y": spot["y"]}]
    cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": point})
    page.wait_for_timeout(150)
    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    page.wait_for_function("() => window.fractalViewer.selectedName === 'workbench'")
    _no_ring_after_a_moment(page)
    page.evaluate("() => window.fractalViewer.deselect()")
    cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": point})
    page.wait_for_timeout(800)
    expect(page.locator(f"{RING} .title")).to_have_text("workbench", timeout=5000)
    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    page.wait_for_timeout(300)
    expect(page.locator(RING)).to_be_visible()
    page.keyboard.press("Escape")


@pytest.mark.e2e
def test_ctrl_s_saves_the_variant_from_anywhere_while_the_editor_is_open(page: Page, url: str):
    page.goto(f"{url}/viewer/sites/parts_library")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
    page.locator(ROW.format("calibration_cube")).click()
    expect(page.locator("#part-params .param-slider").first).to_be_visible(timeout=20000)
    expect(page.locator(".scad-editor .cm-content")).to_be_visible(timeout=20000)
    page.locator("#part-params .param-slider").first.focus()
    page.keyboard.press("Control+s")
    expect(page.locator("#status")).to_contain_text("saved as the variant", timeout=30000)


# --------------------------------------------------------------------------
# Addresses that hold still; confirming by consequence
# --------------------------------------------------------------------------

WEDGES = """() => Object.fromEntries([...document.querySelectorAll('#ring-overlay .wedge')]
    .filter((w) => !w.classList.contains('empty'))
    .map((w) => [w.getAttribute('aria-label'), w.dataset.cell]))"""


def _canvas_ring(page: Page) -> dict:
    _world(page)
    page.keyboard.press("Shift+M")
    expect(page.locator(RING)).to_be_visible(timeout=5000)
    page.wait_for_function("() => document.querySelectorAll('#ring-overlay .wedge').length > 0")
    cells = page.evaluate(WEDGES)
    page.keyboard.press("Escape")
    expect(page.locator(RING)).to_have_count(0)
    return cells


@pytest.mark.e2e
def test_the_canvas_rings_constant_cells_keep_one_address_everywhere(page: Page, url: str):
    """Pieces 8, Site 6, View 2, Panels 4, Pictures 9 and Rebuild 3 at the garage's root,
    stepped into a piece, at a leaf, and in a site with no groups; Step out and Group,
    which come and go, after them."""
    constant = {
        "Pieces": "8",
        "Site": "6",
        "View": "2",
        "Panels": "4",
        "Pictures": "9",
        "Rebuild": "3",
    }
    _open(page, url)
    root = _canvas_ring(page)
    assert {k: root[k] for k in constant} == constant and "Step out" not in root
    page.locator(ROW.format("printer_1")).dblclick()
    page.wait_for_function("() => window.fractalViewer.focusPath.join('.') === 'printer_1'")
    nested = _canvas_ring(page)
    assert {k: nested[k] for k in constant} == constant and nested["Step out"] == "1"
    page.goto(f"{url}/viewer/sites/parts_library")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
    library = _canvas_ring(page)
    assert {k: library[k] for k in constant} == constant and "Group" not in library
    page.locator(ROW.format("calibration_cube")).dblclick()
    page.wait_for_function("() => window.fractalViewer.focusPath.join('.') === 'calibration_cube'")
    leaf = _canvas_ring(page)
    assert {k: leaf[k] for k in constant} == constant and leaf["Step out"] == "1"


@pytest.mark.e2e
def test_rebuild_asks_twice_on_its_wedge_and_the_emergency_stop_never_asks(page: Page, url: str):
    """Rebuild, chosen once, says "again to rebuild" on its own wedge and does nothing;
    let go, it is not done. The Machine's E-STOP sends M112 at once, with no dialog."""
    sent = []
    page.on("request", lambda r: sent.append(r.url) if "/menu/intent" in r.url else None)
    dialogs = []
    page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
    _open(page, url)
    _world(page)
    page.keyboard.press("Shift+M")
    expect(page.locator(RING)).to_be_visible(timeout=5000)
    page.wait_for_function("() => document.querySelectorAll('#ring-overlay .wedge').length > 0")
    page.keyboard.press("3")
    expect(page.locator(f"{RING} .wedge[aria-label='again to rebuild']")).to_have_count(1)
    expect(page.locator(f"{RING} .label.armed")).to_contain_text("again to")
    page.keyboard.press("Escape")
    expect(page.locator(RING)).to_have_count(0)
    page.wait_for_timeout(300)
    assert sent == [], sent

    badge = page.locator(BADGE)
    expect(badge).to_be_visible(timeout=15000)
    badge.click()
    machine = page.locator(".panel[data-panel='machine']")
    expect(machine.locator("#estop")).to_be_visible(timeout=10000)
    machine.locator("#estop").click()
    expect(machine.locator("#log")).to_contain_text("M112", timeout=10000)
    assert dialogs == [], dialogs


# --------------------------------------------------------------------------
# Selected: the stage bar, the focus; the status line; the world's keys
# --------------------------------------------------------------------------

PINNED = ".panel[data-panel='selected'] .panel-pinned"


def _ring_labels(page: Page, *labels: str) -> None:
    for label in labels:
        page.wait_for_function(
            "(l) => [...document.querySelectorAll('#ring-overlay .wedge')]"
            ".some((w) => w.getAttribute('aria-label') === l)",
            arg=label,
            timeout=5000,
        )
        page.keyboard.press(page.evaluate(WEDGES)[label])


@pytest.mark.e2e
def test_the_stage_bar_is_pinned_only_while_editing(page: Page, url: str):
    """calibration_cube chosen from Site: its editor in Selected, its bar in the part's
    section, nothing pinned above the body, and Selected's name first. A value staged:
    the bar pinned. Put back: in its section again. Part › Edit: pinned, nothing staged."""
    page.goto(f"{url}/viewer/sites/parts_library")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=15000)
    page.locator(ROW.format("calibration_cube")).click()
    expect(page.locator("#part-params .param-number").first).to_be_visible(timeout=20000)
    expect(page.locator(f"{PINNED} #stage-bar")).to_have_count(0)
    expect(page.locator("#selected-body .part-editor #stage-bar")).to_have_count(1)
    expect(page.locator("#selected-body > .prop-row").first).to_contain_text("Name")

    box = page.locator("#part-params .param-number").first
    box.fill(str(float(box.input_value()) + 2))
    box.press("Tab")
    expect(page.locator(f"{PINNED} #stage-bar")).to_have_count(1, timeout=10000)
    page.locator("#revert-btn").click()
    expect(page.locator("#stage-summary")).to_have_text("No staged changes", timeout=10000)
    expect(page.locator(f"{PINNED} #stage-bar")).to_have_count(0)

    page.locator(ROW.format("calibration_cube")).click(button="right", modifiers=["Control"])
    expect(page.locator(RING)).to_be_visible(timeout=5000)
    _ring_labels(page, "Part", "Edit")
    expect(page.locator(f"{PINNED} #stage-bar")).to_have_count(1, timeout=10000)
    expect(page.locator("#stage-summary")).to_have_text("No staged changes")


@pytest.mark.e2e
def test_selected_keeps_the_focus_the_status_is_announced_and_the_arrows_are_the_worlds(
    page: Page, url: str
):
    """A box focused in Selected has the focus again after the panel is drawn anew; the
    status line is a polite live region; the world takes the focus, and the arrows pan
    the view only while it has it."""
    _open(page, url)
    page.locator(ROW.format("printer_1")).click()
    expect(page.locator("#pos-x")).to_be_visible(timeout=5000)
    page.locator("#pos-x").focus()
    page.evaluate("() => window.fractalViewer.renderSelectedPanel()")
    assert page.evaluate("() => document.activeElement.id") == "pos-x"
    status = page.locator("#status")
    expect(status).to_have_attribute("role", "status")
    expect(status).to_have_attribute("aria-live", "polite")

    canvas = page.locator("#viewer-canvas")
    expect(canvas).to_have_attribute("tabindex", "0")
    _unfocus(page)
    before = _orbit(page)["target"]
    page.keyboard.press("ArrowLeft")
    settled(page)
    assert _near(_orbit(page)["target"], before, 0.01), "the arrows panned a world without focus"
    _world(page)
    page.keyboard.press("ArrowLeft")
    settled(page)
    assert not _near(_orbit(page)["target"], before, 0.01), "the arrows did not pan the world"


@pytest.mark.e2e
def test_the_worlds_ring_shows_when_tab_brings_the_focus_and_not_after_a_press(
    page: Page, url: str
):
    _open(page, url)
    outline = "() => getComputedStyle(document.getElementById('viewer-canvas')).outlineStyle"
    page.locator("#ring-open").focus()
    page.keyboard.press("Tab")
    assert page.evaluate("() => document.activeElement.id") == "viewer-canvas"
    assert page.evaluate(outline) == "solid"
    empty = page.evaluate(SPOT, [None, True])
    page.mouse.click(empty["x"], empty["y"])
    assert page.evaluate("() => document.activeElement.id") == "viewer-canvas"
    assert page.evaluate(outline) == "none"
