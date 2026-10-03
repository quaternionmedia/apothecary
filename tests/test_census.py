"""The census: one ceiling on the viewer's count, how a page is read, and the
two modules the page imports that the census cannot see into."""

import re

import pytest
from click.testing import CliRunner

from apothecary import census
from apothecary.cli.census import census as command

STATIC = census.TEMPLATES.parent / "apothecary" / "static"

# The viewer's controls of its own today. A change that adds one raises this
# on purpose; a change that removes one may lower it.
#
# Pictures plan Phase 3, first commit: the census also counts the marks modules
# the page imports (census.MARKS). Before: 137 controls of its own, 65
# ring-backed, 70 places the page listens. After: the same -- machine_marks.js
# writes no markup and listens nowhere, so the new count it adds is nothing.
#
# Phase 3, the looks drawn: the camera badge's listener leaves the page for
# picture_marks.js as the place badge's (badge:click:onSelect); no ring address
# moved. Before and after: 137 controls of its own, 65 ring-backed, 70 places.
#
# Phase 4, the loop's verbs on the host. Before: 137 controls of its own, 65
# ring-backed (47.4%), 70 places the page listens. After: 128, 61 ring-backed
# (47.7%), 77 places. Gone with the camera panel's camera, capture, Look and
# placement sections and Open as one: cam-pick, cam-allow, cam-refresh,
# cam-name, cam-width, cam-capture, cam-look, cam-place, cam-unplace, pic-open,
# and pic-refresh (the list is fetched when the panel mounts and after each
# change). Added: Selected's width box (look-width) and a look's Unpin in the
# pins list (look-unpin-one, ring-backed by Picture › Unpin); cam-unplace-one
# and pic-forget are now backed by Camera › Unpin and Picture › Forget; pic-file
# keeps a picture without pinning it, which no cell does, so it is no longer
# backed. Ring addresses moved: Camera › Allow is Camera › Pin here › Allow on a
# host's node ring (the floor's under Pictures › Floor); Unplace is Camera ›
# Unpin there; Open as one is gone; the canvas ring's Camera is Pictures in the
# same seat (Add, Floor, Purge, Gather), its Kept › Add and Purge now Pictures ›
# Add (pinned at the floor) and Pictures › Purge.
#
# The Kept stub (the pictures plan's Phase 5, stubbed at the owner's word "stub
# kept now"). Before: 128 controls of its own, 61 ring-backed (47.7%), 77 places
# the page listens. After: 128, 58 ring-backed (45.3%), 75 places. The per-row
# buttons of the old "Pictures & pins" panel -- forget a picture, unpin a
# camera, unpin a look (pic-forget, cam-unplace-one, look-unpin-one) -- move to
# Kept (kept-forget, kept-camera-unpin, kept-look-unpin) and are reclassified:
# not ring-backed but census.TAKEN_BACK, the lasting exception for taking a
# thing back from the list that shows it. They were counted as backed by Camera
# › Unpin, Picture › Unpin and Picture › Forget, though a row can name another
# site's pin, which those cells reach only from that site; §6 asks for every
# site's to be taken back from the one list. The boards' Unpin and the list's
# refresh move with them (pin-unpin, pin-refresh become kept-board-unpin,
# kept-refresh), and Purge (pic-purge, kept-purge) stays backed by Pictures ›
# Purge. The three row listeners are one on Kept's list. No ring address moved
# but the panels': Panels › Camera is Panels › Pictures › Gather, beside Kept.
#
# The first-time camera flow: no control added or removed, and no ring address
# moved. One place the page listens is added, in pictures.js: the browser's
# camera permission changing (status:change:listCameras), automatic, since it
# is the browser reporting a yes given in the address bar and not a control.
# `apothecary census` before and after: the same meter and the same ring-backed
# count; one more place the page listens.
# The picture-to-editor seam: the part panel became one editor over a target,
# serving a made piece too, and Part › Edit joined the node ring. Before and
# after: 128 controls of its own, 58 ring-backed, 75 places the page listens.
# The editor's markup is written once for either target (a made piece leaves
# its checklist and Regenerate STL unwritten), so no control was added; the
# Regenerate STL listener is keyed by the editor's apply (applyEditor) now.
#
# Consolidation Phase 1, the words: a picture pinned at a place is a view. The
# census's keys follow the page: kept-look-unpin is kept-view-unpin, look-width
# is view-width, and Selected's row listener is row:click:drawView, still backed
# by Picture › Views' picture:draw. Camera › Look is Camera › Take picture in the
# same cell, Picture › Looks is Picture › Views in the same cell; no ring address
# moved. Before and after: 128 controls of its own, 58 ring-backed, 76 places
# the page listens.
VIEWER_CEILING = 128


