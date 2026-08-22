"""`apothecary preflight`: run the CI gates here, before pushing.

CI is not a barrier on this repository -- `main` is unprotected and no ruleset
is applied, so every check is a signal to whoever merges rather than a gate
that stops them. A signal only works if somebody reads it before it costs a
round trip.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import click

from ..preflight import LOCAL_DIFFERENCES, partition

SUBMODULE_MISSING = """
The governance submodule is not checked out, so its workflow runner is
not here:
    git submodule update --init --recursive"""

PYYAML_MISSING = """
The runner needs pyyaml, and the workflows install their own tools with
pip:
    uv run --group preflight apothecary preflight
`uv run` re-syncs the environment and drops the group, so naming it on a
sync beforehand is undone by the very next `uv run`."""


@click.command(context_settings={"ignore_unknown_options": True})
@click.argument("passthrough", nargs=-1, type=click.UNPROCESSED)
def preflight(passthrough: tuple[str, ...]) -> None:
    """Run this repository's CI workflows locally, before pushing.

    Delegates to the governance corpus's own runner rather than restating what
    the workflows do. A second list of "what CI runs" is a list that drifts.

        apothecary preflight                        # a pull request into main
        apothecary preflight --event push --ref main

    A pass here is evidence, not proof. `uses:` steps and the runner image are
    not reproduced, and this machine carries tools a fresh runner does not --
    which is how a green local suite hid a CI failure here more than once.
    `walkthrough/09-preflight.md` has the detail.
    """
    root = Path(__file__).resolve()
    runner = repo = None
    for parent in root.parents:
        seed = parent / "governance" / "qm" / "project-seed" / "ci" / "run_workflows_locally.py"
        if seed.exists():
            runner, repo = seed, parent
            break

    if runner is None:
        raise click.ClickException(SUBMODULE_MISSING)

    try:
        import yaml  # noqa: F401
    except ImportError:
        raise click.ClickException(PYYAML_MISSING) from None

    # Refuse to report gates red for a reason that is not about the gates. Five
    # failing workflows all saying the same thing about a shell is noise that
    # trains a reader to stop looking.
    if not _runner_can_run_steps(runner):
        raise click.ClickException(STALE_RUNNER)

    # The workflows install their own tools, and `actions/setup-python` is an
    # environment step nothing reproduces -- so `python -m pip install ...`
    # goes wherever `python` points, which on a developer box is the system
    # interpreter. `uv sync --locked` is the same hazard aimed at .venv: it
    # strips whatever the lockfile does not name. So preflight runs against a
    # scratch environment it owns, and nothing it does reaches the interpreter
    # you work in.
    scratch = repo / ".preflight" / "venv"
    bin_dir = scratch / ("Scripts" if os.name == "nt" else "bin")

    def ensure_scratch() -> None:
        if not bin_dir.exists():
            click.echo(f"Creating the preflight environment in {scratch} ...")
            # --seed: the workflows call `python -m pip`, and a bare uv venv
            # has no pip at all.
            subprocess.check_call(["uv", "venv", "--seed", str(scratch)])
        # reuse-lint.yml installs plain `reuse`, which imports libmagic at
        # start-up and dies before it lints anything on a box with no `file`
        # command. Re-seeded every pass, because a previous workflow's
        # `uv sync --locked` strips it back out.
        subprocess.check_call(
            [
                "uv",
                "pip",
                "install",
                "--quiet",
                "--python",
                str(scratch),
                "reuse[charset-normalizer]",
            ]
        )

    env = dict(os.environ)
    env["UV_PROJECT_ENVIRONMENT"] = str(scratch)
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    env["VIRTUAL_ENV"] = str(scratch)

    # An explicit --workflows means the caller has said what to execute.
    if any(a.startswith("--workflows") for a in passthrough):
        ensure_scratch()
        sys.exit(subprocess.call([sys.executable, str(runner), *passthrough], cwd=repo, env=env))

    # Otherwise one invocation per workflow. The runner executes every job in a
    # single environment; CI gives each job a fresh machine. That difference is
    # not cosmetic -- in the sibling project, one workflow's `uv sync --locked`
    # stripped the tools a later workflow needed, and its licensing gate failed
    # for it while saying nothing about licensing.
    source = repo / ".github" / "workflows"
    staged_root = repo / ".preflight" / "workflows"
    if staged_root.exists():
        shutil.rmtree(staged_root)

    names, set_aside = partition(source)
    runnable = []
    for name in names:
        staged = staged_root / Path(name).stem
        staged.mkdir(parents=True)
        shutil.copy2(source / name, staged / name)
        runnable.append((name, staged))

    if set_aside:
        click.echo("Not run here. CI still runs them:")
        for name in set_aside:
            _report(name)
        click.echo("")

    failed = []
    for name, staged in runnable:
        ensure_scratch()
        code = subprocess.call(
            [sys.executable, str(runner), *passthrough, "--workflows", str(staged)],
            cwd=repo,
            env=env,
        )
        if code != 0:
            failed.append(name)

    click.echo("")
    click.echo("=" * 60)
    if failed:
        click.echo(f"{len(failed)} workflow(s) reported a failure: {', '.join(failed)}")
        click.echo("")
        click.echo("A local failure is a question: a defect, or a difference between")
        click.echo("this machine and the runner. These are recorded as the second:")
        for name in failed:
            _report(name)
        sys.exit(1)

    click.echo(f"{len(runnable)} workflow(s) passed locally.")
    if set_aside:
        click.echo(f"{len(set_aside)} not run here, named above. A skip is not a pass.")


STALE_RUNNER = """
The pinned governance runner cannot run a workflow step on this machine.

