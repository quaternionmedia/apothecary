# Contributing

Read [AGENTS.md](AGENTS.md) first, person or agent: it holds the governance rules every
commit here follows, and the project's own commands.

## Set up

```bash
git clone --recurse-submodules https://github.com/quaternionmedia/apothecary.git
cd apothecary
uv sync
uv run playwright install chromium   # once per machine, for the browser tests
uv run apothecary openscad install   # an OpenSCAD with Manifold, for the renders
```

Rendering STLs needs OpenSCAD: `uv run apothecary openscad install` puts a development
snapshot with Manifold in the tools dir ([docs/openscad.md](docs/openscad.md) says what it
installs on each platform and which OpenSCAD a render uses). With the snapshot installed,
the `--slow` suite also renders the parts that need an OpenSCAD newer than 2021.01.
[Walkthrough page 00](walkthrough/00-getting-started.md) is the same path for a person
trying it, and names the optional installs: the slicer and each firmware toolchain.

## The loop

```bash
uv run apothecary test run                      # the ordinary command: unit tests and the walkthrough, whose demonstration drives Chromium
uv run apothecary test all                      # the same, then every browser test
uv run apothecary test all --workers 2 -k part  # the browser part on two workers; further arguments narrow both parts
uv run pytest                                   # the quick inner loop: unit tests and the walkthrough; browser tests skip
uv run pytest --slow                            # also full renders and accuracy benches
uv run pytest tests/e2e --start-server          # the browser tests, on a server of their own
uv run pytest tests/e2e --start-server -n auto --dist loadfile   # the same, a worker per core, files kept whole
uv run pytest tests/e2e --start-server --shard 2/3               # one CI shard: whole files, by tests/e2e/durations.json
uv run ruff check apothecary tests              # kept clean; format only the files you change
uv run --group preflight apothecary preflight   # the CI workflows, run here, before a push
```

`apothecary test run` is the one to run before a commit; it runs the window manager's
browser tests too, which start no server. Before a pull request is marked ready,
`apothecary test all` runs here, and its body says what ran and what it said: a pull
request's CI runs the governance checks and lint alone, and the tests run in CI at a version
tag. A browser test needs a server of its own (`--start-server`) or one named for it
(`--base-url`); with neither it skips, and it never uses a server that happens to be
listening. No limit is chosen by hand: in CI a browser test's cap is twice the time recorded
for it, so a hung wait fails that test and names it, and a job's is twice its recorded
median. Run here, nothing is capped.

`walkthrough/` is executable: its pages are doctests. Pages 01 and 02 are written by their
browser tests, and a loop's page (03, 04, 05, 06) by the browser suite alone; commit what a
run rewrites, and change their words in the test that writes them, not in the page.
[tests/e2e/README.md](tests/e2e/README.md) has the browser suite's flags and recorders, and
[walkthrough/15-preflight.md](walkthrough/15-preflight.md) says what `preflight` reproduces
and what it cannot.

### The Rust workspace

`Cargo.toml` at the root is a Cargo workspace of the crates under `crates/`: two stubs,
`apothecary-core` and `apothecary-service`, each with a README saying what it is for. No
Python suite builds them, CI does not, and the wheel carries neither. Check them locally
with `cargo check --workspace` when you change them. A Rust firmware sketch under `parts/`
is not a member: it is its own Cargo project, built by its own toolchain
(`apothecary firmware install --rust-esp32`).

## What CI gates

