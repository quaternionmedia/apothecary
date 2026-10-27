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
- Pictures without Pillow, a research effort: whether a library under an approved licence decodes JPEG and PNG, resizes and reads pixels as well and as fast as Pillow does here, and what moving would cost. Until it reports, Pillow stays, a conflict row in the adoption scope: [the governance plan's stub](docs/plans/governance-2026-10-13.md#stubbed-pictures-without-pillow).
- The installers' hardening. A download is checked against its listed size
  and published SHA-256; not checked are the GPG `.asc` signatures beside
  OpenSCAD's and arduino-cli's downloads, the macOS app's code signature and
  Team ID, Windows Authenticode on `openscad.exe`, and a source build's
  tarballs (codeload publishes no checksum). A source build takes no nested
  submodules and no `.1` second build of a night. Windows on ARM is refused:
  no ARM64 snapshot is published.
- A host-side bound on where the print head ends. Each jog's move is capped
  (`JOG_MAX_MM`), jogs one after another add up, and the firmware's soft
  endstops, after a homing, are what keeps the head on the machine
  ([docs/firmware.md](docs/firmware.md)).
- Keyboard: the Contents tree's rows, carets and crumbs answer clicks alone.
  They are `li` and `span` elements with click listeners, and the canvas is
  the only element given a `tabindex`.
- The 2026-10-24 review's items not listed here
  ([docs/plans/review-2026-10-24.md](docs/plans/review-2026-10-24.md)): the
  four installers as one; the wrapper-import pattern; logging in place of
  `api.py`'s prints; the example modules at the package root; `httpx2` among
  the dev dependencies, and `pydantic_core` imported without being declared;
  a `docs/architecture.md`; the slowest browser file profiled, a marker on the
  order-dependent files, a JavaScript unit layer and the remaining
  `wait_for_timeout` calls.
- The landing method has no command. A stack tested once on the tree `main`
  ends at ([CONTRIBUTING.md](CONTRIBUTING.md)) is the
  [landing plan](docs/plans/landing-the-stack-2026-10-20.md)'s `git
  merge-tree` loop, run by hand; and `apothecary test all` runs the unit part,
  then the browser files in file order, where the longest browser files first,
  beside the unit part, is the order that shortens a landing run.
- Walkthrough pictures that move with no change to the page: a full browser
  run rewrites a few by a few pixels (the masked clocks' shade, the SCAD
  editor's sideways scroll in page 06's), so a run leaves the tree changed.
  Such a run's pictures are not committed.
- A browser shard in CI was cancelled at its job's limit on #85's and #89's
  pushes with no test named. The browser suite runs in CI at a version tag
  alone, and none has run since; there, each phase's bound names a test that
  hangs.

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
  Python packages alone; the rest is a conflict row in the adoption scope
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
- Land apothecary's records in qm, in this order: qm#171 into
  `project/apothecary`; then qm#121 (seven records) merges
  `project/apothecary` in, keeping its own ADR list; qm#145 (the records
  address the charter by name) takes #121's text where they conflict; then
  qm#172, qm#197 and qm#211. Ratify the drafts proposed in #121 -- the
  firmware, G-code and slicer seams, one screen, rad host integration,
  personal data staying on the device, the adoption-scope amendment -- and
  move the `governance/qm` pin to `project/apothecary`'s tip, the pin alone
  in its commit. Until then the pin is `baec440`, #211's head, which no other
  ref carries, so #211's branch stays.
- Propagate qm#226 (the seed's `AGENTS.md`, ADR index and editor settings
  read true in a project's copy) into `project/apothecary`: it is on qm's
  `main` and in no pin. Then copy the seed's `AGENTS.md` and `.vscode/`
  settings here again.
- Cut the first version tag. The browser suite, the Rust check, doc capture
  and the step-through tests run in CI there, and its run is the
  runtime-bound walkthrough pages' evidence (the walkthrough record's
  decision 7).
- Review rad#7 (a ring entered at an item); apothecary's ring follows what
  rad decides.

## For a person to decide

- Protect `main`? It has no protection: the checks a merge waits on, the
  whole suite before a merge and the bot gate ([CONTRIBUTING.md](CONTRIBUTING.md))
  hold by convention. A merge queue needs required checks.
- The review cycle proposed in
  [docs/plans/review-cycle-2026-10-24.md](docs/plans/review-cycle-2026-10-24.md):
  a merge queue tested once a batch, releases reviewed by area at a tag,
  shallow stacks, and the shared files split.
- The branches on origin: most of its heads are landed or closed, among them
  the eleven the [landing plan](docs/plans/landing-the-stack-2026-10-20.md)
  names under *After*. Delete them, or keep them.
- Serve the root README in the app? `/docs` and `/walkthrough` are served;
  the README, whose map a review walks, is not.
- README map rows for the features no browser test walks (the 2026-10-24
  review): add them, or leave the map to what the browser suite holds.
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
- qm#121's *Personal data stays on the device* does not name the console's
  receive-only UDP listeners (sACN on 5568, OSC on 8001), which
  `apothecary/stays_local.py` allows and [docs/lighting.md](docs/lighting.md)
  describes.
- The apothecary handoff's records chain (`handbook/handoffs/apothecary-merge-queue.md`,
  §3) leaves out qm#121 and qm#145, which land between #171 and #172
  (*For a person to do*, above).
- The site and structure record's *Pends on* says no production
  implementation of `Assembly` exists; the API, the firmware bindings and
  the gathering are built on it (`apothecary/hierarchy.py`, which calls
  itself a prototype too).
