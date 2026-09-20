"""The count of ways in has to be a measurement, not a memory.

Most of these exist because an independent reviewer broke the first version of
the counter. Each one names the attack it came from, so that removing a test
means arguing with the attack rather than only with the test.
"""

import re

import pytest

from apothecary import census

# --------------------------------------------------------------------------
# The figure itself
# --------------------------------------------------------------------------


def test_the_page_has_fifty_four_controls_of_its_own():
    """The meter. Unifying means this number falls, and falls to nothing.

    Not the twelve an earlier version of this file asserted. Twelve was a hand
    tally reproduced by a counter built to reproduce it: it counted names rather
    than controls, so two buttons on a job were one and three boxes for typing a
    position were one, and it left out a drop-down that nothing listens to.
    Counted properly, one control at a time, there were twenty.

    Thirty-three next, and the meter went up rather than down: two buttons that
    keep or discard a piece's staged numbers, six controls and a link for a
    board's serial log, the same link again where no board is found, and three
    for how much of a subassembly to draw. Each arrived with a feature; none of
    them was unified with anything.

    Fifty-four now, up by twenty-one, and this is the first rise that came with
    the thing that makes it fall. The printer seam brought a tick-box and a
    drop-down for looking for boards on a schedule, a link to the monitor, five
    controls on the serial log for identifying a board and asking it for a
    report, and thirteen in the chosen piece's Device section for pinning,
    polling, watching and querying its board. The ring arrived in the same
    change, and fifteen of the fifty-four are ring-backed: the same verb is a
    cell of the ring, with its address written on the button -- thirteen in
    the Device section and serial log, and the two navigation buttons (step
    out, go in) once the ring learned to list pieces and step back up. Those
    fifteen are the ones that can go, and the meter falls as they do. The
    Contents rows are ring-backed too (the canvas ring's Pieces cell reaches
    every row at the current level), but rows are a list, not the meter.

    One hundred and sixteen now, and this rise is the one-screen plan's third
    phase arriving: the world mounts the machine (widgets/machine.js, the
    monitor's whole body -- sixty-two controls, forty-one of them on the
    ring) in a popup tethered to the printer, and a widget's controls are the
    page's on every page that mounts it. The page's own fifty-four are what
    they were; the three-screen meter counts the machine once, by its source.
    """
    taken = census.take()
    own_here = [f for f in taken.controls_of_its_own() if not f.source]
    from_machine = [f for f in taken.controls_of_its_own() if f.source == "machine.js"]
    assert (len(own_here), len(from_machine)) == (54, 62)
    assert len(taken.controls_of_its_own()) == 116
    assert len(taken.ring_backed()) == 56  # 15 of the page's own, 41 of the machine's
    assert taken.sentence().startswith("116 controls of its own, 56 of them also on the ring.")
    rows = [f for f in taken.found if f.key == "li:click:selectChild"]
    assert rows and rows[0].ring_action.startswith("select:")


def test_the_firmware_page_is_counted_as_the_third_screen():
    """The toolchain page, counted so the three screens have one meter between
    them before they become one screen: 148 controls of their own in all,
    60 of them on a ring. Thirty here -- install, cores, libraries, a sketch's
    board and port, compile and upload, the esptool form, the task cancel, and
    each device card's probe, identify, poll, live and monitor link -- and
    four of them on the ring (poll, monitor, live as watch, rescan), since
    this page has no ring yet. A class that only says how a control looks
    (`small`, `primary`) does not name it; `class="small dev-probe"` is the
    probe button."""
    taken = census.take(census.FIRMWARE)
    assert len(taken.controls_of_its_own()) == 30
    assert len(taken.ring_backed()) == 4
    assert taken.sentence().startswith("30 controls of its own, 4 of them also on the ring.")
    assert "no ring yet" in taken.sentence()
    names = {f.name for f in taken.found if f.how == "markup"}
    assert {"dev-probe", "dev-identify", "dev-printer", "dev-monitor", "dev-live"} <= names
    assert "small" not in names
    listening = [f for f in taken.found if f.how == "listening"]
    assert len(listening) == 8
    assert taken.of_surface(census.LIST) == tuple(
        f for f in taken.found if f.key in ("sketches:click:closest", "history:click:closest")
    )


