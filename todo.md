# TODO

Part readiness, bounds drift and contested values are computed, not listed
here: run `apothecary problems`.

## Open in this repository

- JSCAD: generated modules import `@jscad/modeling/src/*` deep paths.
  `node --check` passes, but no test loads a module against the package.
- Packaging: the wheel ships `apothecary/` only. `parts/` and `templates/` are
  not in it, so an installed wheel cannot render a part.
- The one-screen move, phases 4-5: [docs/plans/one-screen-2026-09-20.md](docs/plans/one-screen-2026-09-20.md).
- Optional local models behind the shape finder: [docs/plans/photo-finders-local-models-2026-09-21.md](docs/plans/photo-finders-local-models-2026-09-21.md).

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
