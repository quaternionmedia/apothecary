# Consolidation — landing the printer seam on the integration branch

**Stamped 2026-09-19.** apothecary on the local branch `consolidate/2026-09-19`:
`origin/consolidate/2026-09-19` at `3837828`, plus the five commits made today
on `feature/firmware-toolchain` (tip `b6f9701`), merged as `90161e7`, plus the
ring and the census that follow it; none pushed. `origin/main` at `f1c1543`.
Governance: the merged tree pins qm at `20e00bd`; the records sit on the qm
branch `adr/firmware-toolchain-seam`, unpushed.

**Every figure on this page was true at those commits and nowhere else.**
Re-derive before quoting one; the command is beside each.

---

## The one-paragraph version

Two lines of work exist. This branch holds the printer seam: a Marlin board
is monitored, drives its node in the viewer, and has a monitor page of its
own. The integration branch `consolidate/2026-09-19` already holds this
branch's older commits merged together with the photo work, the wider
viewer, and a census that counts the viewer's controls and refuses to count
one nobody has classified. Merging the two is small in git terms — nine files
conflict, none by more than sixty lines — and large in one other: the census
refused the merged viewer until thirty new controls were classified, and
the doctrine behind the census says the number should be going *down*. The
classification is done and the ring is built; the census now says how many
of the page's controls the ring backs, and the direction -- delete them --
is written down below. Nothing here pushes anything.

## Where the lines are

| Line | Tip | Holds | Command |
|---|---|---|---|
| `feature/firmware-toolchain` (this branch) | `b5a7dd5` | 10 commits past main: the toolchain seam, the snowplow, and today's four — bindings groundwork, the G-code printer seam, the viewer and monitor pages, the docs | `git rev-list --count origin/main..HEAD` → 10 |
| `origin/consolidate/2026-09-19` | `3837828` | everything on this branch as of `3d8ac0d`, merged with `evolve/photo-shapes-and-light-language`, `prototype/site-structure-hierarchy`, one commit re-applying the wider viewer, and `139c513` "Make the three lines agree" | `git rev-list --count HEAD..origin/consolidate/2026-09-19` → 40; `git rev-list --count origin/consolidate/2026-09-19..HEAD` → 4 |
| `origin/main` | `f1c1543` | nothing the other two lack | `git rev-list --count origin/consolidate/2026-09-19..origin/main` → 0 |

Branches not in the integration branch, and what to do with them:

- `origin/feature/fractal-viewer-scale-and-overlays` — its viewer commit
  lives on in `3837828` under a different patch id; its two lint commits
  (`fee2b11`: ruff B904/B011 fixes, deletes the inert `playwright.config.py`,
  moves ruff's `select`/`ignore` under `[tool.ruff.lint]`; `062ab0c`: black
  and isort over 18 files) are in neither integration nor main, **and stay
  out**: #21's description decides that lint is not a gate and that a
  tree-wide reformat belongs in a commit that says so. They are a pull
  request of their own after #21 merges, or never.
  `git cherry origin/consolidate/2026-09-19 origin/feature/fractal-viewer-scale-and-overlays`
- `origin/feature/datum-scaffold`, `origin/governance/license-and-reuse`,
  `origin/governance/submodule-check` — already in main by content (`git
  cherry origin/main <branch>` prints only `-`). Delete after a look.
- `origin/gridfinity`, `origin/uv-rework`,
  `origin/governance/adopt-license-and-datum-scaffold` — ancestors of main
  (`git merge-base --is-ancestor origin/<branch> origin/main`). Delete.
- `origin/prototype/site-structure-hierarchy`,
  `origin/evolve/photo-shapes-and-light-language`,
  `origin/feature/rc-snowplow-docs-cleanup`, and this branch — contained in
  the integration branch; delete once it lands.
- Five `dependabot/uv/*` branches (anyio, idna, pytest, starlette, urllib3),
  all against `054b05e`, none satisfied by any `uv.lock` in play. Each
  rewrites `uv.lock`, which today's work also touches (pyserial). Land them
  after the merge and a fresh `uv lock`; land the starlette bump alone with
  the full suite — it is a major (0.49 → 1.3) and drags fastapi
  0.121 → 0.141 under the 479 tests this branch collects (`uv run pytest
  --collect-only --ignore=tests/e2e` → 441; `tests/e2e` → 38).

## The order of operations