def test_the_three_screens_have_one_meter():
    """What the one-screen consolidation is measured against
    (docs/plans/one-screen-2026-09-20.md): every control once, wherever it
    is mounted. A widget module two pages mount (the machine, on the monitor
    page and in the world's popup) is one thing, counted by its source."""
    own = backed = 0
    widgets_seen: set = set()
    for page in census.PAGES:
        taken = census.take(page)
        for source in {f.source for f in taken.controls_of_its_own()}:
            if source and source in widgets_seen:
                continue  # the same module, mounted by another page: counted already
            widgets_seen.add(source)
            here = [f for f in taken.controls_of_its_own() if f.source == source]
            own += len(here)
            backed += sum(1 for f in here if f.ring_action)
    assert (own, backed) == (148, 60)


def test_the_monitor_page_is_counted_too():
    """The second page, counted the same way and never added to the first.

    Sixty-four controls of its own, and forty-one of them are on the ring:
    the control overlay's heat, fan, home, jog, SD, motors, quickstop,
    break-wait and mesh buttons, the emergency stop, the latch's arm and
    disarm, the header's poll, identify, reconnect, reset and release, the
    bed card's probe, read and four corners, and the print card's print,
    pause, resume and cancel (the Print cell's verbs go to whichever print
    is running). What is not backed is the plumbing of the page itself:
    which port, how often, the log's tick-boxes, the download, and the
    print card's file picker, its list and its forget button.
    """
    taken = census.take(census.MONITOR)
    assert (
        len(taken.controls_of_its_own()) == 64
    )  # 2 of the page's own (its links), 62 the machine's
    assert {f.source for f in taken.controls_of_its_own()} == {"", "machine.js"}
    assert len(taken.ring_backed()) == 41
    assert taken.sentence().startswith("64 controls of its own, 41 of them also on the ring.")
    listening = [f for f in taken.found if f.how == "listening"]
    # Fourteen in the machine module, one on the page (the board view following
    # the port picker): the bed card and the print card follow the port from
    # selectPort itself now, and the two listeners they had are gone.
    assert len(listening) == 15
    assert taken.of_surface(census.GESTURE) == ()
    assert taken.of_surface(census.LIST) == tuple(
        f for f in taken.found if f.key == "level-history:click:closest"
    )


def test_the_two_buttons_on_a_job_are_two():
    """The exact case that showed the old counter was counting names.

    Giving a job to a machine and finishing a job are two buttons, side by side,
    fetched the same way. Anything that reports one has stopped counting
    controls.
    """
    taken = census.take()
    doing = {f.description for f in taken.found if f.how == "listening"}
    assert "giving a job to a machine" in doing
    assert "finishing a job" in doing
    in_markup = {f.name for f in taken.found if f.how == "markup"}
    assert {"job-assign-btn", "job-complete-btn"} <= in_markup


def test_three_boxes_for_a_position_are_three():
    taken = census.take()
    boxes = {f.name for f in taken.found if f.name.startswith("pos-")}
    assert boxes == {"pos-x", "pos-y", "pos-z"}


def test_a_control_nothing_listens_to_is_still_a_control():
    """The drop-down of machines has no listener; its value is read when asked.

    The first counter read only listeners and so could not see it at all.
    """
    taken = census.take()
    by_name = {f.name: f for f in taken.found if f.how == "markup"}
    assert "job-printer-select" in by_name
    assert by_name["job-printer-select"].surface == census.WIDGET


# --------------------------------------------------------------------------
# Refusals — the count must stop rather than be wrong
# --------------------------------------------------------------------------


def test_a_control_nobody_has_classified_stops_the_count(tmp_path):
    page = tmp_path / "page.html"
    page.write_text('<button id="mystery-btn">go</button>\n', encoding="utf-8")
    with pytest.raises(census.Unclassified, match="mystery-btn"):
        census.take(page)


def test_a_new_control_cannot_hide_inside_an_old_one(tmp_path):
    """The reviewer's sharpest attack, kept as a test.

    A destructive button added to a row of a list attaches exactly the way the
    buttons already there attach. The old counter absorbed it into an existing
    entry and reported the same number as before. Naming what the handler does
    is what makes it impossible.
    """
    page = tmp_path / "page.html"
    page.write_text(
        "li.addEventListener('click', () => this.selectChild(path));\n"
        "li.addEventListener('click', () => this.deleteNode(path));\n",
        encoding="utf-8",
    )
    with pytest.raises(census.Unclassified) as refusal:
        census.take(page)
    assert "li:click:deleteNode" in str(refusal.value)
    assert "li:click:selectChild" not in str(refusal.value)


