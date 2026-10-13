# TODO

Part readiness, bounds drift and contested values are computed, not listed
here: run `apothecary problems`.

## Open in this repository

- JSCAD: generated modules import `@jscad/modeling/src/*` deep paths.
  `node --check` passes, but no test loads a module against the package.
- Packaging: the wheel ships `apothecary/` only. `parts/` and `templates/` are
  not in it, so an installed wheel cannot render a part.
- Pictures in the world, what is open: Phase 7, the old photo routes closed,
  after gathering leaves core (*Next round*):
  [docs/plans/pictures-the-rest-2026-10-13.md](docs/plans/pictures-the-rest-2026-10-13.md).
- Optional local models behind the shape finder: [docs/plans/photo-finders-local-models-2026-09-21.md](docs/plans/photo-finders-local-models-2026-09-21.md).
- Pictures without Pillow, a research effort: whether a library under an approved licence decodes JPEG and PNG, resizes and reads pixels as well and as fast as Pillow does here, and what moving would cost. Until it reports, Pillow stays, a recorded exception in the adoption scope: [the governance plan's stub](docs/plans/governance-2026-10-13.md#stubbed-pictures-without-pillow).
- The installers' hardening. A download is checked against its listed size
  and published SHA-256; not checked are the GPG `.asc` signatures beside
  OpenSCAD's and arduino-cli's downloads, the macOS app's code signature and
  Team ID, Windows Authenticode on `openscad.exe`, and a source build's
  tarballs (codeload publishes no checksum). A source build takes no nested
  submodules and no `.1` second build of a night. Windows on ARM is refused:
  no ARM64 snapshot is published.

## Next round

Decided, not started. Each waits on what its line names.

- Photo gathering becomes an optional extra.
  `apothecary/gathering/` and its benches move behind
  `pip install apothecary[photos]` (`uv sync --extra photos` from a
  checkout), and `photo gather` names the extra when it is missing. How
  much of `apothecary/vision/` goes with it is settled then: the API's
  photo routes and `vocabulary/match.py` import from it.
  [Pictures in the world: what is open](docs/plans/pictures-the-rest-2026-10-13.md)
  proposes an answer for a person to take or leave. The
  camera routes (`/sites/{s}/cameras`) and Pillow stay in core, because the
  bench walkthrough and `apothecary docs generate` use them. Split `gather` into steps only after
  the move.
- `api.py` into routers, with a lock on the site store; first a pure move,
  then the behaviour changes.
- The viewer template's inline script into modules, with the ring's verbs
  declared once (`data-action`) and a test that holds them.
- One registry for firmware ports. It drives real heaters and motion, so it
  lands with a bench session on the Ender
  ([docs/bench-checklist.md](docs/bench-checklist.md)).
- Data-only part wrappers become `part.json`; the import hook goes; the
  snowplow gets one name.
- The unit suite under pytest-xdist.
- A licence gate for the Rust crates (the workspace's `Cargo.lock` and each Rust
  sketch's) and the vendored three.js and CodeMirror. `license-check.yml` gates
  Python packages alone; the rest is a recorded exception in the adoption scope
  ([the governance plan](docs/plans/governance-2026-10-13.md)). It ends, and the
  gate is built, at the first of: a second Rust sketch, a crate or a vendored
  library outside the allowlist, or the corpus's own gate for them.
- The hidden command stubs `apothecary/cli/retired.py` makes (`system`,
  `install`, `testrun`, `dev`, `inventory`, `submodules`, `photo look`,
  `test setup-e2e`, `test validate-e2e`, `test run-e2e`) are removed one
  release after they were hidden.

## For a person to do

- Run [the bench checklist](docs/bench-checklist.md) on the Ender and the
  ESP32: the governance records stand as written, confirmed by that run.
- Ratify the drafts proposed in qm#121 -- the firmware, G-code and slicer
  seams, one screen, rad host integration, personal data staying on the
  device, the adoption-scope amendment -- and move the `governance/qm` pin
  to them, the pin alone in its commit.
- Review rad#7 (a ring entered at an item); apothecary's ring follows what
  rad decides.
- Close or rebase the Dependabot bumps once the stack lands.
- Once qm#136 (durable text) is ratified and the pin carries
  `check_timeless.py`, run it in CI and `preflight` on the lines each change
  adds.

## For a person to decide

- Is the pictures plan's Phase 6, Selected tethered to the selection,
  dropped? Selected is in the one rail, and the page has no tether.
- May a made piece be saved as a variant? The draft record *Personal data
  stays on the device* (§6) says a made piece is saved, varied and committed
  as a part is; the page offers a made piece no Save, and shows its SCAD read
  only.

- What counts as "this machine": a home cluster, or the one machine? The draft
  record *Personal data stays on the device* says the one machine; storage,
  asking the video editor (alfred) for a frame, and any cluster deployment
  wait on its ratification.
- Is a person's one-time download of an openly licensed model the same class
  as the install-time fetches that record allows?
- When local-only makes something impossible: build it badly and say so, or
  do not build it?
- Should photo gathering guess before it is asked, or propose and wait? It
  guesses; a person's word wins over a guess.
- Where a person's answers about their photographs are kept, and when one
  expires: they live in the file handed to `--answers`.
- Are the questions `photo gather --ask` ranks first the ones worth a minute?
  Only a person with a real folder of photographs can check.
- Backups are the person's, not the program's; say so where the stays-local
  rule is stated.

## For governance/qm (file there)

- A run that goes green because tests were skipped reports success; nothing
  records what did not run.
- A green suite is not evidence until faults are injected and caught; no rule
  asks for it where a decision rests on a number.
- The plain-language proposal belongs there; its read-aloud check needs a
  second person. `git show 7c63846^:docs/plans/proposals/light-language.md`
  prints it.
- A check that asks for credit to an address no human reads recurs on every
  change until the check changes or an exception is written.
- No rule says what information may leave for a project that sends data.
- Proposing a decision to a project has no category in the rulebook's list.