It invokes steps as bare `bash`, and Windows resolves that through
System32 -- where the WSL App Execution Alias lives -- before it ever
looks at PATH. With no WSL distribution installed the alias reports the
step's script as a path that does not exist, backslashes stripped, and
every step fails for a reason that names neither the step nor the shell.
No PATH change fixes it: System32 is searched first.

This is fixed upstream. `resolve_bash` passes an absolute POSIX bash, and
it is on the corpus's `main` and in the sibling project's pin already.
`governance/qm` here is pinned to `project/apothecary`, which has not had
a propagation merge since 2026-08-11 and predates the fix.

Bumping that pin is a governance act, not this command's: org ratifications
reach a project by merging `main` into its branch, and that merge commit is
the pin bump.

Until then, the gates still run here directly:
    uv run pytest                       the suite and the walkthrough
    uv run pytest tests/e2e --start-server
    uv run --with "reuse[charset-normalizer]" reuse lint
"""


def _runner_can_run_steps(runner: Path) -> bool:
    """Whether the pinned runner can actually spawn a shell here.

    Cheap and specific: the fix is a named function, and its absence only
    matters on Windows, where the bare name resolves to something that is not
    a POSIX shell. Probing rather than assuming, because a machine with no WSL
    alias would be fine either way.
    """
    if "def resolve_bash" in runner.read_text(encoding="utf-8"):
        return True
    if os.name != "nt":
        return True

    with tempfile.NamedTemporaryFile(
        "w", suffix=".sh", delete=False, newline="\n", encoding="utf-8"
    ) as fh:
        fh.write("exit 0\n")
        probe = fh.name
    try:
        return subprocess.run(["bash", "-e", probe], capture_output=True).returncode == 0
    except OSError:
        return False
    finally:
        os.unlink(probe)


def _report(name: str) -> None:
    """Name a gate that did not run here, and what covers it instead.

    A workflow with no recorded difference is the interesting case: nothing
    explains why it failed, so the answer is a defect until someone shows
    otherwise.
    """
    difference = LOCAL_DIFFERENCES.get(name)
    if difference is None:
        click.echo(f"  {name} -- NOT a recorded difference. Read it as a defect.")
        return
    click.echo(f"  {name} -- {difference.why}")
    click.echo(f"      covered here by: {difference.covered_by}")
