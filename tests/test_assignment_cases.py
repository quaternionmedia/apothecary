"""The server's reading of a SCAD text's assignments, held to the cases the page's
reading is held to (tests/assignment_cases.json): the page rewrites a parameter's
line itself, so the two must agree on the grammar (apothecary/projects/parts/
assignments.py's docstring). tests/e2e/test_assignments_in_the_page.py runs the
same cases through apothecary/static/widgets/assignments.js in a browser.

The expected answers were written by the server's module; a change to the grammar
changes them here first, and the page must follow."""

import json
from pathlib import Path

import pytest

from apothecary.projects.parts.assignments import parse_assignments, write_values

CASES = json.loads((Path(__file__).with_name("assignment_cases.json")).read_text(encoding="utf-8"))


def read(text: str):
    """The assignments as the page is answered them: by alias, ``from`` and ``to``."""
    return [a.model_dump(by_alias=True) for a in parse_assignments(text)]


@pytest.mark.parametrize("case", CASES["parse"], ids=[c["why"] for c in CASES["parse"]])
def test_the_server_reads_each_case_as_written_down(case):
    assert read(case["text"]) == case["assignments"]


@pytest.mark.parametrize(
    "case", CASES["write"], ids=[json.dumps(c["values"]) for c in CASES["write"]]
)
def test_the_server_writes_each_value_as_written_down(case):
    assert write_values(case["text"], case["values"]) == case["out"]


def test_the_cases_reach_every_part_of_the_grammar():
    """Each thing the grammar reads appears in some case: a case dropped would leave
    the page free to read it otherwise."""
    found = [a for c in CASES["parse"] for a in c["assignments"]]
    assert any(a["computed"] for a in found)
    assert any(not a["parameter"] for a in found)
    assert any(a["group"] for a in found)
    assert any(a["caption"] for a in found)
    assert any(a["unit"] for a in found)
    assert any(a["options"] for a in found)
    assert any(a["step"] is not None for a in found)
    assert any(isinstance(a["value"], list) for a in found)
    assert any(isinstance(a["value"], str) for a in found)
    assert any(c["text"] != c["text"].encode("ascii", "ignore").decode() for c in CASES["parse"])
    assert any(not c["text"].endswith("\n") for c in CASES["write"])