def test_a_refusal_says_where(tmp_path):
    page = tmp_path / "page.html"
    page.write_text('\n\n\n<button id="mystery-btn">go</button>\n', encoding="utf-8")
    with pytest.raises(census.Unclassified, match="line 4"):
        census.take(page)


def test_every_unknown_is_named_at_once(tmp_path):
    page = tmp_path / "page.html"
    page.write_text(
        '<button id="one-btn">a</button><button id="two-btn">b</button>\n',
        encoding="utf-8",
    )
    with pytest.raises(census.Unclassified) as refusal:
        census.take(page)
    assert "one-btn" in str(refusal.value)
    assert "two-btn" in str(refusal.value)


def test_a_page_it_could_not_read_is_refused_not_answered_zero(tmp_path):
    """A count that reports nothing found is the same as a perfect score.

    The old counter only accepted one style of quotation mark. Reformatting the
    page — which a tidying tool does unasked — took the number to zero with no
    complaint and a successful exit.
    """
    page = tmp_path / "page.html"
    page.write_text("nothing here at all\n", encoding="utf-8")
    with pytest.raises(census.NothingFound):
        census.take(page)


def test_either_style_of_quotation_mark_is_read(tmp_path):
    page = tmp_path / "page.html"
    page.write_text('this.canvas.addEventListener("wheel", (e) => this.onWheel(e));\n', "utf-8")
    taken = census.take(page)
    assert [f.key for f in taken.found] == ["canvas:wheel:onWheel"]


# --------------------------------------------------------------------------
# Reading the page — the ways it went wrong before
# --------------------------------------------------------------------------


def test_the_thing_listened_on_is_read_backwards_and_not_across(tmp_path):
    """A label in the statement above must not claim a listener of its own.

    The old counter searched a fixed window of characters, so a mention on the
    line before won, and the listener was filed under the wrong thing with no
    complaint.
    """
    page = tmp_path / "page.html"
    page.write_text(
        "const b = el.querySelector('.zoom-in-btn');\n"
        "this.canvas.addEventListener('wheel', (e) => this.onWheel(e));\n",
        encoding="utf-8",
    )
    taken = census.take(page)
    assert [f.key for f in taken.found] == ["canvas:wheel:onWheel"]


def test_a_gap_filled_in_as_the_page_is_written_is_not_a_statement_boundary(tmp_path):
    page = tmp_path / "page.html"
    page.write_text(
        "document.getElementById(`pos-${axis}`).addEventListener('change', (e) => {\n"
        "    this.recomputeWorldBounds(node);\n"
        "});\n",
        encoding="utf-8",
    )
    taken = census.take(page)
    assert [f.key for f in taken.found] == ["posAxis:change:recomputeWorldBounds"]


def test_a_short_handler_does_not_borrow_the_next_line_s_work(tmp_path):
    """Reading a fixed number of characters ran off the end of the handler.

    The handle-taking listener does nothing but set a flag; the counter read past
    it and reported the following line's listening as this one's doing.
    """
    page = tmp_path / "page.html"
    page.write_text(
        "this.transformControls.addEventListener('dragging-changed', (event) => {\n"
        "    this.controls.enabled = !event.value;\n"
        "});\n"
        "this.transformControls.addEventListener('objectChange', () => this.onGizmoDrag());\n",
        encoding="utf-8",
    )
    taken = census.take(page)
    assert [f.key for f in taken.found] == [
        "transformControls:dragging-changed:(nothing)",
        "transformControls:objectChange:onGizmoDrag",
    ]


def test_plumbing_is_not_mistaken_for_the_point(tmp_path):
    page = tmp_path / "page.html"
    page.write_text(
        "this.jobFormEl.addEventListener('submit', (e) => {\n"
        "    e.preventDefault();\n"
        "    this.createJob();\n"
        "});\n",
        encoding="utf-8",
    )
    taken = census.take(page)
    assert [f.key for f in taken.found] == ["jobFormEl:submit:createJob"]


# --------------------------------------------------------------------------
# The tables themselves
# --------------------------------------------------------------------------


def test_every_classification_uses_a_kind_that_exists():
    for table in (census.CONTROLS, census.LISTENING):
        for key, (surface, effect, description) in table.items():
            assert surface in census.SURFACES, f"{key} is filed under {surface!r}"
            assert effect in census.EFFECTS, f"{key} changes {effect!r}, which is not a thing"
            assert description.strip(), f"{key} has no description"