| Workflow | Fails on |
|---|---|
| `pytest.yml` | At a `v*` tag and on demand. On Python 3.11: a finding from `ruff check apothecary tests`; the walkthrough; the unit tests with `--slow`, rendering with a pinned OpenSCAD snapshot so the tests that need one run; the walkthrough and the unit tests again on the newest Python (3.14); the wheel failing to install and render a scene. In three more jobs, in parallel: the browser tests, a third each by recorded time (`--shard K/3`), and a walkthrough page they rewrote |
| `lint.yml` | On every pull request and a push to `main`: a finding from `ruff check apothecary tests`, at the version `uv.lock` pins |
| `reuse-lint.yml` | A file with no copyright or licence information (`reuse lint`) |
| `license-check.yml` | A third-party dependency whose licence is not on the OSI/FSF allowlist, or that has a known vulnerability (`pip-audit`) |
| `adr-lint.yml` | A record in `governance/qm/adr/`: a draft that narrates its own revisions, a numbered one not ratified, a ratified body edited outside its Amendments, or an index that disagrees with the directory |
| `submodule-check.yml` | A submodule pin its own remote does not have |
| `leak-check.yml` | On a pull request into `main` and a push to it: a tracked file naming an account's home folder, a path through one person's home layout or a session's scratch space, a shared-conversation link, or a conversation archive's path (the corpus's seed check, copied to `.github/qm-seed/`) |
| `one-pr-check.yml` | A pull request that is ready while its base is another open pull request's branch, and a pull request body that addresses its own contributor (the corpus's seed checks, run out of `governance/qm/project-seed/ci/`) |
| `integrates.yml` | A pull request whose head conflicts with the open pull requests merged before it, depth first from their base and oldest first on each, and every pull request stacked on it (`.github/ci/check_integrates.py`): it is fixed in its own branch before it merges |
| `timeless-check.yml` | On a pull request into `main` and a push to it: a line it adds that sets a phrase in capitals or only narrates how the text came to be, unless the line says `timeless: allow` and why (the corpus's seed check) |
| `tag-claims.yml` | A pushed `v*` tag that is lightweight, or whose annotation does not name the review, the manual test against the real runtime and what the automated gate did not cover (the corpus's seed check) |

Nothing else is a gate. Formatting is not checked in CI, and neither is the Rust workspace.
`docs-generate.yml` runs at a `v*` tag and on demand, and gates nothing: `apothecary docs
generate` runs the doc-capture tests, which nothing else runs, and keeps `docs/generated/`
as the run's artifact. A job's cap is twice its median over the runs GitHub records for it;
one with no record has GitHub's own. `tests/test_ci_workflows.py` holds what runs when.

## Commits and pull requests

The rules are in [AGENTS.md](AGENTS.md). In short:

- The subject is one plain sentence saying what is now true; the body says why, with
  evidence. `git log --oneline` shows the style.
- No `Co-Authored-By:` trailer, and no tool or model named as an author. A tool's part is
  disclosed in a `Tools:` line in the body.
- Work reaches `main` through a pull request from a branch.

## Numbers in prose

Prose never states a number a command computes; it names the command. The viewer's
controls: `apothecary census` ([docs/census.md](docs/census.md) says what it counts, and
what a change to the page keeps). What is open: `apothecary problems`. The tests:
`uv run pytest --co -q`. Only pages a run writes (walkthrough pages 01 to 06, and
`docs/generated/`) print such numbers.

## Words on the page

Every verb says in the status line what it did and what comes next, with the
ring address of the cell that does it ([docs/viewer.md](docs/viewer.md#the-header));
a message that ends a step names the next one.

## Where things go

- A part: [docs/parts-authoring.md](docs/parts-authoring.md).
- A scene primitive: `apothecary/primitives.py`, exported from `apothecary/__init__.py`,
  tested in `tests/test_primitives_transforms.py`, its JSON in
  [docs/scene-json.md](docs/scene-json.md).
- A sketch: beside the part it belongs to, `parts/<name>/<name>.ino` with an optional
  `firmware.json`, or a Cargo project whose `firmware.json` names its toolchain
  ([docs/firmware.md](docs/firmware.md#sketches-live-with-their-parts)).
- A toolchain module (a board family or a language): a subclass of `ToolchainModule` in a
  file of its own under `apothecary/firmware/modules/`, registered in `_registry` there,
  tested in `tests/test_firmware_modules.py`. The Bench, a board's Machine, the routes and
  the CLI draw it with no change of their own.
- A slicer module: a subclass of `SlicerModule` in a file of its own under
  `apothecary/slicer/modules/`, registered in `_registry` there
  ([docs/slicer.md](docs/slicer.md#another-slicer)), tested in `tests/test_slicer.py`.
- A decision: a `DRAFT-*.md` in `governance/qm/adr/`, following
  `governance/qm/adr/README.md`. A human ratifies it.
- A change a user would notice: one line in [CHANGELOG.md](CHANGELOG.md).
- A release: [walkthrough page 16](walkthrough/16-being-depended-on.md) says who pins
  this repository, what `apothecary release` checks, and the two acts that publish one,
  a merge to `main` and a tag.
- A plan: `docs/plans/<topic>-<date>.md`, dated, listed under *Plans* in
  [docs/README.md](docs/README.md). When its work is built it moves to that page's
  *History*, and each decision of it that is still true is stated where it lives: a
  guide in `docs/`, a governance record, or the code's own docstring.
