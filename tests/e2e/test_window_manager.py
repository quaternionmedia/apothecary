"""The page's window manager on its own: panels.js and systems.js, tested on a page
that holds nothing else.

The page is served from ``apothecary/static`` by the browser's own routing: no server,
no world, no site, no three.js -- GoldenLayout, the two modules and windows made up for
each test. Every behaviour the viewer builds on is held here, case by case:

- where a window opens when it is not in the layout (its home);
- views: what they lay out, what they need, what they leave;
- what a browser remembers of the layout, and what it forgets;
- a window's life: its body filled when first shown, told when shown again and
  when closed, taken away and registered again; a loud one's tab and frame;
- what a person moves: a tab dropped on another stack or beside the world, the
  splitter beside the world, kept through a reload and undone by a reset;
- focused systems from a registry: sections closed until asked for, opened by the
  verbs that act on them, a system made for the moment attached and detached;
- a stack's + and the world alone.

The viewer's own tests then hold what the viewer does with them, not the layout.
"""

from __future__ import annotations

import json
import mimetypes
import re
from pathlib import Path
from urllib.parse import urlparse

import pytest
import windows
from browsers import CHROMIUM_MISSING
from playwright.sync_api import Page, expect

from apothecary.projects.parts.skeleton import ROOT
from apothecary.systems import Section, System, manifest

# Every test here is a browser test on a page of its own, run by `apothecary test run`.
pytestmark = pytest.mark.windows

STATIC = ROOT / "apothecary" / "static"
ORIGIN = "http://windows.test"

HARNESS = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="/static/vendor/golden-layout/css/goldenlayout-base.css">
<link rel="stylesheet" href="/static/vendor/golden-layout/css/goldenlayout-dark-theme.css">
<script type="importmap">{"imports": {"golden-layout": "/static/vendor/golden-layout/index.js"}}</script>
<style>html, body { margin: 0; height: 100%; } #host { position: absolute; inset: 0; }
.panel { height: 100%; } .lm_spawn { width: 18px; }</style>
</head><body><div id="host"></div>
<script type="module">
import { mountPanels } from '/static/panels.js';
import { mountSystems, knownWindows, transientWindows, openFor } from '/static/systems.js';
const host = document.getElementById('host');
const log = [];
const H = {
    log,
    // A layout mounted afresh: the page's own root, the windows it knows of and those
    // made for the moment; the windows given registered, each with a body of its own.
    mount({ root = null, known = [], transient = [], register = [], columnStacks = null } = {}) {
        if (window.P) window.P.destroy();
        host.replaceChildren();
        const world = document.createElement('div');
        world.id = 'world';
        world.textContent = 'world';
        const options = { host, world, storageKey: 'windows.test', known, transient };
        if (root) options.defaultRoot = root;
        if (columnStacks) options.columnStacks = columnStacks;
        window.P = mountPanels(options);
        for (const [id, opts] of register) H.reg(id, opts);
        return true;
    },
    body(id) { const el = document.createElement('div'); el.className = 'body'; el.dataset.of = id; el.textContent = id; return el; },
    reg(id, opts = {}) {
        const o = { title: id, body: H.body(id), ...opts };
        if (o.lazy) { delete o.lazy; o.body = (slot) => { log.push(`fill ${id}`); slot.append(H.body(id)); }; }
        if (o.told) { delete o.told; o.onOpen = () => log.push(`open ${id}`); o.onClose = () => log.push(`close ${id}`); }
        return !!P.register(id, o);
    },
    item: (id) => P.layout.findFirstComponentItemById(id),
    // Where a window stands: its stack's windows and which is in front, and its stack's
    // place among its parent's children, with the parent's kind and every child's ids.
    where(id) {
        const ci = H.item(id);
        if (!ci) return null;
        const stack = ci.parentItem, parent = stack.parent;
        const ids = (it) => (it.isStack ? it.contentItems.map((c) => c.id) : [it.type]);
        return {
            stack: stack.contentItems.map((c) => c.id),
            front: stack.getActiveComponentItem()?.id ?? null,
            parent: parent.type,
            at: parent.contentItems.indexOf(stack),
            children: parent.contentItems.map(ids),
        };
    },
    size(id) { const ci = H.item(id); return ci ? ci.parentItem.size : null; },
    height(id) { const ci = H.item(id); return ci ? ci.parentItem.element.getBoundingClientRect().height : null; },
};
window.H = H;
window.__wm = { mountPanels, mountSystems, knownWindows, transientWindows, openFor };
window.__ready = true;
</script></body></html>"""

# The page's own layout in these tests: the world, and a column of a stack of two
# (a, b), Selected-like `sel`, and a stack of tabbed windows (t1, t2).
TAB = {"type": "component", "isClosable": True}
ROOT_LAYOUT = {
    "type": "row",
    "content": [
        {
            "type": "stack",
            "width": 70,
            "header": {"show": False},
            "content": [{**TAB, "componentType": "world", "id": "world", "isClosable": False}],
        },
        {
            "type": "column",
            "width": 30,
            "content": [
                {
                    "type": "stack",
                    "content": [
                        {**TAB, "componentType": "a", "id": "a"},
                        {**TAB, "componentType": "b", "id": "b"},
                    ],
                },
                {"type": "stack", "content": [{**TAB, "componentType": "sel", "id": "sel"}]},
                {
                    "type": "stack",
                    "content": [
                        {**TAB, "componentType": "t1", "id": "t1"},
                        {**TAB, "componentType": "t2", "id": "t2"},
                    ],
                },
            ],
        },
    ],
}
PAGE_WINDOWS = [
    ["a", {"home": "column"}],
    ["b", {"home": "a"}],
    ["sel", {"home": "column"}],
    ["t1", {"home": "tabs"}],
    ["t2", {"home": "tabs"}],
]


def _serve(route) -> None:
    path = urlparse(route.request.url).path
    if path in ("/", "/index.html"):
        route.fulfill(body=HARNESS, content_type="text/html")
        return
    file = STATIC / path.removeprefix("/static/")
    if not path.startswith("/static/") or not file.is_file():
        route.fulfill(status=404, body="")
        return
    kind = "text/javascript" if file.suffix == ".js" else mimetypes.guess_type(file.name)[0]
    route.fulfill(path=str(file), content_type=kind or "application/octet-stream")


@pytest.fixture(scope="session", autouse=True)
def _chromium_here(browser_type):
    """This page needs no server, only Chromium, so it runs wherever Playwright has
    installed Chromium -- `uv run pytest` too -- and skips where it has not, before a
    browser is launched."""
    if not Path(browser_type.executable_path).exists():
        pytest.skip(CHROMIUM_MISSING)


@pytest.fixture
def browser_context_args():
    """No server's address: this page is served from the checkout by the browser's own
    routing."""
    return {}


@pytest.fixture(scope="session")
def _verify_url():
    """pytest-base-url checks the server's address before every test, asking for one;
    this page has none to check."""


@pytest.fixture
def wm(page: Page) -> Page:
    """The harness page, a layout of the page's own windows mounted on it."""
    page.set_viewport_size({"width": 1200, "height": 800})
    page.route(f"{ORIGIN}/**", _serve)
    page.goto(f"{ORIGIN}/")
    page.wait_for_function("() => window.__ready === true", timeout=10000)
    _mount(page)
    return page


