"""Typing in the ring, in a browser: rad's vectors pressed into the page's own ring, and
the garage's rings searched as a person searches them.

rad's *typing in an open ring finds an item* (docs/viewer.md, "The ring"): letters typed
while the ring is open are a query; each result shows the keys that reach it; Tab
completes, Enter presses the result's address from the root; and the status line says,
after the choice, the keys that would have made it. tests/test_ring_search.py holds the
search itself to rad's vectors in Python and in ring.js; here the ring that draws and
presses is held to their `walk` and `type` cases, with the resolver's answer the tree
those cases run on.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from garage import open_garage, said, status
from playwright.sync_api import Page, expect
from ring_helpers import rad_ring
from rings import (
    RING_MS,
    cells,
    open_from_key,
    open_on_row,
    open_on_world,
    press_cells,
    query,
    result_on,
    results,
)

VECTORS = json.loads(
    (Path(__file__).resolve().parents[1] / "conformance" / "rad" / "vectors.json").read_text(
        encoding="utf-8"
    )
)
SEARCH = [c["search"] for c in VECTORS["cases"] if "search" in c]

CAPTURE = (
    "window.__intents = []; "
    "window.addEventListener('apothecary:intent', (e) => window.__intents.push(e.detail));"
)
# A key of rad's vectors as Playwright presses it.
PRESSED = {" ": "Space", "Ctrl+b": "Control+b"}


@pytest.fixture(scope="module")
def url(start_server):
    return start_server()


def _on_rads_tree(page: Page, url: str) -> dict:
    """The garage open, its intents captured, and every ring resolved as rad's workshop
    tree: the ring that draws and presses is the page's, the options are the vectors'."""
    page.add_init_script(CAPTURE)
    open_garage(page, url, settle=False)
    workshop = rad_ring(VECTORS, "workshop").model_dump(mode="json")
    page.route(
        "**/menu/resolve",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(workshop)
        ),
    )
    return {o["id"]: o for o in _every(workshop["options"])}


def _every(options):
    for option in options:
        yield option
        yield from _every(option.get("children") or [])


def _closed(page: Page) -> None:
    """The ring away: Escape lets a query go first, then closes the ring."""
    for _ in range(3):
        if not page.locator("#ring-overlay").count():
            return
        page.keyboard.press("Escape")
    expect(page.locator("#ring-overlay")).to_have_count(0)


def _chose(page: Page, option_id: str, address: str) -> None:
    page.wait_for_function(
        "([id, at]) => window.__intents.some((i) => i.option_id === id && i.address === at)",
        arg=[option_id, address],
        timeout=RING_MS,
    )


def _ring_at(page: Page) -> dict:
    return page.evaluate(
        "() => { const r = window.apothecaryRing.current(); return { depth: r.stack.length, address: r.address }; }"
    )


@pytest.mark.e2e
def test_an_address_pressed_into_the_ring_does_what_rads_machine_does(page: Page, url: str):
    """Each `walk` case of rad's vectors: its cells pressed by their digits, and what the
    page's ring then holds -- the option chosen, or the ring it stands in."""
    _on_rads_tree(page, url)
    walks = [k for s in SEARCH for k in s.get("walk", [])]
    assert walks
    for k in walks:
        open_from_key(page)
        press_cells(page, *k["address"])
        if k["expectCommitted"]:
            _chose(page, k["expectCommitted"], k["address"])
            expect(page.locator("#ring-overlay")).to_have_count(0)
        else:
            assert page.locator("#ring-overlay").count() == (1 if k["expectOpen"] else 0), k
            if k["expectOpen"] and k.get("expectDepth"):
                assert _ring_at(page)["depth"] == k["expectDepth"], k
        _closed(page)


@pytest.mark.e2e
def test_keys_typed_in_the_ring_read_as_rads_vectors_say(page: Page, url: str):
    """Each `type` case: its keys pressed in the open ring, the query written under it as
    the case says, and what Enter chose pressed -- a leaf chosen, a ring entered."""
    by_id = _on_rads_tree(page, url)
    cases = [k for s in SEARCH for k in s.get("type", [])]
    assert len(cases) >= 20
    for k in cases:
        open_from_key(page)
        for key in k["keys"]:
            page.keyboard.press(PRESSED.get(key, key))
        assert query(page) == k["expectText"], k
        if k.get("expectChosen"):
            option_id, address = k["expectChosen"]
            if by_id[option_id].get("children"):
                assert _ring_at(page)["address"] == address, k
            else:
                _chose(page, option_id, address)
        _closed(page)