def test_the_tables_do_not_rot():
    """Everything classified is actually in the page.

    A table that keeps entries for controls that no longer exist quietly becomes
    a record of what somebody once believed rather than of what is there.
    """
    seen_markup = set()
    seen_listening = set()
    for page in census.PAGES:
        taken = census.take(page)
        seen_markup |= {f.name for f in taken.found if f.how == "markup"}
        seen_listening |= {f.key for f in taken.found if f.how == "listening"}
    made_by_the_page = {"category-chip", "tree-caret", "contents-item", "breadcrumb"}
    stale = set(census.CONTROLS) - seen_markup - made_by_the_page
    assert not stale, f"classified but not in either page: {sorted(stale)}"
    assert not set(census.LISTENING) - seen_listening
    assert not set(census.RING_BACKED) - seen_markup - seen_listening


def test_the_two_questions_are_kept_apart():
    """Surface and effect must vary independently, or one is dressing the other.

    The first counter collapsed them, which is how the same behaviour came to be
    called a control in one place and moving your attention in another.
    """
    taken = census.take()
    widgets = {f.effect for f in taken.of_surface(census.WIDGET)}
    lists = {f.effect for f in taken.of_surface(census.LIST)}
    assert census.WHAT_IS_THERE in widgets and census.WHAT_YOU_SEE in widgets
    assert lists == {census.WHAT_YOU_SEE}


def test_stepping_out_is_called_the_same_thing_wherever_it_is_done():
    """Every way of changing which piece you are looking at agrees.

    A button that steps out, a key that steps out, a wheel that steps out and a
    trail that steps out run the same three lines. The old counter called some of
    them commands and the rest navigation, which is how it reached the number it
    had already decided on.
    """
    taken = census.take()
    stepping = [
        f
        for f in taken.found
        if f.how == "listening" and f.key.endswith(("zoomOut", "zoomIn", "jumpTo"))
    ]
    assert len(stepping) >= 5
    assert {f.effect for f in stepping} == {census.WHAT_YOU_SEE}


def test_there_is_a_ring_and_the_counter_says_so():
    """One control is filed under the ring on each page: the button that opens it.

    The ring's own listeners live in the module the page imports and are the
    ring's, not the page's; the next test holds the module to that.
    """
    for page in census.PAGES:
        taken = census.take(page)
        ring = taken.of_surface(census.RING)
        if page is census.FIRMWARE:
            # The third screen has no ring; the one-screen plan folds it into
            # the world rather than giving it one of its own.
            assert ring == () and "no ring yet" in taken.sentence()
            continue
        assert [f.name for f in ring] == ["ring-open"]
        assert "a ring" in taken.sentence()
        assert "no ring yet" not in taken.sentence()


RING_MODULE = census.TEMPLATES.parent / "apothecary" / "static" / "ring.js"


def test_the_ring_module_opens_three_ways_and_the_pages_import_it():
    """What the census counts once, behind `ring-open`, checked at the source.

    The module installs the `m` key on the window, right-click on the document
    and a click on the button, and nothing else on either. Everything else it
    listens to is on the ring's own element while the ring is open. A fourth
    way in added to the module would be a way in the census cannot see, so it
    is refused here instead.
    """
    text = RING_MODULE.read_text(encoding="utf-8")
    on_page = re.findall(r"(window|document)\.addEventListener\(\s*[\"'](\w+)[\"']", text)
    assert sorted(set(on_page)) == [("document", "contextmenu"), ("window", "keydown")]
    assert 'button = "#ring-open"' in text
    for page in census.PAGES:
        imports_it = "/static/ring.js" in page.read_text(encoding="utf-8")
        assert imports_it == (page is not census.FIRMWARE)


def test_a_ring_would_be_reported_if_there_were_one(tmp_path):
    """The half of the meter that has nothing to measure yet is still exercised."""
    page = tmp_path / "page.html"
    page.write_text('<button id="the-ring">ring</button>\n', encoding="utf-8")
    census.CONTROLS["the-ring"] = (census.RING, census.WHAT_IS_THERE, "the ring")
    try:
        taken = census.take(page)
        assert len(taken.of_surface(census.RING)) == 1
        assert "a ring" in taken.sentence()
        assert taken.controls_of_its_own() == ()
    finally:
        del census.CONTROLS["the-ring"]


# --------------------------------------------------------------------------
# Ring-backed — a control the ring has already replaced in all but deletion
# --------------------------------------------------------------------------