def _mount(page: Page, **extra) -> None:
    config = {"root": ROOT_LAYOUT, "register": PAGE_WINDOWS, **extra}
    page.evaluate("(c) => H.mount(c)", config)


def _js(page: Page, script: str, arg=None):
    return page.evaluate(script, arg)


def _where(page: Page, pid: str):
    return page.evaluate("(id) => H.where(id)", pid)


# --- where a window opens -------------------------------------------------------


def _beside_its_home(page):
    _js(page, "() => { H.reg('x', { home: 'a', open: false }); P.open('x'); }")
    w = _where(page, "x")
    assert w["stack"] == ["a", "x", "b"] and w["front"] == "x"


def _beside_kin_when_its_home_is_closed(page):
    _js(
        page,
        "() => { P.close('a'); H.reg('k1', { home: 'a', open: false }); H.reg('k2', { home: 'a', open: false }); }",
    )
    _js(page, "() => { P.open('b'); P.open('k1'); P.open('k2'); }")
    assert _where(page, "k2")["stack"] == _where(page, "k1")["stack"]
    assert "k2" in _where(page, "k1")["stack"]


def _among_the_tabs(page):
    _js(page, "() => H.reg('x', { home: 'tabs' })")
    w = _where(page, "x")
    # Registered, it joins the tabs behind the one in front; a person's open brings it.
    assert w["stack"] == ["t1", "t2", "x"] and w["front"] == "t1"
    _js(page, "() => P.open('x')")
    assert _where(page, "x")["front"] == "x"


def _under_the_window_it_follows(page):
    _js(page, "() => H.reg('x', { home: 'column', after: 'sel', open: false })")
    _js(page, "() => P.open('x')")
    w, sel = _where(page, "x"), _where(page, "sel")
    assert w["parent"] == "column" and w["stack"] == ["x"] and w["at"] == sel["at"] + 1


def _with_its_siblings_under_that_window(page):
    _js(
        page,
        "() => { for (const id of ['x', 'y']) H.reg(id, { home: 'column', after: 'sel', open: false }); }",
    )
    _js(page, "() => { P.open('x'); P.open('y'); }")
    assert _where(page, "y")["stack"] == ["x", "y"]
    assert _where(page, "y")["at"] == _where(page, "sel")["at"] + 1


