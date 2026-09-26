# Handoff — the picture path, and the seam under the ring

**Stamped 2026-08-30.** apothecary at `cba0209` on
`evolve/photo-shapes-and-light-language`, base `f1c1543`, **three commits, none
pushed**. Governance pinned at `20e00bd`. qm `origin/main` at `a5072a3`, with two
unpushed branches described below.

**Every figure on this page was true at those commits and nowhere else.**
Re-derive before quoting one; the command is beside each. The page this replaces
carried three different figures for one test suite, and none of them matched the
machine.

---

## The one-paragraph version

The picture path works and is demonstrated by one run that writes its own page.
The seam the ring will speak through exists and carries no traffic yet. Nothing
is pushed, nothing is ratified, and **governance adoption has not moved** — the
pin is 233 commits behind the corpus, three records sit `Proposed`, and no gate
has run against any of this work. The next agent's job is governance, and none of
it is blocked on the code.

## State

| | |
|---|---|
| apothecary | `cba0209`, tree clean apart from `.cache/`, **never pushed** |
| Base | `f1c1543` on `main` |
| Governance pin | `20e00bd`, this project's own branch tip |
| Behind the corpus | **233** — `git -C governance/qm rev-list --count origin/project/apothecary..origin/main` |
| Tests | **2 failed, 722 passed, 1 skipped** — see *Before your first command* |
| Records | three on qm `project/apothecary`, all `Proposed`, none numbered, none ratified |
| Tags | none. No release claim has been made about any of this |

**Two unpushed branches in qm** (`c:\Users\peter\repos\qm\qm`), neither checked
out anywhere — no worktree holds either, so both can be checked out directly:

- `adr/apothecary-what-v0-0-2-asserts` at `4973952`, based on
  `project/apothecary`. Two commits, `adr/` only. Adds
  `adr/DRAFT-what-v0-0-2-asserts.md` and one line to `adr/README.md`.
- `perspective/2026-08-30-a-guard-that-reads-prose` at `e154ff9`, based on
  `origin/main`. One commit, `perspectives/` only.

## Before your first command

A plain checkout cannot run its own tests, and the failures read like broken code
rather than missing setup.

    git submodule update --init --recursive
    uv sync

Then, with a server of its own:

    uv run apothecary test run --e2e

That command starts its own server and runs everything, including the
demonstration. To reproduce the figure above exactly, start a server yourself and
run the suite against it:

    mkdir -p /tmp/pics
    APOTHECARY_PICTURE_ROOT=/tmp/pics uv run apothecary serve --port 8765 &
    APOTHECARY_PICTURE_ROOT=/tmp/pics uv run pytest tests walkthrough -rs --doctest-glob='*.md'

**On Windows, set `PYTHONIOENCODING=utf-8`** or `apothecary serve` dies encoding a
tick mark on a cp1252 console. That is the console, not the code.

**Two failures are expected on Windows and are not yours.** Both are in
`tests/test_photo_in_the_viewer.py`: `os.mkfifo` does not exist on Windows, and a
symlink to `/etc/hostname` resolves to nothing so the server answers 404 where the
test expects 403. Confirmed by running that file alone. On Linux the suite should
be clean; if it is not, that is a finding.

**One skip, and it misreports itself.** `tests/test_cli_testing.py` skips saying
"Chromium not available" when the reason underneath is a Playwright
sync-API-inside-asyncio error. Chromium is available. The skip names the wrong
cause and is worth fixing.

## What exists

**The picture path.** A photograph becomes flat shapes, each matched to one of
five words, placed as an ordinary arrangement — sized if told how wide the
picture is, marked unsized rather than guessed if not. A folder of photographs is
sorted into what belongs with what, with the pairs it declines reported as
answers rather than gaps. It ranks the questions worth asking; a person answers
in plain sentences; their word wins outright, carries downstream, and scores the
machine. Two contradictory answers are refused rather than averaged.

**One demonstration, and it writes its own page.**
`tests/e2e/test_docs_photo_walkthrough.py` walks the whole chain — the model half
in-process, the viewer half in a real browser — and emits
`walkthrough/11-photographs-into-pieces.md` plus its screenshots. The ordinary
test command runs it, so the page is a record of a run rather than a description
beside one. **The page is output.** Editing it by hand is editing the output of a
program; the next run puts it back.

**The seam under the ring.** `apothecary/routes/menu.py`, the project's first
`APIRouter`: `POST /menu/resolve` returns the ring for what you are pointing at,
`POST /menu/intent` carries a chosen option out, says the viewer carries it, or
refuses. Migration step 1 of `docs/plans/edits/apothecary-surface.md`, which is
the step where nothing visible changes. The viewer does not call either route —
`grep -c 'menu/resolve' templates/fractal_viewer.html.j2` returns 0.

## What does not exist

