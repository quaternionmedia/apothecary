"""Site: the site's Contents tree as its body, its problems at the top, its
generated SCAD and Pinned -- every site's pins, each taken back from its row.

The problems: a piece a problem names -- by the tree path the server sends
beside its name -- is red in the tree and its ancestors say something inside is
invalid; each problem is a row that selects its piece, at its level; the
toolbar's count opens them. Pinned is what Kept's pins list was
(the pictures plan's Phase 5): a camera and a view pinned in ``garage`` are
taken back from their rows while the page shows ``parts_library``, and the site
on screen and the URL never change.
"""

from __future__ import annotations

import io
import json
import re
from urllib.parse import urlparse

import pytest
from PIL import Image, ImageDraw
from playwright.sync_api import expect

CAMERA = "pinned_panel_camera"


def _png(offset: int) -> bytes:
    img = Image.new("L", (400, 300), 245)
    ImageDraw.Draw(img).rectangle((40 + offset, 40, 200 + offset, 160), fill=30)
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def _keep(page, base_url: str, name: str, offset: int, where: str = "") -> dict:
    kept = page.request.post(
        f"{base_url}/photos/pictures?name={name}&kept=upload{where}",
        data=_png(offset),
        headers={"Content-Type": "image/png"},
    )
    assert kept.status == 201, kept.text()
    return kept.json()


def _open(page, base_url: str, site: str = "garage") -> None:
    page.goto(f"{base_url}/viewer/sites/{site}")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=20000)
    page.evaluate("() => localStorage.removeItem('apothecary.panels')")


def _row(page, path: str):
    return page.locator(f"#contents-list .contents-item[data-path='{path}']")


@pytest.fixture
def leaves_as_found(page, base_url: str):
    """After the test: the camera, views and kept pictures it added are taken back."""
    api = page.request
    views = {vw["id"] for vw in api.get(f"{base_url}/placed").json()["views"]}
    pictures = {p["path"] for p in api.get(f"{base_url}/photos/pictures").json()}
    yield
    api.delete(f"{base_url}/cameras/{CAMERA}")
    for view in api.get(f"{base_url}/placed").json()["views"]:
        if view["id"] not in views:
            api.delete(f"{base_url}/sites/{view['site']}/views/{view['id']}")
    for picture in api.get(f"{base_url}/photos/pictures").json():
        if picture["path"] not in pictures and picture["kept"]:
            api.delete(f"{base_url}/photos/pictures/{picture['path']}")


@pytest.mark.e2e
def test_site_is_stacked_in_the_one_rail_and_the_retired_panels_are_gone(page, base_url: str):
    """Site is the one rail's, open and stacked over Selected, with the tree as its body;
    Validation, OpenSCAD, Kept and Gather are no panels of the page's."""
    _open(page, base_url)
    rail = page.locator(".panel-rail")
    expect(rail).to_have_count(1)
    site = rail.locator(".panel[data-panel='site']")
    expect(site).to_be_visible()
    expect(site.locator(".panel-name")).to_have_text("Site")
    expect(site.locator("#contents-list")).to_be_visible()
    assert page.evaluate("() => window.apothecaryPanels.state('site').zone") == "stack"
    ids = page.evaluate("() => window.apothecaryPanels.list().map((p) => p.id)")
    assert ids == ["site", "selected", "pictures"]
    for gone in ("contents", "validation", "scad", "kept", "camera", "jobs"):
        assert page.evaluate("(id) => window.apothecaryPanels.state(id)", gone) is None
    # The one rail leaves the world at least half the page.
    width = page.viewport_size["width"]
    assert page.locator(".viewer-panel").bounding_box()["width"] >= width / 2 - 2


@pytest.mark.e2e
def test_a_layout_remembered_with_the_old_panels_is_ignored(page, base_url: str):
    """A browser that remembered two rails -- Site docked left, the right rail narrowed
    and the left hidden -- and Contents, Validation, OpenSCAD, Kept and Gather opens
    the page with no error and the panels and the one rail as they start."""
    old = {
        "contents": {"open": False, "where": "free", "x": 9, "y": 9},
        "validation": {"open": True, "collapsed": True, "where": "left"},
        "scad": {"open": False},
        "kept": {"open": True, "where": "free"},
        "camera": {"open": True},
        "site": {"open": True, "collapsed": True, "where": "left"},
        "selected": {"open": False, "where": "right"},
        "_rails": {
            "right": {"width": 300, "hidden": False},
            "left": {"width": 260, "hidden": True},
        },
    }
    page.add_init_script(
        f"try {{ localStorage.setItem('apothecary.panels', {json.dumps(json.dumps(old))}); }} catch (e) {{}}"
    )
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"{base_url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=20000)
    states = page.evaluate("() => window.apothecaryPanels.list()")
    assert [(s["id"], s["open"], s["collapsed"], s["where"]) for s in states] == [
        ("site", True, False, "rail"),
        ("selected", True, False, "rail"),
        ("pictures", True, False, "rail"),
    ]
    expect(page.locator(".panel-tab")).to_have_count(0)  # nothing closed
    rail = page.locator(".panel-rail")
    expect(rail).to_be_visible()
    expect(rail).to_have_attribute("data-side", "right")
    # The width it starts with, not the one a right rail was dragged to.
    assert page.evaluate("() => window.apothecaryPanels.railWidth()") != 300
    assert errors == []


