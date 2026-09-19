# Consolidation — landing the printer seam on the integration branch

**Stamped 2026-09-19.** apothecary at `b5a7dd5` on `feature/firmware-toolchain`
(four commits made today, none pushed); `origin/consolidate/2026-09-19` at
`3837828`; `origin/main` at `f1c1543`. Governance: this branch pins `a6c7afb`;
the integration branch pins `20e00bd`; the two new records sit on the qm
branch `adr/firmware-toolchain-seam` at `ce4e15f`, unpushed.

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
will refuse the merged viewer until thirty new controls are classified, and
the doctrine behind the census says the number should be going *down*. The
merge is a morning's work; the direction is a person's decision. Nothing here
pushes anything.

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
  and isort over 18 files) are in neither integration nor main. Cherry-pick
  both onto the integration branch **after** this merge; they touch the same
  files and would only add conflicts before it.
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

`test_the_page_has_thirty_three_controls_of_its_own` asserts 33, and
`census.take()` on the merged template refuses with **30 unclassified items**
(17 controls, 13 listeners): `uv run apothecary census` on the integration
branch with this branch's template in place. Run against
`templates/monitor.html.j2` (`uv run apothecary census --page
templates/monitor.html.j2`) it refuses with 34 more (24 and 10), on a page
the census does not read today.
The 30 on the viewer, by the names the census prints:

- controls: `devices-auto`, `devices-interval`, `serial-identify`,
  `serial-monitor`, `serial-query-row`, `serial-query`, `dev-watch`,
  `dev-poll`, `dev-unpin` (twice), `dev-rescan` (twice), `dev-manual`,
  `dev-pin-manual`, `dev-pick`, `dev-query`, `dev-pin`
- listeners: `autoEl:change`, `intervalEl:change`,
  `document:visibilitychange`, the delegated `click`/`keydown` handlers in
  `bindDeviceSection` and the overlay's `queryRow:submit`

Classifying them is mechanical — each is a `widget` with the effect it has —
and the count then reads about fifty. Do that, change the 33, and say in the
test's docstring that the meter went **up**, as `139c513` did when it moved
it from twenty to thirty-three. Do not reclassify anything to make the number
smaller; the number is the point.

Then, in this order, each with the suite green before the next:

1. `uv run pytest -q --ignore=tests/e2e` and `uv run pytest -q tests/e2e
   --start-server` on the merged tree. This is the first time the integration
   branch's firmware line runs on Linux at all: `139c513` was built on
   Windows, where the fake toolchain cannot exec. Expect surprises that have
   nothing to do with the merge.
2. `uv run apothecary docs generate` — both walkthroughs (`fractal-viewer`,
   `printer-monitor`) must pass under their own server.
3. Cherry-pick `fee2b11` then `062ab0c`; suite again.
4. Open a pull request from the integration branch to `main`. `pytest.yml`
   runs only on pushes to `main` and pull requests to it, so this is also the
   first CI run for everything on the integration branch.
5. Dependabot, one at a time, starlette last and alone.

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

- **Widgets against the ring.** The census exists to hold up the claim that
  the viewer's own controls fall to zero as a ring menu replaces them. Today's
  work adds seventeen to the viewer and a page of thirty-four beside it. Either
  the ring is meant to absorb device control too — then these are the next
  things it absorbs, and the census should read the monitor page as well — or
  a printer's controls are a different kind of surface, and the doctrine says
  so. Neither is a merge question.
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
