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
snapshot with Manifold in the tools dir (on Linux x86_64, macOS and Windows x64 the
published build; on Linux arm64 a build from source; README.md says what each does), or
the `openscad` CLI on `PATH` is used. With the snapshot installed, the `--slow` suite also
renders the parts that need an OpenSCAD newer than 2021.01.
[Walkthrough page 00](walkthrough/00-getting-started.md) is the same path for a person
trying it, and names the optional installs: the slicer and each firmware toolchain.

## The loop

```bash
uv run apothecary test run                      # the ordinary command: unit tests and the walkthrough, whose demonstration drives Chromium
uv run apothecary test all                      # the same, then every browser test
uv run pytest -q                                # the quick inner loop: unit tests and the walkthrough; browser tests skip
uv run pytest -q --slow                         # also full renders and accuracy benches
uv run pytest tests/e2e --start-server          # the browser tests, on a server of their own
uv run pytest tests/e2e --start-server -n auto --dist loadfile   # the same, a worker per core, files kept whole
uv run pytest tests/e2e --start-server --shard 2/3               # one CI shard: whole files, by tests/e2e/durations.json
uv run ruff check apothecary tests              # kept clean; format only the files you change
uv run --group preflight apothecary preflight   # the CI workflows, run here, before a push
```

`apothecary test run` is the one to run before a commit. A browser test needs a server of
its own (`--start-server`) or one named for it (`--base-url`); with neither it skips, and it
never uses a server that happens to be listening.

`walkthrough/` is executable: its pages are doctests. Pages 11 and 12 are written by their
browser tests, and a loop's page (13, 14, 15, 16) by the browser suite alone; commit what a
run rewrites, and change their words in the test that writes them, not in the page.
[tests/e2e/README.md](tests/e2e/README.md) has the browser suite's flags and recorders, and
[walkthrough/09-preflight.md](walkthrough/09-preflight.md) says what `preflight` reproduces
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
| `pytest.yml` | On Python 3.11: a finding from `ruff check apothecary tests`; the walkthrough; the unit tests with `--slow`; the wheel failing to install and render a scene. In three more jobs, in parallel: the browser tests, a third each by recorded time (`--shard K/3`), and a walkthrough page they rewrote |
| `reuse-lint.yml` | A file with no copyright or licence information (`reuse lint`) |
| `license-check.yml` | A third-party dependency whose licence is not on the OSI/FSF allowlist, or that has a known vulnerability (`pip-audit`) |
| `adr-lint.yml` | A record in `governance/qm/adr/`: a draft that narrates its own revisions, a numbered one not ratified, a ratified body edited outside its Amendments, or an index that disagrees with the directory |
| `submodule-check.yml` | A submodule pin its own remote does not have |

Nothing else is a gate. Formatting is not checked in CI, and neither is the Rust workspace.

## Commits and pull requests

The rules are in [AGENTS.md](AGENTS.md). In short:

- The subject is one plain sentence saying what is now true; the body says why, with
  evidence. `git log --oneline` shows the style.
- No `Co-Authored-By:` trailer, and no tool or model named as an author. A tool's part is
  disclosed in a `Tools:` line in the body.
- Work reaches `main` through a pull request from a branch.

## Numbers in prose

Prose never states a number a command computes; it names the command. The viewer's
controls: `apothecary census`. What is open: `apothecary problems`. The tests:
`uv run pytest --co -q`. Only pages a run writes (walkthrough pages 11 to 16, and
`docs/generated/`) print such numbers.

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