def _beside_the_world_with_room_from_the_world(page):
    before = _js(page, "() => H.size('world')")
    _js(page, "() => { H.reg('x', { home: 'beside', open: false }); P.open('x'); }")
    w = _where(page, "x")
    assert w["parent"] == "row" and w["at"] == _where(page, "world")["at"] + 1
    after = _js(page, "() => H.size('world')")
    assert after == pytest.approx(before - min(28, before / 2), abs=0.5)
    # Closed, its room goes back to the world.
    _js(page, "() => P.close('x')")
    page.wait_for_function("(w) => Math.abs(H.size('world') - w) < 0.5", arg=before)


def _at_the_column_foot_after_nothing(page):
    _js(page, "() => { H.reg('x', { home: 'column', open: false }); P.open('x'); }")
    w = _where(page, "x")
    assert w["parent"] == "column" and w["at"] == len(w["children"]) - 1


# The column holds three stacks of the page's own; by default four at most.
def _a_tab_beside_the_window_it_follows_once_the_column_is_full(page):
    _js(page, "() => H.reg('x', { home: 'column', after: 'sel', open: false })")
    _js(page, "() => H.reg('z', { home: 'column', after: 't1', open: false })")
    _js(page, "() => { P.open('x'); P.open('z'); }")
    assert _where(page, "x")["stack"] == ["x"]  # the fourth stack
    z = _where(page, "z")
    assert z["stack"] == ["t1", "t2", "z"] and z["front"] == "z" and len(z["children"]) == 4


def _a_tab_at_once_in_a_column_of_three(page):
    _mount(page, columnStacks=3)
    _js(page, "() => { H.reg('x', { home: 'column', after: 'sel', open: false }); P.open('x'); }")
    assert _where(page, "x")["stack"] == ["sel", "x"]


def _a_tab_at_the_foot_of_a_full_column_after_nothing(page):
    _mount(page, columnStacks=3)
    _js(page, "() => { H.reg('x', { home: 'column', open: false }); P.open('x'); }")
    w = _where(page, "x")
    assert w["stack"] == ["t1", "t2", "x"] and len(w["children"]) == 3


@pytest.mark.e2e
@pytest.mark.parametrize(
    "case",
    [
        _beside_its_home,
        _beside_kin_when_its_home_is_closed,
        _among_the_tabs,
        _under_the_window_it_follows,
        _with_its_siblings_under_that_window,
        _beside_the_world_with_room_from_the_world,
        _at_the_column_foot_after_nothing,
        _a_tab_beside_the_window_it_follows_once_the_column_is_full,
        _a_tab_at_once_in_a_column_of_three,
        _a_tab_at_the_foot_of_a_full_column_after_nothing,
    ],
    ids=lambda f: f.__name__.strip("_"),
)
def test_a_window_opens_at_its_home(wm: Page, case):
    case(wm)


# --- a window with nothing to show ----------------------------------------------------


def _minimised(page: Page, pid: str) -> bool:
    return _js(page, "(id) => P.state(id).minimised", pid)


def _alone_its_stack_is_minimised_and_has_its_height_back(page):
    before = _js(page, "() => H.size('sel')")
    _js(page, "() => P.setEmpty('sel')")
    assert _js(page, "() => P.state('sel').empty") is True and _minimised(page, "sel")
    assert _js(page, "() => H.height('sel')") <= 42  # its tabs and a hidden sliver
    _js(page, "() => P.setEmpty('sel', false)")
    assert not _minimised(page, "sel")
    assert _js(page, "() => H.size('sel')") == pytest.approx(before, abs=0.5)


def _in_front_of_one_with_something_it_gives_that_one_the_front(page):
    _js(page, "() => { P.open('b'); P.setEmpty('b'); }")
    assert _where(page, "a")["front"] == "a" and not _minimised(page, "a")


def _emptied_one_by_one_it_keeps_the_window_it_had_in_front(page):
    _js(page, "() => { P.open('a'); P.setEmpty('a'); }")
    assert _where(page, "a")["front"] == "b"
    _js(page, "() => P.setEmpty('b')")
    assert _where(page, "a")["front"] == "a" and _minimised(page, "a")
    _js(page, "() => P.setEmpty('a', false)")
    assert _where(page, "a")["front"] == "a" and not _minimised(page, "a")


def _a_stack_is_minimised_once_all_of_it_is_empty(page):
    _js(page, "() => P.setEmpty('a')")
    assert not _minimised(page, "a")
    _js(page, "() => P.setEmpty('b')")
    assert _minimised(page, "a")


def _opened_it_has_its_height_back(page):
    _js(page, "() => P.setEmpty('sel')")
    _js(page, "() => P.open('sel')")
    assert not _minimised(page, "sel") and _js(page, "() => H.height('sel')") > 42


