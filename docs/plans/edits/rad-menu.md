# rad-menu carries the principle at its foundation

| | |
|---|---|
| **Kind** | repo-edit |
| **Repo** | quaternionmedia/rad-menu — **existence unverified** |
| **State** | stub |
| **Depends on** | rad is a unification engine — the foundational principle |
| **Graduates to** | a mirrored record in rad-menu's own `adr/`, citing rad as origin |
| **Verified** | Not reachable from the drafting session: no `gh` CLI, and `api.github.com/orgs/...` refuses (`sessions are bound to their configured repositories`). Shape below is inference from rad's core-extraction and platform-plans records. |

## What
Whatever `rad-menu` turns out to be — the extracted platform-free core the
core-extraction record proposes (`core/` + `dom/`, with `index.html` becoming
build output), or a sibling port alongside the Android `:radialmenu` module — it
opens with the unification principle rather than inheriting it silently.
`AGENTS.md` and the README lead with what adopting it means, not with the
geometry. The record is mirrored and cited by title, with rad named as origin,
never re-derived.

## Why now
Now, because a core package that ships describing itself as a menu component
will be adopted as one. The principle is cheapest to state before the first
consumer reads the README, and impossible to retrofit into an adoption that has
already shipped.

## Seam
The grep lint that keeps `core/` free of `document|window|HTMLElement` is the
natural place to also assert the core exports no host-side control helpers. A
core offering a convenience for building a toolbar of verbs is a core that has
conceded the argument, and that is a mechanical check rather than a review one.

## Open questions
- Does the repository exist? Settle it before writing anything:
  `gh api orgs/quaternionmedia/repos --paginate --jq '.[].name'` from a session
  holding the credential. A 404 from a token that cannot see private repos means
  *unknown*, never *absent*.
- If it does not exist, **do not create a stub repository.** An empty repo reads
  as an adopted project to `governance_status.py`, and `unmanaged: 97` is already
  the org's problem. Creating it is one of the human-only steps in rad's own
  adoption record.
- Is `rad-menu` the extracted core, or a distinct port? The two readings imply
  different homes for the mirrored record.