@pytest.mark.e2e
def test_a_layout_remembered_with_the_jobs_panel_is_harmless(page, base_url: str):
    """A one-rail layout remembered while the Jobs panel was a tab of the strip -- Jobs
    floated free, then its tab the one shown -- opens the page with no error and no
    Jobs anywhere; the rest of what was remembered still holds, and the next thing
    remembered forgets Jobs."""
    old = {
        "_rail": {"side": "left", "width": 360, "hidden": False, "tab": "jobs"},
        "site": {"open": True, "collapsed": False, "where": "rail"},
        "selected": {"open": True, "collapsed": True, "where": "rail"},
        "jobs": {"open": True, "collapsed": False, "where": "free", "x": 80, "y": 60},
        "pictures": {"open": False, "collapsed": False, "where": "rail"},
    }
    page.add_init_script(
        f"if (!sessionStorage.getItem('seeded')) {{ sessionStorage.setItem('seeded', '1');"
        f" localStorage.setItem('apothecary.panels', {json.dumps(json.dumps(old))}); }}"
    )
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"{base_url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=20000)
    states = page.evaluate("() => window.apothecaryPanels.list()")
    assert [(s["id"], s["open"], s["collapsed"]) for s in states] == [
        ("site", True, False),
        ("selected", True, True),
        ("pictures", False, False),
    ]
    assert page.evaluate("() => window.apothecaryPanels.state('jobs')") is None
    expect(page.locator("[data-panel='jobs']")).to_have_count(0)
    rail = page.locator(".panel-rail")
    expect(rail).to_have_attribute("data-side", "left")
    # Pictures' tab, closed, brings it back into the strip and shows it.
    page.locator(".panel-tab[data-panel='pictures']").click()
    expect(rail.locator(".panel[data-panel='pictures']")).to_be_visible(timeout=2000)
    remembered = json.loads(page.evaluate("() => localStorage.getItem('apothecary.panels')"))
    assert "jobs" not in remembered and remembered["_rail"]["tab"] == "pictures"
    assert errors == []


@pytest.mark.e2e
def test_a_problem_marks_its_pieces_and_its_row_selects_one_at_its_level(page, base_url: str):
    """printer_1 moved onto printer_2: both rows red, saying why on hover; the problem
    listed at Site's top selects printer_1 from a level below, stepping out to it."""
    _open(page, base_url)
    status = page.locator("#status")
    problems = page.locator("#site-problems")
    expect(problems).to_be_hidden()
    _row(page, "printer_1").click()
    x = page.locator("#pos-x")
    expect(x).to_be_visible()
    x.fill("650")
    x.press("Tab")
    expect(page.locator("#validity-indicator")).to_contain_text("violation", timeout=5000)
    rows = page.locator("#problem-list li")
    expect(rows).to_have_count(1)
    expect(rows.first).to_have_text("printer_1 and printer_2 overlap")
    expect(page.locator("#site-problems-count")).to_have_text("1 problem")
    for name in ("printer_1", "printer_2"):
        expect(_row(page, name)).to_have_class(re.compile(r"\binvalid\b"))
        expect(_row(page, name)).to_have_attribute(
            "title", re.compile("printer_1 and printer_2 overlap")
        )
    expect(_row(page, "printer_3")).not_to_have_class(re.compile(r"\binvalid"))

    # From inside the bench, the row steps back out to the root and selects printer_1.
    page.evaluate("() => window.fractalViewer.zoomIn('workbench')")
    expect(page.locator("#breadcrumb")).to_contain_text("workbench")
    rows.first.click()
    expect(page.locator("#breadcrumb")).not_to_contain_text("workbench")
    assert page.evaluate("() => window.fractalViewer.focusPath") == []
    assert page.evaluate("() => window.fractalViewer.selectedName") == "printer_1"
    expect(_row(page, "printer_1")).to_have_class(re.compile(r"\bselected\b"))

    # Moved back: no problem, no mark.
    x = page.locator("#pos-x")
    x.fill("100")
    x.press("Tab")
    expect(page.locator("#validity-indicator")).to_have_text("Layout valid", timeout=5000)
    expect(problems).to_be_hidden()
    expect(_row(page, "printer_1")).not_to_have_class(re.compile(r"\binvalid"))
    expect(status).not_to_have_class(re.compile(r"\berror\b"))


