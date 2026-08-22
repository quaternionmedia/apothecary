# Running the checks before pushing

**Hermetic.**

CI is not a barrier on this repository. `main` is unprotected, no ruleset is
applied, and the governance corpus says so about itself: *"every gate in this
repository is a signal to whoever merges rather than a barrier."* A signal only
works if somebody reads it before it costs a round trip, so read it here:

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

Each workflow gets its own invocation. That is not tidiness: the runner
executes every job in one environment where CI gives each job a fresh machine.
In the sibling project that difference was not theoretical — one workflow's
`uv sync --locked` stripped the tools a later workflow needed, and the
licensing gate failed for it while saying nothing about licensing.

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

`pytest.yml` installs OpenSCAD with `apt-get` and Playwright with
`--with-deps`. Both are Linux-only, so that gate cannot run on a Windows
machine — and saying so is only acceptable because something else here does
cover it:

    >>> from apothecary.preflight import LOCAL_DIFFERENCES
    >>> sorted(LOCAL_DIFFERENCES)
    ['pytest.yml']
    >>> "uv run pytest" in LOCAL_DIFFERENCES["pytest.yml"].covered_by
    True

That is the rule this module exists to hold. An excuse with no local equivalent
is a gap wearing a reason, and it is checked rather than trusted:

    >>> from apothecary.preflight import differences_are_current
    >>> differences_are_current()
    []

The same check catches the quieter failure: a workflow renamed or deleted while
its excuse stays behind, still describing a gate that no longer exists.

## A pass here is evidence, not proof

`uses:` steps are environment, not logic, and are not reproduced. The runner
image differs from this machine — which is the usual reason a locally green
step fails on a runner, and this repository has been caught by it more than
once: `npm ci` died in CI on a postinstall a local `npm install` had long since
cached, and seven tests read STLs that only existed here.

The command can also refuse to run at all, and that refusal is worth reading
rather than working around. The pinned governance runner invokes steps as bare
`bash`; on Windows that resolves through System32, where the WSL alias lives,
before PATH is consulted. The upstream fix passes an absolute POSIX shell and
is already on the corpus's `main`, but `governance/qm` here is pinned to
`project/apothecary`, which has not had a propagation merge since 2026-08-11.
Bumping that pin is a governance act — org ratifications reach a project by
merging `main` into its branch, and that merge commit is the pin bump.
