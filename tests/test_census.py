"""The count of ways in has to be a measurement, not a memory.

Most of these exist because an independent reviewer broke the first version of
the counter. Each one names the attack it came from, so that removing a test
means arguing with the attack rather than only with the test.
"""

import pytest

from apothecary import census

# --------------------------------------------------------------------------
# The figure itself
# --------------------------------------------------------------------------


def test_the_page_has_thirty_controls_of_its_own():
    """The meter. Unifying means this number falls, and falls to nothing.

    Not the twelve an earlier version of this file asserted. Twelve was a hand
    tally reproduced by a counter built to reproduce it: it counted names rather
    than controls, so two buttons on a job were one and three boxes for typing a
    position were one, and it left out a drop-down that nothing listens to.
    Counted properly, one control at a time, there were twenty.

    Thirty now, and the meter went up rather than down: two buttons that keep or
    discard a piece's staged numbers, six controls and a link for a board's
    serial log, and the same link again where no board is found. Each arrived
    with a feature; none of them is unified with anything.
    """
    taken = census.take()
    assert len(taken.controls_of_its_own()) == 30


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
    taken = census.take()
    seen_markup = {f.name for f in taken.found if f.how == "markup"}
    seen_listening = {f.key for f in taken.found if f.how == "listening"}
    made_by_the_page = {"category-chip", "tree-caret", "contents-item", "breadcrumb"}
    stale = set(census.CONTROLS) - seen_markup - made_by_the_page
    assert not stale, f"classified but not in the page: {sorted(stale)}"
    assert not set(census.LISTENING) - seen_listening


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


def test_there_is_no_ring_yet_and_the_counter_says_so():
    taken = census.take()
    assert taken.of_surface(census.RING) == ()
    assert "no ring yet" in taken.sentence()


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
