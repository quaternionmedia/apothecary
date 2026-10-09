# Cleanup, sorted and triaged

*Taken stock with the owner on 2026-10-08: every open cleanup item, from the
work in flight to the next round, sorted by kind and given an order. What
`apothecary problems` and `apothecary census` compute is named, not counted
here. Each item names where it is tracked; this page is the order to take
them in.*

## The order

- **Now**: in flight, or blocking the split of the review pull request.
- **This round**: done alongside the Rust work and the UI flows
  ([rust-2026-10-08.md](rust-2026-10-08.md),
  [ui-flows-2026-10-08.md](ui-flows-2026-10-08.md)).
- **Next round**: decided, not started (`todo.md`'s *Next round*).
- **A person**: only the owner can close it.

## In flight

| Item | Order | Where |
|---|---|---|
| View at the top of the canvas ring with Fit inside it; the Machine's tab title and the hint bar on one row at 1024 px | Now | `build/less-on-screen`; the cameras plan, *Decided after Phase 2* |
| Cameras in the world (Phase 3): the part drawn, aimed, its ring, Selected's camera, P, the mat through the projection, Pictures by camera | Now | `build/camera-parts`; [cameras-and-clutter-2026-10-04.md](cameras-and-clutter-2026-10-04.md) |
| The browser tests for a garage with one printer | Now | `build/camera-parts` |
| Pictures of it (Phase 4): the walkthrough and generated docs regenerated, the census's numbers in the records | Now, after both merge | the cameras plan |

## Delivery

| Item | Order | Where |
|---|---|---|
| The review pull request split into a stack, each a run of the review branch's own history, none rewritten: #21 at the bottom, then the 09-26 review's workstreams, pictures in the world, the installers, the consolidation, and cameras and clutter on top. #22 is closed with a pointer to the stack (decided 2026-10-08). *Done 2026-10-09: #24 to #29 above #21, and #30 holds the review branch.* | Now | GitHub |
| The Rust work and the UI flows each a pull request of its own, stacked on the cameras-and-clutter one | This round | the Rust and flows plans |
| The dependency bumps Dependabot opened, closed or rebased once the stack lands | A person, after the stack | GitHub |
| Merged worktree branches left by finished agent runs (`worktree-*`), deleted | Now | local only |

## Dead code and words left behind

| Item | Order | Where |
|---|---|---|
| What the clutter pass retired: Load, Zoom Out, the old problems list, the tethered Machine, Panels › View, the text badges -- their code, CSS and comments | Now | `build/less-on-screen`'s polish pass |
| What camera parts retired: the `/cameras` routes, Pin here and Unpin, the cameras file's helpers, the old place-badge text | Now | `build/camera-parts`'s polish pass |
| Present-tense docs that still describe Pin here (the README among them) | Now | `build/camera-parts` |
| The hidden command stubs, removed one release after they were hidden | Next round | `todo.md` |
| The owner's own `~/.apothecary/cameras.json`, no longer read | A person | left in place on purpose |

## Parts that do not yet tell the whole truth

`apothecary problems` lists them; by kind:

| Kind | Order | Note |
|---|---|---|
| *unprintable*: print settings not declared, or not checked against the printer | This round, with the part design loop | the loop's check shows each one where the part is edited |
| *unprintable*: geometry does not render (gridfinity, the snowplow) | This round | gridfinity needs a newer OpenSCAD than the oldest supported one; the snowplow is the part with two names (*Next round*) |
| *unbounded*: declared bounds not yet held to the geometry | This round | closed by rendering each part once and declaring what it renders to |
| *contested*: `datum_core.board_y` has two candidate values | A person | a measurement decides it |
| *unmeasured*: `datum_core` not yet fitted to measured artifacts | A person (the datum project) | |

## Tests and their machinery

| Item | Order | Where |
|---|---|---|
| The shards' recorded times refreshed after the new browser test files land | Now, with Phase 4 | `tests/e2e/durations.json` |
| Every flow of the UI held end to end by a browser test | This round | [ui-flows-2026-10-08.md](ui-flows-2026-10-08.md) |
| A generated JSCAD module loaded against the real package in a test | Next round | `todo.md` |
| The unit suite under pytest-xdist | Next round | `todo.md` |
| A run that goes green because tests were skipped says what did not run | A person (governance) | `todo.md`'s *For governance/qm* |

## Structure

All decided, none started; each is `todo.md`'s *Next round* and stays there:
`api.py` into routers with a lock on the site store; the viewer's inline
script into modules with the ring's verbs declared once; one registry for
firmware ports (with a bench session); data-only part wrappers as
`part.json`; photo gathering as an optional extra; the wheel carrying
`parts/` and `templates/`.

## For the owner

- Ratify the governance drafts (the one-screen record, the personal-data
  record's new hosts, the Rust fetches when they are drafted), and bump the
  project's governance pin.
- Review rad#7 (open-at-an-item).
- Run the bench checklist on the one page with the Ender
  ([2026-09-20-ender-bench.md](../validation/2026-09-20-ender-bench.md)), and
  the Rust blink on the bench's ESP32 when it lands.
- Decide `datum_core.board_y`.
- `todo.md`'s *For a person to decide*.
