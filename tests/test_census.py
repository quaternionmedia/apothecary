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
#
# Consolidation Phase 1, taking and finding: Take picture, a drop, a paste,
# Picture › Add and Picture › Folder pin a view and find nothing; Picture › Find
# shapes finds, a cell of its own; Camera › Keep is gone. Keep and Find shapes
# are ring cells with no control behind them, and no listener was added, removed
# or re-keyed (the drop, paste and Add listeners only say what they do now).
# Before and after: 128 controls of its own, 58 ring-backed, 76 places the page
# listens. Ring addresses moved, inside a host's Camera and Picture (and the
# floor's, under Pictures › Floor): with this browser's camera pinned, Keep left
# cell 4 and Unpin moved from cell 9 to cell 4 (Look's cell 2 is Take picture's).
# Find shapes is appended after Unpin and Forget, so their cells stay put
# whether it is there or not; where it replaces Find (another finder can read a
# view already searched), Find moved from before Unpin to the last cell, and
# Unpin and Forget each moved one cell earlier in the seating order (at a host:
# Unpin 3 to 9, Forget 1 to 3; at the floor: Unpin 9 to 4, Forget 3 to 9).
#
# Consolidation Phase 2, the Site and Pictures panels. Before: 128 controls of
# its own, 58 ring-backed (45.3%), 76 places the page listens. After: 128, 58
# ring-backed (45.3%), 82 places. Gone with Kept and the Gather panel: Kept's
# refresh (kept-refresh; Site's Pinned lists again each time it is unfolded) and
# its rows' buttons, which move: the pins' take-backs to Site's Pinned
# (kept-camera-unpin, kept-view-unpin, kept-board-unpin become pinned-*-unpin,
# TAKEN_BACK still, and the row listener kept-list:click:closest is
# pinned-list:click:closest), a kept picture's Forget and Purge to Pictures
# (pictures-forget, TAKEN_BACK; pictures-purge, backed by Pictures › Purge as
# kept-purge was). The gathering (pic-all, pic-gather, gather-answers, answer)
# and the file picker (pic-file) move with the same names to Pictures. Added:
# Pictures' Pin here (pictures-pin), counted and not ring-backed -- the ring's
# Picture › Folder pins the seven newest pictures (and a chosen one, which the
# page does not tell it), and Pin here pins any picture in the folder, the older
# ones included, which no cell reaches. The Validation and OpenSCAD panels had
# no controls. Six places the page listens are added: Pin here
# (pin:click:pinHere), Forget (forgetBtn:click:forget, TAKEN_BACK), a view's
# place on a picture's row (chip:click:showView, backed as Selected's view rows
# are), a problem's row (li:click:goToProblem), Pinned unfolded
# (pinnedEl:toggle:pinnedOpened), and the toolbar's count, a readout listened to
# and not a control in the markup (validityEl:click:openProblems). Ring
# addresses moved, all under the canvas ring's Panels (cell 9): Contents' cell 8
# is Site's (98); Selected 96 and Jobs 92 stay; Validation's cell 4 is Pictures'
# (94); OpenSCAD (99) is gone, and the Machine group moved from 91 to 99 (the
# machine 918 to 998, its comms log 916 to 996); the Pictures group (93: Kept
# 938, Gather 936) is gone, and Rail moved from 97 to 93. Picture › Folder's
# eighth leaf keeps its cell: More opens Pictures (picture:more), not Kept.
#
# Consolidation Phase 2's follow-ups, a picture chosen in Pictures feeds the
# ring. Before: 128 controls of its own, 58 ring-backed (45.3%), 82 places the
# page listens. After: 127, 58 ring-backed (45.7%), 83 places. Pictures' Pin
# here (pictures-pin, and its listener pin:click:pinHere) is gone: a row of
# Pictures is chosen by a click (row:click:rowClicked, a list, not a control)
# and let go by Escape (window:keydown:letGo, a key), the page tells every ring
# the chosen picture, and Picture › Folder pins it -- the seven newest by name,
# an older one as the eighth cell, "Pin" and its short name -- so every picture
# in the folder is pinned from the ring and the button only did the same thing
# again. No ring address moved: Pin <name> takes the eighth cell More holds
# when nothing older is chosen (at the bench ⌗367, at the floor under the
# canvas ring's Pictures › Floor ⌗46287), and a chosen picture among the seven
# is marked in its own cell. The one rail (panels.js) is chrome, off the meter.
#
# Consolidation Phase 3, jobs: a print is the job. Before: 127 controls of its
# own, 58 ring-backed (45.7%), 83 places the page listens. After: 118, 58
# ring-backed (49.2%), 80 places. Gone with the Jobs panel and its hand-typed
# records: its form (job-form, job-name, job-x, job-y, job-z and the form's send
# button), a queued job's drop-down of printers and Assign (job-printer-select,
# job-assign-btn), an assigned one's Mark Done (job-complete-btn), and their three
# listeners (jobFormEl:submit:createJob, jobBtn:click:assignJob,
# jobBtn:click:completeJob); none was ring-backed. Ring addresses moved, all under
# the canvas ring's Panels (cell 9), Jobs (92) being gone: Pictures moved from 94
# to 92, the Machine group from 99 to 94 (the machine 998 to 948, its comms log
# 996 to 946), and Rail from 93 to 99. Site 98 and Selected 96 stay.
#
# Phase 3, the Print card starts a print job. Before: 118 controls of its own, 58
# ring-backed (49.2%), 80 places the page listens. After: 119, 58 ring-backed
# (48.7%), 80 places. Added: the card's drop-down of the part a print makes
# (print-part), the parts and pieces of the site the printer is pinned in; it is
# read when Print is pressed, so nothing listens to it. Not ring-backed: Control ›
# Print › Send file prints what the card has chosen, the part with the file, and no
# cell chooses either. No ring address moved.
#
# Phase 3, Site lists the site's jobs. Before: 119 controls of its own, 58
# ring-backed (48.7%), 80 places the page listens. After: 119, 58 ring-backed
# (48.7%), 81 places. Added: a job's row in Site's Jobs, a list, selecting its
# machine at its level and opening it (siteJobsListEl:click:closest). Site's Jobs
# is a fold, as Pinned is, and adds no control. No ring address moved.
VIEWER_CEILING = 119


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
# The rows' take-backs: taken back from the list that shows them, not ring-backed
# --------------------------------------------------------------------------


