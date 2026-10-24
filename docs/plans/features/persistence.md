# Nothing survives a restart

| | |
|---|---|
| **Kind** | feature |
| **Repo** | quaternionmedia/apothecary |
| **State** | stub |
| **Depends on** | Photo → shapes → words → placed scenes → links |
| **Graduates to** | a record, once there is something worth keeping |
| **Verified** | `site_store.py`, `example_hierarchy.py::JobStore` and `revisions.py::RevisionGraph` each say so in their own module docstrings: in-memory, process-lifetime, not shared across workers. |

## What
`SiteStore`, `JobStore`, the planned `LinkStore` and `RevisionGraph` are all
in-memory and single-process. A photo-derived site is lost on restart, which is
tolerable for a demo and not for anything else.

## Why now
When a user would be upset to lose the result. That threshold arrives with links
— a scene graph someone has curated is worth more than a scene someone can
re-derive from the same photograph in one command.

## Seam
`records/DRAFT-house-stack.md` names PostgreSQL as the default store, and moat
has no PostgreSQL chart, so this is a dependency question and a deployment
question at once.

## Open questions
- Whether a photo-derived site persists as a `Detection` plus a scale (re-derived
  on load) or as a materialised `Assembly` tree. The first is smaller and
  reproducible; the second survives a change to the matcher.
