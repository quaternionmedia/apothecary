# rad is a unification engine — the foundational principle

| | |
|---|---|
| **Kind** | repo-edit |
| **Repo** | quaternionmedia/rad (`evolve/rad-unification-principle`) |
| **State** | drafted |
| **Depends on** | nothing |
| **Graduates to** | rad is a unification engine (rad's own `adr/`) |
| **Verified** | rad cloned at tip of `main`; the four supporting records read in full; `adr/README.md` index row added. The topic entry below is **not** written — it is described here rather than landed untested. |

## What
rad stops being described as a radial menu and is described as what its own
machinery already measures: a mechanism for collapsing a host's scattered input
idioms into one command surface. The principle lands as
`adr/DRAFT-rad-is-a-unification-engine.md` with three enforcement clauses —
superset generalized from chords to all surfaces, one intent path, and a surface
census with numbers — plus an explicit statement of what it does not claim, since
the adoption-and-scope record puts the host's state layer outside rad's scope.

## Why now
Now, because the release-milestones draft claims v0.0.2 when apothecary and
benchmark have shipped an integration standard that does not yet exist. Without
this record both hosts can satisfy that milestone by mounting a ring beside an
existing toolbar, passing all thirty-four vectors, and calling it adoption.

## Seam
`adr/DRAFT-rad-is-a-unification-engine.md` (written) ·
`perspectives/2026-08-14-the-menu-that-removes-menus.md` (written) ·
`adr/README.md` drafts-in-flight list (row added) ·
`tests/topics.mjs` → a `unification` topic entry (**not written**) ·
the README intro, which is build output from that topic entry and therefore
follows from it rather than being hand-edited.

## Open questions
- The `unification` topic entry needs assertions against real in-page globals
  (`resolveMenu`, `CHORD_MAP`, `store.intents`). Those were not read closely
  enough to write assertions that have been *seen to fail*, and writing them
  blind is the exact failure the verification-shaped-prose perspective names.
  Land it only after running `npm run gate` locally.
- The census is enforced by review, not by a gate. Accepted and named in the
  record; if a mechanism appears, the record's revision triggers say so.
- Whether §2's three carve-outs — navigation, direct manipulation, read-only
  views — are drawn in the right place. A host that finds a fourth category is
  telling us something.