def test_the_rows_take_backs_are_counted_and_not_claimed_as_ring_backed():
    """Unpin a camera, a view or a board's pin from Site's Pinned, forget a kept
    picture from Pictures: the lasting exception for taking a thing back from the
    list that shows it, counted on the meter and never ring-backed, since a row
    can name another site's pin that a ring cell reaches only from that site."""
    taken = census.take()
    by_name = {f.name: f for f in taken.controls_of_its_own()}
    for name in ("pinned-camera-unpin", "pinned-view-unpin", "pinned-board-unpin"):
        assert by_name[name].source == "pinned.js"
        assert by_name[name].ring_action is None, name
        assert by_name[name].taken_back, name
    assert by_name["pictures-forget"].source == "picture_list.js"
    assert {f.name for f in taken.taken_back()} == {
        "pictures-forget",
        "pinned-camera-unpin",
        "pinned-view-unpin",
        "pinned-board-unpin",
    }
    # Purge stays a cell of the canvas ring's Pictures, and so does Gather.
    assert by_name["pictures-purge"].ring_action == "picture:purge"
    assert by_name["pic-gather"].ring_action == "camera:gather"
    # Kept and the Gather panel are gone from the page, and from the tables; so
    # are the older panel's rows before them.
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
    """Consolidation Phase 2 held the ring-backed share where it was, 58 of 128; its
    follow-ups do not let it fall below that, and neither does Phase 3, which deleted
    the Jobs panel's controls, none of them ring-backed."""
    taken = census.take()
    own, backed = len(taken.controls_of_its_own()), len(taken.ring_backed())
    assert backed / own >= 58 / 128, f"{backed} of {own} ring-backed"


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
