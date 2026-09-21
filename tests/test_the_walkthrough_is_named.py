"""The walkthrough is written by a run, and that run has to be one the command makes.

This is a guard about a guard. The walkthrough is the page a newcomer meets, and
it is now the output of the run that asserts it rather than prose standing beside
one. Two ways that arrangement fails quietly, and both have happened here:

- **The run is not selected.** A demonstration nothing runs writes nothing, so
  the committed page is whatever the last run that did happen left behind. This
  is the same failure the directory-naming guard was written for, moved to where
  the demonstration now lives.
- **A second demonstration appears.** The viewer half used to be a separate
  doc-workflow behind `apothecary docs generate`, and the hand-written page said
  so in its own closing section. Two pages describing one path is the state this
  replaced; one of them is always the stale one.

**Watched failing.** Dropping the marker expression from
`apothecary/cli/testing.py::run_command` turns the first test red; dropping
`--start-server` from the same list turns the second red; putting
`@pytest.mark.docs` back on the demonstration turns the last red. Each was run
with the fault in place before this note was written.

The first of those is the reason `run_command` exists. The check began as a scan
of the command's source for the marker's name, and it passed with the marker
expression deleted -- the word was in the command's own docstring. A guard that
reads prose reports on prose.
"""

import subprocess
from pathlib import Path

from apothecary.cli import testing
from apothecary.projects.parts.skeleton import ROOT

# The runs that write pages, and the test in each that does the writing.
DEMONSTRATION_MODULES = {
    Path(__file__).resolve().parent / "e2e" / "test_docs_photo_walkthrough.py": (
        "test_photographs_into_pieces"
    ),
    Path(__file__).resolve().parent / "e2e" / "test_docs_bench_walkthrough.py": (
        "test_the_bench_as_it_is"
    ),
}

# The pages a run writes, as opposed to the executable pages a person writes and
# pytest runs as doctests. The guards about being output apply to the first kind
# only: a hand-written page that claimed to be generated would be the lie the
# guard exists to catch, pointed the other way.
GENERATED_PAGES = ("11-photographs-into-pieces.md", "12-the-bench-as-it-is.md")


def test_the_command_collects_the_run_that_writes_the_page():
    """Ask pytest what the ordinary command collects, rather than reading the code.

    The first version of this scanned the command's source for the marker's name.
    That passed with the marker expression deleted, because the word was in the
    command's own docstring -- found by deleting it and watching the check stay
    green. Collection is the behaviour; prose about it is not.
    """
    argv = testing.run_command() + ["--collect-only", "-q"]
    collected = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True)
    assert collected.returncode == 0, collected.stderr[-2000:]
    for module, run in DEMONSTRATION_MODULES.items():
        assert run in collected.stdout, (
            f"the ordinary test command does not collect {module.name}::{run}, the run "
            "that writes its walkthrough page, so the committed page is whatever the "
            "last run that did happen left behind — and nothing else would have told you"
        )


def test_the_command_supplies_what_the_demonstration_needs():
    """The demonstration drives a browser against a real server."""
    argv = testing.run_command()
    assert "--start-server" in argv, (
        "the command does not start a server, so the demonstration dies on a "
        "fixture instead of running and the page stops being regenerated"
    )


def test_there_is_exactly_one_walkthrough_and_it_has_pages():
    here = Path(__file__).resolve().parent.parent / testing.WALKTHROUGH
    assert here.is_dir(), f"{testing.WALKTHROUGH}/ does not exist"
    pages = sorted(here.glob("*.md"))
    assert pages, "a walkthrough with no pages is a directory"
    for page in pages:
        assert page.name[:2].isdigit(), (
            f"{page.name} is not ordinal-first, so the pages have no order"
        )


def test_every_page_says_whether_it_needs_anything_of_the_machine():
    here = Path(__file__).resolve().parent.parent / testing.WALKTHROUGH
    for page in sorted(here.glob("*.md")):
        text = page.read_text(encoding="utf-8")
        assert "Hermetic" in text or "Runtime-bound" in text, (
            f"{page.name} does not say whether it needs anything of the machine "
            "it runs on, so a reader cannot tell a real skip from a broken one"
        )


def test_every_generated_page_says_what_it_leaves_out():
    here = Path(__file__).resolve().parent.parent / testing.WALKTHROUGH
    for name in GENERATED_PAGES:
        text = (here / name).read_text(encoding="utf-8")
        assert "does not show" in text, (
            f"{name} does not say what it leaves out. A demonstration that "
            "names no boundary invites every reader to draw their own"
        )


def test_every_generated_page_says_it_is_output_rather_than_source():
    """A generated page a reader edits by hand is a page the next run destroys."""
    here = Path(__file__).resolve().parent.parent / testing.WALKTHROUGH
    for name in GENERATED_PAGES:
        assert (here / name).is_file(), f"{name} was not written by any run"
        text = (here / name).read_text(encoding="utf-8")
        assert "written by the run it describes" in text, (
            f"{name} does not say it is written by its own run. A reader who "
            "does not know that edits it, and the next run silently reverts them"
        )
    for page in sorted(here.glob("*.md")):
        if page.name in GENERATED_PAGES:
            continue
        assert "written by the run it describes" not in page.read_text(encoding="utf-8"), (
            f"{page.name} claims to be generated but no run writes it"
        )


def test_the_path_has_one_demonstration_and_not_two():
    """The viewer half is a section of the walkthrough, not a workflow of its own.

    `docs`-marked tests are what `apothecary docs generate` runs and renders into
    docs/generated/. The demonstration carrying that marker is what made the
    viewer a second page about the same path, produced by a command somebody had
    to remember.
    """
    for module in DEMONSTRATION_MODULES:
        source = module.read_text(encoding="utf-8")
        assert "pytest.mark.walkthrough" in source, (
            f"{module.name} is not marked as the walkthrough, so the ordinary test "
            "command's marker expression does not select it"
        )
        assert "pytest.mark.docs" not in source, (
            f"{module.name} is marked as a doc workflow as well, so "
            "`apothecary docs generate` renders a second page about the same path into "
            "docs/generated/ — which is the split this replaced"
        )