def _its_tab_pressed_it_has_its_height_back(page):
    _js(page, "() => P.setEmpty('sel')")
    page.locator(".lm_tab[data-panel='sel']").click()
    assert not _minimised(page, "sel")


def _a_view_lays_it_out_minimised_again(page):
    _js(page, "() => { P.setEmpty('sel'); P.open('sel'); }")
    _js(page, "() => P.applyView('default')")
    assert _minimised(page, "sel")


def _remembered_at_the_height_it_had(page):
    before = _js(page, "() => H.size('sel')")
    _js(page, "() => P.setEmpty('sel')")
    _reload(page)
    assert not _minimised(page, "sel")
    assert _js(page, "() => H.size('sel')") == pytest.approx(before, abs=0.5)


@pytest.mark.e2e
@pytest.mark.parametrize(
    "case",
    [
        _alone_its_stack_is_minimised_and_has_its_height_back,
        _in_front_of_one_with_something_it_gives_that_one_the_front,
        _a_stack_is_minimised_once_all_of_it_is_empty,
        _emptied_one_by_one_it_keeps_the_window_it_had_in_front,
        _opened_it_has_its_height_back,
        _its_tab_pressed_it_has_its_height_back,
        _a_view_lays_it_out_minimised_again,
        _remembered_at_the_height_it_had,
    ],
    ids=lambda f: f.__name__.strip("_"),
)
def test_a_window_with_nothing_to_show_gives_its_room_away(wm: Page, case):
    case(wm)


@pytest.mark.e2e
@pytest.mark.parametrize("reloaded", [False, True], ids=["at-once", "after-a-reload"])
def test_with_the_world_alone_on_the_root_a_window_opens_beside_it(wm: Page, reloaded: bool):
    """Every window closed, GoldenLayout lays the world's stack on the root, where
    nothing can stand beside it: a window opened is laid out in a row with it, at once
    or once the page has remembered the world alone."""
    _js(wm, "() => { for (const id of ['a', 'b', 'sel', 't1', 't2']) P.close(id); }")
    if reloaded:
        _reload(wm)
        assert _js(wm, "() => ['a', 'b', 'sel', 't1', 't2'].some((id) => P.isOpen(id))") is False
    _js(wm, "() => P.open('sel')")
    assert _where(wm, "sel")["parent"] in ("row", "column")
    assert _where(wm, "world")["parent"] == "row"


# --- views ----------------------------------------------------------------------

VIEW = {
    "row": [
        {"world": True, "size": 50},
        {
            "column": [
                {"stack": ["sel", "nowhere"], "size": 40},
                {"stack": ["t2", "t1"], "active": "t1"},
            ]
        },
    ]
}


@pytest.mark.e2e
def test_a_view_lays_out_what_it_names_and_leaves_out_what_the_page_has_not(wm: Page):
    _js(wm, "(v) => P.defineView('v', { title: 'V', layout: v })", VIEW)
    assert _js(wm, "() => P.applyView('v')") is True
    assert _where(wm, "sel")["stack"] == ["sel"]  # `nowhere` is no window of the page's
    t = _where(wm, "t1")
    assert t["stack"] == ["t2", "t1"] and t["front"] == "t1"
    assert _js(wm, "() => P.isOpen('a')") is False  # a window the view leaves out is closed
    assert _js(wm, "() => P.applyView('default')") is True
    assert _where(wm, "a")["stack"] == ["a", "b"]


@pytest.mark.e2e
def test_a_view_that_needs_a_window_the_page_has_not_says_so_and_does_nothing(wm: Page):
    _js(
        wm,
        "(v) => P.defineView('v', { title: 'V', layout: v, requires: 'm', hint: 'its ring' })",
        VIEW,
    )
    assert _js(wm, "() => P.viewMissing('v')") == {"id": "m", "title": "V", "hint": "its ring"}
    assert _js(wm, "() => P.applyView('v')") is False
    assert _where(wm, "a") is not None  # nothing moved
    button = _js(
        wm,
        """() => { const into = document.createElement('div'); P.fillMenu(into);
            const b = into.querySelector("[data-view='v']"); return [b.disabled, b.title]; }""",
    )
    assert button == [True, "V lays out V's windows: open V first (its ring)"]
    _js(wm, "() => H.reg('m', { open: false })")
    assert _js(wm, "() => P.viewMissing('v')") is None and _js(wm, "() => P.applyView('v')") is True


@pytest.mark.e2e
@pytest.mark.parametrize("was_open", [True, False], ids=["open-stays-open", "closed-stays-closed"])
def test_a_window_made_for_the_moment_keeps_its_state_through_a_view(wm: Page, was_open: bool):
    _mount(wm, transient=["m"])
    _js(wm, "(o) => { H.reg('m', { home: 'beside', open: o }); }", was_open)
    assert _js(wm, "() => P.isOpen('m')") is was_open
    _js(wm, "() => P.applyView('default')")
    assert _js(wm, "() => P.isOpen('m')") is was_open


