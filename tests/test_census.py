"""The census: one ceiling on the viewer's count, how a page is read, and the
two modules the page imports that the census cannot see into."""

import re

import pytest
from click.testing import CliRunner

from apothecary import census
from apothecary.cli.census import census as command

STATIC = census.TEMPLATES.parent / "apothecary" / "static"

# The viewer's controls of its own: a change that adds one raises this; one that removes
# one may lower it. `uv run apothecary census` lists them, and docs/census.md says what
# is counted, how each is classified and how the ceiling and the share's floor move.
VIEWER_CEILING = 161


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
    text = '<a class="dev-via" href="/parts/x/scad">m</a>\n<a href="/parts/x/scad">d</a>\n'
    assert _keys(tmp_path, text) == ["dev-via", "part-scad-download"]


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
        '<button class="dev-open">o</button><button id="mystery-btn">m</button>\n',
        encoding="utf-8",
    )
    written = census.report(page)
    assert written.startswith("2 controls of its own, 1 of them also on the ring.")
    assert "⌗ device:open" in written


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
    """ring.js installs its keys (`m` and Shift+M unless Settings gives others) on the
    window; on the document, the press and release of a right-click held with its
    modifier, a touch held still, and the browser's menu kept away where the ring is
    asked for; and a click on `#ring-open`, and nothing else on either. Everything else
    it listens to is on the ring's own element while the ring is open. keys.js, which
    names a key and says when a shortcut may act, listens to nothing."""
    text = (STATIC / "ring.js").read_text(encoding="utf-8")
    assert _on_the_page(text) == [
        ("document", "contextmenu"),
        ("document", "pointercancel"),
        ("document", "pointerdown"),
        ("document", "pointermove"),
        ("document", "pointerup"),
        ("window", "keydown"),
    ]
    assert "addEventListener" not in (STATIC / "keys.js").read_text(encoding="utf-8")
    assert 'button = "#ring-open"' in text
    assert census.PAGES == (census.VIEWER,)
    assert "/static/ring.js" in census.VIEWER.read_text(encoding="utf-8")


def test_the_panel_module_keeps_its_chrome_to_itself():
    """panels.js listens on the elements it makes, and on the window only for
    the tilde key and the pointer moves that finish a drag, each taken off
    again; the viewer loads it."""
    text = (STATIC / "panels.js").read_text(encoding="utf-8")
    assert _on_the_page(text) == [
        ("window", "keydown"),
        ("window", "pointermove"),
        ("window", "pointerup"),
    ]
    for event in ("keydown", "pointermove", "pointerup"):
        assert f'window.removeEventListener("{event}"' in text
    assert "/static/panels.js" in census.VIEWER.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# The marks modules: counted with the page that imports them
# --------------------------------------------------------------------------


def test_the_viewer_counts_its_marks_modules():
    """The viewer imports machine_marks.js and boards.js itself, so both are counted
    with it."""
    assert (census.STATIC / "machine_marks.js") in census.marks_of(census.VIEWER)
    assert (census.STATIC / "boards.js") in census.marks_of(census.VIEWER)
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
# The rows' take-backs: taken back from the list that shows them, not ring-backed
# --------------------------------------------------------------------------


def test_the_rows_take_backs_are_counted_and_not_claimed_as_ring_backed():
    """Remove a camera, unpin a view or a board's pin from Site's Pinned, forget a
    kept picture from Pictures: the lasting exception for taking a thing back from
    the list that shows it, counted on the meter and never ring-backed, since a row
    can name another site's camera or pin that a ring cell reaches only from that
    site."""
    taken = census.take()
    by_name = {f.name: f for f in taken.controls_of_its_own()}
    for name in ("pinned-camera-remove", "pinned-view-unpin", "pinned-board-unpin"):
        assert by_name[name].source == "pinned.js"
        assert by_name[name].ring_action is None, name
        assert by_name[name].taken_back, name
    assert by_name["pictures-forget"].source == "picture_list.js"
    assert {f.name for f in taken.taken_back()} == {
        "pictures-forget",
        "pinned-camera-remove",
        "pinned-view-unpin",
        "pinned-board-unpin",
    }
    # Purge stays a cell of the canvas ring's Pictures, and so does Gather.
    assert by_name["pictures-purge"].ring_action == "picture:purge"
    assert by_name["pic-gather"].ring_action == "camera:gather"
    # Kept, the Gather panel and the older panel's rows are not on the page, nor in
    # the tables.
    for gone in (
        "kept-refresh",
        "kept-purge",
        "kept-forget",
        "kept-camera-unpin",
        "kept-view-unpin",
        "kept-board-unpin",
        "pic-forget",
        "cam-unplace-one",
        "look-unpin-one",
        "pic-purge",
        "pin-unpin",
        "pinned-camera-unpin",
    ):
        assert gone not in by_name
        assert gone not in census.CONTROLS and gone not in census.RING_BACKED
        assert gone not in census.TAKEN_BACK
    assert "kept-list:click:closest" not in census.LISTENING
    listening = {f.key: f for f in taken.found if f.how == "listening" and f.source == "pinned.js"}
    assert list(listening) == ["pinned-list:click:closest"]
    assert listening["pinned-list:click:closest"].taken_back
    assert "⤺ takes back a view, every site's" in census.report()