Merge **this branch into the integration branch**, not the other way. The
integration branch is the line that already resolved three merges and holds
the census; this branch is four commits of new work with one clean base. The
same conflicts arise in either direction; resolving them on the integration
branch keeps its history the one that says what was decided.

    git checkout -b consolidate/2026-09-19 origin/consolidate/2026-09-19
    git merge --no-ff feature/firmware-toolchain

Nine files conflict, sized from `git merge-tree --write-tree
origin/consolidate/2026-09-19 b5a7dd5` and reading the result:

| File | Hunks / lines | Resolution |
|---|---|---|
| `apothecary/cli/docs.py` | 1 / 9 | the doc server's env: keep the integration branch's picture-root variable **and** this branch's `_simulated_device_env` (scripted ports, simulated printer, temp state dir) |
| `apothecary/cli/parts.py` | 1 / 7 | take the integration branch's `_generate` signature (`param_pairs`, `openscad_path`); keep this branch's validated-params path beneath it |
| `pyproject.toml` | 1 / 4 | keep both dependencies (pillow there, pyserial here), then `uv lock` |
| `templates/fractal_viewer.html.j2` | 2 / 20 | both hunks are in the toolbar: their detail-mode / overlay toggles and this branch's `↻ Devices` toggle, interval select and `🖨 Monitor` link. Keep all; keep their `id="firmware-link"` and give the Monitor link an id of its own — the census keys on ids |
| `tests/conftest.py` | 2 / 18 | take their structure (`pytest_addoption` lives here now; it imports `firmware_fakes`); keep this branch's `_isolate_firmware_state`, which also resets `devices._SCAN` and `devices._LAST_STATUS` — without those two lines the 2 s port-scan cache leaks across tests |
| `tests/e2e/conftest.py` | 2 / 63 | keep their walkthrough fixture and their removal of `pytest_addoption`; add this branch's `sys.path.insert` for `tests/` |
| `tests/test_firmware_{api,devices,seam}.py` | 1–2 / 1–4 | import name only, see the next point |

Two helper modules do one job: their `tests/firmware_fakes.py`
(`FAKE_ARDUINO_CLI`, `_isolate_firmware_state`, `fake_cli_calls`; imported by
four files) and this branch's `tests/firmware_helpers.py` (`FAKE_ARDUINO_CLI`,
`write_fake_arduino_cli`, `fake_cli_calls`; imported by eleven, including
`apothecary/cli/docs.py` and the printer e2e tests). Keep **`firmware_helpers.py`**
— fewer import sites to change — and move `_isolate_firmware_state` into it;
delete `firmware_fakes.py`; point the four imports at the survivor.

Then the gate that will actually fail:

    uv run pytest -q tests/test_census.py

**Resolved on the integration branch, 2026-09-19.** The gate no longer
fails; what it says has changed. The merged viewer had thirty unclassified
items and the monitor page thirty-four, and the direction this consolidation
takes -- asked for as "evolve the rad menu and roll every control up to the
numpad protocol", where the first draft of this plan left it open below --
is that the ring absorbs device control too. So the ring was built (`apothecary/static/ring.js`,
`POST /menu/resolve` returning each option with its cell, the Device and
Control rings in `apothecary/menu.py`) and the census grew a second concept
to measure it against:

- **Ring-backed.** `census.RING_BACKED` names, for a control of its own, the
  ring action that does the same thing. `Found.ring_action` carries it,
  `Census.ring_backed()` counts it, and the sentence reads *N controls of
  its own, M of them also on the ring*. The meter is still N; M is the part
  of N that can go.
- **The viewer:** 54 controls of its own, 15 of them also on the ring
  (`test_the_page_has_fifty_four_controls_of_its_own`, whose docstring
  accounts for the twenty-one added since thirty-three). The rise is larger
  than the thirty the refusal named because the census also stopped hiding
  things: a submit button is now named by its form rather than counted as
  the job form's, and an anchor with a class is the thing its class says
  rather than the recipe download, which surfaced the Device section's two
  links and the serial log's send button.
- **The monitor page**, `census.MONITOR`, counted the same way and never
  added to the viewer's: 51 controls of its own, 28 of them also on the
  ring. The control overlay's buttons carry their G-code line rather than a
  name, so the census names them by that (`cmd:G28`, `jog:Y+`); the "24
  controls" the refusal named were the ones it could see. Every button that
  acts on the machine or its link has a cell (the link verbs under a Link
  cell that keeps its number on a devkit and a printer; the motor verbs
  sharing one); the page's plumbing -- port, interval, the log's tick-boxes,
  the download -- is the part with no cell, and is said so.
