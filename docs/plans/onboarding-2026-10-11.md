# Onboarding, docs, tests and pictures at the top of the stack

*Reviewed on 2026-10-11 at the top of the pull-request stack (#36, the SCAD
loop): a newcomer's path from a fresh clone, every present-tense document
against the code, the suites as CI runs them, and every picture against its
caption. Decided with the owner one question at a time. The local demo is
this branch, `build/onboarding`, with OrcaSlicer and Rust for the ESP32
installed in the owner's tools folder.*

## What the review found

- **A plain `pytest` ran the browser suite against any server answering on
  port 8765** -- the port walkthrough page 02 tells a person to serve on --
  and reset sites, removed cameras and forgot pictures there. Fixed at every
  level of the stack: the browser tests use only a server of their own
  (`--start-server`) or one named on purpose (`--base-url`).
- **`apothecary test run` fails on a fresh clone**: the walkthrough's browser
  tests leave an event loop running for a unit test that needs its own.
- **Nothing lets a person try the loops without hardware.** Past the camera
  steps, the picture-to-print loop needs a printer pinned to printer_1's
  mainboard and a slicer; firmware needs a board.
- **Bugs a newcomer meets:** the site drop-down never changes the address,
  so a variant's link and a reload land elsewhere; Defaults then Apply does
  not return to the saved part after a SCAD edit; `/walkthrough` answers 404;
  `photo view` prints the addresses of a port it cannot take; Slice appears
  on a devkit's ring; a printer's own Pin pins the wrong node.
- **Docs**: the CHANGELOG describes states that were later undone; several
  documents still describe retired things or miss new ones (the slicer and
  Rust installs, page 16, the View menu, the SCAD editor, the Cargo
  workspace); `parts/datum_core/README.md` describes the lid that moved to
  `datum_cap`; some `--help` texts are missing or stale.
- **Pictures**: pages 11 to 15 show the hint bar's old words, because CI
  checks the walkthrough's pages and not its pictures; several pictures do
  not show what their captions name; and edges drawn on faces, sleeps in
  place of `settled()`, the simulated printer's shared random state and
  blanks sized by their words make pictures change from run to run.
- **Tests**: no flaky test in two full browser runs under load; the shards'
  recorded times are stale; a few recommended paths have no test that walks
  them (serving for real, a bare `/viewer`, the piece's Print cell, the
  README's example scene).

## Decided

- **`apothecary serve --demo`** starts the viewer on a state folder of its
  own -- never the person's -- with an idle simulated Ender pinned to
  printer_1's mainboard, a simulated ESP32 devkit and the scripted firmware
  tools. It slices with the real OrcaSlicer when one is installed (else says
  how to install it) and prints to the simulated printer. A banner says it is
  the demo. Every loop goes round end to end, and real boards are untouched.
- **Make selects the piece it made** (Make all: the first), as Add here
  selects the camera it added.
- **A printer's Pin pins its mainboard**, where Device, the Machine and
  Slice look, and says so.
- **A Docs link in the header** opens `/docs` and the walkthrough,
  ring-backed by Panels › Docs.
- **A Getting started page, walkthrough 00**: install, `apothecary check`,
  `apothecary openscad install`, `apothecary serve --demo`, then the four
  loops, with what each needs (nothing, a printer, a board). The README's
  *Start here* points to it, and `apothecary --help` ends with the same
  steps. Page 01 onward stays the library's tour.
- **`apothecary test run` is the ordinary test command**: the unit suite and
  the walkthrough, its browser part in a pytest of its own so no event loop
  is shared. `test all` adds every browser test; `pytest -q` stays the quick
  inner loop. The README names Chromium's install.
- **Pictures**: made deterministic first (edges drawn clear of faces,
  `settled()` before every picture, the simulated printer's bed seeded by
  place alone, blanks of a fixed size, every STL built before the first
  picture). CI then **warns, without failing**, when a picture differs from
  the committed one beyond a small tolerance, and names it.

## Work

Three parts, each on a branch of its own from this one, merged here:

1. **The demo and the page**: `serve --demo`; Make selecting its piece; a
   printer's Pin; the Docs link; the bugs above; the clearer refusals and
   words the review named.
2. **Tests and pictures**: `test run`'s event loop; determinism; captions
   and framing; the picture warning in CI; tests for the uncovered paths;
   the shards' times; then every picture taken again once 1 and 3 are in.
3. **Docs**: page 00 and the README's *Start here*; every finding of the docs
   and onboarding reviews; the CHANGELOG as the net change; `--help` texts.
