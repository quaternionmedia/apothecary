# Running the checks before pushing

**Hermetic.**

CI runs the workflows after a push, and what they say is a signal to whoever
merges. `preflight` runs them here first, so it is read before it costs a
round trip:

```
uv run --group preflight apothecary preflight
```

The group has to be named on the command that runs. `uv run` re-syncs the
environment and drops it, so `uv sync --group preflight` beforehand is undone
by the very next `uv run`.

## What it does

It delegates to the governance corpus's own runner, out of the submodule,
rather than restating what the workflows do. A second list of "what CI runs" is
a list that drifts, and the point is to find out what the runner will say —
which a paraphrase cannot tell you.

Each workflow gets its own invocation, because the runner executes every job
in one environment where CI gives each job a fresh machine: in one environment,
one workflow's `uv sync --locked` would strip the tools a later workflow
needs, and that workflow would fail for a reason that is not its own.

It also runs against a scratch environment it owns, under `.preflight/`. The
workflows install their own tools, and `actions/setup-python` is an environment
step nothing reproduces, so `python -m pip install ...` goes wherever `python`
points — which on a developer box is the system interpreter.

## Every workflow is classified

A gate quietly dropped from a local run is how "it passed locally" stops
meaning anything, so nothing is allowed to fall between the two lists:

    >>> from apothecary.preflight import WORKFLOWS, partition
    >>> runnable, set_aside = partition()
    >>> {p.name for p in WORKFLOWS.glob("*.yml")} == set(runnable) | set(set_aside)
    True

Nothing here uses a matrix, which the runner cannot evaluate, so nothing is set
aside before it runs:

    >>> set_aside
    []

## An excuse must name what covers it

`pytest.yml` installs OpenSCAD with `apt-get` when the machine has none, and
Chromium's system libraries with `--with-deps` on a runner. Both are
Linux-only, so that gate cannot run on a Windows machine — and saying so is only acceptable because something else here does
cover it:

    >>> from apothecary.preflight import LOCAL_DIFFERENCES
    >>> sorted(LOCAL_DIFFERENCES)
    ['one-pr-check.yml', 'pytest.yml']
    >>> "uv run pytest" in LOCAL_DIFFERENCES["pytest.yml"].covered_by
    True

`one-pr-check.yml` reads a pull request's body in its second step, and a local
run has none; the body is checked by the same script before it is posted:

    >>> "check_pr_voice.py" in LOCAL_DIFFERENCES["one-pr-check.yml"].covered_by
    True

That is the rule `apothecary/preflight.py` holds. An excuse with no local
equivalent is a gap, so each is checked rather than trusted:

    >>> from apothecary.preflight import differences_are_current
    >>> differences_are_current()
    []

It also reports an excuse naming a workflow that is not there, renamed or
deleted.

## A pass here is evidence, not proof

`uses:` steps are environment, not logic, and are not reproduced. The runner
image is not this machine either: a tool, a cache or a file this machine has
and a fresh runner does not (an STL rendered here, a package cached) passes a
step here that fails there.

On Windows the command can refuse to run, and the refusal is worth reading
rather than working around. A runner without the corpus's `resolve_bash`
invokes steps as bare `bash`, which Windows resolves through System32, where
the WSL alias lives, before PATH is consulted. `preflight` looks for
`resolve_bash` in the pinned runner (`governance/qm`, on `project/apothecary`)
and, where it is missing and the bare name does not run, refuses and names the
gates to run directly. The fix is on the corpus's `main`. Bumping the pin is a
governance act: org ratifications reach a project by merging `main` into its
branch, and that merge commit is the pin bump.