The ring is not drawn — `grep -i ring` on the viewer's markup returns hits that
are all inside `stringify`, `toString`, `docstring`, `triggering`, `rendering`
and `coloring`. There is no `apothecary/links.py`, so arrangements cannot be
linked. Nothing survives a restart. No detector has been selected, and the
sorting's accuracy is measured only on pictures it drew itself. A printable model
needs `openscad` on `PATH`.

---

## For the agent applying governance

**None of this is blocked on the code.** In rough order of what unblocks the
most:

**1. Propagate.** 233 commits of corpus have not reached `project/apothecary`;
the pin is from 2026-08-12. The route is a `propagate/apothecary-<date>` pull
request from `main` into `project/apothecary`, merged and never rebased, because
this repository's submodule pins the tip. `project-seed/ci/check_pr_base.py`
refuses the wrong direction. **This is a person's to start** — say so rather than
starting it if that has not changed.

*One cost of the gap is now concrete:* another session holds an unmerged qm
branch renaming principles from `P6`-style numbers to slugs. This project's two
older records cite `P4`, `P5` and `P6`. If that lands, they cite identifiers the
corpus no longer uses.

**2. Close the `v0.0.1` floor, or say why not.** Two mechanical gaps, both from
`governance-status.yaml`: `one-pr-check.yml` is absent from this repository's
workflows, and its `adr-lint.yml` declares no `RECORDS_DIR`. Note that the
missing workflow is the gate enforcing the one-pull-request rule, and this
repository's slot is currently over. **The mechanical set never qualifies** — the
phase ladder's §6 — so closing both leaves `v0.0.1` still needing a human who has
reviewed and tested it. Nobody has.

**3. Free the pull request slot.** `uv run qm slot --repo quaternionmedia/apothecary`
reports two human pull requests open, `#13` (draft, 2026-08-09) and `#18`
(ready, 2026-08-20), both the reviewer's. One survives; the rest are closed or
folded. **Folding is a git operation with an order to it: close the pull request
first, then push its commits onto the branch that survives.** Pushing first
merges it, with no review and no way to undo the record. This is a decision for
the person, not a task.

**4. Three obligations are undischarged**, of the eight
`project-seed/adr/README.md` creates: service inventory, control-plane instance
record, risk register. Verified against `adr/DRAFT-constitution-adoption-scope.md`
on `project/apothecary` — it has no service inventory, no quarterly upstream scan,
and the word "risk" does not appear in it. All three are made more material by
the feature line: a detector reached over a network is a §6 service, and provider
abandonment is a risk with nowhere to be written down.

**5. The `v0.0.2` record is drafted and waiting.**
`adr/DRAFT-what-v0-0-2-asserts.md` on `adr/apothecary-what-v0-0-2-asserts`. It
defines the rung as one path end to end with a single demonstration as its
evidence. Its §1 and §2 hold today; §3, §4 and §5 do not. **It is `Proposed` and
pends on rad's core-extraction decision** — `rad/adr/DRAFT-rad-core-extraction.md`
is itself `Proposed`, pending a human decision. An assistant drafts; a person
ratifies.

## What is blocked, and on whom

| Blocked | On |
|---|---|
| Pushing anything | A person. Nothing here has been pushed, deliberately |
| Ratifying any record | A person, and a second code owner that does not exist |
| The `v0.0.2` rung's §5 | rad's core-extraction decision, which is a person's |
| Which pull request survives in apothecary | A person. Do not close either on your own judgment |
| Propagation | Org-side, a person's |

## Standing constraints

- **Keep everything local.** The unpushed state is deliberate, not an oversight.
- **Do not add a co-author trailer naming an address no human reads**, and check
  the committer as well as the author. `git config user.email` for this clone is
  already the reviewer's.
- **Do not ratify anything.**
- **Do not put a model, a service, or a network call anywhere in
  `apothecary/gathering/`, `vision/` or `vocabulary/`.** Four tests refuse it.
- **Do not hand-edit `walkthrough/11-photographs-into-pieces.md`.** It is output.

## What could not be verified here

- **Everything green on this page is this project's own suite on one Windows
  machine.** No organisation-side gate has run against any of it, because nothing
  is pushed. Whether the two Windows failures vanish on Linux is inference.
- **`check_pr_base.py` could not run at all.** It resolves both refs through
  `origin`, and neither branch is pushed. That is a step this machine cannot
  reproduce rather than a step that passed.
- The screenshots under `walkthrough/screenshots/` are binary and will differ on
  every run. The page's prose and figures do not: generated twice, `diff` says
  identical.

## What is dirty, and why it was left

`.cache/` is untracked and was left alone. It holds two things: the runtime STL
cache the API writes (`_NODE_STL_CACHE_DIR`), and `.cache/apothecaryhandoff20260828.tar.gz`
with its extracted `export/`, which is the archive this session was picked up
from. It is not ignored, so it shows in every `git status` here and has done
since before this session. Ignoring it would also hide the archive, which is why
it was not done rather than an oversight.
