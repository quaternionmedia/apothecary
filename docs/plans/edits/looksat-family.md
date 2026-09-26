# looksatphotos, looksatvideos, and what unknown means

| | |
|---|---|
| **Kind** | repo-edit |
| **Repo** | quaternionmedia/looksat* — **existence unverified** |
| **State** | stub |
| **Depends on** | nothing |
| **Graduates to** | rows in whichever record needs the name |
| **Verified** | Probed by `git ls-remote` across many name variants: `looksatphotos`, `LooksAtPhotos`, `looksatphoto`, `looks-at-photos`, `looksAtPhotos`, `looksatvideos`, `LooksAtVideos`, `rad-android`, `rad_android`, `radandroid`, `RadAndroid` — none resolved. `alfred` (lowercase) did. `looksatwords` **is** real: it appears in `qm/governance-status.yaml` under `org.unmanaged_named`. The org lists 34 private repositories and withholds 31 unmanaged names. |

## What
The natural upstream of the `ShapeProvider` seam is a service that lives outside
apothecary and speaks the Protocol — which is what a `looksat*` repository sounds
like it already is. Whether these exist is unknown, and this stub's job is to
keep unknown from silently becoming absent.

## Why now
Now, because the difference is the finding. A 404 from a token that cannot see
private repositories means unknown. The corpus already has the idiom for this:
`governance-status.yaml`'s `undefined:` block, whose rows are *term* /
*why_not_computed* / *would_be_settled_by*. Use those three columns, with the
command run and its verbatim output, in whichever record needs the name.

## Seam
If they exist, they are a third `ShapeProvider` implementation across the
Protocol — which is exactly the shape P4's "build the seam, buy the engines"
doctrine wants, with detectors named explicitly as engines to select rather than
code to write.

## Open questions
- **First action, before anything else is written:**
  `gh api orgs/quaternionmedia/repos --paginate --jq '.[].name' | sort`
  from a session holding the credential. It settles all four names at once.
- **Do not create stub repositories.** An empty repo reads as an adopted project
  to `governance_status.py`, and `unmanaged: 97` is already the org's problem.
- `looksatwords` is real and ungoverned. Whether it is related to the word
  vocabulary in `edits/apothecary-model.md` is unknown and worth ten minutes.