def _with_posts_overlapping(printer: str):
    """A route answering the garage with one more problem: two posts inside
    ``printer``'s gantry, as the site's answer would carry an overlap between
    siblings -- their names, and beside them their paths."""

    def route_it(route):
        answer = route.fetch()
        body = answer.json()
        body["violations"] = [
            *body["violations"],
            {
                "kind": "overlap",
                "message": "left_post and right_post overlap",
                "structures": ["left_post", "right_post"],
                "paths": [
                    f"{printer}.gantry_system.left_post",
                    f"{printer}.gantry_system.right_post",
                ],
            },
        ]
        body["is_valid"] = False
        route.fulfill(response=answer, json=body)

    return route_it


@pytest.mark.e2e
def test_a_problem_deep_in_the_tree_marks_every_piece_above_it(page, base_url: str):
    """A problem a validator finds below the root -- here two posts inside printer_1's
    gantry -- marks the posts, and printer_1 and its gantry say something inside is
    invalid; the row zooms to the posts' level and selects the first."""
    page.route(
        lambda url: urlparse(url).path == "/sites/garage", _with_posts_overlapping("printer_1")
    )
    _open(page, base_url)
    printer = _row(page, "printer_1")
    expect(printer).to_have_class(re.compile(r"\binvalid-inside\b"))
    expect(printer).to_have_attribute("title", re.compile("something inside is invalid"))
    expect(printer.locator(".problem-mark")).to_be_visible()
    expect(_row(page, "printer_2")).not_to_have_class(re.compile(r"\binvalid"))
    expect(page.locator("#validity-indicator")).to_have_text("1 violation")

    page.locator("#problem-list li", has_text="left_post and right_post overlap").click()
    assert page.evaluate("() => window.fractalViewer.focusPath") == ["printer_1", "gantry_system"]
    selected = "printer_1.gantry_system.left_post"
    assert page.evaluate("() => window.fractalViewer.selectedName") == selected
    for path in (selected, "printer_1.gantry_system.right_post"):
        expect(_row(page, path)).to_have_class(re.compile(r"\binvalid\b"))
    expect(_row(page, "printer_1.gantry_system.gantry_bar")).not_to_have_class(
        re.compile(r"\binvalid")
    )
    page.evaluate("() => window.fractalViewer.zoomOut()")
    expect(_row(page, "printer_1.gantry_system")).to_have_class(re.compile(r"\binvalid-inside\b"))


@pytest.mark.e2e
def test_a_problem_selects_the_right_one_of_two_pieces_of_the_same_name(page, base_url: str):
    """Every printer's gantry has a left and a right post. A problem with printer_2's
    posts marks printer_2's and its row selects printer_2's left post -- by the path
    the problem carries, not the first piece of that name, which is printer_1's."""
    page.route(
        lambda url: urlparse(url).path == "/sites/garage", _with_posts_overlapping("printer_2")
    )
    _open(page, base_url)
    expect(_row(page, "printer_2")).to_have_class(re.compile(r"\binvalid-inside\b"))
    expect(_row(page, "printer_1")).not_to_have_class(re.compile(r"\binvalid"))
    expect(page.locator("#problem-list li")).to_have_attribute(
        "data-path", "printer_2.gantry_system.left_post"
    )

    page.locator("#problem-list li", has_text="left_post and right_post overlap").click()
    assert page.evaluate("() => window.fractalViewer.focusPath") == ["printer_2", "gantry_system"]
    selected = "printer_2.gantry_system.left_post"
    assert page.evaluate("() => window.fractalViewer.selectedName") == selected
    expect(_row(page, selected)).to_have_class(re.compile(r"\bselected\b"))
    for path in (selected, "printer_2.gantry_system.right_post"):
        expect(_row(page, path)).to_have_class(re.compile(r"\binvalid\b"))
    # printer_1's posts, of the same names, are not in it.
    page.evaluate(
        "() => { const v = window.fractalViewer; v.jumpTo(0); v.zoomIn('printer_1'); v.zoomIn('gantry_system'); }"
    )
    expect(_row(page, "printer_1.gantry_system.left_post")).to_be_visible(timeout=5000)
    for path in ("printer_1.gantry_system.left_post", "printer_1.gantry_system.right_post"):
        expect(_row(page, path)).not_to_have_class(re.compile(r"\binvalid"))


