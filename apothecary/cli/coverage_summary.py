"""What a run of the suite covered: the package's statements, and the lines a change
adds or changes -- the measure a pull request's body carries (CONTRIBUTING.md, "The
loop"). It informs a reader of the pull request; nothing fails on a number.

`apothecary test all --coverage` measures every part of the run into one data file:
the unit tests and the walkthrough, then every browser test with the server they
drive, which coverage follows into its process (pyproject's [tool.coverage.run]
patches subprocess).
"""

from __future__ import annotations

import contextlib
import fnmatch
import io
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import click

from ..projects.parts.skeleton import ROOT

PACKAGE = "apothecary"
DATA = ROOT / ".coverage"
# A pull request's base, when none is named: what it would land on.
BASE = "origin/main"

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def changed_lines(diff: str) -> dict[str, set[int]]:
    """The lines a unified diff adds or changes, by file, numbered as the new file has
    them. A hunk that only removes lines adds none."""
    lines: dict[str, set[int]] = {}
    path = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            name = line[4:]
            path = None if name == "/dev/null" else name.removeprefix("b/")
            continue
        hunk = _HUNK.match(line)
        if hunk and path:
            start, count = int(hunk.group(1)), int(hunk.group(2) or 1)
            lines.setdefault(path, set()).update(range(start, start + count))
    return {path: numbers for path, numbers in lines.items() if numbers}


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def change_against(since: str) -> dict[str, set[int]]:
    """The package's lines this checkout adds or changes since it parted from ``since``:
    committed or not, and every line of a file it adds."""
    base = _git("merge-base", since, "HEAD")
    if base.returncode != 0:
        raise click.ClickException(f"cannot compare with {since}: {base.stderr.strip()}")
    diff = _git("diff", "-U0", "--no-color", "--no-ext-diff", base.stdout.strip(), "--", PACKAGE)
    lines = changed_lines(diff.stdout)
    added = _git("ls-files", "--others", "--exclude-standard", "--", PACKAGE).stdout.split()
    for path in added:
        count = len((ROOT / path).read_text(encoding="utf-8", errors="replace").splitlines())
        lines[path] = set(range(1, count + 1))
    return lines


def ranges(numbers) -> str:
    """Line numbers as runs: 3, 4, 5, 9 -> "3-5, 9"."""
    runs: list[list[int]] = []
    for n in sorted(numbers):
        if runs and n == runs[-1][1] + 1:
            runs[-1][1] = n
        else:
            runs.append([n, n])
    return ", ".join(str(a) if a == b else f"{a}-{b}" for a, b in runs)


@dataclass
class Measured:
    """The package's statements run, in percent; of the statements on the lines a change
    adds or changes, how many there are and how many ran; and those that did not."""

    total: float
    changed: int = 0
    run: int = 0
    missed: dict[str, list[int]] = field(default_factory=dict)
    # Changed files written after the run: their lines are numbered as the run saw them.
    newer: list[str] = field(default_factory=list)

    def share(self) -> str:
        return f"{100 * self.run / self.changed:.0f}%" if self.changed else "--"


def measure(change: dict[str, set[int]], data: Path | None = None, root: Path = ROOT) -> Measured:
    """Read a run's coverage data (``DATA``) against a change (``change_against``), with
    the project's coverage settings, from its root: the source and the omitted paths
    are named relative to it."""
    import coverage

    data = data or DATA
    if not data.exists():
        raise click.ClickException(
            f"no coverage data at {data}: `apothecary test all --coverage` writes it"
        )
    with contextlib.chdir(root):
        cov = coverage.Coverage(data_file=str(data), config_file=str(root / "pyproject.toml"))
        cov.load()
        omit = cov.config.run_omit or []
        # What the run's settings leave out stays out of the total, though a process
        # measured it.
        measured = Measured(total=cov.report(file=io.StringIO(), omit=omit))
        for path, lines in sorted(change.items()):
            where = (path, str(root / path))
            if not path.endswith(".py") or any(
                fnmatch.fnmatch(name, pattern) for name in where for pattern in omit
            ):
                continue
            if (root / path).stat().st_mtime > data.stat().st_mtime:
                measured.newer.append(path)
            _, statements, _, missing, _ = cov.analysis2(str(root / path))
            mine = lines & set(statements)
            unrun = sorted(mine & set(missing))
            measured.changed += len(mine)
            measured.run += len(mine) - len(unrun)
            if unrun:
                measured.missed[path] = unrun
    return measured


def said(measured: Measured, since: str) -> str:
    """The run's coverage, for the terminal."""
    lines = [
        f"coverage: {measured.total:.1f}% of the package's statements ran",
        f"  the change since {since}: {measured.run} of its {measured.changed} statements ran"
        f" ({measured.share()})",
    ]
    lines += [f"    not run: {path} {ranges(numbers)}" for path, numbers in measured.missed.items()]
    if measured.newer:
        lines.append(f"  changed since the run, so read as the run saw them: {', '.join(measured.newer)}")
    return "\n".join(lines)


def markdown(measured: Measured, since: str) -> str:
    """The same, as a line for a pull request's body."""
    text = (
        f"Coverage (`apothecary test all --coverage`): the package's statements, "
        f"{measured.total:.1f}%; the statements this pull request adds or changes since "
        f"`{since}`, {measured.run} of {measured.changed} ({measured.share()})."
    )
    if measured.missed:
        text += " Not run: " + "; ".join(
            f"`{path}` {ranges(numbers)}" for path, numbers in measured.missed.items()
        ) + "."
    if measured.newer:
        text += f" Changed since the run: {', '.join(f'`{path}`' for path in measured.newer)}."
    return text