def test_pictures_chooses_a_row_and_has_no_pin_here():
    """A picture's row is chosen for the ring's Picture › Folder to pin, the older
    pictures included, so Pictures has no Pin here: its rows are a list a person
    chooses from, as Site's tree is, and Escape is a key."""
    taken = census.take()
    assert "pictures-pin" not in {f.name for f in taken.controls_of_its_own()}
    for gone in ("pictures-pin", "pin:click:pinHere"):
        assert gone not in census.CONTROLS and gone not in census.LISTENING
        assert gone not in census.RING_BACKED and gone not in census.TAKEN_BACK
    listening = {f.key: f for f in taken.found if f.how == "listening"}
    row = listening["row:click:rowClicked"]
    assert (row.source, row.surface) == ("picture_list.js", census.LIST)
    assert listening["window:keydown:letGo"].surface == census.GESTURE
    assert listening["forgetBtn:click:forget"].taken_back
    # A view's place on a picture's row draws it, as Selected's view rows do.
    assert (
        listening["chip:click:showView"].ring_action == listening["row:click:drawView"].ring_action
    )


def test_the_viewers_ring_backed_share_did_not_fall():
    """The ring-backed share of the viewer's controls does not fall below its floor.
    A change that adds a ring-backed control raises the floor with it (docs/census.md);
    `apothecary census` gives the share."""
    taken = census.take()
    own, backed = len(taken.controls_of_its_own()), len(taken.ring_backed())
    assert backed / own >= 87 / 161, f"{backed} of {own} ring-backed"


def test_the_headers_docs_is_panels_docs_and_back_and_forward_follow_the_address():
    """The header's Docs is a control of its own, ring-backed by Panels › Docs; Back
    and Forward are the browser's, the page listening for them as for a resize."""
    taken = census.take()
    by_name = {f.name: f for f in taken.controls_of_its_own()}
    assert by_name["docs-link"].ring_action == "panel:docs"
    listening = {f.key: f for f in taken.found if f.how == "listening"}
    assert listening["window:popstate:followAddress"].surface == census.AUTOMATIC
    assert listening["siteSelect:change:chooseSite"].surface == census.WIDGET
    assert "siteSelect:change:loadSite" not in census.LISTENING


def test_the_serial_overlay_left_nothing_behind():
    """No control or listener of the serial overlay, the toolbar's look-for-boards
    tick-box or Selected's Watch, Poll now and Monitor is counted or classified; a
    board's Machine is opened by Open, which the ring backs, and the boards' model is
    counted with the viewer, every listener of it classified."""
    taken = census.take()
    gone = (
        "serial-",
        "devices-auto",
        "devices-interval",
        "firmware-page-link",
        "dev-watch",
        "dev-poll",
        "toggle:change:show",
        "portSel:change:renderMeta",
        "baudSel:",
        "queryRow:",
        "autoEl:",
        "intervalEl:",
        "devWatch:",
        "devPoll:",
        "es:open:add",
        "es:close:line",
        "window:beforeunload:disconnect",
        "document:visibilitychange:scheduleAutoRefresh",
    )
    assert not [f.key for f in taken.found if f.key.startswith(gone)]
    for table in (census.CONTROLS, census.LISTENING, census.RING_BACKED):
        assert not [k for k in table if k.startswith(gone)], table
    by_name = {f.name: f for f in taken.controls_of_its_own()}
    assert by_name["dev-open"].ring_action == "device:open"
    listening = {f.key: f for f in taken.found if f.how == "listening"}
    assert listening["devOpen:click:openMachine"].ring_action == "device:open"
    from_model = [f for f in taken.found if f.source == "boards.js"]
    assert from_model and all(f.surface == census.AUTOMATIC for f in from_model), from_model
    assert "device:watch" not in census.RING_BACKED.values()
    assert "device:monitor" not in census.RING_BACKED.values()


def test_the_jobs_panel_left_nothing_behind():
    """No control or listener of the hand-typed Jobs panel is counted or classified."""
    taken = census.take()
    assert not [f.key for f in taken.found if f.key.startswith(("job-", "jobFormEl", "jobBtn"))]
    assert not [k for k in census.CONTROLS if k.startswith("job-")]
    assert not [k for k in census.LISTENING if k.startswith(("jobFormEl", "jobBtn"))]


def test_nothing_is_both_taken_back_and_ring_backed():
    assert set(census.TAKEN_BACK) & set(census.RING_BACKED) == set()
    for key in census.TAKEN_BACK:
        assert key in census.CONTROLS or key in census.LISTENING, key


