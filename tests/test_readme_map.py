"""The README's map, *What it does, and how to see it*, is the reviewer's: each row is one
thing the code does, the tests that hold it and its walkthrough page. A review walks the
rows on the running demo, so a row naming a test or a page that is not there sends the
reviewer nowhere, a browser test in no row holds something no reviewer is shown, and a
page a run writes in no row naming that run is a picture nobody is pointed at."""

import re

import pytest

from apothecary.projects.parts.skeleton import ROOT

SECTION = "## What it does, and how to see it"
TESTS = ROOT / "tests"


def _rows(readme: str) -> list[list[str]]:
    """The map's rows, each its four cells, the header and the rule left out."""
    start = readme.index(SECTION)
    end = readme.find("\n## ", start + len(SECTION))
    lines = readme[start : end if end != -1 else len(readme)].splitlines()
    table = [line for line in lines if line.startswith("|")][2:]
    return [[cell.strip() for cell in line.strip("|").split(" | ")] for line in table]


def _held_by(cell: str) -> list[str]:
    """The test modules a Held by cell names, as paths under tests/."""
    return re.findall(r"`((?:e2e/)?test_[a-z0-9_]+\.py)`", cell)


def _pages(cell: str) -> list[str]:
    """The walkthrough pages a Page cell links."""
    return re.findall(r"\]\((walkthrough/[0-9]{2}-[a-z0-9-]+\.md)\)", cell)


def _writer(page_text: str) -> str | None:
    """The run that writes a page, as the page's own *Written by* line names it."""
    found = re.search(r"^Written by `tests/([^`]+\.py)`", page_text, re.MULTILINE)
    return found.group(1) if found else None


def map_problems(readme: str, root=ROOT) -> list[str]:
    """What is wrong with the map in ``readme`` against the tree at ``root``."""
    problems = []
    rows = _rows(readme)
    if not rows:
        return [f"{SECTION!r} has no rows"]
    named: set[str] = set()
    for row in rows:
        if len(row) != 4:
            problems.append(f"a row has {len(row)} cells, not 4: {' | '.join(row)[:80]}")
            continue
        what, _, held, pages = row
        modules = _held_by(held)
        if not modules:
            problems.append(f"{what[:60]!r} names no test")
        for module in modules:
            path = root / "tests" / module
            if not path.is_file():
                problems.append(f"{what[:60]!r} names tests/{module}, which is not there")
            elif not re.search(r"^\s*def test_", path.read_text(encoding="utf-8"), re.MULTILINE):
                problems.append(f"{what[:60]!r} names tests/{module}, which holds no test")
            named.add(module)
        for page in _pages(pages):
            if not (root / page).is_file():
                problems.append(f"{what[:60]!r} links {page}, which is not there")
    for path in sorted((root / "tests" / "e2e").glob("test_*.py")):
        if f"e2e/{path.name}" not in named:
            problems.append(f"tests/e2e/{path.name} is in no row")
    for page in sorted((root / "walkthrough").glob("[0-9][0-9]-*.md")):
        writer = _writer(page.read_text(encoding="utf-8"))
        if writer is None:
            continue
        linked = [row for row in rows if len(row) == 4 and f"walkthrough/{page.name}" in row[3]]
        if not any(writer in _held_by(row[2]) for row in linked):
            problems.append(
                f"walkthrough/{page.name} is written by tests/{writer}, in no row with it"
            )
    return problems


def test_the_map_names_only_what_is_there_and_every_browser_test():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert map_problems(readme) == []


@pytest.mark.parametrize(
    "breaks, says",
    [
        (
            ("`e2e/test_ring.py`", "`e2e/test_rung.py`"),
            "names tests/e2e/test_rung.py, which is not there",
        ),
        (("`e2e/test_ring.py`, ", ""), "tests/e2e/test_ring.py is in no row"),
        (
            ("(walkthrough/07-a-part.md)", "(walkthrough/07-a-parts.md)"),
            "links walkthrough/07-a-parts.md",
        ),
        (("`e2e/test_scad_loop.py`, ", ""), "walkthrough/06-editing-a-parts-scad.md is written by"),
    ],
)
def test_the_map_says_what_is_wrong_with_it(breaks, says):
    """Each failure the map can have, made in a copy of the README, is named."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    old, new = breaks
    assert old in readme
    problems = map_problems(readme.replace(old, new, 1))
    assert any(says in problem for problem in problems), problems


def test_the_maps_address_asked_as_another_host_serves_something_here():
    """The row showing that the server answers this machine only names an address that
    serves something here and is refused when asked as another host: an address serving
    nothing would show the refusal while sending the reviewer nowhere."""
    from fastapi.testclient import TestClient

    from apothecary.api import app

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    asked = [
        found
        for row in _rows(readme)
        for found in re.findall(
            r"`curl -H 'Host: ([^']+)' http://127\.0\.0\.1:8000(/[^`\s]*)`", row[1]
        )
    ]
    assert asked, "the map names no address to ask as another host"
    here = TestClient(app)
    for host, path in asked:
        assert here.get(path).status_code == 200, f"{path} serves nothing here"
        assert here.get(path, headers={"host": host}).status_code == 403, f"{path} answers {host}"