# --- what a browser remembers -----------------------------------------------------


def _reload(page: Page, **extra) -> None:
    page.wait_for_function("() => P.remembered()", timeout=5000)
    page.reload()
    page.wait_for_function("() => window.__ready === true")
    _mount(page, **extra)


@pytest.mark.e2e
def test_a_layout_is_remembered_and_a_window_made_for_the_moment_is_not(wm: Page):
    _mount(wm, transient=["m"])
    _js(wm, "() => { H.reg('m', { home: 'beside' }); P.close('t2'); P.open('b'); }")
    wm.wait_for_function("() => P.remembered()", timeout=5000)
    saved = _js(wm, "() => localStorage.getItem('windows.test')")
    assert '"componentType":"b"' in saved and '"componentType":"m"' not in saved
    _reload(wm, transient=["m"])
    assert _js(wm, "() => P.isOpen('t2')") is False  # closed by a person, it stays closed
    assert _where(wm, "b")["front"] == "b"


CHOSEN = ["gone", "y", "z", "w"]


@pytest.mark.e2e
@pytest.mark.parametrize("front", ["y", "z", "w"])
def test_a_remembered_stack_keeps_the_window_it_had_in_front(wm: Page, front: str):
    """A remembered stack loses a window the page no longer has; the one that was in
    front stays in front, wherever it now stands."""
    stack = {"type": "stack", "content": [{**TAB, "componentType": c, "id": c} for c in CHOSEN]}
    root = {**ROOT_LAYOUT, "content": [ROOT_LAYOUT["content"][0], stack]}
    _mount(wm, root=root, register=[[c, {}] for c in CHOSEN])
    _js(wm, "(id) => P.open(id)", front)
    # The page again, without `gone`: its own layout no longer names it.
    _reload(wm, known=CHOSEN[1:], register=[[c, {}] for c in CHOSEN[1:]])
    assert _js(wm, "() => P.isOpen('gone')") is False
    w = _where(wm, "y")
    assert w["stack"] == CHOSEN[1:] and w["front"] == front


@pytest.mark.e2e
def test_a_remembered_layout_the_page_cannot_read_is_ignored(wm: Page):
    wm.evaluate('() => localStorage.setItem(\'windows.test\', \'{"root": {"type": "stack"}}\')')
    wm.reload()
    wm.wait_for_function("() => window.__ready === true")
    _mount(wm)
    assert _where(wm, "a")["stack"] == ["a", "b"]


# --- a window's life ----------------------------------------------------------------


@pytest.mark.e2e
def test_a_windows_body_is_filled_when_first_shown_and_it_is_told_after(wm: Page):
    _js(wm, "() => H.reg('x', { home: 'beside', open: false, lazy: true, told: true })")
    assert _js(wm, "() => H.log.slice()") == []
    _js(wm, "() => P.open('x')")
    # Filled before open returns, so a verb sent to it next finds it.
    assert _js(wm, "() => !!document.querySelector(\".panel[data-panel='x'] .body\")") is True
    log = _js(wm, "() => H.log.slice()")
    assert log[0] == "fill x" and "close x" not in log
    _js(wm, "() => { P.close('x'); P.open('x'); }")
    log = _js(wm, "() => H.log.slice()")
    assert log.count("fill x") == 1  # filled once
    assert log.index("close x") < len(log) - 1 and log[-1] == "open x"


@pytest.mark.e2e
def test_a_window_taken_away_and_registered_again_is_the_same_body(wm: Page):
    _js(
        wm,
        "() => { window.kept = H.body('x'); P.register('x', { title: 'x', body: kept, home: 'beside' }); }",
    )
    _js(wm, "() => P.unregister('x')")
    assert _js(wm, "() => P.state('x')") is None
    _js(wm, "() => P.register('x', { title: 'x', body: kept, home: 'beside' })")
    assert (
        _js(wm, "() => document.querySelector(\".panel[data-panel='x'] .body\") === kept") is True
    )


@pytest.mark.e2e
def test_a_tab_says_something_new_and_wears_its_flag(wm: Page):
    _js(wm, "() => P.retitle('b', 'b (3)', { flag: 'bad' })")
    tab = wm.locator(".lm_tab[data-panel='b']")
    expect(tab).to_have_class(re.compile(r"\bbad\b"))
    expect(tab).to_contain_text("b (3)")
    _js(wm, "() => P.retitle('b', 'b')")
    expect(tab).not_to_have_class(re.compile(r"\bbad\b"))


@pytest.mark.e2e
def test_a_loud_window_wears_it_on_its_tab_and_its_frame(wm: Page):
    _js(wm, "() => H.reg('x', { home: 'beside', loud: true })")
    expect(wm.locator(".lm_tab[data-panel='x']")).to_have_class(re.compile(r"\bloud\b"))
    expect(
        wm.locator(".panel-window.loud", has=wm.locator(".panel[data-panel='x']"))
    ).to_have_count(1)