def test_one_page_is_counted_and_the_retired_pages_left_nothing_behind():
    """The census counts one page, the viewer: /firmware and /firmware/monitor open the
    Bench and a board's Machine in it, no template stands for either, and no toolbar
    link to them, monitor port picker or firmware device card or row is counted or
    classified."""
    assert census.PAGES == (census.VIEWER,)
    for gone in ("firmware.html.j2", "monitor.html.j2"):
        assert not (census.TEMPLATES / gone).exists(), gone
    assert not (census.STATIC / "board_view.js").exists()
    retired = (
        "firmware-link",
        "monitor-link",
        "viewer-link",
        "dev-monitor",
        "port",
        "refresh-btn",
        "boards-btn",
        "esp-off",
        "esp-path",
        "esp-rm",
        "esp-add",
        "dev-probe",
        "dev-identify",
        "dev-printer",
        "dev-live",
        "port:change:selectPort",
        "portSel:change:mountFor",
        "es:close:stopLive",
        "devices:click:closest",
        "cores:click:closest",
        "sketches:click:closest",
        "fqbn-input:input:updateButtons",
        "port-select:change:updateButtons",
        "esp-images:click:contains",
        "history:click:closest",
    )
    taken = census.take()
    assert not [f.key for f in taken.found if f.key in retired]
    for table in (census.CONTROLS, census.LISTENING, census.RING_BACKED):
        assert not [k for k in table if k in retired], table
    # The Bench's modules are counted with the viewer, which imports them.
    sources = {f.source for f in taken.found}
    assert {"toolchain.js", "sketches.js", "tasks.js", "machine.js"} <= sources
    by_name = {f.name: f for f in taken.controls_of_its_own()}
    assert by_name["compile-btn"].ring_action == "bench:compile"
    assert by_name["listen"].ring_action == "device:listen"


def test_the_header_is_one_row_with_its_view_menu_on_the_ring():
    """The header has no Load or Zoom Out, and neither is counted; Snap to grid,
    Detail, Assembly outlines and Walls selectable are in the View menu, each backed
    by a cell of the canvas ring's View that the ring really produces."""
    from apothecary.menu import Context, Pointing, resolve

    taken = census.take()
    for gone in ("load-btn", "zoom-out-btn", "loadBtn:click:loadSite", "zoomOutBtn:click:zoomOut"):
        assert gone not in {f.key for f in taken.found}
        for table in (census.CONTROLS, census.LISTENING, census.RING_BACKED):
            assert gone not in table
    by_name = {f.name: f for f in taken.controls_of_its_own()}
    ring = resolve(Context(pointing=Pointing.CANVAS), site_names=["garage"], groups=["wall"])
    produced = set()

    def walk(options):
        for option in options:
            if option.action:
                produced.add(option.action)
            walk(option.children or [])

    walk(ring.options)
    for name, action in (
        ("snap-toggle", "view:snap"),
        ("detail-mode", "view:detail:full"),
        ("overlay-toggle", "view:outlines"),
        ("walls-toggle", "view:walls"),
    ):
        assert by_name[name].ring_action == action and action in produced, name
    assert "view-menu" in census.VIEWER.read_text(encoding="utf-8")


def test_settings_rows_are_counted_and_unbacked_and_its_view_item_is_view_settings():
    """The Settings panel's rows are controls of their own, counted from the module
    that writes them and never ring-backed (the panel has a cell, and no row has one);
    ⚙ View › Settings is backed by the canvas ring's View › Settings, which the ring
    really produces. The right button's press and release and the zoom
    keys are things done to the scene."""
    from apothecary.menu import Context, Pointing, resolve

    taken = census.take()
    by_name = {f.name: f for f in taken.controls_of_its_own()}
    rows = (
        "setting-key",
        "setting-choice",
        "setting-tick",
        "setting-number",
        "setting-reset",
        "settings-reset-all",
    )
    for name in rows:
        assert by_name[name].source == "settings.js", name
        assert by_name[name].ring_action is None and by_name[name].taken_back is None, name
    assert by_name["settings-open"].ring_action == "view:settings"
    ring = resolve(Context(pointing=Pointing.CANVAS), site_names=["garage"], groups=["wall"])
    view = next(o for o in ring.options if o.label == "View")
    assert "view:settings" in [c.action for c in view.children]
    listening = {f.key: f for f in taken.found if f.how == "listening"}
    for key in (
        "canvas:pointerdown:onPress",
        "canvas:pointerup:onRelease",
        "layer:pointerup:onRelease",
        "window:keydown:onZoomKey",
        "window:keydown:onEscapeKey",
    ):
        assert listening[key].surface == census.GESTURE, key
    assert listening["settingsOpenBtn:click:openSettings"].ring_action == "view:settings"
