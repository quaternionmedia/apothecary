# What can and cannot be chorded

| | |
|---|---|
| **Kind** | feature |
| **Repo** | quaternionmedia/apothecary |
| **State** | stub |
| **Depends on** | Twenty controls of its own become none |
| **Graduates to** | a clause in the rad host integration record |
| **Verified** | `rad/index.html` `CHORD_MAP` (16 words) and `tests/conformance.spec.mjs` read: the vocabulary must be prefix-free (vector 29), and every chord verb must also be reachable in a menu (asserted at line 76). |

## What
CharaChorder input arrives as machine-fast words over plain HID, split at 250 ms
gaps and classified as chorded when every inter-key gap is ≤30 ms. The vocabulary
must be prefix-free so a known word finalises on its last keystroke.

## Why now
After the rings are stable, because the menu-as-superset rule means the chord set
is a subset of what the rings already expose. Designing chords first would design
the rings backwards.

## Seam
The important consequence for this feature line: **words are nouns and verbs are
verbs.** A vocabulary of arbitrarily many shape tokens cannot be chorded, because
every chord-bound verb must also be reachable in a menu and a ring holds eight
items. The chordable set is the verb vocabulary — `pin`, `hide`, `delete`,
`word:*` as a category rather than per-word — and words reach the ring through
grouping by `ShapeKind`.

## Open questions
- Whether `word:plate` and friends are distinct verbs or one verb with an
  argument. rad's `color:*` precedent suggests the latter, and it names a token
  rather than a literal.