def test_the_viewer_stays_under_its_ceiling():
    own = census.take().controls_of_its_own()
    assert len(own) <= VIEWER_CEILING, (
        f"{len(own)} controls of the viewer's own, over the ceiling of "
        f"{VIEWER_CEILING}. Raise VIEWER_CEILING in the change that adds a "
        "control, or unify one away. `uv run apothecary census` lists them."
    )


# --------------------------------------------------------------------------
# What is not in the tables is counted, not refused
# --------------------------------------------------------------------------


def test_a_control_nobody_has_classified_is_counted_and_named(tmp_path):
    page = tmp_path / "page.html"
    page.write_text('\n\n\n<button id="mystery-btn">go</button>\n', encoding="utf-8")
    taken = census.take(page)
    assert [(f.name, f.line) for f in taken.unclassified()] == [("mystery-btn", 4)]
    assert len(taken.controls_of_its_own()) == 1
    assert "unclassified: 1" in census.report(page)


def test_a_new_listener_cannot_hide_inside_an_old_one(tmp_path):
    """A listener is keyed by the first thing its handler does."""
    page = tmp_path / "page.html"
    page.write_text(
        "li.addEventListener('click', () => this.selectChild(path));\n"
        "li.addEventListener('click', () => this.deleteNode(path));\n",
        encoding="utf-8",
    )
    taken = census.take(page)
    assert [f.key for f in taken.unclassified()] == ["li:click:deleteNode"]
    assert taken.controls_of_its_own() == ()


def test_a_page_it_could_not_read_is_refused_not_answered_zero(tmp_path):
    page = tmp_path / "page.html"
    page.write_text("nothing here at all\n", encoding="utf-8")
    with pytest.raises(census.NothingFound):
        census.take(page)


def test_every_classification_uses_a_kind_that_exists():
    for table in (census.CONTROLS, census.LISTENING):
        for key, (surface, effect, description) in table.items():
            assert surface in census.SURFACES, f"{key} is filed under {surface!r}"
            assert effect in census.EFFECTS, f"{key} changes {effect!r}, which is not a thing"
            assert description.strip(), f"{key} has no description"


# --------------------------------------------------------------------------
# Reading the page
# --------------------------------------------------------------------------


def _keys(tmp_path, text: str) -> list:
    page = tmp_path / "page.html"
    page.write_text(text, encoding="utf-8")
    return [f.key for f in census.take(page).found]


def test_either_style_of_quotation_mark_is_read(tmp_path):
    text = 'this.canvas.addEventListener("wheel", (e) => this.onWheel(e));\n'
    assert _keys(tmp_path, text) == ["canvas:wheel:onWheel"]


def test_the_thing_listened_on_is_read_backwards_and_not_across(tmp_path):
    """A label in the statement above does not claim the listener."""
    text = (
        "const b = el.querySelector('.zoom-in-btn');\n"
        "this.canvas.addEventListener('wheel', (e) => this.onWheel(e));\n"
    )
    assert _keys(tmp_path, text) == ["canvas:wheel:onWheel"]


def test_a_gap_filled_in_as_the_page_is_written_is_not_a_statement_boundary(tmp_path):
    text = (
        "document.getElementById(`pos-${axis}`).addEventListener('change', (e) => {\n"
        "    this.recomputeWorldBounds(node);\n"
        "});\n"
    )
    assert _keys(tmp_path, text) == ["posAxis:change:recomputeWorldBounds"]


def test_a_short_handler_does_not_borrow_the_next_line_s_work(tmp_path):
    text = (
        "this.transformControls.addEventListener('dragging-changed', (event) => {\n"
        "    this.controls.enabled = !event.value;\n"
        "});\n"
        "this.transformControls.addEventListener('objectChange', () => this.onGizmoDrag());\n"
    )
    assert _keys(tmp_path, text) == [
        "transformControls:dragging-changed:(nothing)",
        "transformControls:objectChange:onGizmoDrag",
    ]


def test_plumbing_is_not_mistaken_for_the_point(tmp_path):
    text = (
        "this.jobFormEl.addEventListener('submit', (e) => {\n"
        "    e.preventDefault();\n"
        "    this.createJob();\n"
        "});\n"
    )
    assert _keys(tmp_path, text) == ["jobFormEl:submit:createJob"]