@pytest.mark.e2e
def test_the_canvas_ring_searched_shows_each_results_keys_and_says_them_after(page: Page, url: str):
    """The garage's own canvas ring, from m with nothing selected: `fit` finds View › Fit
    at m 2 8 first, and the page's own f and Shift+F after the ring's options. Tab
    completes the query to each in turn and round; Enter presses the one it is on, and
    the status line says the keys after what Fit said."""
    page.add_init_script(CAPTURE)
    open_garage(page, url, settle=False)
    open_from_key(page)
    page.keyboard.type("fit")
    assert query(page) == "fit"
    found = results(page)
    assert found[0] == "View › Fit  m 2 8", found
    assert found[-2:] == ["Fit the selection  f", "Fit the level  Shift+F"], found
    for i in range(len(found) + 1):
        page.keyboard.press("Tab")
        assert query(page) == found[(i) % len(found)].rsplit("  ", 1)[0]
    page.keyboard.press("Enter")
    page.wait_for_function(
        "() => window.__intents.some((i) => i.address === '28')", timeout=RING_MS
    )
    intent = page.evaluate("() => window.__intents.find((i) => i.address === '28')")
    assert (intent["label"], intent["searched"]) == ("Fit", "m 2 8")
    said(page, "next time, m 2 8")


@pytest.mark.e2e
def test_a_ring_entered_by_a_search_stays_open_and_says_its_keys(page: Page, url: str):
    """`view` finds View, a ring of its own: Enter enters it and leaves the ring open at
    ⌗2, and the status line says how it is entered next time."""
    open_garage(page, url, settle=False)
    open_from_key(page)
    page.keyboard.type("view")
    assert results(page)[0] == "View  m 2"
    page.keyboard.press("Enter")
    assert _ring_at(page) == {"depth": 2, "address": "2"}
    assert query(page) == ""
    said(page, "View: next time, m 2")
    _closed(page)


@pytest.mark.e2e
def test_a_digit_typed_mid_query_is_its_cell(page: Page, url: str):
    """The query has no digits: 2 pressed while one is up lets it go and enters View."""
    open_garage(page, url, settle=False)
    open_from_key(page)
    page.keyboard.type("zz")
    assert results(page) == ["nothing found"]
    page.keyboard.press("2")
    assert query(page) == ""
    assert _ring_at(page) == {"depth": 2, "address": "2"}
    _closed(page)


@pytest.mark.e2e
def test_the_pages_own_keys_are_found_after_the_rings_and_pressed_as_keys(page: Page, url: str):
    """`fit the l` finds no option and finds Shift+F, Fit the level: Enter closes the ring
    and presses Shift+F, which frames the level and says so, and the keys after."""
    open_garage(page, url, settle=False)
    open_from_key(page)
    page.keyboard.type("fit the l")
    assert results(page) == ["Fit the level  Shift+F"]
    page.keyboard.press("Enter")
    expect(page.locator("#ring-overlay")).to_have_count(0)
    said(page, "Framed the level")
    said(page, "next time, Shift+F")


@pytest.mark.e2e
def test_a_greyed_ring_on_the_way_stops_the_walk_where_it_is_refused(page: Page, url: str):
    """rad's tree with View greyed: `fit a` still finds View › Fit › All, and Enter presses
    4 -- refused, its reason said -- and stops there, rather than pressing 8 and 8 in the
    ring it stayed in, which would choose Heat's Hotend on."""
    page.add_init_script(CAPTURE)
    open_garage(page, url, settle=False)
    ring = rad_ring(VECTORS, "workshop").model_dump(mode="json")
    view = next(o for o in ring["options"] if o["id"] == "view")
    view.update(enabled=False, why="nothing to view here")
    page.route(
        "**/menu/resolve",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(ring)
        ),
    )
    open_from_key(page)
    page.keyboard.type("fit a")
    assert results(page) == ["View › Fit › All  m 4 8 8"]
    page.keyboard.press("Enter")
    assert _ring_at(page) == {"depth": 1, "address": ""}
    expect(page.locator("#status")).to_contain_text("nothing to view here", timeout=RING_MS)
    assert page.evaluate("() => window.__intents") == []
    _closed(page)


def _on_a_tree(page: Page, url: str, ring: dict) -> None:
    """The garage open, its intents captured, and every ring resolved as ``ring``."""
    page.add_init_script(CAPTURE)
    open_garage(page, url, settle=False)
    page.route(
        "**/menu/resolve",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(ring)
        ),
    )


@pytest.mark.e2e
def test_a_greyed_result_chosen_is_refused_as_its_cell_pressed_is(page: Page, url: str):
    """rad's tree: `arm` finds Arm, greyed, drawn off; Enter presses 3, which refuses as a
    press on it does -- the ring stays, the reason is said, and nothing is chosen."""
    _on_a_tree(page, url, rad_ring(VECTORS, "workshop").model_dump(mode="json"))
    open_from_key(page)
    page.keyboard.type("arm")
    expect(page.locator("#ring-overlay .found.off")).to_have_text("Arm  m 3")
    page.keyboard.press("Enter")
    assert _ring_at(page) == {"depth": 1, "address": ""}
    expect(status(page)).to_contain_text("Arm (⌗3)", timeout=RING_MS)
    assert page.evaluate("() => window.__intents") == []
    _closed(page)


