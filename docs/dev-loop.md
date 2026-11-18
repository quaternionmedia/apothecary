# The dev loop

A change goes round five steps: change, see, test, commit, integrate. Each has a
command. [Walkthrough page 00](../walkthrough/00-getting-started.md) is the first
run from a fresh clone; [CONTRIBUTING.md](../CONTRIBUTING.md) holds the rules
behind each step and what CI gates; [AGENTS.md](../AGENTS.md) holds the governance
every commit follows.

## Once, on a fresh clone

```bash
git clone --recurse-submodules https://github.com/quaternionmedia/apothecary.git
cd apothecary
uv sync                              # the locked environment, the dev tools included
uv run apothecary check              # what is installed here, and the next step
uv run apothecary openscad install   # an OpenSCAD with Manifold, for the renders
uv run playwright install chromium   # the browser the tests drive
```

A clone made without `--recurse-submodules` has an empty `governance/qm`: run
`git submodule update --init --recursive`.

## Seeing a change

```bash
uv run apothecary serve --reload     # or --simulated, for a bench with nothing real on it
```

`serve` prints where it answers: the viewer, the docs, the API, and this page.

| A change to | Shows after |
|---|---|
| `apothecary/static/`, the page's scripts and styles | A browser reload: the server serves them as they are |
| The package's Python | A restart: under `--reload`, each saved `.py` file under `apothecary/` or `templates/` restarts the server; a file anywhere else in the checkout, another worktree inside it or a cache under `.cache/` included, does not |
| A part's SCAD | Its next build: `apothecary parts generate-stl <name>` builds an STL older than its SCAD again |
| `docs/` or `walkthrough/` | A browser reload of the page under `/docs` or `/walkthrough`, rendered as it is asked for |
| `uv.lock` or `pyproject.toml` | `uv sync`, then a restart: `--reload` does not see a new package |

## Two loops at once

The viewer's server listens on 6283, tau: each server of the estate sits on a
mathematical constant of its own, and 8000 is the port anything else grabs. A
second checkout or worktree runs its own server beside the first on another port:

```bash
uv run apothecary serve --port 6284
APOTHECARY_PORT=6284 uv run apothecary serve   # the same, for every command in that shell
```

`APOTHECARY_PORT` is read by every command that starts the server or talks to a
running one: `serve`, `photo view` and `photo gather --view`, `slicer slice` for a
site's piece, and `lighting simulate`. The tests use neither: each browser test
starts a server of its own on a free port, and so does `apothecary docs generate`.
Each worktree has its own `.venv`; run `uv sync` in it once.

## Testing

```bash
uv run apothecary test changed       # the loop, before each commit: the walkthrough, the unit groups and browser areas the change reaches, less what is unchanged since it passed
uv run apothecary test group NAME    # one unit group (tests/groups.py); no name lists them
uv run apothecary test run           # the ordinary command: the unit tests and the walkthrough
uv run apothecary test all           # before a merge, once, on the stack's head: every browser test too
uv run ruff check apothecary tests   # kept clean; format only the files the change touches
```

`test changed` is the loop and is never the gate. It leaves out a unit file, or the
walkthrough, unchanged since a run in which it passed, and says so on lines of their
own (`not run: unchanged since green at` a time); `--even-unchanged` runs them too, and
[CONTRIBUTING.md](../CONTRIBUTING.md#the-loop) says what unchanged is. `test run`,
`test changed` and `test group` run the unit part on a core fewer than the machine has;
`--workers 1` runs it in one process. The gate is `test all` on the head of the stack
being pulled, which carries every level beneath it
([CONTRIBUTING.md](../CONTRIBUTING.md#the-loop),
[the integration checklist](integration-checklist.md)). Every test has a time
bound, here as in CI, so a hang ends with its stack written.

### The gate keeps one process

`test run`, `test changed` and `test group` run the unit part on workers; `test all` runs
it in one process. A test can pass in a worker that never ran what leaves state behind it,
and fail in the one process that did: a module registered at the import of another, a
universe a walkthrough page already built. The whole suite in one process, in file order,
is the run that finds those, and it is the gate's. Measured on a four-core machine, both ways, the unit part
alone (`walkthrough` and `tests`, the browser tests left out), alternating, on a machine
shared with other test runs:

| Run | One process | Three workers |
|---|---|---|
| 1 | 698 s (load 5.9 to 8.1) | 350 s (load 8.1 to 13.4), 2 failed |
| 2 | 722 s (load 13.4 to 8.9) | 405 s (load 8.9 to 11.9), 2 failed |
| 3 | 634 s (load 11.9 to 9.7) | 283 s (load 9.7 to 10.5) |

Each time is the wall time, with the one-minute load when the run began and ended. The
load moved between 6 and 13 throughout, other test runs sharing the four cores, so the
numbers say two to one and no more. In two of the three runs the workers also failed two
tests that passed in one process (two experiments of `tests/test_loop_tuning.py`, then one
of them and one of `tests/test_family_procedures.py`): timing tests that a loaded machine
holds to their bound, so a red parallel run is read before it is
believed.

Whether only the one process finds the order faults was tried on a copy of the tree with
the fixes of the two recent ones taken out: the one process failed
`tests/test_loop_tuning.py` (one run of one), the workers did in one of two runs, and
neither failed `tests/test_jobs.py` for the registration order. So the evidence for the
one process is thin and is not more than the two faults found by it; what it costs is
about four minutes of a gate that runs the browser suite after it for more than half an
hour, once per stack. `test all --workers N` runs both parts on workers when that time is
wanted more than that evidence.

## Committing

One branch per change, off `main`. A commit subject is one plain sentence saying
what is now true (`git log --oneline` shows the style); the body says why, with
evidence, and ends with a `Tools:` line when a tool took part. No co-author trailer
names an address nobody reads.

## Integrating

### What others pushed, into a checkout

```bash
git switch main && git pull          # on a branch instead: git fetch && git merge origin/main
uv sync                              # the lock as it is now
git submodule update --init          # governance/qm at its pin
uv run apothecary check              # a tool a new part or loop needs
uv run apothecary test run           # what moved under the change
```

Then start `serve` again: a new package or a moved pin is read only as it starts.

### A change, into main

A change reaches `main` as a pull request, or as a stack of them pulled from its
head. [The integration checklist](integration-checklist.md) is the path, box by
box: the tree that will land, the suite once on it, the pictures and the docs,
preflight, the pull requests and the landing.