def test_two_forms_send_buttons_are_two(tmp_path):
    """A submit button has no name of its own, so it is named by its form."""
    text = (
        '<form id="job-form"><button type="submit">go</button></form>\n'
        '<form id="qform"><button type="submit">send</button></form>\n'
    )
    assert _keys(tmp_path, text) == ["job-form", "job-form:submit", "qform", "qform:submit"]


def test_a_button_that_carries_its_line_is_named_by_the_line(tmp_path):
    """Two buttons of one class that send two different lines are two."""
    page = tmp_path / "page.html"
    page.write_text(
        '<button class="warm" data-cmd="M104 S{h-hot}">Set</button>\n'
        '<button class="warm" data-cmd="M140 S{h-bed}">Set</button>\n'
        '<button data-jog="Y+">up</button><button data-step="10">10</button>\n',
        encoding="utf-8",
    )
    taken = census.take(page)
    assert [(f.name, f.ring_action) for f in taken.found] == [
        ("cmd:M104 S{h-hot}", "control:hotend-on"),
        ("cmd:M140 S{h-bed}", "control:bed-on"),
        ("jog:Y+", "control:jog:Y+"),
        ("step:10", None),
    ]


def test_a_link_with_a_class_is_the_thing_its_class_says(tmp_path):
    text = (
        '<a class="dev-monitor" href="/firmware/monitor?port=x">m</a>\n'
        '<a href="/parts/x/scad">d</a>\n'
        '<a href="/viewer">v</a>\n'
    )
    assert _keys(tmp_path, text) == ["dev-monitor", "part-scad-download", "viewer-link"]


def test_a_control_fetched_by_the_one_letter_helper_is_named(tmp_path):
    text = '$("port").addEventListener("change", () => selectPort($("port").value));\n'
    assert _keys(tmp_path, text) == ["port:change:selectPort"]


def test_a_bare_handler_is_the_thing_it_does(tmp_path):
    text = '$("auto").addEventListener("change", schedule);\n'
    assert _keys(tmp_path, text) == ["auto:change:schedule"]


def test_pin_and_pin_by_typing_are_two_listeners(tmp_path):
    """`.dev-pin-manual` begins with `.dev-pin`, and must not be read as it."""
    text = (
        "el.querySelector('.dev-pin')?.addEventListener('click', () => this.setNodeDevice(p));\n"
        "el.querySelector('.dev-pin-manual')?.addEventListener('click', pinManual);\n"
    )
    assert _keys(tmp_path, text) == ["devPin:click:setNodeDevice", "devPinManual:click:pinManual"]


def test_the_report_says_how_many_are_on_the_ring(tmp_path):
    page = tmp_path / "page.html"
    page.write_text(
        '<button class="dev-watch">w</button><button id="serial-clear">c</button>\n',
        encoding="utf-8",
    )
    written = census.report(page)
    assert written.startswith("2 controls of its own, 1 of them also on the ring.")
    assert "⌗ device:watch" in written


# --------------------------------------------------------------------------
# The command
# --------------------------------------------------------------------------


def test_the_command_prints_the_count():
    result = CliRunner().invoke(command, [])
    assert result.exit_code == 0, result.output
    assert "controls of its own" in result.output
    assert "unclassified: " in result.output


def test_the_command_lists_what_is_unclassified_and_still_answers(tmp_path):
    page = tmp_path / "page.html"
    page.write_text('<button id="mystery-btn">go</button>\n', encoding="utf-8")
    result = CliRunner().invoke(command, ["--page", str(page)])
    assert result.exit_code == 0, result.output
    assert "unclassified: 1" in result.output
    assert "mystery-btn" in result.output


def test_the_command_refuses_a_page_it_could_not_read(tmp_path):
    page = tmp_path / "page.html"
    page.write_text("nothing here\n", encoding="utf-8")
    result = CliRunner().invoke(command, ["--page", str(page)])
    assert result.exit_code == 1
    assert "no number is given" in result.output


# --------------------------------------------------------------------------
# The modules the census counts once, behind the page
# --------------------------------------------------------------------------


def _on_the_page(text: str) -> list:
    found = re.findall(r"(window|document)\.addEventListener\(\s*[\"'](\w+)[\"']", text)
    return sorted(set(found))


def test_the_ring_module_opens_three_ways_and_the_pages_import_it():
    """ring.js installs the `m` key on the window, right-click on the document
    and a click on `#ring-open`, and nothing else on either; everything else it
    listens to is on the ring's own element while the ring is open."""
    text = (STATIC / "ring.js").read_text(encoding="utf-8")
    assert _on_the_page(text) == [("document", "contextmenu"), ("window", "keydown")]
    assert 'button = "#ring-open"' in text
    for page in census.PAGES:
        imports_it = "/static/ring.js" in page.read_text(encoding="utf-8")
        assert imports_it == (page is not census.FIRMWARE)


