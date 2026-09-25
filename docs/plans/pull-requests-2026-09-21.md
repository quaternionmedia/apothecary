# The pull requests, ready to open

*Written 2026-09-21 at the tip of `consolidate/2026-09-19`, before this
machine had a credential; every gate the two repositories run was run here
first, and the descriptions were written to be pasted. Later that day, with
`gh` signed in: both branches pushed, apothecary #21's title and description
replaced with the text below (through the REST API; `gh pr edit` trips on
the repository's classic-projects field), and qm **#121** opened as a draft
against `project/apothecary`, assigned, no review requested; its base check
is pasted in. The commands stay here for the next time. The consolidation plan
([consolidation-2026-09-19.md](consolidation-2026-09-19.md)) says why the
branches are shaped as they are; the queue
([queue-2026-09-20.md](queue-2026-09-20.md)) says what is left.*

## The commands

```bash
# 1. apothecary: the integration branch updates #21 (consolidate/2026-09-19 → main)
cd ~/Documents/apothecary
git log --oneline origin/consolidate/2026-09-19..HEAD | wc -l   # 31
git push origin consolidate/2026-09-19
# then replace #21's description with the text under "apothecary #21" below

# 2. qm: the records, as a DRAFT pull request against project/apothecary -- never main
cd governance/qm
git push -u origin adr/firmware-toolchain-seam
python project-seed/ci/check_pr_base.py --base origin/project/apothecary --head adr/firmware-toolchain-seam
#   paste that output into the description, under "Base check"
gh pr create --draft --base project/apothecary --head adr/firmware-toolchain-seam \
   --title "Six records for apothecary: the toolchain and printer seams, the rings, one screen, and personal data staying on the device" \
   --body-file <the text under "qm draft pull request" below> --assignee @me
# no review request: draft is the state, and leaving it is the reviewer's call after their own testing
```

The parent's submodule pin stays at `20e00bd` on purpose: bumping it carries
unrelated governance changes and reopens the adoption record; it is bumped
in a commit of its own once the qm pull request merges.

Commits on `#21` so far are GPG-signed; the 31 here are not (no key on this
machine). Either sign them on the way out --
`git rebase --exec 'git commit --amend --no-edit -S' 3837828` -- or say in
the description that the tail is unsigned, as the text below does.

## What was run before writing this

Every step the two repositories' workflows run, executed locally on the tip
(`cc46e86`):

| Gate | Command | Result |
|---|---|---|
| `pytest.yml` | `uv run pytest walkthrough -q` | 10 passed |
| `pytest.yml` | `uv run apothecary test all` | 1159 unit + 71 browser = 1230 passed, 0 failed (the server fenced on temporary state and pictures, as the suite now does) |
| `reuse-lint.yml` | `uv run --with "reuse[charset-normalizer]" python -m reuse lint` | compliant, 368/368 |
| `license-check.yml` | the workflow's `pip-licenses --allow-only` string, verbatim | exit 0; the one new dependency on the branch is `pyserial` (BSD-3-Clause) |
| `adr-lint.yml` | the workflow's grep over `governance/qm/adr/DRAFT-*.md` | clean; and qm's own `adr_lint.py --records-dir adr --index adr/README.md`: clean |
| `submodule-check.yml` | the pin `20e00bd` is on `origin/project/apothecary` | yes (`git merge-base --is-ancestor`) |
| qm `reuse-lint.yml` | `reuse lint` in `governance/qm` on the branch | compliant, 122/122 |
| qm `check_pr_base.py` | needs the branch on origin | run it after the push (command above) |

## apothecary #21 -- `consolidate/2026-09-19 → main`

*Replace the description with this.*

---

**What this branch is.** The integration branch for everything since
`3837828`: the printer seam landed on the bench, the world made the one
screen with the monitor and the camera in front of it, personal data held on
the device by the program's shape, and the bench drawn as the machines and
boards it holds. 31 commits past what `#21` last saw; each one's message
says what it did and why. The two lint commits (`fee2b11`, `062ab0c`) are
kept out, as this description decided: lint is not a gate here.

**The census, on this tip.** The viewer: **137 controls of its own, 65 of
them on the ring** (`apothecary census`). The monitor: 64 / 41. The firmware
page: 30 / 4, no ring yet. One meter for the three screens: **169 / 69**
(`tests/test_census.py`). Page 11 of the walkthrough was written by its own
run on this tip and says 137.

**What is in it, by capability**

1. *A G-code printer is monitored, not programmed.* `apothecary firmware
   printer` and the `/firmware/printers/*` routes identify a Marlin board
   (`M115`), poll temperatures, position, endstops and SD progress over a
   held link, run allowlisted queries, and drive the printer's scene node
   from the board pinned inside it. Latched control (heaters, jog, home, SD,
   mesh; `M112` always), bed leveling read and probed as records with a
   heatmap and a relief drawn on the bed in the world, and printing without
   an SD card (a kept file streamed one line per `ok`, checked first, a
   safe-off on any failure). Transport is an engine slot: pyserial, termios,
   or an in-process simulated printer for demos and browser tests. Bench
   validation against a real Ender board found three defects the simulator
   could not (DTR dropped on close, pins by port name, the board view's
   frame), fixed with tests; the arm-side checks are a checklist for a
   person (`docs/validation/2026-09-20-ender-bench.md`).
2. *The ring addresses nine cells.* Every device and control verb sits on a
   numeric keypad with a stable address (`⌗2728` is Device › Control › Jog ›
   Y+ from a printer's node); the ring navigates the tree; the census reads
   both pages and says what the ring already backs.
3. *One screen.* The fractal viewer is the app: an anchor layer fixes HTML to
   points in the scene (a badge above every connected board), a printer's
   marks (nozzle, bed plane, bed relief) live at its node, the side column
   became a rail of panels (close, collapse, float, drag, dock, resize, hide
   on tilde, move sides), and the monitor's whole body is a module the world
   mounts in a popup tethered to the printer. The docs are served with the
   viewer (`/docs`, `/walkthrough`) and regenerated on start.
4. *The photo workflow from the browser.* A Camera & pictures panel: the
   browser's cameras listed and shown live, a frame kept on this machine,
   looked at and opened as an arrangement, a camera placed at a piece and
   drawn there for every browser, pictures gathered with the machine's
   questions answered by button. The camera's first sanity check is to
   record its own surroundings.
5. *Personal data stays on the device, by construction.*
   `apothecary/stays_local.py`, installed when the package is imported: the
   process cannot connect, bind, send or resolve past loopback (port 53 on
   loopback included); one tool fetch with one caller; every `--host`
   through `require_loopback`; an ASGI middleware that answers only a
   request whose client, bound address, `Host` and sender are all this
   machine; a Content-Security-Policy on every response; Swagger and ReDoc
   off; nothing reaching a page raw; arduino-cli given a managed config
   (its cloud board lookup and update check off) and a scrubbed environment;
   the picture root never the home folder. Two fan-outs of skeptics tried to
   break it without editing a file; what they found is closed and what is
   left is in the record's risk register. The named eventual exception is
   *secured user accounts*: a future record, not a setting.
6. *Geometry made elsewhere, and the bench drawn as it is.* `apothecary
   parts import` brings an STL or OBJ in as a part with its provenance;
   a `part.json` beside a SCAD is a wrapper; `Import` carries transforms and
   measures its file; the garage's printers are Ender 3s from published
   dimensions (PSU offset right, spool over the top bar, the Creality V4.2.2
   in the electronics box) and the boards are the boards (Uno, Pi 4, Teensy
   4.0, ESP32-DevKitC), each described by a sidecar; `build_origin` puts a
   machine's bed where it is.
7. *A plan for a model behind the shape finder*
   (`docs/plans/photo-finders-local-models-2026-09-21.md`): the seam, what a
   model adds, the plugin shape, what is lawful under the rules, candidates
   with licences checked, phases, and what it pends on. Nothing of it built.

**Tests and docs.** 1166 unit tests, 73 browser tests, 10 walkthrough pages
run as doctests -- all green on this tip with `apothecary test all` and
`pytest walkthrough`. Every capability has its page under `docs/`
(`firmware.md`, `geometry-from-elsewhere.md`, the plans, the validation
record) and its walkthrough page written by a test run; the walkthrough's
pages 11 and 12 are runs, not descriptions. `CHANGELOG.md` carries one
entry per capability.

**Governance.** Six records are drafted on qm's `adr/firmware-toolchain-seam`
(a draft pull request against `project/apothecary`): the firmware toolchain
seam, the G-code printer seam, the rad host integration, one screen, and
personal data staying on the device. The submodule pin is unchanged
(`20e00bd`); it is bumped in a commit of its own once that merges. No
`Co-Authored-By` trailers; tool use is a `Tools:` line in each commit body.

**What is deliberately not here.** The lint commits; a dependabot bump
(after this merges, one at a time, starlette last); the submodule bump; the
one-screen phases 4 and 5; the hot-versus-cold bed reading chart; phase 0 of
the finder plan. All in `docs/plans/queue-2026-09-20.md`.

**Signing.** The 31 commits past `3837828` are unsigned: no key on the
machine that made them.

---

## qm draft pull request -- `adr/firmware-toolchain-seam → project/apothecary`

*The body. Open as a draft, assign the person who asked for the work, request
no review.*

---

Six draft records for apothecary, one decision each, on the project's own
branch (`project/apothecary`), never `main`. Each is Status Draft with its
`Pends on` row where an input is not settled; numbers are assigned at
ratification, by a human. Lint is clean (`project-seed/ci/adr_lint.py
--records-dir adr --index adr/README.md`), and `adr/README.md`'s in-flight
list names all six.

| Record | The decision |
|---|---|
| Firmware toolchain seam | arduino-cli and esptool are engines behind a subprocess seam, never linked; an installer that fetches one release archive with a checksum; a port rule scoped to what a port name may be |
| G-code printer seam | a printer running Marlin (or another G-code firmware) is monitored over the line protocol through a transport engine slot; the port is held, reset only on request; queries are allowlisted; its first and sixth decisions read the bed and stream a print |
| rad host integration for apothecary | the rings address nine cells, as rad's record says; options seated cardinals first, cell 5 backs out, digits are addresses |
| One screen | the world is the one screen; the other two stand in front of it as anchors, popups and panels, in six phases with the census as the meter |
| Personal data stays on the device, by construction | the guard on the process, one tool fetch with one caller, a server that answers this machine alone, pages fenced to their origin, subprocesses told where to fetch, what is kept kept here, tests holding every door, and the named exception -- secured user accounts -- as a future record; with the service inventory and risk register the open-license record asks for |

What these do not decide: which detector the photo path selects (a later
record, per `detector-selection.md`); the secured-user-accounts exception
itself (its own record, when wanted).

**Base check.** *(paste the output of
`python project-seed/ci/check_pr_base.py --base origin/project/apothecary --head adr/firmware-toolchain-seam` here after the push)*

**Workflows run locally** (`project-seed/ci/run_workflows_locally.py --event
pull_request --base-ref project/apothecary`): the record lint passes for
`records/` and for this branch's `adr/`; symlink integrity passes; REUSE is
compliant (122/122, run with `reuse` installed by hand since the venv has no
pip). The steps that could not run here: the one-PR slot check (needs a
token), the base check (needs the branch on origin -- above), the CI-tooling
tests (need `gh`), and the governance-status render (the document is behind
`origin/main` on every project, not only this one).

No `Co-Authored-By` trailers; each commit carries a `Tools:` line.

---