- **The ring** is one control on each page (`ring-open`, filed under
  `ring`); its own listeners live in the module and a test holds the module
  to the three ways in (`m`, right-click, the button).
- Every ring-backed action is checked against `apothecary.menu`: it must be
  one `carried_by` knows and one some ring actually offers.

`uv run pytest -q tests/test_census.py` is 35 passed on the merged tree.
The number went up and the docstring says so, as `139c513` did; nothing was
reclassified to make it smaller.

Then, in this order, each with the suite green before the next:

1. `uv run pytest -q --ignore=tests/e2e` and `uv run pytest -q tests/e2e
   --start-server` on the merged tree. This is the first time the integration
   branch's firmware line runs on Linux at all: `139c513` was built on
   Windows, where the fake toolchain cannot exec. Expect surprises that have
   nothing to do with the merge.
2. `uv run apothecary docs generate` — both walkthroughs (`fractal-viewer`,
   `printer-monitor`) must pass under their own server.
3. Push. The pull request to `main` already exists (#21, below); the push
   updates it, and `pytest.yml` runs only on pushes to `main` and pull
   requests to it, so #21's checks are the first CI run for everything on
   the integration branch. Re-run datum's enclosure gate on the final tip
   and tell datum where to pin.
4. Dependabot, one at a time, starlette last and alone, after #21 merges.

## The pull requests, and datum

Read from the GitHub API on 2026-09-19 (`curl -s
https://api.github.com/repos/quaternionmedia/<repo>/pulls?state=open`); no
credential on this machine, so nothing below was changed, only read.

**apothecary #21 — `consolidate/2026-09-19 → main`, ready, green.** Seven
checks pass on `3837828`: the test suite, `reuse`, `license-check`,
`adr-lint`, `check-submodule-refs` (twice), GitGuardian. This is the
integration branch this plan lands on, so "open a pull request to main" is
already done: **pushing this branch updates #21**, and every commit here has
to keep those seven green. What #21's description decides, this plan keeps:

- *The two lint commits stay out.* #21 says lint is not a gate, the tree
  carries 217 ruff findings of its own, and a tree-wide reformat belongs in a
  commit that says so. So `fee2b11` and `062ab0c` are **not** cherry-picked
  here; they are a pull request of their own after #21 merges, or never.
- *The census meter is stated in the PR and on page 11 of the walkthrough.*
  #21 reads 33. This branch moves it and the ring appears, so the description
  needs a paragraph for the printer seam and the ring with the new reading,
  and page 11 (`walkthrough/11-photographs-into-pieces.md`, written by
  `tests/e2e/test_docs_photo_walkthrough.py` when it runs) must be
  regenerated by that run on this tip, not edited.
- *Commits on #21 are GPG-signed.* Today's local commits are not (`git log
  --format='%h %G?' 3837828..HEAD` shows `N`); no key is configured here.
  Sign them on the way out — `git rebase --exec 'git commit --amend --no-edit
  -S' 3837828` — or say in the description that the tail is unsigned.
- `reuse lint` is compliant with the new files (`uv run --with reuse reuse
  lint` → 327/327); `REUSE.toml`'s `**` annotation covers them.

**apothecary #14, #15, #16, #17, #19 — dependabot, all `→ main`.** Unchanged
from the order above: after #21 merges and `uv lock` runs on main, one at a
time, starlette (#15, a major) last and alone. Merging any of them into #21
would only add a `uv.lock` conflict to a pull request that is clean.

**datum #2 — `wp3-firmware → main`, ready, 34 commits.** datum's enclosure
lives here and nowhere else; its `schema/src/datum/apothecary.py` pins
`APOTHECARY_PIN = "3837828"`, `APOTHECARY_PARTS = ("datum_core",)`, and its
`.github/workflows/enclosure.yml` clones this repository at that pin and runs
`apothecary parts verify` on each part. Its description says plainly that the
job cannot pass until #21 lands, and that its pin moves to #21's tip. Two
consequences for this plan:

- Every commit this branch adds moves #21's tip, so datum's pin moves again.
  Pin it once, to the commit #21 merges as — the merge commit on `main`, or
  the branch tip if #21 is merged fast-forward — not to each intermediate tip.
  `datum apothecary --check` is the gate that arms itself once apothecary
  publishes a release; until then a bare commit is what it accepts.
- The gate itself passes on this tree: `uv run apothecary parts verify
  datum_core` → `x 46.80 y 46.80 z 15.60, 0 drifted`, the figure #21 quotes.
  Re-run it on the final tip before telling datum where to pin.

datum's governance pin is qm `project/datum`; nothing here touches it.

**qm — no open pull requests.** The two records on `adr/firmware-toolchain-seam`
(`ce4e15f`) become one, as a draft against `project/apothecary`, once pushed.

**rad #2 — dependabot, playwright bump.** Irrelevant to apothecary, except
that the conformance edit proposed in
[`edits/rad-nine-cells-conformance.md`](edits/rad-nine-cells-conformance.md)
should branch from `main` after it, not before, to keep its own diff to the
vectors.

### Text for #21's description, once this tip is pushed

> **The printer seam, the Device panel, the monitor, and the ring.** A
> Marlin mainboard is monitored rather than programmed: identified by
> `M115`, polled over a link the server holds open, reset only on request,
> and pinned to the `mainboard` node inside a garage printer, whose status
> follows the board. A focused monitor page carries the port's comms log,
> a temperature history and a latched control overlay; two allowlists keep
> a person's own G-code to report-only queries and, once armed, bounded
> operator controls. The ring appears: right-click, `m` or ⌗ Ring open the
> node, canvas or device ring; every option has a keypad cell and every
> intent an address, per rad's *The menu addresses nine cells*. The census
> classifies the new controls and reads **N of its own, M of them also on
> the ring** (was 33), and page 11 was regenerated by its run on this tree.
> datum's pin moves to the commit this merges as.

(Replace N and M with the figures `uv run apothecary census` prints on the
final tip.)

## The governance side

- This branch pins `governance/qm` at `a6c7afb`; the integration branch at
  `20e00bd`, which is origin's `project/apothecary` tip and contains
  `a6c7afb`. The merge takes the pointer to `20e00bd`; that is correct, and
  the submodule check passes because it is reachable on origin.
- The two records (the firmware toolchain seam, revised; the G-code printer
  seam, new) are one commit on the qm branch `adr/firmware-toolchain-seam`
  (`ce4e15f`, on top of `20e00bd`). Its lint is clean:
  `python project-seed/ci/adr_lint.py --records-dir adr --index adr/README.md --base-ref origin/project/apothecary`.
  Push that branch and open a **draft** pull request with base
  `project/apothecary` — never `main`; the corpus's own `AGENTS.md` says why,
  and `check_pr_base.py` refuses the wrong direction. Once merged there, bump
  the submodule pointer in apothecary in a commit of its own.
- The corpus's `main` is far ahead of `project/apothecary` (347 commits past
  `a6c7afb`, 233 past `20e00bd`: `git -C governance/qm rev-list --count
  20e00bd..origin/main`), and
  the adoption record is still `Proposed`. `docs/plans/HANDOFF.md` and
  `GOVERNANCE-REFRESH.md` on the integration branch already carry that work;
  this plan does not duplicate it.

## For a person to decide

- **Widgets against the ring -- decided, and now measured.** The ring absorbs
  device control: the Device and Control rings exist, the census reads the
  monitor page as well, and the census reports how many of each page's
  controls the ring already backs (15 of 54 on the viewer, 28 of 51 on the
  monitor). What remains for a person is the deletions -- each ring-backed
  button that goes takes the meter down by one -- and whether the page's
  plumbing (port, interval, the log's tick-boxes) belongs on a ring at all
  or is the doctrine's "list beside the scene". The adoption
  itself is the draft *rad host integration for apothecary* in
  `governance/qm/adr/`, which pends on rad's own nine-cells record.
- **A page that can heat and move a machine.** The control latch, the
  bounded allowlist and the localhost binding are the safety argument, written
  in the G-code record and `docs/firmware.md`. The HIL review
  (`docs/plans/HIL-REVIEW.md`) should read that argument as it reads the
  photo path's, and the reviewer should try to break it.
- **The record's `Pends on`.** Both firmware records pend on the adoption
  record; ratifying that is the human step everything else waits behind.
- **Which branches to delete**, from the list above — a look before each.

## What is not in this plan

Pushing anything (this machine has no credentials for it). Ratifying any
record. The ring menu's design. The dependabot merges themselves — only their
order. The Windows run: the firmware tests' fake toolchain is a shebang script
and stays CI-only there.
