# AGENTS.md

This project is governed by the Quaternion Media constitution, vendored at
`governance/qm` (a submodule pinned to this project's `project/<name>`
branch of that repo). If you are an AI coding agent opening this repo with
no other briefing, read this file fully before your first commit or edit.

## Before you do anything

1. Read `governance/qm/README.md` and `governance/qm/PRINCIPLES.md` in full
   — the namespaces/precedence rules and the charter. Both are short.
2. This project's own decision records live in `adr/`, as `ADR-NNNN`
   (numbered locally, at ratification) or `DRAFT-*.md` before ratification.
   A human ratifies; you draft.
3. **Human-only contributorship applies to every commit you make here** (see
   `governance/qm/records/DRAFT-human-only-contributorship.md`): do not add
   yourself, your model name, or any co-author trailer naming an unmonitored
   address (e.g. a vendor `noreply@` address) to any commit. If your default
   tooling normally appends a `Co-Authored-By:` trailer, suppress it for
   this repo. Tool involvement is disclosed as a `Tools:` note where the
   artifact calls for one, never as a byline.
4. Follow the drafting-session handoff contract in `adr/README.md` before
   writing or amending any record.
5. A QM record may be tightened by this project's own `adr/`, never
   relaxed — see `governance/qm/README.md`'s "Namespaces and precedence."

## One-time setup on a fresh clone (Windows)

`CLAUDE.md` and `.github/copilot-instructions.md` are real symlinks to this
file, not copies — POSIX checkouts resolve them with no setup. On Windows,
enable Developer Mode (Settings → For developers) and run `git config
core.symlinks true` once per clone, then `git checkout -- .` if the files
were already checked out before that. Skipping this doesn't break
anything — the files degrade to one-line pointers containing just the
target path — but it isn't the intended, tested experience; see the
IDE-integrated governance discovery record in `governance/qm/records/` for
what was actually verified.

<!-- Project-specific setup commands, test commands, and conventions belong
     below this line; this seed only carries the governance-discovery part. -->

## Apothecary-specific setup and commands

Apothecary is an OpenSCAD generation toolkit (Pydantic scene models → OpenSCAD/JSCAD)
plus a curated parts library, CLI, and FastAPI viewer. Python 3.11+, managed with `uv`.

The governance corpus is a submodule at `governance/qm`, and a plain clone
leaves it empty. `git clone --recurse-submodules`, or after the fact:

```bash
git submodule update --init    # governance/qm, or it is an empty directory
```

Without it every record this file cites is unreadable, the governance CI gates
fail for a reason that has nothing to do with your change, and an agent reads
this file's summary of the corpus instead of the corpus.

```bash
uv sync                        # install dependencies
uv run apothecary test all     # full test suite (unit + E2E)
uv run pytest -q               # unit tests only
uv run apothecary serve        # start the FastAPI viewer at :8000
uv run apothecary check        # verify install (incl. OpenSCAD availability)
```

Rendering STLs requires the `openscad` CLI on `PATH`; the E2E suite additionally
requires `playwright install` for browser binaries. See `README.md` and
`QUICKSTART.md` for the full command reference.