# --- what a person moves ----------------------------------------------------------------


def _tab(page: Page, pid: str):
    return page.locator(f".lm_tab[data-panel='{pid}']")


def _onto_the_worlds_left(page: Page, pid: str) -> None:
    """A window's tab dropped on the world's left edge: a stack of its own there."""
    world = page.locator("#world").bounding_box()
    windows.drag(page, _tab(page, pid), (world["x"] + 30, world["y"] + world["height"] / 2))
    page.wait_for_function(
        "(id) => H.where(id).stack.length === 1 && H.where(id).at < H.where('world').at", arg=pid
    )


def _onto_sels_stack(page: Page, pid: str) -> None:
    """A window's tab dropped on sel's header, just after sel's tab."""
    tab = _tab(page, "sel").bounding_box()
    windows.drag(
        page, _tab(page, pid), (tab["x"] + tab["width"] + 20, tab["y"] + tab["height"] / 2)
    )
    page.wait_for_function("(id) => H.where(id).stack.includes('sel')", arg=pid)


def _on_another_stack_it_stays_there_when_opened_again(page):
    _onto_sels_stack(page, "t2")
    _js(page, "() => P.open('t2')")
    w = _where(page, "t2")
    assert w["stack"] == ["sel", "t2"] and w["front"] == "t2"


def _on_the_worlds_left_it_is_a_window_of_its_own_with_a_tab(page):
    _onto_the_worlds_left(page, "sel")
    _js(page, "() => P.open('sel')")
    assert _where(page, "sel")["parent"] == "row"
    expect(_tab(page, "sel")).to_be_visible()
    assert page.locator("#world").bounding_box()["x"] > 100


def _on_the_worlds_right_quarter_it_is_a_window_of_its_own_with_a_tab(page):
    world = page.locator("#world").bounding_box()
    to = (world["x"] + world["width"] * 0.85, world["y"] + world["height"] / 2)
    windows.drag(page, _tab(page, "t1"), to)
    page.wait_for_function("() => H.where('t1').stack.length === 1")
    expect(_tab(page, "t1")).to_be_visible()
    # The world's own stack still shows no header.
    expect(page.locator(".lm_stack:has(#world) > .lm_header")).to_be_hidden()


def _moved_it_is_where_it_was_put_after_a_reload(page):
    _onto_the_worlds_left(page, "sel")
    _reload(page)
    w = _where(page, "sel")
    assert w["stack"] == ["sel"] and w["at"] < _where(page, "world")["at"]


def _reset_puts_every_window_back_at_its_home(page):
    before = {pid: _where(page, pid) for pid in ("sel", "t2")}
    _onto_the_worlds_left(page, "sel")
    _onto_sels_stack(page, "t2")
    _js(page, "() => P.reset()")
    assert {pid: _where(page, pid) for pid in ("sel", "t2")} == before


def _made_for_the_moment_closed_and_opened_again_it_is_at_its_home(page):
    _mount(page, transient=["m"])
    _js(page, "() => { H.reg('m', { home: 'tabs', open: false }); P.open('m'); }")
    _onto_sels_stack(page, "m")
    _js(page, "() => P.open('m')")
    assert _where(page, "m")["stack"] == ["sel", "m"]
    _js(page, "() => { P.close('m'); P.open('m'); }")
    w = _where(page, "m")
    assert w["stack"] == ["t1", "t2", "m"] and w["front"] == "m"


def _the_splitter_beside_the_world_keeps_its_width_after_a_reload(page):
    before = _js(page, "() => H.size('world')")
    splitter = page.locator(".lm_root > .lm_row > .lm_splitter").first
    box = splitter.bounding_box()
    windows.drag(page, splitter, (box["x"] - 120, box["y"] + box["height"] / 2))
    page.wait_for_function("(w) => H.size('world') < w - 5", arg=before)
    moved = _js(page, "() => H.size('world')")
    _reload(page)
    assert _js(page, "() => H.size('world')") == pytest.approx(moved, abs=0.5)


@pytest.mark.e2e
@pytest.mark.parametrize(
    "case",
    [
        _on_another_stack_it_stays_there_when_opened_again,
        _on_the_worlds_left_it_is_a_window_of_its_own_with_a_tab,
        _on_the_worlds_right_quarter_it_is_a_window_of_its_own_with_a_tab,
        _moved_it_is_where_it_was_put_after_a_reload,
        _reset_puts_every_window_back_at_its_home,
        _made_for_the_moment_closed_and_opened_again_it_is_at_its_home,
        _the_splitter_beside_the_world_keeps_its_width_after_a_reload,
    ],
    ids=lambda f: f.__name__.strip("_"),
)
def test_a_window_a_person_moves_stays_where_it_is_put(wm: Page, case):
    case(wm)


