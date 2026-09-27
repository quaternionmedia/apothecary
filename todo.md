# TODO

Part readiness, bounds drift and contested values are computed, not listed
here: run `apothecary problems`.

## Open in this repository

- JSCAD: generated modules import `@jscad/modeling/src/*` deep paths.
  `node --check` passes, but no test loads a module against the package.
- Packaging: the wheel ships `apothecary/` only. `parts/` and `templates/` are
  not in it, so an installed wheel cannot render a part.
- The one-screen move, phases 4-5: [docs/plans/one-screen-2026-09-20.md](docs/plans/one-screen-2026-09-20.md).
- Designing a part from the browser, a spike with a recommended order: [docs/plans/part-editing-in-the-browser-2026-09-27.md](docs/plans/part-editing-in-the-browser-2026-09-27.md).
- Pictures, captures and found shapes in the world, the camera panel retired: [docs/plans/pictures-in-the-world-2026-09-26.md](docs/plans/pictures-in-the-world-2026-09-26.md).
- Optional local models behind the shape finder: [docs/plans/photo-finders-local-models-2026-09-21.md](docs/plans/photo-finders-local-models-2026-09-21.md).

## Next round

Decided, not started. Each waits on what its line names.

- Photo gathering becomes an optional extra (decided 2026-09-26).
  `apothecary/gathering/` and its benches move behind
  `pip install apothecary[photos]`, and `photo gather` names the extra when
  it is missing. An extra only adds dependencies, so gathering becomes a
  distribution of its own that the extra installs; `apothecary/vision/`
  stays in core. [The pictures plan](docs/plans/pictures-in-the-world-2026-09-26.md)
  says how, as its Phase 1, which lands with this round. The
  `/cameras` routes and Pillow stay in core, because the bench walkthrough and
  `apothecary docs generate` use them. Split `gather` into steps only after
  the move.
- `api.py` into routers, with a lock on the site store; first a pure move,
  then the behaviour changes.
- The viewer template's inline script into modules, with the ring's verbs
  declared once (`data-action`) and a test that holds them.
- One registry for firmware ports and a job object. It drives real heaters
  and motion, so it lands with a bench session on the Ender
  (`docs/validation/2026-09-20-ender-bench.md`).
- Data-only part wrappers become `part.json`; the import hook goes; the
  snowplow gets one name.
- The unit suite under pytest-xdist.
- The hidden command stubs (`system`, `install`, `testrun`, `dev`,
  `inventory`, `submodules`) are removed one release after they were hidden.

## For a person to decide

- What counts as "this machine": a home cluster, or the one machine? The draft
  record *Personal data stays on the device* says the one machine; storage,
  asking the video editor (alfred) for a frame, and any cluster deployment
  wait on its ratification.
- Is a person's one-time download of an openly licensed model the same class
  as the install-time fetches that record allows?
- When local-only makes something impossible: build it badly and say so, or
  do not build it?
- Should photo gathering guess before it is asked, or propose and wait? It
  guesses now; a person's word already wins.
- Where a person's answers about their photographs are kept, and when one
  expires: today they live in the file handed to `--answers`.
- Are the questions `photo gather --ask` ranks first the ones worth a minute?
  Only a person with a real folder of photographs can check.
- Backups are the person's, not the program's; say so where the stays-local
  rule is stated.

## For governance/qm (file there)

- A run that goes green because tests were skipped reports success; nothing
  records what did not run.
- A green suite is not evidence until faults are injected and caught; no rule
  asks for it where a decision rests on a number.
- The plain-language proposal (`docs/plans/proposals/light-language.md`, in
  git history) belongs there; its read-aloud check needs a second person.
- A check that asks for credit to an address no human reads recurs on every
  change until the check changes or an exception is written.
- No rule says what information may leave for a project that sends data.
- Proposing a decision to a project has no category in the rulebook's list.