@pytest.mark.e2e
def test_the_toolbar_count_opens_sites_problems(page, base_url: str):
    """Site closed, or the rail hidden: the toolbar's count opens Site, shows the rail and
    brings the problems into view at its top."""
    _open(page, base_url)
    _row(page, "printer_1").click()
    x = page.locator("#pos-x")
    x.fill("650")
    x.press("Tab")
    expect(page.locator("#validity-indicator")).to_contain_text("violation", timeout=5000)
    page.evaluate("() => { window.apothecaryPanels.close('site'); }")
    expect(page.locator(".panel[data-panel='site']")).to_have_count(0)
    page.locator("#validity-indicator").click()
    problems = page.locator("#site-problems")
    expect(problems).to_be_visible(timeout=2000)
    expect(problems).to_be_in_viewport()
    assert page.evaluate("() => window.apothecaryPanels.state('site').open") is True

    page.evaluate(
        "() => { window.apothecaryPanels.collapse('site'); window.apothecaryPanels.hideRail(); }"
    )
    expect(problems).to_be_hidden()
    page.locator("#validity-indicator").click()
    expect(problems).to_be_visible(timeout=2000)
    assert page.evaluate("() => window.apothecaryPanels.railHidden()") is False
    x = page.locator("#pos-x")
    x.fill("100")
    x.press("Tab")
    expect(page.locator("#validity-indicator")).to_have_text("Layout valid", timeout=5000)


@pytest.mark.e2e
def test_sites_scad_section_shows_the_sites_scad(page, base_url: str):
    """The site's generated OpenSCAD is a section of Site, folded until opened."""
    _open(page, base_url)
    code = page.locator(".panel[data-panel='site'] #code-content")
    expect(code).to_be_hidden()
    page.locator("#site-scad summary").click()
    expect(code).to_be_visible()
    expect(code).to_contain_text("// Structure: workbench")
    expect(code).not_to_contain_text("Load a site to see")


@pytest.mark.e2e
def test_pinned_takes_back_another_sites_pins_without_switching(
    page, base_url: str, leaves_as_found
):
    """Site's Pinned lists every site's pins, each naming its site; another site's
    camera and view are taken back from their rows on this site's page."""
    api = page.request
    placed = api.put(
        f"{base_url}/cameras/{CAMERA}",
        data={"label": "pinned test camera", "site": "garage", "path": "workbench"},
    )
    assert placed.ok, placed.text()
    pinned = _keep(page, base_url, "pinned_view.png", 0, "&site=garage&host=workbench")
    view = pinned["view"]
    assert view, pinned

    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    _open(page, base_url, "parts_library")
    url = page.url
    status = page.locator("#status")

    section = page.locator(".panel[data-panel='site'] #site-pinned")
    expect(section.locator(".pin-row")).to_have_count(0)  # folded: not fetched yet
    section.locator("summary").click()

    # Each row names its site; garage's are not this page's.
    camera = section.locator(".pin-row.camera", has_text="pinned test camera")
    expect(camera).to_contain_text("garage › workbench", timeout=5000)
    expect(camera).not_to_have_class(re.compile(r"\bhere\b"))
    row = section.locator(f".pin-row.view:has(.pinned-view-unpin[data-id='{view['id']}'])")
    expect(row).to_contain_text("garage › workbench")

    # The camera, unpinned from its row.
    camera.locator(".pinned-camera-unpin").click()
    expect(camera).to_have_count(0, timeout=5000)
    assert CAMERA not in {c["id"] for c in api.get(f"{base_url}/cameras").json()}
    expect(status).to_contain_text("camera unpinned from garage › workbench")

    # The view, unpinned from its row; its picture stays kept.
    row.locator(".pinned-view-unpin").click()
    expect(row).to_have_count(0, timeout=5000)
    views = api.get(f"{base_url}/sites/garage/attached").json()["views"]
    assert view["id"] not in {vw["id"] for vw in views}
    assert pinned["path"] in {p["path"] for p in api.get(f"{base_url}/photos/pictures").json()}

    # A pin made elsewhere shows when the section is opened again.
    again = _keep(page, base_url, "pinned_again.png", 30, "&site=garage&host=workbench")
    section.locator("summary").click()
    section.locator("summary").click()
    expect(section.locator(f".pinned-view-unpin[data-id='{again['view']['id']}']")).to_be_visible(
        timeout=5000
    )

    # Nothing switched the site.
    assert page.url == url
    assert page.evaluate("() => window.fractalViewer.siteName") == "parts_library"
    expect(page.locator("#site-select")).to_have_value("parts_library")
    expect(status).not_to_have_class(re.compile(r"\berror\b"))
    assert errors == []