# --- focused systems ------------------------------------------------------------------


def _system(sid: str, sections, *, transient: bool = False, view=None) -> System:
    """A system of the test's own, written as the registry writes one: its main window
    the system's id, its view (unless given) the world and a stack of every window."""
    return System(
        id=sid,
        title=sid.title(),
        group=sid.title(),
        main=sid,
        sections=tuple(sections),
        view=view
        or {"row": [{"world": True}, {"stack": [sid, *(f"{sid}-{s.id}" for s in sections)]}]},
        cell=f"{sid.title()} view",
        opened_by=f"{sid.title()}'s ring",
        transient=transient,
    )


# Two systems as the page is given them (apothecary/systems.py's manifest): Alpha, which
# lasts, a section beside its main window and one in the column; Beta, made for the
# moment, its sections in the column.
SYSTEMS = manifest(
    (
        _system(
            "alpha",
            [
                Section("one", "One", "the first", home="alpha", verbs=("alpha:one",)),
                Section("two", "Two", "the second", home="column", verbs=("alpha:pre:",)),
            ],
        ),
        _system(
            "beta",
            [
                Section("x", "X", "an x", home="column", verbs=("beta:x",)),
                Section("y", "Y", "a y", home="column"),
            ],
            transient=True,
        ),
    )
)

MOUNT_SYSTEMS = """(systems) => {
    const { mountSystems } = window.__wm;
    window.mounted = 0;
    window.redrawn = 0;
    window.S = mountSystems(P, systems, {
        alpha: {
            main: { title: 'Alpha' },
            mount: (slot, sections) => {
                window.mounted += 1;
                for (const [id, el] of Object.entries(sections)) el.textContent = `drawn ${id}`;
                return { redraw: () => { window.redrawn += 1; } };
            },
        },
        beta: { mount: () => ({}) },
    });
}"""


def _systems(page: Page) -> None:
    known = page.evaluate("(s) => window.__wm.knownWindows(s)", SYSTEMS)
    transient = page.evaluate("(s) => window.__wm.transientWindows(s)", SYSTEMS)
    assert known == ["alpha", "alpha-one", "alpha-two", "beta", "beta-x", "beta-y"]
    assert transient == ["beta", "beta-x", "beta-y"]
    _mount(page, known=known, transient=transient)
    page.evaluate(MOUNT_SYSTEMS, SYSTEMS)


@pytest.mark.e2e
def test_a_systems_sections_are_windows_closed_until_asked_for(wm: Page):
    _systems(wm)
    for pid in ("alpha", "alpha-one", "alpha-two"):
        state = _js(wm, "(id) => P.state(id)", pid)
        assert state["open"] is False and state["group"] == "Alpha"
    assert _js(wm, "() => window.mounted") == 0  # nothing mounted until something is shown
    _js(wm, "() => S.alpha.showSection('one')")
    mounted, redrawn = _js(wm, "() => [window.mounted, window.redrawn]")
    assert mounted == 1 and redrawn >= 1  # a section shown mounts the widget and draws it
    _js(wm, "() => S.alpha.showSection('two')")
    assert _js(wm, "() => window.mounted") == 1  # mounted once
    assert _js(wm, "() => window.redrawn") > redrawn
    assert _js(wm, "() => P.isOpen('alpha-one')") is True
    assert _where(wm, "alpha-two")["parent"] == "column"  # its home, the column


@pytest.mark.e2e
def test_a_remembered_section_comes_back_drawn(wm: Page):
    """A section open when the layout was remembered is open after a reload with its
    body in it: the window the remembered layout names before the system is mounted is
    registered by the system all the same, and drawn."""
    _systems(wm)
    _js(wm, "() => S.alpha.showSection('one')")
    wm.wait_for_function("() => P.remembered()", timeout=5000)
    wm.reload()
    wm.wait_for_function("() => window.__ready === true")
    _systems(wm)
    assert _js(wm, "() => P.state('alpha-one')")["registered"] is True
    expect(wm.locator(".panel[data-panel='alpha-one']")).to_have_text("drawn one")


@pytest.mark.e2e
@pytest.mark.parametrize(
    "action, opened",
    [
        ("alpha:one", {"alpha-one"}),
        ("alpha:pre:anything", {"alpha-two"}),
        ("alpha:pre", set()),  # a prefix is not its own verb
        ("alpha:one:more", set()),  # a named verb is not a prefix
        ("beta:x", set()),  # Beta is not attached: its windows are not there
    ],
)
def test_a_verb_opens_the_sections_it_acts_on(wm: Page, action: str, opened: set):
    _systems(wm)
    _js(wm, "([s, a]) => window.__wm.openFor(P, s, a)", [SYSTEMS, action])
    every = ["alpha-one", "alpha-two", "beta-x", "beta-y"]
    assert {pid for pid in every if _js(wm, "(id) => P.isOpen(id)", pid)} == opened


