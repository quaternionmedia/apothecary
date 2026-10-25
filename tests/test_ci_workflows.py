"""What CI runs when (CONTRIBUTING.md, "What CI gates"): a pull request's push runs the
governance checks and lint alone; the tests, the browser suite among them, run here
before a pull request is ready and in CI at a version tag or on demand."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
# The checks a pull request's push runs: the governance seed's, and lint.
ON_A_PULL_REQUEST = {
    "adr-lint.yml",
    "integrates.yml",
    "leak-check.yml",
    "license-check.yml",
    "lint.yml",
    "one-pr-check.yml",
    "reuse-lint.yml",
    "submodule-check.yml",
    "timeless-check.yml",
}
# What runs the tests: at a version tag, and on demand.
AT_A_TAG = {"pytest.yml", "docs-generate.yml"}


def _triggers(name: str) -> dict:
    doc = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    on = doc.get(True, doc.get("on"))
    return on if isinstance(on, dict) else {on: None}


def test_a_pull_request_runs_the_governance_checks_and_lint_alone():
    pull = {p.name for p in WORKFLOWS.glob("*.yml") if "pull_request" in _triggers(p.name)}
    assert pull == ON_A_PULL_REQUEST


def test_the_tests_run_at_a_version_tag_and_on_demand():
    for name in AT_A_TAG:
        on = _triggers(name)
        assert set(on) == {"push", "workflow_dispatch"}, name
        assert on["push"] == {"tags": ["v*"]}, name


def test_lint_runs_the_ruff_the_lock_pins():
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
    (locked,) = re.findall(r'\nname = "ruff"\nversion = "([^"]+)"', lock)
    lint = (WORKFLOWS / "lint.yml").read_text(encoding="utf-8")
    assert re.findall(r"uvx ruff@(\S+) check", lint) == [locked]