@pytest.mark.e2e
def test_a_result_asked_twice_asks_and_its_second_press_says_the_keys(page: Page, url: str):
    """rad's tree with Stop asked twice: Enter presses 9, which asks, "again to stop"; the
    second press is the ring's own, and the choice it makes still says m 9 after."""
    ring = rad_ring(VECTORS, "workshop").model_dump(mode="json")
    next(o for o in ring["options"] if o["id"] == "stop")["twice"] = True
    _on_a_tree(page, url, ring)
    open_from_key(page)
    page.keyboard.type("stop")
    page.keyboard.press("Enter")
    expect(page.locator("#ring-overlay .label.armed")).to_contain_text("again to")
    assert page.evaluate("() => window.__intents") == []
    page.keyboard.press("Enter")
    _chose(page, "stop", "9")
    intent = page.evaluate("() => window.__intents.find((i) => i.option_id === 'stop')")
    assert intent["searched"] == "m 9" and intent["confirmed"] is True
    expect(status(page)).to_contain_text("next time, m 9", timeout=RING_MS)


@pytest.mark.e2e
def test_a_results_keys_start_from_the_key_that_opens_its_ring(page: Page, url: str):
    """The same View › Fit, reached from each way in: m with nothing selected and Shift+M
    give their own key; the canvas ring opened by Ctrl+right-click on the world is Shift+M's,
    and a piece's ring opened on its row is m's, the piece being selected; a ring key moved
    in Settings is shown as the new key."""
    open_garage(page, url, settle=False)
    for key, keys in (("m", "m 2 8"), ("Shift+M", "Shift+M 2 8")):
        open_from_key(page, key)
        page.keyboard.type("fit")
        assert results(page)[0] == f"View › Fit  {keys}"
        _closed(page)
    open_on_world(page)
    page.keyboard.type("fit")
    assert results(page)[0] == "View › Fit  Shift+M 2 8"
    _closed(page)
    open_on_row(page, "printer_1")
    page.keyboard.type("why")
    assert results(page)[0] == "Why this  m 2"
    _closed(page)
    assert page.evaluate("() => window.fractalViewer.settings.set('ringKey', 'k').ok")
    open_from_key(page, "k")
    page.keyboard.type("fit")
    assert results(page)[0] == "View › Fit  k 2 8"
    _closed(page)
    page.evaluate("() => window.fractalViewer.settings.resetAll()")


@pytest.mark.e2e
def test_searched_from_inside_a_ring_the_keys_and_the_press_start_from_the_top(
    page: Page, url: str
):
    """Standing in View (⌗2), `layers` still shows View › Layers at m 2 1 -- the keys from a
    closed ring -- and Enter presses them from the top: out to the canvas ring, then 2, 1."""
    page.add_init_script(CAPTURE)
    open_garage(page, url, settle=False)
    open_from_key(page)
    press_cells(page, "2")
    assert _ring_at(page) == {"depth": 2, "address": "2"}
    page.keyboard.type("layers")
    assert results(page)[0] == "View › Layers  m 2 1"
    page.keyboard.press("Enter")
    assert _ring_at(page) == {"depth": 3, "address": "21"}
    said(page, "Layers: next time, m 2 1")
    _closed(page)


@pytest.mark.e2e
def test_a_search_seats_nothing_and_escape_lets_the_query_go_first(page: Page, url: str):
    """The ring's cells are the same while a query is up as before it; Escape lets the
    query go and leaves the ring open, and the next Escape closes it."""
    open_garage(page, url, settle=False)
    open_from_key(page)
    before = cells(page)
    page.keyboard.type("fit")
    assert results(page) and cells(page) == before
    page.keyboard.press("Escape")
    assert query(page) == "" and results(page) == []
    expect(page.locator("#ring-overlay")).to_have_count(1)
    assert cells(page) == before
    page.keyboard.press("Escape")
    expect(page.locator("#ring-overlay")).to_have_count(0)


@pytest.mark.e2e
def test_tab_past_the_fifth_result_writes_the_one_it_is_on(page: Page, url: str):
    """`step` finds more than five on the canvas ring: Tab walks them in order, and the one
    it is on is written under the ring and lit, past the fifth as before it."""
    open_garage(page, url, settle=False)
    open_from_key(page)
    page.keyboard.type("step")
    assert result_on(page) == results(page)[0]
    seen = []
    for _ in range(6):
        page.keyboard.press("Tab")
        lit = result_on(page)
        assert lit.rsplit("  ", 1)[0] == query(page), (lit, query(page))
        seen.append(lit)
    assert len(set(seen)) == 6, seen
    _closed(page)
