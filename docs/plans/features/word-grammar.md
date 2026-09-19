# Words that carry composition rules

| | |
|---|---|
| **Kind** | feature |
| **Repo** | quaternionmedia/apothecary |
| **State** | stub |
| **Depends on** | Photo → shapes → words → placed scenes → links |
| **Graduates to** | an extension of the word record, or its own |
| **Verified** | Nothing in the tree: zero hits for `grammar` or `language`. |

## What
A word today is a named, parameterized `Assembly` factory. A word with a grammar
also carries rules about what may attach to what, and at which datum — so a scene
is *parsed* rather than assembled, and an invalid composition is a parse error
rather than an overlap violation discovered later.

## Why now
Not yet. Grammar is the thing that makes the vocabulary metaphor more than a
metaphor, and it is also the thing most likely to be over-designed before there
are enough real words to generalise from. Revisit after the lexicon has grown
past its five seed entries against real photographs.

## Seam
`Assembly.validate()` and `LayoutReport` already exist as the place a
composition is judged. A grammar would add rules that run there rather than a
parallel validation path.

## Open questions
- Does a grammar belong to the word, to the pair of words, or to the site? All
  three are defensible and they imply different data shapes.
- Interaction with the hierarchy record's free-form `role`. If grammar needs a
  genuine type distinction the `role` string cannot express, that fires that
  record's own revision trigger and is a finding worth surfacing.