def test_every_ring_backed_action_is_one_a_ring_produces_and_somebody_carries():
    """A control cannot claim a backing that does not exist.

    Two checks, from the ring's own vocabulary in `apothecary.menu`: the action
    is one `carried_by` knows, and one that some ring actually offers -- the
    node ring standing on a piece with a printer pinned to it, the device ring
    on a port, or the canvas ring. A typo in `RING_BACKED` would otherwise be a
    control reported as on the ring with no cell that reaches it.
    """
    from apothecary import menu

    printer = menu.Device(port="/dev/ttyUSB0", printer=True, armed=False, bound=True)
    armed = menu.Device(port="/dev/ttyUSB0", printer=True, armed=True, bound=True)
    unpinned = menu.Device(port="/dev/ttyUSB0", printer=True, armed=False, bound=False)
    on_node = menu.Context(pointing=menu.Pointing.NODE, targets=["p"])
    on_port = menu.Context(pointing=menu.Pointing.DEVICE, targets=["/dev/ttyUSB0"])
    on_canvas = menu.Context(pointing=menu.Pointing.CANVAS)
    from apothecary.example_hierarchy import create_example_site

    garage = create_example_site()  # the canvas ring's Pieces are real pieces
    zoomed = menu.Context(pointing=menu.Pointing.CANVAS, targets=["printer_1"])
    rings = [
        menu.resolve(on_node, device=printer),
        menu.resolve(on_port, device=armed),
        menu.resolve(on_port, device=unpinned),
        menu.resolve(on_canvas, garage, site_names=["garage"]),
        menu.resolve(zoomed, garage),  # Up (zoom-out) exists only below the root
    ]
    offered = menu.every_action(rings)
    for page in census.PAGES:
        for found in census.take(page).found:
            if found.ring_action is None:
                continue
            assert menu.carried_by(found.ring_action) is not menu.Carries.UNBUILT, found
            assert found.ring_action in offered, f"{found.key} claims {found.ring_action!r}"


def test_a_ring_backed_control_is_still_on_the_meter():
    """Backing is not deletion. The meter falls when the control goes, not before."""
    taken = census.take()
    backed = taken.ring_backed()
    assert backed
    assert set(backed) <= set(taken.controls_of_its_own())
    assert all(f.surface == census.WIDGET for f in backed)


def test_the_sentence_says_how_many_are_on_the_ring(tmp_path):
    page = tmp_path / "page.html"
    page.write_text(
        '<button class="dev-watch">w</button><button id="serial-clear">c</button>\n',
        encoding="utf-8",
    )
    taken = census.take(page)
    assert taken.sentence().startswith("2 controls of its own, 1 of them also on the ring.")
    assert taken.ring_backed()[0].ring_action == "device:watch"


def test_the_report_writes_the_address_beside_a_backed_control(tmp_path):
    page = tmp_path / "page.html"
    page.write_text('<button class="dev-poll">p</button>\n', encoding="utf-8")
    assert "⌗ device:poll" in census.report(page)


# --------------------------------------------------------------------------
# Reading the page — what the printer seam's pages made visible
# --------------------------------------------------------------------------


def test_two_forms_send_buttons_are_two(tmp_path):
    """A submit button has no name of its own, so it is named by its form.

    Named by its shape alone, the serial log's send button was counted as the
    job form's, and a second form could never add a control.
    """
    page = tmp_path / "page.html"
    page.write_text(
        '<form id="job-form"><button type="submit">go</button></form>\n'
        '<form id="qform"><button type="submit">send</button></form>\n',
        encoding="utf-8",
    )
    taken = census.take(page)
    assert [f.name for f in taken.found] == ["job-form", "job-form:submit", "qform", "qform:submit"]


def test_a_button_that_carries_its_line_is_named_by_the_line(tmp_path):
    """Two buttons of one class that send two different lines are two.

    The monitor's control overlay names nothing: each button carries the G-code
    it sends. Named by class, both temperature buttons were `warm`, and the
    twenty with no class at all were not there.
    """
    page = tmp_path / "page.html"
    page.write_text(
        '<button class="warm" data-cmd="M104 S{h-hot}">Set</button>\n'
        '<button class="warm" data-cmd="M140 S{h-bed}">Set</button>\n'
        '<button data-jog="Y+">up</button><button data-step="10">10</button>\n',
        encoding="utf-8",
    )
    taken = census.take(page)
    assert [f.name for f in taken.found] == [
        "cmd:M104 S{h-hot}",
        "cmd:M140 S{h-bed}",
        "jog:Y+",
        "step:10",
    ]
    assert [f.ring_action for f in taken.found] == [
        "control:hotend-on",
        "control:bed-on",
        "control:jog:Y+",
        None,
    ]