@pytest.mark.e2e
def test_a_system_made_for_the_moment_is_attached_and_detached_with_its_subject(wm: Page):
    _systems(wm)
    assert _js(wm, "() => P.state('beta-x')") is None
    assert _js(wm, "() => P.viewMissing('beta')") == {
        "id": "beta",
        "title": "Beta",
        "hint": "Beta's ring",
    }
    _js(wm, "() => { H.reg('beta', { home: 'tabs' }); S.beta.attach(); }")
    assert _js(wm, "() => P.state('beta-x').open") is False
    _js(wm, "([s]) => window.__wm.openFor(P, s, 'beta:x')", [SYSTEMS])
    assert _js(wm, "() => P.isOpen('beta-x')") is True
    assert _js(wm, "() => P.applyView('beta')") is True
    assert _where(wm, "beta")["stack"] == ["beta", "beta-x", "beta-y"]
    _js(wm, "() => { S.beta.detach(); P.unregister('beta'); }")
    assert [_js(wm, "(id) => P.state(id)", pid) for pid in ("beta", "beta-x", "beta-y")] == [
        None
    ] * 3


# A system whose sections are for kinds of subject: one for any, one for each of two.
KINDED = manifest(
    (
        _system(
            "gamma",
            [
                Section(sid, sid, sid, home="column", kind=kind)
                for sid, kind in (("any", None), ("one", "one"), ("two", "two"))
            ],
            transient=True,
            view={"row": [{"world": True}, {"stack": ["gamma"]}]},
        ),
    )
)


@pytest.mark.e2e
@pytest.mark.parametrize(
    "steps, there",
    [
        ([{}], {"gamma-any"}),
        ([{"kind": "one"}], {"gamma-any", "gamma-one"}),
        ([{"kind": "one"}, {"kind": "two"}], {"gamma-any", "gamma-two"}),
        ([{"kind": "two", "without": ["two"]}], {"gamma-any"}),
    ],
    ids=["no-kind-yet", "one", "one-then-two", "without"],
)
def test_a_subject_has_the_sections_of_its_kind(wm: Page, steps: list, there: set):
    """A section for one kind of subject is a window only while the subject is of that
    kind: attached again as it turns out to be another, and left out where asked."""
    _mount(wm, transient=["gamma", "gamma-any", "gamma-one", "gamma-two"])
    _js(
        wm,
        "(s) => { window.G = window.__wm.mountSystems(P, s, { gamma: { mount: () => ({}) } }); }",
        KINDED,
    )
    for step in steps:
        _js(wm, "(o) => G.gamma.attach(o)", step)
    every = ["gamma-any", "gamma-one", "gamma-two"]
    assert {w for w in every if _js(wm, "(id) => P.state(id)", w) is not None} == there


# --- a stack's + and the world alone --------------------------------------------------------


@pytest.mark.e2e
def test_every_stack_but_the_worlds_has_a_plus_that_opens_a_window_there(wm: Page):
    expect(wm.locator(".lm_stack:has(#world) .lm_spawn")).to_have_count(0)
    expect(wm.locator(".lm_spawn")).to_have_count(3)
    _js(wm, "() => H.reg('x', { group: 'Mine', home: 'beside', open: false })")
    plus = wm.locator(".lm_stack:has(.lm_tab[data-panel='t1']) .lm_spawn")
    plus.click()
    menu = wm.locator(".spawn-list")
    expect(menu.locator(".spawn-group")).to_contain_text(["Panels", "Mine"])
    expect(menu.locator("[data-window='x']")).to_have_text("○ x")
    wm.keyboard.press("Escape")
    expect(menu).to_have_count(0)
    plus.click()
    menu.locator("[data-window='x']").click()
    assert _where(wm, "x")["stack"] == ["t1", "t2", "x"]  # in that stack, not at its home
    assert _where(wm, "x")["front"] == "x"


@pytest.mark.e2e
def test_the_world_alone_and_a_window_opened_brings_everything_back(wm: Page):
    assert _js(wm, "() => P.worldAlone(true)") is True
    assert _js(wm, "() => P.isShown('sel')") is False
    _js(wm, "() => P.open('sel')")
    assert _js(wm, "() => [P.isWorldAlone(), P.isShown('sel')]") == [False, True]


@pytest.mark.e2e
def test_the_harness_is_the_modules_the_viewer_loads():
    """The page under test is the viewer's own modules, not copies: the viewer imports
    panels.js and systems.js from /static, as the harness does."""
    viewer = (ROOT / "templates" / "fractal_viewer.html.j2").read_text(encoding="utf-8")
    assert "from '/static/panels.js'" in viewer and "from '/static/systems.js'" in viewer
    assert json.loads(json.dumps(SYSTEMS))  # plain JSON, as manifest() gives the page
