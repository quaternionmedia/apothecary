"""The page's reading of a SCAD text's assignments (apothecary/static/widgets/
assignments.js), held to the cases the server's reading is held to
(tests/assignment_cases.json, which tests/test_assignment_cases.py runs through
apothecary/projects/parts/assignments.py): a control rewrites its parameter's line in
the page, at once, and the server reads that text, so the two must agree on what an
assignment is, where its value stands, and how a value is written."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from playwright.sync_api import Page

CASES = json.loads(
    (Path(__file__).parent.parent / "assignment_cases.json").read_text(encoding="utf-8")
)

RUN = """async (cases) => {
    const m = await import('/static/widgets/assignments.js');
    return {
        parse: cases.parse.map((c) => m.parseAssignments(c.text).map((a) => ({ ...a, printed: null }))),
        write: cases.write.map((c) => m.writeValues(c.text, c.values)),
    };
}"""


@pytest.mark.e2e
def test_the_page_reads_and_writes_each_case_as_the_server_does(page: Page, base_url: str):
    page.goto(f"{base_url}/docs")
    got = page.evaluate(RUN, CASES)
    for case, found in zip(CASES["parse"], got["parse"], strict=True):
        assert found == case["assignments"], case["why"]
    for case, out in zip(CASES["write"], got["write"], strict=True):
        assert out == case["out"], case["values"]