def test_a_link_with_a_class_is_the_thing_its_class_says(tmp_path):
    """Named by its link before its class, a Device-section link was the recipe download."""
    page = tmp_path / "page.html"
    page.write_text(
        '<a class="dev-monitor" href="/firmware/monitor?port=x">m</a>\n'
        '<a href="/parts/x/scad">d</a>\n'
        '<a href="/viewer">v</a>\n',
        encoding="utf-8",
    )
    taken = census.take(page)
    assert [f.name for f in taken.found] == ["dev-monitor", "part-scad-download", "viewer-link"]


def test_a_control_fetched_by_the_one_letter_helper_is_named(tmp_path):
    page = tmp_path / "page.html"
    page.write_text(
        '$("port").addEventListener("change", () => selectPort($("port").value));\n', "utf-8"
    )
    taken = census.take(page)
    assert [f.key for f in taken.found] == ["port:change:selectPort"]


def test_a_bare_handler_is_the_thing_it_does(tmp_path):
    """`addEventListener("change", schedule)` does one thing, and it is named."""
    page = tmp_path / "page.html"
    page.write_text('$("auto").addEventListener("change", schedule);\n', "utf-8")
    taken = census.take(page)
    assert [f.key for f in taken.found] == ["auto:change:schedule"]


def test_pin_and_pin_by_typing_are_two_listeners(tmp_path):
    """`.dev-pin-manual` begins with `.dev-pin`, and must not be read as it."""
    page = tmp_path / "page.html"
    page.write_text(
        "el.querySelector('.dev-pin')?.addEventListener('click', () => this.setNodeDevice(p));\n"
        "el.querySelector('.dev-pin-manual')?.addEventListener('click', pinManual);\n",
        encoding="utf-8",
    )
    taken = census.take(page)
    assert [f.key for f in taken.found] == [
        "devPin:click:setNodeDevice",
        "devPinManual:click:pinManual",
    ]


# --------------------------------------------------------------------------
# The command
# --------------------------------------------------------------------------


def test_the_command_prints_the_count():
    from click.testing import CliRunner

    from apothecary.cli.census import census as command

    result = CliRunner().invoke(command, [])
    assert result.exit_code == 0
    assert "controls of its own" in result.output


def test_the_command_refuses_loudly(tmp_path):
    from click.testing import CliRunner

    from apothecary.cli.census import census as command

    page = tmp_path / "page.html"
    page.write_text('<button id="mystery-btn">go</button>\n', encoding="utf-8")
    result = CliRunner().invoke(command, ["--page", str(page)])
    assert result.exit_code == 1
    assert "mystery-btn" in result.output


def test_the_command_refuses_a_page_it_could_not_read(tmp_path):
    from click.testing import CliRunner

    from apothecary.cli.census import census as command

    page = tmp_path / "page.html"
    page.write_text("nothing here\n", encoding="utf-8")
    result = CliRunner().invoke(command, ["--page", str(page)])
    assert result.exit_code == 1
    assert "no number is given" in result.output


PANELS_MODULE = census.TEMPLATES.parent / "apothecary" / "static" / "panels.js"


def test_the_panel_module_keeps_its_chrome_to_itself():
    """What stands in front of the world (panels.js) listens on the elements it
    makes -- a panel's collapse, float and close buttons, its title bar, the
    tabs of closed panels -- and on the window only for the pointer moves that
    finish a drag, put on when a drag starts and taken off when it ends. The
    page's census cannot see inside the module, so this holds the module to
    that; a fourth way in would be added here first."""
    text = PANELS_MODULE.read_text(encoding="utf-8")
    on_page = re.findall(r"(window|document)\.addEventListener\(\s*[\"'](\w+)[\"']", text)
    assert sorted(set(on_page)) == [("window", "pointermove"), ("window", "pointerup")]
    assert 'window.removeEventListener("pointermove"' in text
    assert 'window.removeEventListener("pointerup"' in text
    assert "/static/panels.js" in census.VIEWER.read_text(encoding="utf-8")
    assert "/static/panels.js" not in census.MONITOR.read_text(encoding="utf-8")