def test_the_panel_module_keeps_its_chrome_to_itself():
    """panels.js listens on the elements it makes, and on the window only for
    the tilde key and the pointer moves that finish a drag, each taken off
    again; the viewer loads it and the monitor does not."""
    text = (STATIC / "panels.js").read_text(encoding="utf-8")
    assert _on_the_page(text) == [
        ("window", "keydown"),
        ("window", "pointermove"),
        ("window", "pointerup"),
    ]
    for event in ("keydown", "pointermove", "pointerup"):
        assert f'window.removeEventListener("{event}"' in text
    assert "/static/panels.js" in census.VIEWER.read_text(encoding="utf-8")
    assert "/static/panels.js" not in census.MONITOR.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# The marks modules: counted with the page that imports them
# --------------------------------------------------------------------------


def test_the_viewer_counts_its_marks_modules_and_the_monitor_does_not():
    """The viewer imports machine_marks.js itself; the monitor reaches it only
    through board_view.js, so its count does not change."""
    assert (census.STATIC / "machine_marks.js") in census.marks_of(census.VIEWER)
    assert census.marks_of(census.MONITOR) == []
    assert census.marks_of(census.FIRMWARE) == []
    for chrome in ("ring.js", "panels.js", "anchors.js"):
        assert chrome not in census.MARKS


def test_a_listener_in_a_marks_module_is_counted_and_named_when_unclassified(tmp_path, monkeypatch):
    monkeypatch.setattr(census, "STATIC", tmp_path)
    (tmp_path / "machine_marks.js").write_text(
        "\nbadge.addEventListener('click', () => mystery(path));\n", encoding="utf-8"
    )
    page = tmp_path / "page.html"
    page.write_text(
        "import { makeMachineMarks } from '/static/machine_marks.js';\n"
        "import { mountAnchors } from '/static/anchors.js';\n",
        encoding="utf-8",
    )
    taken = census.take(page)
    assert [(f.key, f.source, f.line) for f in taken.unclassified()] == [
        ("badge:click:mystery", "machine_marks.js", 2)
    ]


def test_every_listener_in_the_viewers_marks_modules_is_classified():
    taken = census.take()
    marks = {m.name for m in census.marks_of(census.VIEWER)}
    assert [f.key for f in taken.unclassified() if f.source in marks] == []


# --------------------------------------------------------------------------
# Kept's rows: taken back from the list that shows them, not ring-backed
# --------------------------------------------------------------------------


def test_kepts_take_back_buttons_are_counted_and_not_claimed_as_ring_backed():
    """Forget a picture, unpin a camera, unpin a view: Kept's per-row buttons are
    the lasting exception for taking a thing back from the list that shows it,
    counted on the meter and never ring-backed, since a row can name another
    site's pin that a ring cell reaches only from that site."""
    taken = census.take()
    by_name = {f.name: f for f in taken.controls_of_its_own()}
    for name in ("kept-forget", "kept-camera-unpin", "kept-view-unpin", "kept-board-unpin"):
        assert by_name[name].source == "kept.js"
        assert by_name[name].ring_action is None, name
        assert by_name[name].taken_back, name
    assert {f.name for f in taken.taken_back()} == {
        "kept-forget",
        "kept-camera-unpin",
        "kept-view-unpin",
        "kept-board-unpin",
    }
    # Purge stays a cell of the canvas ring's Pictures.
    assert by_name["kept-purge"].ring_action == "picture:purge"
    # The old panel's rows are gone from the page, and from the tables.
    for gone in ("pic-forget", "cam-unplace-one", "look-unpin-one", "pic-purge", "pin-unpin"):
        assert gone not in by_name
        assert gone not in census.CONTROLS and gone not in census.RING_BACKED
    listening = {f.key: f for f in taken.found if f.how == "listening" and f.source == "kept.js"}
    assert list(listening) == ["kept-list:click:closest"]
    assert listening["kept-list:click:closest"].taken_back
    assert "⤺ takes back a view, every site's" in census.report()


def test_nothing_is_both_taken_back_and_ring_backed():
    assert set(census.TAKEN_BACK) & set(census.RING_BACKED) == set()
    for key in census.TAKEN_BACK:
        assert key in census.CONTROLS or key in census.LISTENING, key
