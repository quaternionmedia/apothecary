"""What CI runs when (CONTRIBUTING.md, "What CI gates"): a pull request's push runs the
governance checks, lint and the walkthrough's hermetic pages; the rest of the tests, the
browser suite among them, run here before a pull request is ready and in CI at a version
tag or on demand."""

from __future__ import annotations

import doctest
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
# The checks a pull request's push runs: the governance seed's, lint, and the
# walkthrough's hermetic pages.
ON_A_PULL_REQUEST = {
    "adr-lint.yml",
    "integrates.yml",
    "leak-check.yml",
    "license-check.yml",
    "lint.yml",
    "one-pr-check.yml",
    "reuse-lint.yml",
    "signature-check.yml",
    "submodule-check.yml",
    "timeless-check.yml",
    "walkthrough.yml",
}
# What runs the tests: at a version tag, and on demand.
AT_A_TAG = {"pytest.yml", "docs-generate.yml", "rust.yml", "steps.yml"}


def _triggers(name: str) -> dict:
    doc = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    on = doc.get(True, doc.get("on"))
    return on if isinstance(on, dict) else {on: None}


def test_a_pull_request_runs_the_governance_checks_lint_and_the_walkthrough():
    pull = {p.name for p in WORKFLOWS.glob("*.yml") if "pull_request" in _triggers(p.name)}
    assert pull == ON_A_PULL_REQUEST


def test_the_tests_run_at_a_version_tag_and_on_demand():
    for name in AT_A_TAG:
        on = _triggers(name)
        assert set(on) == {"push", "workflow_dispatch"}, name
        assert on["push"] == {"tags": ["v*"]}, name


def test_the_walkthrough_runs_on_every_pull_request_and_on_main():
    """The corpus's walkthrough record: hermetic pages run in CI on every pull request, and
    a page has run only on evidence of a job's run on the default branch."""
    assert _triggers("walkthrough.yml") == {"pull_request": None, "push": {"branches": ["main"]}}
    doc = yaml.safe_load((WORKFLOWS / "walkthrough.yml").read_text(encoding="utf-8"))
    runs = [step.get("run", "") for job in doc["jobs"].values() for step in job["steps"]]
    assert "uv run pytest walkthrough -q" in runs


def test_the_pages_with_examples_are_the_pages_that_say_they_are_hermetic():
    """What `pytest walkthrough` collects is what that job runs with nothing installed: a
    page with examples of its own says it is hermetic, and a hermetic page has some."""
    parser = doctest.DocTestParser()
    pages = sorted((ROOT / "walkthrough").glob("*.md"))
    examples = {p.name for p in pages if parser.get_examples(p.read_text(encoding="utf-8"))}
    hermetic = {
        p.name for p in pages if re.search(r"^\*\*Hermetic\.\*\*", p.read_text(encoding="utf-8"), re.M)
    }
    assert examples and examples == hermetic


def test_dependabot_opens_grouped_security_updates_alone():
    """Its pull requests start cloud CI nobody issued: no version updates, and each
    ecosystem's security updates in one pull request."""
    doc = yaml.safe_load((ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8"))
    assert doc["updates"]
    for update in doc["updates"]:
        assert update["open-pull-requests-limit"] == 0, update["package-ecosystem"]
        groups = update["groups"].values()
        assert [g["applies-to"] for g in groups] == ["security-updates"], update["package-ecosystem"]


def test_lint_runs_the_ruff_the_lock_pins():
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
    (locked,) = re.findall(r'\nname = "ruff"\nversion = "([^"]+)"', lock)
    lint = (WORKFLOWS / "lint.yml").read_text(encoding="utf-8")
    assert re.findall(r"uvx ruff@(\S+) check", lint) == [locked]
