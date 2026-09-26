# Contributing

Read [AGENTS.md](AGENTS.md) first, person or agent: it holds the governance rules every
commit here follows, and the project's own commands.

## Set up

```bash
git clone --recurse-submodules https://github.com/quaternionmedia/apothecary.git
cd apothecary
uv sync
uv run playwright install chromium   # once per machine, for the browser tests
```

Rendering STLs needs the `openscad` CLI on `PATH`.

## The loop

```bash
uv run pytest -q                                # unit tests and the walkthrough; browser tests skip
uv run pytest -q --slow                         # also full renders and accuracy benches
uv run pytest tests/e2e --start-server          # the browser tests, on a server of their own
uv run apothecary test all                      # unit and walkthrough, then the browser tests
uv run ruff check apothecary tests              # kept clean; format only the files you change
uv run --group preflight apothecary preflight   # the CI workflows, run here, before a push
```

`walkthrough/` is executable: its pages are doctests. Pages 11 and 12 are written by their
browser tests; commit what a run rewrites. [tests/e2e/README.md](tests/e2e/README.md) has
the browser suite's flags and recorders, and
[walkthrough/09-preflight.md](walkthrough/09-preflight.md) says what `preflight` reproduces
and what it cannot.

## What CI gates

| Workflow | Fails on |
|---|---|
| `pytest.yml` | The walkthrough; the unit tests with `--slow`; the browser tests; a walkthrough page the browser run rewrote; the wheel failing to install and render a scene |
| `reuse-lint.yml` | A file with no copyright or licence information (`reuse lint`) |
| `license-check.yml` | A third-party dependency whose licence is not on the OSI/FSF allowlist, or that has a known vulnerability (`pip-audit`) |
| `adr-lint.yml` | A record in `governance/qm/adr/`: a draft that narrates its own revisions, a numbered one not ratified, a ratified body edited outside its Amendments, or an index that disagrees with the directory |
| `submodule-check.yml` | A submodule pin its own remote does not have |

Nothing else is a gate. Ruff and formatting are not checked in CI.

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
`uv run pytest --co -q`. Only pages a run writes (walkthrough pages 11 and 12, and
`docs/generated/`) print such numbers.

## Where things go

- A part: [docs/parts-authoring.md](docs/parts-authoring.md).
- A scene primitive: `apothecary/primitives.py`, exported from `apothecary/__init__.py`,
  tested in `tests/test_primitives_transforms.py`, its JSON in
  [docs/scene-json.md](docs/scene-json.md).
- A decision: a `DRAFT-*.md` in `governance/qm/adr/`, following
  `governance/qm/adr/README.md`. A human ratifies it.
- A change a user would notice: one line in [CHANGELOG.md](CHANGELOG.md).
