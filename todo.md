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
- Image models as an optional source of measurements, through qmcp over MCP and only when a person asks: quantity, size, shape, material, colour, a label, a cover and a match in another camera's picture, as observations in the family's format beside the plain readers' and never over a person's word, with qmcp's own slice (MCP on its server, the vision tools, the weights fetched from a pinned list) in its repository: [docs/plans/image-models-through-qmcp-2026-10-30.md](docs/plans/image-models-through-qmcp-2026-10-30.md). A prototype of the journeys against a simulated qmcp is built (the Models window); [docs/models-checklist.md](docs/models-checklist.md) is what a person validates by hand.
- The Models window, what its walk left ([docs/models-checklist.md](docs/models-checklist.md)): opened again after a reload, it takes room from the world each time, until windows beside the world share one stack; a person's word is kept by Models in memory, where the Working space should keep it and Models offer it; and the status bar keeps "choose a shape … first" in red after a shape is chosen, until the next action.
- A synth rig photographed through a concert, held in carlos: the first real photographs, the Ender's mainboard's power and USB through the camera aimed at the Ender, waiting for that camera (slice 4, rehearsed on an Uno's drawn pictures: `examples/rigs/uno-power-and-usb.json`, `apothecary rig setup`), then the DFAM and Subharmonicon, then the viewer's window for pinning faces, cues in the record, a mount and corner tabs printed; then the airgap's test rig and a server room: [docs/plans/carlos-concert-rig-2026-10-29.md](docs/plans/carlos-concert-rig-2026-10-29.md).
- The viewer across the efforts in flight, one observation module first, then the words and seats: [docs/plans/ui-coordination-2026-10-31.md](docs/plans/ui-coordination-2026-10-31.md).
- Waiting behind it, the bench as a rig carlos draws, slices 2 and 3 (a picture names a device, IO configuration): [docs/plans/qm-family-carlos-2026-10-29.md](docs/plans/qm-family-carlos-2026-10-29.md).
- A working space seen from every kind of evidence at once: its cameras, one thing from several angles among them, a printer's polls and a board's port, its sensors, a person's goals, directives and actions, and the image models' guesses, each line of the view opening its evidence. First the Ender's three cameras, on the bed for its timelapse, on the head and across the room, tied to its polls (frames kept with polls, then its lead, its motion and its bed seen two ways), then the rig through a concert, the airgap's test rig and a server room. Its first two steps are built and walked from each door in [walkthrough 18](walkthrough/18-the-working-space.md); the next is the Ender's cameras at the bench: [docs/plans/working-space-view-2026-10-30.md](docs/plans/working-space-view-2026-10-30.md).
- Pictures lists every frame the Working space keeps with a poll as one of its camera's pictures, so a print fills it: those frames belong to the Working space, and Pictures would count them rather than tile them.
- Pictures without Pillow, a research effort: whether a library under an approved licence decodes JPEG and PNG, resizes and reads pixels as well and as fast as Pillow does here, and what moving would cost. Until it reports, Pillow stays, a conflict row in the adoption scope: [the governance plan's stub](docs/plans/governance-2026-10-13.md#stubbed-pictures-without-pillow).
- The installers' hardening. A download is checked against its listed size
  and published SHA-256; not checked are the GPG `.asc` signatures beside
  OpenSCAD's and arduino-cli's downloads, the macOS app's code signature and
  Team ID, Windows Authenticode on `openscad.exe`, and a source build's
  tarballs (codeload publishes no checksum). A source build takes no nested
  submodules and no `.1` second build of a night. Windows on ARM is refused:
  no ARM64 snapshot is published.
- `parts/footpedal/footpedal.ino` would not build on a real board: `pushbutton` is
  never declared, and `ledpin` is pin 6, which `b5` reads too. It prints no
  `apothecary footpedal: hello`, since its serial line carries Hairless MIDI, so
  the made thing's Query hears its hello only from the demo's scripted monitor.
- A host-side bound on where the print head ends. Each jog's move is capped
  (`JOG_MAX_MM`), jogs one after another add up, and the firmware's soft
  endstops, after a homing, are what keeps the head on the machine
  ([docs/firmware.md](docs/firmware.md)).
- Keyboard: the Contents tree's rows, carets and crumbs answer clicks alone.
  They are `li` and `span` elements with click listeners, and the canvas is
  the only element given a `tabindex`.
- The 2026-10-24 review's items not listed here
  ([docs/plans/review-2026-10-24.md](docs/plans/review-2026-10-24.md)): the
  four installers as one; the wrapper-import pattern; the example modules at
  the package root; a `docs/architecture.md`; the slowest browser file
  profiled, a marker on the order-dependent files, a JavaScript unit layer and the remaining
  `wait_for_timeout` calls.
- Starlette's test client warns that `httpx` is deprecated in favour of
  `httpx2` (seen at `conftest.py`'s import of `starlette.testclient`) once
  `httpx2` is not installed: move the test client to `httpx2`, or filter the
  warning where it is raised.
- The landing method has no command. A stack tested once on the tree `main`
  ends at ([CONTRIBUTING.md](CONTRIBUTING.md)) is the
  [landing plan](docs/plans/landing-the-stack-2026-10-20.md)'s `git
  merge-tree` loop, run by hand; and `apothecary test all` runs the unit part,
  then the browser files in file order, where the longest browser files first,
  beside the unit part, is the order that shortens a landing run.
- A phase's bound does not allow for a loaded machine: at a load of 12 on four
  cores the camera test (`test_docs_bench_walkthrough.py::test_the_bench_as_it_is`)
  ran 153 s against the 75 s it records, near the bound of twice the longest
  recorded test, so a little more load ends a run that is only slow.
- Walkthrough pictures that move with no change to the page: a full browser
  run rewrites a few by a few pixels (the masked clocks' shade, the SCAD
  editor's sideways scroll in page 06's), so a run leaves the tree changed.
  Such a run's pictures are not committed.
- Walkthrough picture 06-01 (taken on `main` in 3635934b) has a focus ring on
  the Cube size slider that two full browser runs of the stack above `main` no
  longer draw. No commit in the stack is found that explains it, so the picture
  stays as `main` has it until one is.
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
- Photo gathering proposes and waits: `photo gather` lists what it would do
  and does nothing until a person says yes, as an image model is asked only
  when a person asks. A person's word already wins over a guess.
- A made piece saved as a variant: Save turns it into a part in the state
  folder, editable from then on, as the draft record *Personal data stays on
  the device* (§6) says. The page offers a made piece no Save now, and shows
  its SCAD read only.
- The root README served in the app, rendered as `/docs` is, its map's links
  going to the pages the app serves. The map lists what the browser suite
  walks; a feature gets a row when a test walks it.
- The review cycle in
  [docs/plans/review-cycle-2026-10-24.md](docs/plans/review-cycle-2026-10-24.md),
  taken as proposed: a merge queue tested once a batch, releases reviewed by
  area at a tag, shallow stacks, and the shared files split. The merge queue
  needs required checks, so it waits on `main`'s protection (*For a person to
  decide*).
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

- Protect `main`? Not yet: the checks a merge waits on, the whole suite
  before a merge and the bot gate ([CONTRIBUTING.md](CONTRIBUTING.md)) hold by
  convention. The review cycle's merge queue waits on it (*Next round*).
- Are the questions `photo gather --ask` ranks first the ones worth a minute?
  Only a person with a real folder of photographs can check.

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
- *Personal data stays on the device* counts the one machine as the device,
  and a home cluster would be an amendment of its own. Storage, asking the
  video editor (alfred) for a frame, and any cluster deployment wait on the
  record's ratification.
- When keeping data on the device makes something impossible, neither
  building it badly nor leaving it out is the rule: each case is explored and
  its questions brought to the owner to reconcile. The same record could say
  so.
- A model's weights are a fetch of their own, not an install-time fetch: qmcp
  fetches them on a person's word, from a pinned list, and the host learns
  only what was fetched (the image-models plan's *Decided*). The same record
  names the download.
- The *Data retention* record, when drafted, settles where a person's answers
  about their photographs are kept and when one expires, with the other kinds
  of kept data. Until then they live in the file handed to `--answers`.
- A check that reads git trailers for credit (carlos's corpus pin, from
  qm#81's `seed/read-the-trailer`, not on qm's main) refuses `Tools: Claude
  Code` written as a commit's last paragraph, though the corpus names a
  `Tools:` note as how a tool is disclosed. It should tell a `Tools:` note from
  a byline before apothecary's pin takes it.
- qm#121's *Personal data stays on the device* does not name the console's
  receive-only UDP listeners (sACN on 5568, OSC on 8001), which
  `apothecary/stays_local.py` allows and [docs/lighting.md](docs/lighting.md)
  describes.
- The apothecary handoff's records chain (`handbook/handoffs/apothecary-merge-queue.md`,
  §3) leaves out qm#121 and qm#145, which land between #171 and #172
  (*For a person to do*, above).
- No rule says how long a program keeps what it is given and what it makes,
  who forgets it, or how a person deletes it: qmcp's invocation rows,
  apothecary's observations and frames, carlos's states (*Data retention* in
  [the image-models plan](docs/plans/image-models-through-qmcp-2026-10-30.md#records-it-needs)).
- The site and structure record's *Pends on* says no production
  implementation of `Assembly` exists; the API, the firmware bindings and
  the gathering are built on it (`apothecary/hierarchy.py`, which calls
  itself a prototype too).
