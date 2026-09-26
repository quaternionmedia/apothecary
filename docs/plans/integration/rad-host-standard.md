# The integration standard, host side

| | |
|---|---|
| **Kind** | integration |
| **Repo** | quaternionmedia/rad + quaternionmedia/apothecary |
| **State** | stub |
| **Depends on** | rad is a unification engine — the foundational principle; Twenty controls of its own become none |
| **Graduates to** | rad host integration for apothecary (qm `project/apothecary`) |
| **Verified** | `rad/adr/DRAFT-rad-release-milestones.md` v0.0.2 read in full — apothecary and benchmark are named, the standard is called "the real deliverable of this milestone", and at least one new vector found by a host is required. `DRAFT-rad-adoption-and-scope.md` §1 confirms the host's state layer is outside rad's scope. |

## What
How a host mounts rad, supplies a `MenuContext`, receives `Intent`s, and routes
them through its own state layer without the menu touching the scene. The
standard is rad's deliverable and is co-authored; apothecary's own record is the
host half of it, and it opens with the unification principle so that "how do I
mount it" and "what adopting it means" are not two documents that can drift.

## Why now
Concurrently with everything else. The standard is a dependency of apothecary's
host record, so starting it late serialises two repositories that did not need to
be serialised.

## Seam
Three findings apothecary contributes, all verified:

1. **`MenuContext.targetIds` are already apothecary's dotted paths.** No new
   identifier scheme is needed — `_find_node_by_path`, `pathForChild`, `?focus=`
   deep links and `diff_assemblies` keys all already speak it.
2. **The resolver can live server-side.** rad's contract says `resolve()` is a
   pure function doing data manipulation, so a Python implementation is
   conforming — and it makes the ≤8 ceiling and the 12-character label rule
   **pytest assertions** rather than browser tests.
3. **Vector replay is Playwright against the embedded core**, pinning `0.3.0`,
   with a drift test mirroring rad's own `sync-vectors.mjs` remedy. Porting the
   state machine to Python would make apothecary a second implementation, which
   is rad's v0.0.3 with Kotlin.

## Open questions
- **The new vector apothecary owes.** Best candidate: rad's four context types
  cannot express "same context type, different `role`, different verb set", which
  apothecary's free-form `role` produces on day one, and the contract's "hosts may
  extend, not repurpose" clause does not obviously cover it. Second candidate:
  there is no vector for a host whose *entire* command surface is the ring — the
  IPA ledger assumes a menu among other controls.
- **Blocked on rad's C13.** The platform-free core the contract requires is
  currently a comment header inside a file that also calls `document`, so the
  import-boundary lint cannot exist on either side. apothecary's host record is
  `Proposed` pending the core-extraction decision, which is the record correctly
  declining to decide someone else's open question.
