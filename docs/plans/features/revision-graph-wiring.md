# Wiring the revision graph to something

| | |
|---|---|
| **Kind** | feature |
| **Repo** | quaternionmedia/apothecary |
| **State** | stub |
| **Depends on** | Twenty controls of its own become none |
| **Graduates to** | a record citing the hierarchy record |
| **Verified** | `apothecary/revisions.py` read in full — 208 lines, `Revision`, `AssemblyDiff`, `diff_assemblies`, `RevisionGraph` with commit/branch/history/children_of/checkout. Its own header says PROTOTYPE, not wired into the API or viewer yet. `tests/test_revisions.py` exercises it in isolation. |

## What
`RevisionGraph` already does commit, branch, first-parent history and checkout
over `Assembly` trees, with a path-keyed diff that ignores reordering. It is
wired to nothing.

## Why now
`Undo` in the canvas ring is its first natural user, and the one-intent-path rule
makes it cheap: if every mutation is an `Intent` reaching one place, that place is
where a commit happens. Branching design iterations — the thing the module's
docstring reserves as future work — follows for free.

## Seam
`POST /menu/intent` is the commit point. `diff_assemblies` keys on the same
dotted paths as `MenuContext.targetIds`, so an undo and a link and a menu target
all speak one address.

## Open questions
- The revision graph is a **version** graph and `SceneLink` is a **reference**
  graph. They must not be merged; see `edits/apothecary-model.md`.
- Whether undo is per-site or global.
