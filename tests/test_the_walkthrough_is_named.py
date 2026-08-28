"""The walkthrough has to be named on the command line, or it does not run.

This is a guard about a guard. The walkthrough is the one page in this
repository whose examples are executed rather than described, and it only runs
when the directory is given to the test runner explicitly — leaving it to the
configured paths silently skips every page in it, and a page that silently does
not run is prose claiming to be a demonstration.

**Watched failing:** removing `WALKTHROUGH` from the command in
`apothecary/cli/testing.py::test_run` turns the first test here red; deleting
the `--doctest-glob` turns the second red. Both were run with the fault in
place before this note was written.
"""

import inspect
from pathlib import Path

from apothecary.cli import testing


def test_the_walkthrough_is_named_on_the_command_line():
    source = inspect.getsource(testing.test_run.callback)
    assert "WALKTHROUGH" in source, (
        "the walkthrough is not named on the command line, so none of its pages "
        "run — and nothing else would have told you"
    )


def test_the_pages_are_executed_rather_than_read():
    source = inspect.getsource(testing.test_run.callback)
    assert "--doctest-glob" in source, (
        "without this the walkthrough's pages are collected and nothing in them " "is executed"
    )


def test_there_is_exactly_one_walkthrough_and_it_has_pages():
    here = Path(__file__).resolve().parent.parent / testing.WALKTHROUGH
    assert here.is_dir(), f"{testing.WALKTHROUGH}/ does not exist"
    pages = sorted(here.glob("*.md"))
    assert pages, "a walkthrough with no pages is a directory"
    for page in pages:
        assert page.name[
            :2
        ].isdigit(), f"{page.name} is not ordinal-first, so the pages have no order"


def test_every_page_says_whether_it_needs_anything_of_the_machine():
    here = Path(__file__).resolve().parent.parent / testing.WALKTHROUGH
    for page in sorted(here.glob("*.md")):
        text = page.read_text(encoding="utf-8")
        assert "Hermetic" in text or "Runtime-bound" in text, (
            f"{page.name} does not say whether it needs anything of the machine "
            "it runs on, so a reader cannot tell a real skip from a broken one"
        )
        assert "does not show" in text, (
            f"{page.name} does not say what it leaves out. A demonstration that "
            "names no boundary invites every reader to draw their own"
        )
