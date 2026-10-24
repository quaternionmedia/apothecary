"""Which CI gates this machine can run, and which it cannot.

``apothecary preflight`` executes this repository's workflows locally, out of
the governance corpus's own runner, so that "CI is green" is a thing somebody
ran rather than a thing somebody read. Not all of them can run here, and this
module is where that is written down -- because a check quietly dropped from a
local run is how "it passed locally" stops meaning anything.

The rule this module exists to hold: a gate excused from the local run must
name what covers it here instead. An excuse with no local equivalent is a gap
wearing a reason, and the doctests below refuse one.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

REPO = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO / ".github" / "workflows"


@dataclass(frozen=True)
class Difference:
    """A gate CI runs that this machine cannot, and what stands in for it."""

    why: str
    covered_by: str


# Every entry is a fact about the environment, not about the code, and each was
# observed by running preflight rather than predicted from reading a workflow.
LOCAL_DIFFERENCES: Dict[str, Difference] = {
    "pytest.yml": Difference(
        why=(
            "installs OpenSCAD with apt-get and Playwright with --with-deps, "
            "both Linux-only"
        ),
        covered_by=(
            "`uv run pytest` with OpenSCAD already installed, and "
            "`uv run pytest tests/e2e --start-server` once "
            "`uv run playwright install chromium` has been run once."
        ),
    ),
}


def partition(workflows_dir: Path | None = None) -> Tuple[List[str], List[str]]:
    """Split the workflows into what the runner can execute and what it cannot.

    The runner evaluates a small set of ``${{ }}`` expressions and exits on
    anything else, so a single matrix workflow would abort the whole run before
    the others report. Those are set aside and named. This repository has none
    today, which is a fact worth asserting rather than assuming:

        >>> runnable, set_aside = partition()
        >>> set_aside
        []
        >>> "reuse-lint.yml" in runnable
        True

    Nothing falls between the two -- a workflow appearing in neither would be a
    gate nobody notices is missing:

        >>> names = {p.name for p in WORKFLOWS.glob("*.yml")}
        >>> names == set(runnable) | set(set_aside)
        True
    """
    directory = workflows_dir or WORKFLOWS
    runnable, set_aside = [], []
    for workflow in sorted(directory.glob("*.yml")):
        if "matrix:" in workflow.read_text(encoding="utf-8"):
            set_aside.append(workflow.name)
        else:
            runnable.append(workflow.name)
    return runnable, set_aside


def differences_are_current() -> List[str]:
    """Complaints about ``LOCAL_DIFFERENCES``, empty when it is honest.

    A recorded difference has to point at a workflow that exists, and it has to
    say what covers the gate here instead:

        >>> differences_are_current()
        []

    The second half is the one worth enforcing. Every gate excused here names a
    command a reader can run, so "it cannot run locally" never becomes a place
    to put a check nobody looks at again.

        >>> all(d.covered_by for d in LOCAL_DIFFERENCES.values())
        True
    """
    problems = []
    present = {p.name for p in WORKFLOWS.glob("*.yml")}
    for name, difference in sorted(LOCAL_DIFFERENCES.items()):
        if name not in present:
            problems.append(f"{name}: recorded as a local difference, but no such workflow")
        if not difference.why.strip():
            problems.append(f"{name}: no reason given")
        if not difference.covered_by.strip():
            problems.append(f"{name}: nothing named as covering it here")
    return problems
